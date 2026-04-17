#!/usr/bin/env python3
"""Import pre-approved findings from a JSON file directly into the KB.

Bypasses the research pipeline entirely. Findings are written as
provenance='human', created as proposed, then immediately approved
(status='active', approved_at=NOW()).

Usage:
    python scripts/import_findings.py findings.json
"""

import json
import sys
from pathlib import Path

# Add project root to path so src.kb imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError
from src.kb.connection import get_connection, close_pool
from src.kb.crud import KBStore
from src.kb.ingest_models import FindingInput, SourceInput
from src.kb.models import (
    FindingCreate,
    FindingProvenance,
    FindingStatus,
    ManifestationCreate,
    RootAnxiety,
    PankseppCircuit,
    SourceType,
)


def import_finding(store: KBStore, data: FindingInput, index: int) -> str | None:
    """Import a single finding. Returns finding ID on success, None on skip/error."""
    # Build FindingCreate — provenance=human, status=proposed (approve after)
    finding_data = FindingCreate(
        claim=data.claim,
        elaboration=data.elaboration,
        root_anxieties=[RootAnxiety(a) for a in data.root_anxieties],
        primary_circuits=[PankseppCircuit(c) for c in data.primary_circuits] if data.primary_circuits else None,
        confidence_score=data.confidence_score,
        confidence_basis=data.confidence_basis,
        provenance=FindingProvenance.HUMAN,
        academic_discipline=data.academic_discipline,
        cultural_domains=data.cultural_domains,
        era=data.era,
        status=FindingStatus.PROPOSED,
    )

    # create_finding runs SHA-256 → MinHash → cosine >0.90 dedup
    finding = store.create_finding(finding_data)

    # Immediately approve — sets status='active', approved_at=NOW()
    approved = store.approve_finding(finding.id)
    if not approved:
        raise RuntimeError(f"Failed to approve finding {finding.id}")

    # Write sources as manifestations linked to this finding
    for src in data.sources:
        manifestation_data = ManifestationCreate(
            description=src.snippet,
            academic_discipline=data.academic_discipline,
            era=data.era,
            source=src.title,
            source_type=SourceType(src.source_type),
            source_url=src.url,
        )
        store.create_manifestation(manifestation_data, finding_ids=[approved.id])

    return str(approved.id)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_findings.py <findings.json>")
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

    imported = 0
    skipped = 0
    failed = 0

    try:
        with get_connection() as conn:
            store = KBStore(conn)

            for i, item in enumerate(raw):
                # Validate input
                try:
                    data = FindingInput(**item)
                except ValidationError as e:
                    print(f"[{i}] VALIDATION ERROR for claim: {item.get('claim', '<missing>')[:60]}")
                    for err in e.errors():
                        print(f"     {err['loc']}: {err['msg']}")
                    failed += 1
                    continue

                # Import
                try:
                    finding_id = import_finding(store, data, i)
                    print(f"[{i}] IMPORTED: {data.claim[:60]}... → {finding_id}")
                    imported += 1
                except ValueError as e:
                    if "duplicate" in str(e).lower() or "Duplicate" in str(e):
                        print(f"[{i}] SKIPPED (duplicate): {data.claim[:60]}...")
                        skipped += 1
                    else:
                        print(f"[{i}] FAILED: {data.claim[:60]}... — {e}")
                        failed += 1
                except Exception as e:
                    print(f"[{i}] FAILED: {data.claim[:60]}... — {type(e).__name__}: {e}")
                    failed += 1

    finally:
        close_pool()

    print(f"\n{'='*60}")
    print(f"Import complete: {imported} imported, {skipped} skipped as duplicates, {failed} failed with errors")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
