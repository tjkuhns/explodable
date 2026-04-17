#!/usr/bin/env python3
"""Migrate KB data from local Postgres to Supabase via REST API.

Prerequisites:
1. Run data/supabase_schema.sql in the Supabase SQL Editor first
2. Set SUPABASE_SECRET_KEY in .env

Usage:
    python scripts/migrate_to_supabase.py
    python scripts/migrate_to_supabase.py --table findings  # single table
    python scripts/migrate_to_supabase.py --dry-run          # show counts only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
import psycopg

for line in open(Path(__file__).resolve().parent.parent / ".env"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


SUPABASE_URL = "https://cgausradwkpvdsiaarkj.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def get_local_db():
    db_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    if "${POSTGRES_PASSWORD}" in db_url:
        db_url = db_url.replace("${POSTGRES_PASSWORD}", os.environ["POSTGRES_PASSWORD"])
    return psycopg.connect(db_url)


def post_rows(table: str, rows: list[dict], batch_size: int = 50) -> int:
    """POST rows to Supabase REST API in batches."""
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={**HEADERS, "Prefer": "return=minimal,resolution=ignore-duplicates"},
            json=batch,
            timeout=30,
        )
        if resp.status_code not in (200, 201, 204):
            print(f"  ERROR on batch {i//batch_size}: {resp.status_code} {resp.text[:200]}")
            # Try one at a time to identify the bad row
            for j, row in enumerate(batch):
                r2 = requests.post(
                    f"{SUPABASE_URL}/rest/v1/{table}",
                    headers={**HEADERS, "Prefer": "return=minimal,resolution=ignore-duplicates"},
                    json=[row],
                    timeout=15,
                )
                if r2.status_code not in (200, 201, 204):
                    print(f"    Row {i+j} failed: {r2.status_code} {r2.text[:100]}")
                else:
                    total += 1
        else:
            total += len(batch)
    return total


def migrate_findings(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id::text, claim, elaboration,
                   root_anxieties::text[], primary_circuits::text[],
                   confidence_score, confidence_basis,
                   provenance::text, academic_discipline, era,
                   status::text,
                   created_at::text, updated_at::text, approved_at::text,
                   cultural_domains, source_document
            FROM findings ORDER BY id
        """)
        rows = []
        for r in cur.fetchall():
            rows.append({
                "id": r[0], "claim": r[1], "elaboration": r[2],
                "root_anxieties": r[3], "primary_circuits": r[4],
                "confidence_score": r[5], "confidence_basis": r[6],
                "provenance": r[7], "academic_discipline": r[8], "era": r[9],
                "status": r[10],
                "created_at": r[11], "updated_at": r[12], "approved_at": r[13],
                "cultural_domains": r[14], "source_document": r[15],
                # Skip embedding — too large for REST API, re-embed later
            })
        return rows


def migrate_relationships(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id::text, from_finding_id::text, to_finding_id::text,
                   relationship::text, rationale, confidence, created_at::text
            FROM finding_relationships ORDER BY id
        """)
        return [
            {"id": r[0], "from_finding_id": r[1], "to_finding_id": r[2],
             "relationship": r[3], "rationale": r[4], "confidence": r[5],
             "created_at": r[6]}
            for r in cur.fetchall()
        ]


def migrate_manifestations(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id::text, description, academic_discipline, era,
                   source, source_type::text, source_url, source_date::text,
                   created_at::text, updated_at::text
            FROM manifestations ORDER BY id
        """)
        return [
            {"id": r[0], "description": r[1], "academic_discipline": r[2],
             "era": r[3], "source": r[4], "source_type": r[5],
             "source_url": r[6], "source_date": r[7],
             "created_at": r[8], "updated_at": r[9]}
            for r in cur.fetchall()
        ]


def migrate_finding_manifestations(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT finding_id::text, manifestation_id::text FROM finding_manifestations")
        return [{"finding_id": r[0], "manifestation_id": r[1]} for r in cur.fetchall()]


def migrate_root_anxiety_nodes(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id::text, anxiety::text, description, cultural_domains, created_at::text
            FROM root_anxiety_nodes ORDER BY id
        """)
        return [
            {"id": r[0], "anxiety": r[1], "description": r[2],
             "cultural_domains": r[3], "created_at": r[4]}
            for r in cur.fetchall()
        ]


def migrate_anxiety_circuit_affinities(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id::text, anxiety::text, circuit::text, affinity::text, rationale
            FROM anxiety_circuit_affinities ORDER BY id
        """)
        return [
            {"id": r[0], "anxiety": r[1], "circuit": r[2],
             "affinity": r[3], "rationale": r[4]}
            for r in cur.fetchall()
        ]


TABLES = [
    ("root_anxiety_nodes", migrate_root_anxiety_nodes),
    ("anxiety_circuit_affinities", migrate_anxiety_circuit_affinities),
    ("findings", migrate_findings),
    ("manifestations", migrate_manifestations),
    ("finding_manifestations", migrate_finding_manifestations),
    ("finding_relationships", migrate_relationships),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", help="migrate only this table")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Connecting to local Postgres...")
    conn = get_local_db()

    tables = TABLES
    if args.table:
        tables = [(n, f) for n, f in TABLES if n == args.table]
        if not tables:
            print(f"Unknown table: {args.table}")
            return 1

    for table_name, extract_fn in tables:
        print(f"\n{table_name}:")
        rows = extract_fn(conn)
        print(f"  extracted {len(rows)} rows from local DB")

        if args.dry_run:
            continue

        if not rows:
            print("  skipping (empty)")
            continue

        inserted = post_rows(table_name, rows)
        print(f"  inserted {inserted}/{len(rows)} rows into Supabase")

    conn.close()

    if not args.dry_run:
        # Verify
        print("\n=== Verification ===")
        for table_name, _ in tables:
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/{table_name}?select=count",
                headers={**HEADERS, "Prefer": "count=exact"},
            )
            count = resp.headers.get("Content-Range", "?").split("/")[-1]
            print(f"  {table_name}: {count} rows in Supabase")

    return 0


if __name__ == "__main__":
    sys.exit(main())
