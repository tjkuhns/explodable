#!/usr/bin/env python3
"""Run the hybrid pipeline on all 50 test topics.

Executes each topic, scores via the Sonnet judge, verifies router
classification against ground truth, and reports results with
confidence intervals.

Usage:
    python scripts/phase2_run_n50.py                    # all 50
    python scripts/phase2_run_n50.py --start 6 --end 15 # topics T06-T15
    python scripts/phase2_run_n50.py --dry-run           # verify setup, no API calls
    python scripts/phase2_run_n50.py --score-only        # score existing drafts without regenerating
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
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

from config.test_topics_n50 import TOPICS, TestTopic
from src.content_pipeline.experimental.hybrid_graph import HybridContentState, compile_hybrid_graph
from src.content_pipeline.eval.judge import load_rubric, rubric_weights, score_draft


OUTPUT_ROOT = Path("logs/phase2_n50")
RUBRIC_PATH = Path("config/rubrics/analytical_essay.yaml")


def run_topic(graph, topic: TestTopic) -> dict:
    """Run one topic through the hybrid pipeline, return metadata."""
    t0 = time.time()
    result = {
        "topic_id": topic.id,
        "brand": topic.brand,
        "expected_density": topic.expected_density,
        "expected_domains": topic.expected_domains,
        "expected_anxieties": topic.expected_anxieties,
        "status": "pending",
    }

    try:
        initial_state = {
            "topic": topic.prompt,
            "brand": topic.brand,
            "output_type": "newsletter",
            "auto_approve": True,
            "max_bvcs_revisions": 1,
        }

        # Stream to capture intermediate state
        last_state = {}
        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, updates in event.items():
                last_state.update(updates)

        # Extract draft
        draft_obj = last_state.get("draft")
        if not draft_obj:
            result["status"] = "no_draft"
            result["wall_seconds"] = round(time.time() - t0, 1)
            return result

        draft_text = draft_obj.newsletter if hasattr(draft_obj, "newsletter") else str(draft_obj)
        draft_path = OUTPUT_ROOT / f"{topic.id}_draft.md"
        draft_path.write_text(draft_text)

        # Extract routing decision
        decisions = last_state.get("architecture_decisions", [])
        router_decision = next(
            (d for d in decisions if d.get("stage") == "topic_router"),
            {}
        )

        result["status"] = "complete"
        result["draft_path"] = str(draft_path)
        result["word_count"] = len(draft_text.split())
        result["wall_seconds"] = round(time.time() - t0, 1)
        result["router_decision"] = router_decision.get("decision", "unknown")
        result["architecture_decisions"] = decisions

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["wall_seconds"] = round(time.time() - t0, 1)

    return result


def score_topic(result: dict) -> dict:
    """Score a completed topic's draft via the Sonnet judge."""
    if result["status"] != "complete" or "draft_path" not in result:
        return result

    rubric = load_rubric(RUBRIC_PATH)
    weights = rubric_weights(rubric)

    try:
        s = score_draft(result["draft_path"], RUBRIC_PATH)
        result["weighted_score"] = round(s.total_weighted(weights), 1)
        result["unweighted_score"] = s.total_unweighted()
        result["criterion_scores"] = {
            cs.criterion_id: cs.score for cs in s.criterion_scores
        }
    except Exception as e:
        result["score_error"] = str(e)

    return result


def confidence_interval(values: list[float], confidence: float = 0.95) -> tuple[float, float]:
    """Compute confidence interval for the mean using t-distribution."""
    n = len(values)
    if n < 2:
        return (values[0], values[0]) if values else (0, 0)
    mean = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(n)
    # Approximate t-value for 95% CI
    t_val = 2.0 if n >= 30 else 2.1 if n >= 20 else 2.3 if n >= 10 else 2.8
    return (round(mean - t_val * se, 1), round(mean + t_val * se, 1))


