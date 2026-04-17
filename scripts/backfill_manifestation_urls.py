#!/usr/bin/env python3
"""Backfill manifestation URLs for findings with missing source attribution.

Two sub-populations to handle:

1. **45 active findings with ZERO manifestations.** Their source metadata
   is embedded in the `confidence_basis` text field, e.g. "3 source(s):
   Decision Fatigue: A Conceptual Analysis (Pignatiello et al., Review
   of General Psychology 2020); Ego Depletion..."
   - Parse confidence_basis to extract (title, author, year) tuples
   - Look up each via Semantic Scholar, fall back to Tavily
   - Create manifestations with the discovered URLs

2. **48 active findings with manifestations but no source_url.** Simpler
   case: iterate manifestations where source_url is NULL/empty, look up
   by source title, update the row.

Lookup chain: Semantic Scholar (academic-first, free) → Tavily (broader
coverage for non-academic content) → manual flag for operator review.

Usage:
    python scripts/backfill_manifestation_urls.py [--dry-run] [--only-zero-manifest]
                                                   [--only-missing-url] [--limit N]

Flags:
    --dry-run             Show what would be done without writing
    --only-zero-manifest  Only process the zero-manifestation sub-population
    --only-missing-url    Only process the missing-url sub-population
    --limit N             Stop after processing N findings (testing)
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

# Manual .env load
for line in open(Path(__file__).resolve().parent.parent / ".env"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.kb.connection import get_connection, close_pool
from src.kb.crud import KBStore
from src.kb.models import (
    FindingStatus,
    ManifestationCreate,
    SourceType,
)


# ── Source metadata parsing from confidence_basis ──

# Patterns observed in confidence_basis across the 45 zero-manifest findings:
#   "N source(s): Title 1 (Author et al., Journal Year); Title 2 (Author, Year); ..."
#   "AI-proposed from X research; score=Y; N source(s): ..."
#   "Peer-reviewed sources: Title 1; Title 2; ..."
#
# We parse flexibly and extract (title, author, year) tuples.

_SOURCE_LIST_PATTERNS = [
    r"source\(s\):\s*(.+?)(?:\s*$|\s*\.\s*$)",
    r"Peer-reviewed sources?:\s*(.+?)(?:\s*$|\s*\.\s*$)",
    r"[Ss]ources?:\s*(.+?)(?:\s*$|\s*\.\s*$)",
]

# Matches "Title (Author et al., Journal Year)" or variants
_SOURCE_ITEM_PATTERN = re.compile(
    r"^(?P<title>[^()]+?)\s*\((?P<author>[^,)]+?)(?:\s*et al\.?)?(?:,\s*(?P<journal>[^,)]+?))?(?:,\s*(?P<year>\d{4}))?\)",
    re.IGNORECASE,
)


# Matches an orphan author-year fragment like "Steiger & Kühberger, 2018)"
# that has no preceding title — these appear when upstream semicolon
# splitting misfires and a companion citation lands as its own item.
_ORPHAN_AUTHOR_YEAR = re.compile(
    r"^[A-ZÀ-ÖØ-Þ][\w\-]+(?:\s*&\s*[A-ZÀ-ÖØ-Þ][\w\-]+)*,?\s*\d{4}\)?$"
)


def _strip_trailing_parenthetical(title: str) -> str:
    """Remove trailing `(...)` from a title so S2 gets a clean query.

    Source items often arrive as "Title (Author et al., Journal Year)".
    The parenthetical is author/venue metadata, not part of the title —
    leaving it in the query confuses S2's search ranking.
    """
    # Strip balanced trailing parens, possibly repeated
    out = title.strip()
    while out.endswith(")"):
        depth = 0
        cut_at = None
        for i in range(len(out) - 1, -1, -1):
            if out[i] == ")":
                depth += 1
            elif out[i] == "(":
                depth -= 1
                if depth == 0:
                    cut_at = i
                    break
        if cut_at is None or cut_at == 0:
            break
        out = out[:cut_at].strip().rstrip(",").strip()
    return out or title


def parse_sources_from_confidence_basis(basis: str) -> list[dict]:
    """Extract source metadata from a confidence_basis string.

    Returns a list of dicts with keys: title, author, journal, year.
    Missing fields are None. Best-effort — degrades gracefully on
    malformed input.
    """
    if not basis:
        return []

    # Find the "source(s): ..." segment
    source_segment = None
    for pattern in _SOURCE_LIST_PATTERNS:
        match = re.search(pattern, basis, re.IGNORECASE)
        if match:
            source_segment = match.group(1).strip()
            break

    if not source_segment:
        return []

    # Split on semicolons — most common separator in observed data
    items = [item.strip() for item in source_segment.split(";") if item.strip()]

    sources: list[dict] = []
    for item in items:
        if not item:
            continue

        # Drop orphan "Author & Author, YEAR)" fragments — these are
        # misparsed companion citations from upstream splitting, not
        # standalone sources.
        if _ORPHAN_AUTHOR_YEAR.match(item):
            continue

        match = _SOURCE_ITEM_PATTERN.match(item)
        if match:
            raw_title = match.group("title").strip()
            author = (match.group("author") or "").strip()
            # Reject bogus "author" that's actually a year
            if re.fullmatch(r"\d{4}", author):
                author = ""
            sources.append(
                {
                    "title": raw_title,
                    "author": author,
                    "journal": (match.group("journal") or "").strip(),
                    "year": match.group("year"),
                }
            )
        else:
            # Fallback — treat the whole item as a title with no author,
            # but strip any trailing parenthetical metadata so lookups
            # get a clean title string.
            title = _strip_trailing_parenthetical(item.rstrip(",.").strip())
            if title and len(title) > 5 and not _ORPHAN_AUTHOR_YEAR.match(title):
                sources.append({"title": title, "author": "", "journal": "", "year": None})

    return sources


# ── Semantic Scholar lookup ──

# Module-level throttle state. Unauthenticated public S2 shares a global
# rate-limit pool, so we pace ~1 req/sec. With an API key in env we can
# go much faster, but there's no reason to — backfill is <200 calls total.
_S2_LAST_CALL_TS: float = 0.0
_S2_MIN_INTERVAL: float = 1.1  # seconds between unauthenticated calls


def _s2_throttle() -> None:
    global _S2_LAST_CALL_TS
    now = time.monotonic()
    wait = _S2_MIN_INTERVAL - (now - _S2_LAST_CALL_TS)
    if wait > 0:
        time.sleep(wait)
    _S2_LAST_CALL_TS = time.monotonic()


def lookup_semantic_scholar(
    title: str, author: str = "", year: str | None = None
) -> dict | None:
    """Look up a source by title + optional author/year on Semantic Scholar.

    Returns a dict with url, doi, venue, cited_by_count if found, else None.
    Throttles to ~1 req/sec unauthenticated. Retries 429s with backoff
    rather than silently treating them as "no result."
    """
    # Query title-only — S2's search is strong on titles but gets confused
    # when authors are concatenated into the query string. We'll verify the
    # author/year on the returned record instead.
    params = {
        "query": title,
        "limit": 3,
        "fields": "title,url,externalIds,venue,year,citationCount,openAccessPdf,authors",
    }

    headers = {"User-Agent": "Explodable Backfill/1.0"}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    data = None
    try:
        with httpx.Client(timeout=15.0) as client:
            for attempt in range(4):
                if not api_key:
                    _s2_throttle()
                resp = client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params=params,
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    break
                if resp.status_code == 429:
                    backoff = 2 ** attempt + 1  # 2, 3, 5, 9
                    print(f"  S2 429 for '{title[:50]}' — retry in {backoff}s", file=sys.stderr)
                    time.sleep(backoff)
                    continue
                # Other non-200: don't retry
                return None
            if data is None:
                return None

            papers = data.get("data") or []
            if not papers:
                return None

            # Walk the top results looking for a loose title match rather
            # than trusting paper[0]. S2 sometimes ranks a tangential paper
            # first when the query matches tokens from a more-cited work.
            paper = None
            for candidate in papers:
                if _loose_title_match(title, candidate.get("title", "")):
                    paper = candidate
                    break
            if paper is None:
                return None
            returned_title = paper.get("title", "")

            # Loose title match — Semantic Scholar's search is generous,
            # we want to reject matches that are clearly wrong
            if not _loose_title_match(title, returned_title):
                return None

            external_ids = paper.get("externalIds") or {}
            doi = external_ids.get("DOI")
            url = paper.get("url")
            if not url and doi:
                url = f"https://doi.org/{doi}"

            # Prefer open-access PDF if available
            oa = paper.get("openAccessPdf") or {}
            oa_url = oa.get("url") if isinstance(oa, dict) else None

            return {
                "url": url or oa_url,
                "doi": doi,
                "venue": paper.get("venue") or "",
                "year": paper.get("year"),
                "citation_count": paper.get("citationCount") or 0,
                "matched_title": returned_title,
                "source": "semantic_scholar",
            }
    except Exception as e:
        print(f"  S2 lookup failed for '{title[:60]}': {e}", file=sys.stderr)
        return None
    return None


def _loose_title_match(query: str, result: str) -> bool:
    """Check if two titles match loosely enough to trust the result.

    Uses normalized token overlap — at least 60% of query tokens should
    appear in the result title. Rejects obvious mismatches without being
    brittle about punctuation or word order.
    """

    def normalize(s: str) -> set:
        return set(re.findall(r"\w+", s.lower()))

    q_tokens = normalize(query)
    r_tokens = normalize(result)
    if not q_tokens:
        return False
    # Drop 2-char and shorter tokens (articles, small prepositions)
    q_tokens = {t for t in q_tokens if len(t) > 2}
    if not q_tokens:
        return False
    overlap = q_tokens & r_tokens
    return len(overlap) / len(q_tokens) >= 0.6


# ── Tavily lookup (broader web search) ──


# Trusted domains come from config/trusted_domains.yaml — a curated list
# of academic publishers, universities, think tanks, government agencies,
# business press, journalism, and practitioner sources that we consider
# credible enough to footnote. Edit the YAML to add/remove domains
# without touching this script.
#
# Tiers are searched in priority order. Higher tiers are more authoritative
# for primary research; lower tiers handle fallback cases (practitioner
# research from vendors, quality journalism). The first tier that returns
# a title-matching hit wins.

_TRUSTED_TIER_ORDER = [
    "academic",
    "universities",
    "think_tank",
    "gov_stats",
    "business_press",
    "data_research",
    "journalism",
    "practitioner_b2b",
]


def _load_trusted_domains() -> dict[str, list[str]]:
    """Load the tiered trusted-domain allowlist from YAML config."""
    import yaml
    config_path = Path(__file__).resolve().parent.parent / "config" / "trusted_domains.yaml"
    if not config_path.exists():
        print(
            f"  Warning: {config_path} missing — using minimal fallback",
            file=sys.stderr,
        )
        return {"academic": ["doi.org", "pubmed.ncbi.nlm.nih.gov", "nature.com", "science.org"]}
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("tiers", {})


_TRUSTED_DOMAINS_BY_TIER: dict[str, list[str]] = _load_trusted_domains()
_ALL_TRUSTED_DOMAINS: list[str] = [
    d for tier_domains in _TRUSTED_DOMAINS_BY_TIER.values() for d in tier_domains
]


def _is_authoritative_url(url: str, allowed_domains: list[str] | None = None) -> bool:
    """Check whether a URL lives on a trusted domain.

    Accepts an optional tier-scoped domain list (used by the tiered
    Tavily walk), otherwise falls back to the flat union of all trusted
    tiers. Generic .edu / .gov / .ac.uk hosts are always accepted to
    catch universities and agencies we haven't enumerated by name.
    """
    if not url:
        return False
    url_lower = url.lower()
    domains = allowed_domains if allowed_domains is not None else _ALL_TRUSTED_DOMAINS
    for domain in domains:
        if f"//{domain}/" in url_lower or f".{domain}/" in url_lower:
            return True
    if "//" in url_lower:
        host = url_lower.split("//", 1)[1].split("/", 1)[0]
        if host.endswith(".edu") or host.endswith(".gov") or host.endswith(".ac.uk"):
            return True
    return False


def lookup_tavily(title: str, author: str = "") -> dict | None:
    """Look up a source via Tavily web search, walking the trusted-domain
    tiers in priority order. Returns the first tier's hit whose URL is
    authoritative AND whose title loosely matches the query.

    Tavily occasionally ignores include_domains when it has few hits,
    so we also verify each returned URL against the tier allowlist
    ourselves before accepting it.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None

    query = title
    if author:
        query = f'{query} "{author}"'

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)

        for tier_name in _TRUSTED_TIER_ORDER:
            tier_domains = _TRUSTED_DOMAINS_BY_TIER.get(tier_name) or []
            if not tier_domains:
                continue
            response = client.search(
                query=query,
                max_results=5,
                search_depth="advanced",
                include_raw_content=False,
                include_domains=tier_domains,
            )
            results = response.get("results") or []
            for candidate in results:
                url = candidate.get("url", "")
                cand_title = candidate.get("title", "")
                if not _is_authoritative_url(url, allowed_domains=tier_domains):
                    continue
                if not _loose_title_match(title, cand_title):
                    continue
                return {
                    "url": url,
                    "matched_title": cand_title,
                    "source": f"tavily_{tier_name}",
                }
        return None
    except Exception as e:
        print(f"  Tavily lookup failed for '{title[:60]}': {e}", file=sys.stderr)
        return None


