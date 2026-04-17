#!/usr/bin/env python3
"""Test the graph expander's impact on draft quality.

Takes Pipeline C's existing selections for each topic, runs graph expansion
to add up to 5 diversity-maximizing findings, generates a new draft with
the expanded set, and scores via the Phase 0 judge. Compares to Pipeline C's
original scores.

Usage:
    python scripts/phase2_test_graph_expansion.py              # all 5 topics
    python scripts/phase2_test_graph_expansion.py --topic T3   # one topic
    python scripts/phase2_test_graph_expansion.py --dry-run    # show expansion, skip API calls
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict
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
from anthropic import Anthropic

from src.content_pipeline.graph_expander import KBGraph, expand


MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 0.7
MAX_TOKENS = 4000
RUBRIC_PATH = Path("config/rubrics/analytical_essay.yaml")
OUTPUT_ROOT = Path("logs/phase2_graph_expansion")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

TOPICS = {
    "T1": "The silent disengagement: why enterprise customers churn six months before they tell you. Diagnose the psychological and organizational mechanics of disengagement-before-notification, grounded in behavioral science and buyer psychology.",
    "T2": "The first number wins: anchoring in B2B procurement negotiations. Analyze how anchoring and reference dependence shape multi-stakeholder pricing decisions, and what this means for how vendors should structure their first pricing conversation.",
    "T3": "Why B2B vendor lock-in and religious conversion share a psychological architecture. A cross-domain analysis of how identity investment, sunk cost, tribal belonging, and the cost of leaving collapse into the same structural phenomenon across two superficially different domains.",
    "T4": "Legacy anxiety and the economics of signaling after death. Why the things humans build to outlast them — monuments, foundations, endowed chairs, engraved benches — function as commercial products for an anxiety that no product can actually resolve.",
    "T5": "What golf reveals about organizational status games. Using golf as a lens — its rituals, its score structures, its clubhouses, its handicap system — analyze the psychological architecture of the status games that play out in modern organizations.",
}

PASS2_SYSTEM = """You are a senior behavioral-science essayist writing long-form analytical essays for a B2B consulting practice. You have been given a set of research findings — some from an initial selection, some surfaced through relationship-graph expansion to bring in cross-domain connections.

Constraints:

