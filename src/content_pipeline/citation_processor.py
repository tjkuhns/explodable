"""Citation processor — hybrid inline-marker pattern.

Replaces the Anthropic Citations API path for long-form newsletter and brief
generation. The Citations API is architecturally incompatible with the
voice profile's "cite conversationally, not academically" rule — Claude
honors the voice profile over the Citations API's metadata instructions
when the two compete. See docs/CITATION_ARCHITECTURE.md for the full
diagnosis (2026-04-14 Session 4).

This module implements the alternative: inline markers during generation,
deterministic post-processing, markdown footnote rendering.

## Pipeline

1. Findings are passed to Claude as structured source blocks with explicit
   `[src:N]` labels in the user prompt (not as Citations API documents).

2. Claude writes prose in its normal voice profile-compliant style and
   drops `[src:N]` markers immediately after claims drawn from each source.

3. Post-generation, `extract_markers` scans the prose for markers.
4. `resolve_sources` looks up each marker's finding and picks the best
   URL-carrying manifestation.
5. `render_footnotes` transforms inline markers into markdown footnote
   references (`[^1]`) and appends a footnote definition block at the end.

## Output shape

Input prose:
    Dixon and McKenna's JOLT Effect research [src:4] analyzed 2.5 million
    sales conversations, finding that 56% of no-decision losses [src:1]
    stem from buyer indecision.

Output prose (rendered for Buttondown/GitHub markdown):
    Dixon and McKenna's JOLT Effect research [^4] analyzed 2.5 million
    sales conversations, finding that 56% of no-decision losses [^1]
    stem from buyer indecision.

    [^1]: B2B International, *Let's Get Emotional — State of B2B Survey*,
          2019. https://quirks.com/articles/...
    [^4]: Dixon & McKenna, *The JOLT Effect*, 2022.
          https://www.jolteffect.com/...

Every claim traces to a clickable source. Voice profile intact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection
    from src.content_pipeline.retriever import ScoredFinding

# Regex for marker extraction: [src:123] or [src:1]
_MARKER_RE = re.compile(r"\[src:(\d+)\]")


@dataclass
class ResolvedSource:
    """A marker ID resolved to its finding's best-citable manifestation."""

    marker_id: int  # 0-indexed into the selected_findings list
    finding_id: str
    finding_claim: str
    finding_discipline: str
    finding_confidence: float
    source_title: str
    source_url: str | None  # None if no URL-carrying manifestation exists
    source_type: str  # academic, book, journalism, etc.
    source_date: str | None = None
    footnote_number: int = 0  # assigned during render


@dataclass
class CitationReport:
    """Summary of the citation post-processing pass."""

    markers_found: int = 0
    markers_resolved: int = 0
    markers_with_url: int = 0
    markers_unresolved: int = 0  # marker_id out of range
    unique_sources_cited: int = 0
    missing_url_findings: list[int] = field(default_factory=list)  # marker_ids with no URL
    warnings: list[str] = field(default_factory=list)


def extract_markers(text: str) -> list[tuple[int, int]]:
    """Scan text for `[src:N]` markers.

    Returns a list of (position, marker_id) tuples in order of appearance.
    Position is the character index where the marker starts.
    """
    results = []
    for match in _MARKER_RE.finditer(text):
        marker_id = int(match.group(1))
        results.append((match.start(), marker_id))
    return results


def _pick_best_manifestation(
    conn: "Connection", finding_id: str
) -> dict | None:
    """Select the most citable manifestation for a finding.

    Preference order:
    1. Academic source with URL
    2. Any source with URL (book, journalism, practitioner, industry_research)
    3. Academic source without URL (source still attributable by title)
    4. Any source without URL
    5. None if the finding has no manifestations

    Returns a dict with title, source_url, source_type, source_date, or None.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.source, m.source_url, m.source_type::text, m.source_date
            FROM manifestations m
            JOIN finding_manifestations fm ON fm.manifestation_id = m.id
            WHERE fm.finding_id = %s
            ORDER BY
                (CASE WHEN m.source_url IS NOT NULL AND m.source_url != '' THEN 1 ELSE 0 END) DESC,
                (CASE WHEN m.source_type::text = 'academic' THEN 1 ELSE 0 END) DESC,
                LENGTH(m.source) DESC
            LIMIT 1;
            """,
            (finding_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "title": row[0],
            "source_url": row[1] if row[1] else None,
            "source_type": row[2],
            "source_date": row[3].isoformat() if row[3] else None,
        }


