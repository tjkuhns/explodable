#!/usr/bin/env python3
"""Ingest a batch of findings in hr_tech_brief JSON format into the KB.

Handles the hr_tech-format fields (finding_id, source_titles, weighted_score,
connected_anxieties) and inserts as provenance='ai_proposed', status='proposed',
approved_at=NULL.

Dedup: skips any finding whose claim SHA-256 hash already exists in the DB.
Embeddings: generated via the existing embedding pipeline (text-embedding-3-small, 768-dim).

Usage:
    python scripts/ingest_batch_findings.py <findings.json>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.kb.connection import get_connection, close_pool
from src.kb.crud import KBStore
from src.kb.dedup import check_sha256_duplicate
from src.kb.embeddings import generate_embedding
from src.kb.models import (
    FindingCreate,
    FindingProvenance,
    FindingStatus,
    RootAnxiety,
)
from src.kb.relationship_classifier import classify_and_commit


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_batch_findings.py <findings.json>")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"Error: File not found: {json_path}")
        sys.exit(1)

    with open(json_path) as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        print("Error: JSON file must contain an array of finding objects")
        sys.exit(1)

    print(f"Loaded {len(raw)} findings from {json_path}")
    print("=" * 60)

    inserted = 0
    skipped = 0
    errors = []
    rel_stats = {"committed": 0, "queued": 0, "skipped": 0, "fk_errors": 0}

    try:
        with get_connection() as conn:
            store = KBStore(conn)

            for i, item in enumerate(raw):
                claim = item.get("claim", "")
                short_claim = claim[:70]

                try:
                    # Step 1: SHA-256 dedup check on claim_hash
                    dup = check_sha256_duplicate(conn, claim)
                    if dup is not None:
                        print(f"[{i:2d}] SKIP (dup): {short_claim}...")
                        skipped += 1
                        continue

                    # Step 2: Generate embedding
                    embedding = generate_embedding(claim)

                    # Step 3: Build FindingCreate
                    # confidence_basis auto-generated from domain + score + source count
                    source_titles = item.get("source_titles", [])
                    discipline = item.get("academic_discipline") or item.get("domain", "unknown")
                    confidence_basis = (
                        f"AI-proposed from {discipline} research; "
                        f"score={item['confidence_score']}; "
                        f"{len(source_titles)} source(s): {'; '.join(source_titles[:3])}"
                    )

                    finding_data = FindingCreate(
                        claim=claim,
                        elaboration=item["elaboration"],
                        root_anxieties=[RootAnxiety(a) for a in item["root_anxieties"]],
                        primary_circuits=None,
                        confidence_score=item["confidence_score"],
                        confidence_basis=confidence_basis,
                        provenance=FindingProvenance.AI_PROPOSED,
                        academic_discipline=item.get("academic_discipline") or item.get("domain", "unknown"),
                        cultural_domains=item.get("cultural_domains"),
                        era=item.get("era"),
                        status=FindingStatus.PROPOSED,
                        embedding=embedding,
                    )

                    # Step 4: Insert (skip_dedup=True since we already checked SHA-256
                    # and embedding is pre-generated so no double API call)
                    finding = store.create_finding(finding_data, skip_dedup=True)
                    print(f"[{i:2d}] OK:   {short_claim}... → {finding.id}")
                    inserted += 1

                    # Step 5: Classify relationships against nearest neighbors.
                    # Auto-commits above 0.70 confidence; queues the rest for review.
                    # FK validation is built in — invalid IDs are silently skipped.
                    try:
                        result = classify_and_commit(conn, finding.id)
                        rel_stats["committed"] += result["committed"]
                        rel_stats["queued"] += result["queued"]
                        rel_stats["skipped"] += result["skipped"]
                        rel_stats["fk_errors"] += result["fk_errors"]
                        print(f"       → rels: +{result['committed']} committed, {result['queued']} queued")
                    except Exception as rel_e:
                        print(f"       → rels: FAILED ({type(rel_e).__name__}: {rel_e})")

                except Exception as e:
                    err_msg = f"[{i:2d}] ERR:  {short_claim}... — {type(e).__name__}: {e}"
                    print(err_msg)
                    errors.append(err_msg)

    finally:
        close_pool()

    print()
    print("=" * 60)
    print(f"FINDINGS:      {inserted} inserted, {skipped} skipped (duplicates), {len(errors)} errors")
    print(f"RELATIONSHIPS: {rel_stats['committed']} committed, {rel_stats['queued']} queued for review")
    if rel_stats['fk_errors']:
        print(f"               {rel_stats['fk_errors']} FK errors (invalid finding IDs skipped)")
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e}")
    print("=" * 60)


if __name__ == "__main__":
    main()
