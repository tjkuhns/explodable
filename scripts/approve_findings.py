#!/usr/bin/env python3
"""Bulk-approve findings by status, domain, or explicit IDs.

Sets status='active' and approved_at=NOW() for each matched finding.

Usage:
    python scripts/approve_findings.py --status proposed
    python scripts/approve_findings.py --status proposed --domain "healthcare buyer psychology"
    python scripts/approve_findings.py --ids <uuid1> <uuid2> ...
"""

import argparse
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.kb.connection import get_connection, close_pool
from src.kb.crud import KBStore
from src.kb.models import FindingStatus


def main():
    parser = argparse.ArgumentParser(description="Bulk-approve KB findings")
    parser.add_argument("--status", type=str, help="Approve all findings with this status")
    parser.add_argument("--academic-discipline", type=str, dest="academic_discipline", help="Filter by academic discipline (used with --status)")
    parser.add_argument("--ids", nargs="+", type=str, help="Approve specific finding UUIDs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be approved without committing")
    args = parser.parse_args()

    if not args.status and not args.ids:
        parser.error("Must specify --status or --ids")

    try:
        with get_connection() as conn:
            store = KBStore(conn)

            # Collect findings to approve
            if args.ids:
                findings = []
                for uid in args.ids:
                    f = store.get_finding(UUID(uid))
                    if f and f.status == FindingStatus.PROPOSED:
                        findings.append(f)
                    elif f:
                        print(f"SKIP: {uid} — status is '{f.status.value}', not 'proposed'")
                    else:
                        print(f"SKIP: {uid} — not found")
            else:
                findings = store.list_findings(
                    status=FindingStatus(args.status),
                    academic_discipline=args.academic_discipline,
                    limit=1000,
                )

            if not findings:
                print("No matching findings to approve.")
                return

            print(f"Found {len(findings)} finding(s) to approve")
            if args.academic_discipline:
                print(f"  Discipline filter: {args.academic_discipline}")
            print("=" * 60)

            approved = 0
            failed = 0

            for f in findings:
                short_claim = f.claim[:70]
                if args.dry_run:
                    print(f"  [DRY RUN] Would approve: {short_claim}...")
                    approved += 1
                    continue

                result = store.approve_finding(f.id)
                if result:
                    print(f"  APPROVED: {short_claim}...")
                    approved += 1
                else:
                    print(f"  FAILED:   {short_claim}...")
                    failed += 1

            print()
            print("=" * 60)
            prefix = "[DRY RUN] " if args.dry_run else ""
            print(f"{prefix}{approved} approved, {failed} failed out of {len(findings)} total")
            print("=" * 60)

    finally:
        close_pool()


if __name__ == "__main__":
    main()
