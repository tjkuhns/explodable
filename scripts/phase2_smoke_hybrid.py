#!/usr/bin/env python3
"""Smoke test for the hybrid cognitive pipeline.

Invokes the compiled hybrid graph directly on a single topic, bypassing
FastAPI and Celery. Prints every state transition and the final draft.

Usage:
    python scripts/phase2_smoke_hybrid.py                    # T1 Explodable
    python scripts/phase2_smoke_hybrid.py --topic T3         # specific topic
    python scripts/phase2_smoke_hybrid.py --brand the_boulder --topic T4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

for line in open(Path(__file__).resolve().parent.parent / ".env"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.content_pipeline.hybrid_graph import HybridContentState, compile_hybrid_graph


TOPICS = {
    "T1": ("explodable", "The silent disengagement: why enterprise customers churn six months before they tell you. Diagnose the psychological and organizational mechanics of disengagement-before-notification, grounded in behavioral science and buyer psychology."),
    "T2": ("explodable", "The first number wins: anchoring in B2B procurement negotiations. Analyze how anchoring and reference dependence shape multi-stakeholder pricing decisions."),
    "T3": ("the_boulder", "Why B2B vendor lock-in and religious conversion share a psychological architecture. A cross-domain analysis of identity investment, sunk cost, tribal belonging, and the cost of leaving."),
    "T4": ("the_boulder", "Legacy anxiety and the economics of signaling after death. Why the things humans build to outlast them function as commercial products for an anxiety that no product can actually resolve."),
    "T5": ("the_boulder", "What golf reveals about organizational status games. Using golf as a lens to analyze the psychological architecture of status games in modern organizations."),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="T1")
    parser.add_argument("--brand", default=None)
    args = parser.parse_args()

    if args.topic not in TOPICS:
        print(f"Unknown topic: {args.topic}. Options: {list(TOPICS.keys())}")
        return 1

    default_brand, prompt = TOPICS[args.topic]
    brand = args.brand or default_brand

    print(f"Hybrid pipeline smoke test")
    print(f"  Topic: {args.topic} ({prompt[:60]}...)")
    print(f"  Brand: {brand}")
    print()

    graph = compile_hybrid_graph()

    initial_state = {
        "topic": prompt,
        "brand": brand,
        "output_type": "newsletter",
        "auto_approve": True,
        "max_bvcs_revisions": 1,
    }

    t0 = time.time()
    print("Running pipeline...")

    last_state = {}
    try:
        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, updates in event.items():
                elapsed = time.time() - t0
                status = updates.get("status", "")
                last_state.update(updates)
                decisions = updates.get("architecture_decisions", [])
                for d in decisions:
                    print(f"  [{elapsed:5.1f}s] {node_name}: {d.get('decision', '')} — {d.get('reason', '')}")
                if not decisions:
                    print(f"  [{elapsed:5.1f}s] {node_name}: {status}")

    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n  FAILED at {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return 1

    elapsed = time.time() - t0
    print(f"\n  Total time: {elapsed:.1f}s")

    # Extract draft from accumulated state
    draft_obj = last_state.get("draft")
    if not draft_obj:
        print("  No draft in final state")
        return 1
    draft_text = draft_obj.newsletter if hasattr(draft_obj, "newsletter") else str(draft_obj)

    # Save the draft
    output_dir = Path("logs/phase2_hybrid_smoke")
    output_dir.mkdir(parents=True, exist_ok=True)
    draft_path = output_dir / f"{args.topic}_{brand}_hybrid_draft.md"
    draft_path.write_text(draft_text)
    print(f"\n  Draft saved: {draft_path}")
    print(f"  Word count: {len(draft_text.split())}")

    # Save architecture decisions
    decisions = last_state.get("architecture_decisions", [])
    if decisions:
        dec_path = output_dir / f"{args.topic}_decisions.json"
        dec_path.write_text(json.dumps(decisions, indent=2))
        print(f"  Decisions: {dec_path}")
        for d in decisions:
            print(f"    {d.get('stage', '?')}: {d.get('decision', '?')}")

    # Run execution gate
    print("\n  Execution gate...")
    os.system(f"python3 scripts/check_export_gate.py {draft_path}")

    # Print first 20 lines of draft
    print(f"\n  --- Draft preview ---")
    for line in draft_text.split("\n")[:20]:
        print(f"  {line}")
    print(f"  ...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