def print_results(results: list[dict]):
    """Print the full results table with confidence intervals."""
    scored = [r for r in results if "weighted_score" in r]
    if not scored:
        print("No scored results.")
        return

    print(f"\n{'='*70}")
    print(f"N=50 VALIDATION RESULTS")
    print(f"{'='*70}")
    print(f"Completed: {len(scored)}/{len(results)}")
    print()

    # By density
    print(f"{'Density':<15} {'N':<5} {'Mean':<8} {'95% CI':<16} {'Stdev':<8}")
    print("-" * 52)
    for density in ["dense", "medium", "cross_domain", "sparse", "ood"]:
        vals = [r["weighted_score"] for r in scored if r["expected_density"] == density]
        if vals:
            ci = confidence_interval(vals)
            sd = round(statistics.stdev(vals), 1) if len(vals) > 1 else 0
            print(f"{density:<15} {len(vals):<5} {statistics.mean(vals):<8.1f} [{ci[0]}, {ci[1]}]{'':<4} {sd}")

    # Overall
    all_vals = [r["weighted_score"] for r in scored]
    ci = confidence_interval(all_vals)
    print("-" * 52)
    print(f"{'OVERALL':<15} {len(all_vals):<5} {statistics.mean(all_vals):<8.1f} [{ci[0]}, {ci[1]}]")

    # By brand
    print(f"\n{'Brand':<15} {'N':<5} {'Mean':<8} {'95% CI':<16}")
    print("-" * 44)
    for brand in ["explodable", "the_boulder"]:
        vals = [r["weighted_score"] for r in scored if r["brand"] == brand]
        if vals:
            ci = confidence_interval(vals)
            print(f"{brand:<15} {len(vals):<5} {statistics.mean(vals):<8.1f} [{ci[0]}, {ci[1]}]")

    # Router accuracy
    print(f"\nRouter classification accuracy:")
    correct = 0
    total = 0
    for r in scored:
        if "router_decision" not in r:
            continue
        total += 1
        actual_route = r["router_decision"]
        expected = r["expected_density"]
        # Map expected density → expected route
        expected_routes = {
            "dense": "vector_retriever",
            "medium": "vector_retriever",
            "cross_domain": "wiki_selector",
            "sparse": "graph_walker",
            "ood": "vector_retriever",
        }
        if actual_route == expected_routes.get(expected, ""):
            correct += 1
    if total:
        print(f"  {correct}/{total} ({100*correct/total:.0f}%)")

    # Per-criterion averages
    print(f"\nPer-criterion means (across all {len(scored)} drafts):")
    criterion_vals: dict[str, list[int]] = {}
    for r in scored:
        for cid, score in r.get("criterion_scores", {}).items():
            criterion_vals.setdefault(cid, []).append(score)
    for cid in sorted(criterion_vals.keys()):
        vals = criterion_vals[cid]
        print(f"  {cid:<35} {statistics.mean(vals):.2f}/5")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1, help="start topic number")
    parser.add_argument("--end", type=int, default=50, help="end topic number")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--score-only", action="store_true")
    args = parser.parse_args()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    # Filter topics by range
    topics = [t for t in TOPICS if args.start <= int(t.id[1:]) <= args.end]
    print(f"Topics: {len(topics)} (T{args.start:02d}-T{args.end:02d})")

    if args.dry_run:
        for t in topics:
            print(f"  {t.id} [{t.brand}] {t.expected_density:<13} {t.prompt[:60]}...")
        return 0

    # Load existing results if score-only
    meta_path = OUTPUT_ROOT / "_results.json"
    if args.score_only:
        if not meta_path.exists():
            print("No existing results to score.")
            return 1
        results = json.loads(meta_path.read_text())
        print(f"Scoring {len(results)} existing results...")
        for i, r in enumerate(results):
            if "weighted_score" not in r and r.get("status") == "complete":
                print(f"  [{i+1}/{len(results)}] scoring {r['topic_id']}...")
                results[i] = score_topic(r)
        meta_path.write_text(json.dumps(results, indent=2))
        print_results(results)
        return 0

    # Compile the hybrid graph
    print("Compiling hybrid graph...")
    graph = compile_hybrid_graph()

    results = []
    # Load any existing results for incremental runs
    if meta_path.exists():
        results = json.loads(meta_path.read_text())

    existing_ids = {r["topic_id"] for r in results}

    for i, topic in enumerate(topics):
        if topic.id in existing_ids:
            print(f"[{i+1}/{len(topics)}] {topic.id} — already run, skipping")
            continue

        print(f"[{i+1}/{len(topics)}] {topic.id} [{topic.brand}] {topic.expected_density}...", flush=True)
        result = run_topic(graph, topic)

        if result["status"] == "complete":
            print(f"  scoring...", end=" ", flush=True)
            result = score_topic(result)
            score_str = f"{result.get('weighted_score', '?')}/57.5" if "weighted_score" in result else "score failed"
            print(f"{result['word_count']}w, {result['wall_seconds']}s, {score_str}")
        else:
            print(f"  {result['status']}: {result.get('error', '')}")

        results.append(result)
        # Save incrementally
        meta_path.write_text(json.dumps(results, indent=2))

    print_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