- Length: 900-1500 words
- Structure: analytical argument, not listicle. Clear thesis in the opening, structural development through mechanisms and evidence, an earned counterpoint section, a conclusion that advances the argument rather than restates it.
- Citations: every [src:N] marker must be followed by a short quoted phrase (6-15 words) taken verbatim from the finding's claim or elaboration. Example: "Loss aversion loads risk perception asymmetrically [src:42] \\"losses loom roughly twice as large as equivalent gains\\""
- Tone: analytical, serious, evidence-grounded. No Camus references. No generic consulting language.
- Findings marked [EXPANDED] were surfaced via graph traversal for cross-domain diversity. Use them to strengthen cross-domain connections — they are structurally related to the primary findings but may come from different domains.
- Do not write YAML frontmatter. Do not write a Sources section. Just the essay body starting with the title as an H1.
"""


def load_finding_data() -> tuple[dict[int, str], dict[str, str], dict[str, str]]:
    """Returns (pos_to_uuid, uuid_to_claim, uuid_to_elaboration)."""
    db_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    if "${POSTGRES_PASSWORD}" in db_url:
        db_url = db_url.replace("${POSTGRES_PASSWORD}", os.environ["POSTGRES_PASSWORD"])
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id::text, claim, elaboration FROM findings "
                "WHERE status='active' ORDER BY confidence_score DESC, id"
            )
            rows = cur.fetchall()
    pos_to_uuid = {i + 1: r[0] for i, r in enumerate(rows)}
    uuid_to_claim = {r[0]: r[1] for r in rows}
    uuid_to_elab = {r[0]: r[2] for r in rows}
    return pos_to_uuid, uuid_to_claim, uuid_to_elab


def build_findings_block(
    expanded_results, uuid_to_claim, uuid_to_elab, kb_graph
):
    """Build the XML findings block for the drafter, marking expanded findings."""
    lines = ["<selected_findings>"]
    for i, r in enumerate(expanded_results, 1):
        tag = " [EXPANDED]" if r.source == "expanded" else ""
        anxieties = ",".join(kb_graph.finding_anxieties.get(r.finding_id, []))
        domains = ",".join(r.domains) if r.domains else ""
        claim = uuid_to_claim.get(r.finding_id, "")
        elab = uuid_to_elab.get(r.finding_id, "")
        lines.append(
            f'<finding id="{i}" anxieties="{anxieties}" domains="{domains}"'
            f' source="{r.source}">'
        )
        lines.append(f"  <claim>{claim}{tag}</claim>")
        lines.append(f"  <elaboration>{elab}</elaboration>")
        lines.append("</finding>")
    lines.append("</selected_findings>")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", help="run only this topic (T1..T5)")
    parser.add_argument("--dry-run", action="store_true", help="show expansion only, skip API calls")
    args = parser.parse_args()

    topics = list(TOPICS.keys()) if not args.topic else [args.topic]

    print("Loading KB graph and finding data...")
    kb = KBGraph()
    kb.load()
    pos_to_uuid, uuid_to_claim, uuid_to_elab = load_finding_data()

    # Load Pipeline C's original selections
    meta_c = json.load(open("logs/phase1_bakeoff/pipeline_c/_run_metadata.json"))
    c_selections = {r["topic_id"]: r["pass1_selected"] for r in meta_c["runs"]}

    # Load Pipeline C's original judge scores for comparison
    judge_scores = json.load(open("logs/phase1_bakeoff/_judge_scores.json"))
    c_scores = {
        r["topic_id"]: r["weighted_total"]
        for r in judge_scores
        if r["pipeline"] == "C"
    }

    client = None if args.dry_run else Anthropic()
    all_results = []

    for tid in topics:
        print(f"\n{'='*60}")
        print(f"Topic {tid}: {TOPICS[tid][:80]}...")
        print(f"Pipeline C baseline score: {c_scores.get(tid, '?')}")

        # Map Pipeline C's position IDs to UUIDs
        positions = c_selections.get(tid, [])
        uuids = [pos_to_uuid[p] for p in positions if p in pos_to_uuid]
        print(f"Original selection: {len(uuids)} findings")

        # Expand
        expanded = expand(kb, uuids, max_expand=5)
        new_findings = [r for r in expanded if r.source == "expanded"]
        print(f"After expansion: {len(expanded)} findings (+{len(new_findings)} new)")

        for r in new_findings:
            claim = uuid_to_claim.get(r.finding_id, "?")[:80]
            print(f"  + ppr={r.ppr_score:.4f} mmr={r.mmr_score:.4f} domains={r.domains}")
            print(f"    \"{claim}\"")

        if args.dry_run:
            print("  [dry-run: skipping draft generation]")
            continue

        # Generate draft with expanded set
        findings_block = build_findings_block(expanded, uuid_to_claim, uuid_to_elab, kb)
        print(f"Generating draft...")
        t0 = time.time()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=[{"type": "text", "text": PASS2_SYSTEM + "\n\n" + findings_block}],
            messages=[{"role": "user", "content": f"Topic:\n\n{TOPICS[tid]}"}],
        )
        draft = msg.content[0].text
        wall = round(time.time() - t0, 1)
        words = len(re.findall(r"\S+", draft))
        print(f"Draft: {words} words in {wall}s")

        draft_path = OUTPUT_ROOT / f"{tid}_expanded_draft.md"
        draft_path.write_text(draft)

        # Score via judge
        from src.content_pipeline.eval.judge import score_draft, load_rubric, rubric_weights
        print("Scoring via Phase 0 judge...")
        score = score_draft(str(draft_path), RUBRIC_PATH)
        rubric = load_rubric(RUBRIC_PATH)
        weights = rubric_weights(rubric)
        weighted = round(score.total_weighted(weights), 1)
        unweighted = score.total_unweighted()

        baseline = c_scores.get(tid, 0)
        delta = weighted - baseline
        print(f"Judge score: {unweighted}/50 unweighted, {weighted}/57.5 weighted")
        print(f"vs Pipeline C baseline: {baseline} → {weighted} (Δ = {delta:+.1f})")

        all_results.append({
            "topic_id": tid,
            "baseline_weighted": baseline,
            "expanded_weighted": weighted,
            "expanded_unweighted": unweighted,
            "delta": delta,
            "word_count": words,
            "wall_seconds": wall,
            "n_original": len(uuids),
            "n_expanded": len(new_findings),
            "draft_path": str(draft_path),
            "expansion_details": [asdict(r) for r in new_findings],
        })

        # Persist incrementally
        meta_path = OUTPUT_ROOT / "_results.json"
        meta_path.write_text(json.dumps(all_results, indent=2))

    if not args.dry_run and all_results:
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"{'Topic':<6} {'Baseline':<10} {'Expanded':<10} {'Delta':<8}")
        for r in all_results:
            print(f"{r['topic_id']:<6} {r['baseline_weighted']:<10.1f} {r['expanded_weighted']:<10.1f} {r['delta']:+.1f}")
        mean_delta = sum(r["delta"] for r in all_results) / len(all_results)
        print(f"\nMean delta: {mean_delta:+.1f}")
        improved = sum(1 for r in all_results if r["delta"] > 0)
        regressed = sum(1 for r in all_results if r["delta"] < 0)
        print(f"Improved: {improved}/{len(all_results)}, Regressed: {regressed}/{len(all_results)}")


if __name__ == "__main__":
    main()