def lookup_source(title: str, author: str = "", year: str | None = None) -> dict | None:
    """Run the full lookup chain: Semantic Scholar → Tavily → None."""
    result = lookup_semantic_scholar(title, author, year)
    if result and result.get("url"):
        return result

    result = lookup_tavily(title, author)
    if result and result.get("url"):
        return result

    return None


# ── Sub-population 1: findings with zero manifestations ──


def backfill_zero_manifest_findings(dry_run: bool, limit: int | None) -> dict:
    """Parse confidence_basis on zero-manifestation findings, look up URLs,
    create manifestations.
    """
    stats = {
        "processed": 0,
        "sources_parsed": 0,
        "sources_resolved": 0,
        "manifestations_created": 0,
        "failed": 0,
        "no_sources_in_basis": 0,
    }
    unresolved_sources: list[dict] = []

    with get_connection() as conn:
        store = KBStore(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.claim, f.confidence_basis, f.academic_discipline, f.era
                FROM findings f
                WHERE f.status = 'active'
                AND NOT EXISTS (SELECT 1 FROM finding_manifestations WHERE finding_id = f.id)
                ORDER BY f.created_at DESC
                """
                + (f" LIMIT {int(limit)}" if limit else "")
                + ";"
            )
            rows = cur.fetchall()

        print(f"\nFound {len(rows)} zero-manifestation active findings")
        print("=" * 60)

        for finding_id, claim, basis, discipline, era in rows:
            stats["processed"] += 1
            print(f"\n[{stats['processed']}/{len(rows)}] {str(finding_id)[:8]} · {discipline}")
            print(f"  Claim: {claim[:90]}")

            sources = parse_sources_from_confidence_basis(basis or "")
            if not sources:
                stats["no_sources_in_basis"] += 1
                print(f"  ✗ No parseable sources in confidence_basis")
                continue

            print(f"  Parsed {len(sources)} source candidates from confidence_basis")
            stats["sources_parsed"] += len(sources)

            created_here = 0
            for src in sources:
                title = src["title"]
                if len(title) < 10:
                    continue

                result = lookup_source(title, src["author"], src["year"])

                if result and result.get("url"):
                    stats["sources_resolved"] += 1
                    url = result["url"]
                    lookup_src = result.get("source", "unknown")
                    matched = result.get("matched_title", title)
                    print(f"    ✓ [{lookup_src}] {title[:60]}")
                    print(f"      → {url}")
                    if matched != title:
                        print(f"      matched: {matched[:80]}")

                    if not dry_run:
                        try:
                            manif = store.create_manifestation(
                                ManifestationCreate(
                                    description=title[:500],
                                    academic_discipline=discipline,
                                    era=era,
                                    source=title,
                                    source_type=SourceType.ACADEMIC,  # S2-sourced → academic
                                    source_url=url,
                                ),
                                finding_ids=[finding_id],
                            )
                            stats["manifestations_created"] += 1
                            created_here += 1
                        except Exception as e:
                            print(f"      ✗ create_manifestation failed: {e}")
                            stats["failed"] += 1
                else:
                    print(f"    ✗ No URL found: {title[:60]}")
                    unresolved_sources.append(
                        {
                            "finding_id": str(finding_id),
                            "title": title,
                            "author": src["author"],
                            "year": src["year"],
                        }
                    )

            if created_here:
                print(f"  → Created {created_here} manifestation(s) for this finding")

            # Rate-limit courtesy to Semantic Scholar
            time.sleep(0.1)

    # Save unresolved to log for manual follow-up
    if unresolved_sources:
        log_path = Path(__file__).resolve().parent.parent / "logs" / "backfill_unresolved.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(unresolved_sources, indent=2))
        print(f"\n{len(unresolved_sources)} unresolved sources logged to {log_path}")

    return stats


# ── Sub-population 2: manifestations missing source_url ──


def backfill_missing_url_manifestations(dry_run: bool, limit: int | None) -> dict:
    """Iterate manifestations with NULL/empty source_url, look up by title,
    update the source_url field.
    """
    stats = {
        "processed": 0,
        "resolved": 0,
        "updated": 0,
        "unresolved": 0,
    }

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.id, m.source, m.academic_discipline, m.era, m.source_type::text
                FROM manifestations m
                WHERE (m.source_url IS NULL OR m.source_url = '')
                AND EXISTS (
                    SELECT 1 FROM finding_manifestations fm
                    JOIN findings f ON f.id = fm.finding_id
                    WHERE fm.manifestation_id = m.id AND f.status = 'active'
                )
                ORDER BY m.created_at DESC
                """
                + (f" LIMIT {int(limit)}" if limit else "")
                + ";"
            )
            rows = cur.fetchall()

        print(f"\nFound {len(rows)} manifestations with missing URL (linked to active findings)")
        print("=" * 60)

        for manif_id, source_title, discipline, era, source_type in rows:
            stats["processed"] += 1
            print(f"\n[{stats['processed']}/{len(rows)}] {str(manif_id)[:8]} · {source_type}")
            print(f"  Title: {source_title[:90]}")

            result = lookup_source(source_title)
            if result and result.get("url"):
                stats["resolved"] += 1
                url = result["url"]
                print(f"    ✓ {url}")

                if not dry_run:
                    with conn.cursor() as update_cur:
                        update_cur.execute(
                            "UPDATE manifestations SET source_url = %s, updated_at = NOW() WHERE id = %s;",
                            (url, manif_id),
                        )
                        conn.commit()
                    stats["updated"] += 1
            else:
                stats["unresolved"] += 1
                print(f"    ✗ No URL found")

            time.sleep(0.1)

    return stats


