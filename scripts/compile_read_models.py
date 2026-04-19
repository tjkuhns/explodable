#!/usr/bin/env python3
"""Refresh all CQRS read models from the Postgres write model.

Refreshes materialized views, recompiles the wiki index and per-finding
pages, rebuilds the CAG XML cache, and updates version tracking so the
pipeline can detect staleness.

Usage:
    python scripts/compile_read_models.py           # refresh everything
    python scripts/compile_read_models.py --check   # check staleness only, don't refresh
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

for line in open(Path(__file__).resolve().parent.parent / ".env"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg


def _get_db_url() -> str:
    db_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    if "${POSTGRES_PASSWORD}" in db_url:
        db_url = db_url.replace("${POSTGRES_PASSWORD}", os.environ["POSTGRES_PASSWORD"])
    return db_url


def compute_kb_hash(conn) -> tuple[str, int]:
    """Hash of all active finding IDs + updated_at timestamps. Changes when
    any finding is added, updated, or status-changed."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id::text, updated_at::text FROM findings "
            "WHERE status = 'active' ORDER BY id"
        )
        rows = cur.fetchall()
    content = "".join(f"{r[0]}:{r[1]}" for r in rows)
    return hashlib.sha256(content.encode()).hexdigest()[:16], len(rows)


def refresh_materialized_views(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_cluster_index")
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_finding_neighbors")


def compile_wiki(conn) -> int:
    """Rebuild kb_wiki/index.md and per-finding pages. Returns finding count."""
    from src.content_pipeline.experimental.graph_expander import KBGraph
    import re

    wiki_root = Path("kb_wiki")
    wiki_root.mkdir(exist_ok=True)
    findings_dir = wiki_root / "findings"
    findings_dir.mkdir(exist_ok=True)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, claim, elaboration,
                   root_anxieties::text[], academic_discipline,
                   COALESCE(cultural_domains, ARRAY[]::text[]),
                   confidence_score, confidence_level::text
            FROM findings WHERE status = 'active'
            ORDER BY confidence_score DESC, id
            """
        )
        rows = cur.fetchall()

    def slug(s, n=40):
        s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
        return s[:n] or "untitled"

    # Per-finding files
    for ix, (fid, claim, elab, anxieties, disc, domains, conf, conf_level) in enumerate(rows, 1):
        fname = f"{ix:04d}_{slug(claim)}.md"
        body = [
            f"# Finding {ix}",
            "",
            f"- **Anxieties:** {', '.join(anxieties or [])}",
            f"- **Discipline:** {disc}",
        ]
        if domains:
            body.append(f"- **Domains:** {', '.join(domains)}")
        body.extend([
            f"- **Confidence:** {conf_level}",
            "",
            f"**Claim:** {claim}",
            "",
            "**Elaboration:**",
            "",
            elab,
        ])
        (findings_dir / fname).write_text("\n".join(body))

    # Index grouped by anxiety
    lines = [
        "# Knowledge Base Index",
        "",
        f"{len(rows)} active behavioral-science findings. Each row is one finding.",
        "",
        "The `id` column is the stable reference used in essay citations "
        "(cite as `[src:N]` alongside a short quoted phrase from the finding text).",
        "",
    ]

    by_anxiety: dict[str, list] = {}
    for ix, (fid, claim, elab, anxieties, disc, domains, conf, conf_level) in enumerate(rows, 1):
        for a in (anxieties or []):
            by_anxiety.setdefault(a, []).append((ix, claim, disc, domains, conf_level))

    for anxiety in sorted(by_anxiety.keys()):
        lines.append(f"## Anxiety: {anxiety}")
        lines.append("")
        lines.append("| id | claim | discipline | domains | confidence |")
        lines.append("|---:|---|---|---|---|")
        seen = set()
        for ix, claim, disc, domains, conf_level in by_anxiety[anxiety]:
            if ix in seen:
                continue
            seen.add(ix)
            claim_cell = claim.replace("|", "\\|")
            domain_cell = ", ".join(domains) if domains else "—"
            lines.append(f"| {ix} | {claim_cell} | {disc} | {domain_cell} | {conf_level} |")
        lines.append("")

    (wiki_root / "index.md").write_text("\n".join(lines))
    return len(rows)


def compile_cag_xml(conn) -> int:
    """Rebuild the CAG XML cache. Reuses Pipeline B's serialization logic."""
    from scripts.phase1_run_pipeline_b import load_findings, build_kb_xml

    findings = load_findings()
    xml = build_kb_xml(findings)

    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)
    (cache_dir / "kb_cag.xml").write_text(xml)
    return len(findings)


def update_version(conn, model_name: str, kb_hash: str, finding_count: int, notes: str = "") -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO read_model_versions (model_name, compiled_at, kb_hash, finding_count, notes)
            VALUES (%s, now(), %s, %s, %s)
            ON CONFLICT (model_name) DO UPDATE SET
                compiled_at = now(),
                kb_hash = EXCLUDED.kb_hash,
                finding_count = EXCLUDED.finding_count,
                notes = EXCLUDED.notes
            """,
            [model_name, kb_hash, finding_count, notes],
        )


def check_staleness(conn) -> dict[str, bool]:
    """Check if any read model is stale (kb_hash doesn't match current)."""
    current_hash, current_count = compute_kb_hash(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT model_name, kb_hash, finding_count, compiled_at FROM read_model_versions")
        rows = cur.fetchall()
    results = {}
    for name, stored_hash, stored_count, compiled_at in rows:
        is_stale = stored_hash != current_hash
        results[name] = is_stale
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="check staleness only")
    args = parser.parse_args()

    db_url = _get_db_url()
    with psycopg.connect(db_url) as conn:
        kb_hash, finding_count = compute_kb_hash(conn)
        print(f"KB state: {finding_count} active findings, hash={kb_hash}")

        if args.check:
            staleness = check_staleness(conn)
            for name, is_stale in staleness.items():
                status = "STALE" if is_stale else "current"
                print(f"  {name}: {status}")
            return 0

        print("Refreshing materialized views...")
        refresh_materialized_views(conn)
        update_version(conn, "mv_cluster_index", kb_hash, finding_count, "refreshed")
        update_version(conn, "mv_finding_neighbors", kb_hash, finding_count, "refreshed")
        conn.commit()
        print("  mv_cluster_index: refreshed")
        print("  mv_finding_neighbors: refreshed")

        print("Compiling wiki index...")
        n = compile_wiki(conn)
        update_version(conn, "wiki_index", kb_hash, n, "recompiled")
        conn.commit()
        print(f"  kb_wiki/: {n} findings, index rewritten")

        print("Compiling CAG XML cache...")
        n = compile_cag_xml(conn)
        update_version(conn, "cag_xml_cache", kb_hash, n, "recompiled")
        conn.commit()
        print(f"  cache/kb_cag.xml: {n} findings")

        # Embeddings: just update version tracking (embeddings are managed by the ingest pipeline)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM findings WHERE status='active' AND embedding IS NOT NULL")
            embedded = cur.fetchone()[0]
        update_version(conn, "vector_embeddings", kb_hash, embedded,
                       f"{embedded}/{finding_count} findings have embeddings")
        conn.commit()
        print(f"  vector_embeddings: {embedded}/{finding_count} embedded")

        print(f"\nAll read models refreshed. KB hash: {kb_hash}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