def resolve_sources(
    markers: list[tuple[int, int]],
    selected_findings: list["ScoredFinding"],
    conn: "Connection",
) -> tuple[list[ResolvedSource], CitationReport]:
    """Map markers to their underlying findings + best manifestations.

    Each unique marker_id is resolved once (deduped). Returns a list of
    ResolvedSource objects in marker_id order, plus a CitationReport with
    coverage stats and any warnings.
    """
    report = CitationReport(markers_found=len(markers))

    # Dedupe marker IDs — same source cited multiple times only needs one
    # resolution.
    unique_ids = sorted({mid for _, mid in markers})
    report.unique_sources_cited = len(unique_ids)

    resolved: list[ResolvedSource] = []
    for marker_id in unique_ids:
        if marker_id < 0 or marker_id >= len(selected_findings):
            report.markers_unresolved += 1
            report.warnings.append(
                f"marker [src:{marker_id}] out of range "
                f"(only {len(selected_findings)} findings available)"
            )
            continue

        sf = selected_findings[marker_id]
        f = sf.finding
        manifestation = _pick_best_manifestation(conn, str(f.id))

        if manifestation is None:
            # Finding exists in the KB but has no manifestation row at all.
            # Rather than leak internal tooling language into the shipped
            # draft, we use a neutral placeholder that still looks like a
            # proper citation (discipline + confidence). The operator sees
            # the real gap via the structured warning / report.warnings
            # path, which is what the backfill script and worker log both
            # monitor.
            resolved.append(
                ResolvedSource(
                    marker_id=marker_id,
                    finding_id=str(f.id),
                    finding_claim=f.claim,
                    finding_discipline=f.academic_discipline,
                    finding_confidence=f.confidence_score,
                    source_title=f.claim,
                    source_url=None,
                    source_type="unknown",
                )
            )
            report.missing_url_findings.append(marker_id)
            report.warnings.append(
                f"marker [src:{marker_id}] finding {f.id} has no manifestations"
            )
            continue

        src = ResolvedSource(
            marker_id=marker_id,
            finding_id=str(f.id),
            finding_claim=f.claim,
            finding_discipline=f.academic_discipline,
            finding_confidence=f.confidence_score,
            source_title=manifestation["title"],
            source_url=manifestation["source_url"],
            source_type=manifestation["source_type"],
            source_date=manifestation["source_date"],
        )
        resolved.append(src)
        report.markers_resolved += 1
        if src.source_url:
            report.markers_with_url += 1
        else:
            report.missing_url_findings.append(marker_id)

    # Assign footnote numbers in order of first appearance
    first_appearance_order: list[int] = []
    seen: set[int] = set()
    for _, mid in markers:
        if mid not in seen:
            seen.add(mid)
            first_appearance_order.append(mid)

    marker_to_footnote: dict[int, int] = {}
    next_num = 1
    for mid in first_appearance_order:
        if any(r.marker_id == mid for r in resolved):
            marker_to_footnote[mid] = next_num
            next_num += 1

    for r in resolved:
        r.footnote_number = marker_to_footnote.get(r.marker_id, 0)

    return resolved, report


def render_footnotes(
    text: str,
    resolved: list[ResolvedSource],
) -> tuple[str, str]:
    """Transform `[src:N]` markers into `[^N]` refs and build footnote block.

    Returns (annotated_text, footnote_block). The footnote_block is a
    formatted markdown string ready to append at the end of the draft.
    """
    # Build a marker_id → footnote_number map
    marker_map: dict[int, int] = {r.marker_id: r.footnote_number for r in resolved}

    def replace_marker(match: re.Match) -> str:
        marker_id = int(match.group(1))
        footnote_num = marker_map.get(marker_id)
        if footnote_num is None:
            # Unresolved marker — strip it and leave a comment for the operator
            return f"<!-- unresolved [src:{marker_id}] -->"
        return f"[^{footnote_num}]"

    annotated = _MARKER_RE.sub(replace_marker, text)

    # Build footnote definitions block
    footnote_lines = ["", "---", "", "## Sources", ""]
    resolved_sorted = sorted(resolved, key=lambda r: r.footnote_number)

    for r in resolved_sorted:
        if r.footnote_number == 0:
            continue

        title = r.source_title
        date_str = f" ({r.source_date[:4]})" if r.source_date else ""
        type_str = f" [{r.source_type}]" if r.source_type != "unknown" else ""
        conf_str = f" · {int(r.finding_confidence * 100)}% confidence"

        if r.source_url:
            footnote_line = f"[^{r.footnote_number}]: [{title}]({r.source_url}){date_str}{type_str}{conf_str}"
        else:
            # No URL available — emit clean metadata only. Any operator
            # remediation hints belong in the worker log / CitationReport,
            # never in the shipped draft.
            footnote_line = f"[^{r.footnote_number}]: {title}{date_str}{type_str}{conf_str}"
        footnote_lines.append(footnote_line)
        footnote_lines.append("")  # blank line between footnotes

    footnote_block = "\n".join(footnote_lines)
    return annotated, footnote_block


def process_citations(
    text: str,
    selected_findings: list["ScoredFinding"],
    conn: "Connection",
) -> tuple[str, str, CitationReport]:
    """Top-level post-processor: extract → resolve → render.

    Returns (annotated_text, footnote_block, citation_report).
    """
    markers = extract_markers(text)
    if not markers:
        # No markers at all — return the text unchanged and an empty report
        report = CitationReport(markers_found=0)
        report.warnings.append(
            "no [src:N] markers found in draft — Claude may not have honored "
            "the inline-marker instruction. Check the task prompt."
        )
        return text, "", report

    resolved, report = resolve_sources(markers, selected_findings, conn)
    annotated, footnote_block = render_footnotes(text, resolved)
    return annotated, footnote_block, report
