#!/usr/bin/env python3
"""Pre-flight execution-polish check for drafts before they leave the working directory.

Runs deterministic grep-based checks for pipeline scaffolding, placeholder tokens,
and exposed internal metadata that would break executive-ready prose. Exit 0 if
clean, exit 1 if any file has any match.

This is the execution-axis gate complementing the content-axis Opus judge. See
docs/phase0_calibration_result.md for the motivation: the "forward-to-CEO"
criterion has two orthogonal axes, and no amount of rubric calibration will
reliably catch leaked `[src:0]` tokens or "URL pending verification" footnotes.
Deterministic grep is faster, cheaper, and more trustworthy for this class of
failure.

Usage:
    python scripts/check_export_gate.py <path> [<path>...]

Paths can be individual files or directories (directories are walked recursively
for .md files).

Patterns are deliberately conservative: each one is a phrase or token that
should never appear in a reader-facing draft, regardless of brand or topic.
The brand name "Explodable" is intentionally NOT a pattern on its own, because
it will legitimately appear in author bios and consulting footers. The leak
signal is phrases like "anxiety-indexed KB" that only surface from internal
pipeline metadata.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern[str]
    why: str


PATTERNS: list[Pattern] = [
    # placeholder_citation is handled imperatively below — it needs
    # two-sided context (quoted phrase before OR after the marker),
    # which stdlib re can't do with variable-width lookbehind. See
    # _scan_placeholder_citations.
    Pattern(
        "backfill_script_reference",
        re.compile(r"backfill_manifestation", re.IGNORECASE),
        "Leaked reference to internal backfill script",
    ),
    Pattern(
        "anxiety_indexed_kb",
        re.compile(r"anxiety-indexed\s+KB", re.IGNORECASE),
        "Internal knowledge-base name leaked to reader",
    ),
    Pattern(
        "url_pending_verification",
        re.compile(r"URL pending verification", re.IGNORECASE),
        "Pipeline fallback text for unresolved source URL",
    ),
    Pattern(
        "no_manifestation_recorded",
        re.compile(r"no manifestation recorded", re.IGNORECASE),
        "Pipeline fallback text for missing source attribution",
    ),
    Pattern(
        "source_attribution_pending",
        re.compile(r"source attribution pending", re.IGNORECASE),
        "Pipeline fallback text for unresolved citation",
    ),
    Pattern(
        "review_status_field",
        re.compile(r"^\s*review_status:", re.MULTILINE),
        "Exposed review_status metadata field",
    ),
    Pattern(
        "thread_id_field",
        re.compile(r"^\s*thread_id:", re.MULTILINE),
        "Exposed thread_id metadata field",
    ),
    Pattern(
        "finding_uuid",
        re.compile(r"finding\s+[0-9a-f]{8}", re.IGNORECASE),
        "Exposed internal finding UUID",
    ),
    Pattern(
        "triple_h1_title",
        re.compile(r"(?:^|\n)(#\s+[^\n]+)\n+\1\n+\1", re.MULTILINE),
        "Same H1 title repeated 3 times (export artifact)",
    ),
]


@dataclass
class Hit:
    pattern: Pattern
    line_number: int
    line_text: str


_CITATION_MARKER = re.compile(r"\[src:\d+\]")
_CITATION_WINDOW_CHARS = 80
_QUOTE_CHARS = ('"', "\u201c", "\u201d")

_PLACEHOLDER_CITATION_PATTERN = Pattern(
    name="placeholder_citation",
    regex=_CITATION_MARKER,
    why="[src:N] marker with no quoted phrase within ~80 chars (before or after)",
)


def _scan_placeholder_citations(text: str) -> list[Hit]:
    """Flag [src:N] markers that lack a nearby quoted phrase.

    Both Pipeline B (CAG) and Pipeline C (Wiki) produce valid citations,
    but they differ in ordering: B tends to put the quote AFTER the marker,
    C tends to put it BEFORE. Both are legitimate. The actual failure is
    a bare marker with no quote within a reasonable window on either side.
    """
    hits: list[Hit] = []
    for match in _CITATION_MARKER.finditer(text):
        start, end = match.start(), match.end()
        window_before = text[max(0, start - _CITATION_WINDOW_CHARS) : start]
        window_after = text[end : end + _CITATION_WINDOW_CHARS]
        if any(q in window_before or q in window_after for q in _QUOTE_CHARS):
            continue
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        if line_end == -1:
            line_end = len(text)
        line_text = text[line_start:line_end].strip()
        line_number = text.count("\n", 0, start) + 1
        hits.append(Hit(pattern=_PLACEHOLDER_CITATION_PATTERN, line_number=line_number, line_text=line_text))
    return hits


def scan_text(text: str) -> list[Hit]:
    hits: list[Hit] = []
    hits.extend(_scan_placeholder_citations(text))
    for pattern in PATTERNS:
        for match in pattern.regex.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            if line_end == -1:
                line_end = len(text)
            line_text = text[line_start:line_end].strip()
            line_number = text.count("\n", 0, match.start()) + 1
            hits.append(Hit(pattern=pattern, line_number=line_number, line_text=line_text))
    return hits


def collect_files(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"error: path does not exist: {path}", file=sys.stderr)
            sys.exit(2)
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            out.extend(sorted(path.rglob("*.md")))
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: check_export_gate.py <path> [<path>...]", file=sys.stderr)
        return 2

    files = collect_files(argv)
    if not files:
        print("no .md files found", file=sys.stderr)
        return 2

    total_hits = 0
    files_with_hits = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"SKIP {f} (not utf-8)")
            continue
        hits = scan_text(text)
        if not hits:
            print(f"PASS {f}")
            continue
        files_with_hits += 1
        total_hits += len(hits)
        print(f"FAIL {f}")
        for hit in hits:
            snippet = hit.line_text if len(hit.line_text) < 120 else hit.line_text[:117] + "..."
            print(f"  line {hit.line_number:>4}  [{hit.pattern.name}]  {hit.pattern.why}")
            print(f"              > {snippet}")

    print()
    print(f"scanned {len(files)} file(s), {files_with_hits} with issues, {total_hits} total hit(s)")
    return 1 if files_with_hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