# ── Main ──


def main():
    parser = argparse.ArgumentParser(description="Backfill manifestation URLs")
    parser.add_argument("--dry-run", action="store_true", help="Don't write, just report")
    parser.add_argument("--only-zero-manifest", action="store_true",
                        help="Only process zero-manifestation findings")
    parser.add_argument("--only-missing-url", action="store_true",
                        help="Only process manifestations missing URL")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N")
    args = parser.parse_args()

    print("=" * 60)
    print(f"MANIFESTATION URL BACKFILL {'(DRY RUN)' if args.dry_run else ''}")
    print("=" * 60)

    run_zero = not args.only_missing_url
    run_missing = not args.only_zero_manifest

    all_stats = {}

    try:
        if run_zero:
            print("\n\n>>> SUB-POPULATION 1: Zero-manifestation findings")
            all_stats["zero_manifest"] = backfill_zero_manifest_findings(
                dry_run=args.dry_run, limit=args.limit
            )

        if run_missing:
            print("\n\n>>> SUB-POPULATION 2: Manifestations missing URL")
            all_stats["missing_url"] = backfill_missing_url_manifestations(
                dry_run=args.dry_run, limit=args.limit
            )

    finally:
        close_pool()

    # Summary
    print("\n\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for key, stats in all_stats.items():
        print(f"\n{key}:")
        for k, v in stats.items():
            print(f"  {k}: {v}")

    print("\nDone.")


if __name__ == "__main__":
    main()
