#!/usr/bin/env python3
"""Score all drafts in a ranking doc against the rubric and compute Spearman rho.

Reads docs/phase0_editor_rankings.md for Tom's editorial rankings, then runs
the LLM-as-judge against every draft with a filled `rank:` field and reports
Spearman rank correlation between editor ranks and judge weighted totals.

Usage:
    python scripts/score_drafts_and_calibrate.py [--explodable-only]

If --explodable-only is passed, only ranks the 5 Explodable drafts (tighter
calibration set, small-n caveat applies: n=5 requires rho >= 0.9 to be
statistically significant at p=0.05, vs n=12 at rho >= 0.58).
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Manual .env load
for line in open(Path(__file__).resolve().parent.parent / ".env"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.content_pipeline.eval.judge import (
    calibrate,
    load_rubric,
    rubric_weights,
    score_draft,
)


RANKINGS_PATH = Path("docs/phase0_editor_rankings.md")
RUBRIC_PATH = Path("config/rubrics/analytical_essay.yaml")
RESULTS_PATH = Path("logs/phase0_judge_scores.json")


def parse_rankings(markdown: str) -> dict[str, int]:
    """Parse editor rankings out of the phase0_editor_rankings.md file.

    Expects blocks like:
      - [ ] `drafts/foo.md`
        - title: *...*
        - **rank:** 3

    Returns {draft_path: rank}. Skips entries where rank is missing or blank.
    """
    rankings: dict[str, int] = {}
    # Pair up each draft path with the first rank: line that follows it
    draft_pattern = re.compile(r"^\s*-\s*\[[ x]\]\s*`([^`]+\.md)`", re.MULTILINE)
    rank_pattern = re.compile(r"^\s*-\s*\*\*rank:\*\*\s*(\S+)", re.MULTILINE)

    matches = list(draft_pattern.finditer(markdown))
    for i, m in enumerate(matches):
        draft_path = m.group(1).strip()
        # Find the next rank: line before the next draft block
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        block = markdown[start:end]
        rank_m = rank_pattern.search(block)
        if not rank_m:
            continue
        val = rank_m.group(1).strip()
        # Skip "_____" placeholder and anything non-numeric
        if not val.lstrip("-").isdigit():
            continue
        rankings[draft_path] = int(val)
    return rankings


def main():
    parser = argparse.ArgumentParser(description="Score drafts and calibrate against editor rankings")
    parser.add_argument(
        "--explodable-only",
        action="store_true",
        help="Only score and calibrate on the 5 Explodable drafts",
    )
    parser.add_argument(
        "--force-rescore",
        action="store_true",
        help="Rescore drafts even if cached results exist",
    )
    args = parser.parse_args()

    if not RANKINGS_PATH.exists():
        print(f"Rankings file not found: {RANKINGS_PATH}", file=sys.stderr)
        sys.exit(1)

    rankings = parse_rankings(RANKINGS_PATH.read_text())
    if not rankings:
        print(
            f"No rankings parsed from {RANKINGS_PATH}. "
            "Fill in the `rank:` field next to each draft first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.explodable_only:
        rankings = {p: r for p, r in rankings.items() if "drafts/latest_unreviewed" in p or "explodable" in Path(p).read_text()[:400]}

    print(f"Parsed {len(rankings)} editor rankings:")
    for path, rank in sorted(rankings.items(), key=lambda x: x[1]):
        print(f"  rank {rank}: {Path(path).name}")
    print()

    # Load cached scores if they exist, score missing drafts
    cached: dict[str, dict] = {}
    if RESULTS_PATH.exists() and not args.force_rescore:
        cached = {r["draft_path"]: r for r in json.loads(RESULTS_PATH.read_text())}

    rubric = load_rubric(RUBRIC_PATH)
    weights = rubric_weights(rubric)

    from src.content_pipeline.eval.judge import CriterionScore, DraftScore

    judge_scores: dict[str, DraftScore] = {}
    for path in rankings:
        if path in cached and not args.force_rescore:
            d = cached[path]
            judge_scores[path] = DraftScore(
                draft_path=d["draft_path"],
                draft_word_count=d["draft_word_count"],
                rubric_version=d["rubric_version"],
                rubric_path=d["rubric_path"],
                criterion_scores=[
                    CriterionScore(
                        criterion_id=c["criterion_id"],
                        score=c["score"],
                        reasoning=c["reasoning"],
                    )
                    for c in d["criterion_scores"]
                ],
            )
            print(f"  [cached] {Path(path).name}")
        else:
            print(f"  [scoring] {Path(path).name}...", end=" ", flush=True)
            s = score_draft(path, RUBRIC_PATH)
            judge_scores[path] = s
            print(f"{s.total_unweighted()}/50 unweighted")

    # Persist
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps([s.to_dict() for s in judge_scores.values()], indent=2)
    )
    print(f"\nJudge scores written to {RESULTS_PATH}")

    # Calibrate
    result = calibrate(rankings, judge_scores, rubric)
    print("\n" + "=" * 60)
    print("CALIBRATION")
    print("=" * 60)
    print(f"n = {result['n']}")
    print(f"Spearman rho = {result['spearman_rho']:.3f}")
    print(f"Threshold    = {result['threshold']}")
    print(f"Passes       = {result['passes_calibration']}")
    print()
    print("Editor ranks vs judge weighted totals:")
    by_rank = sorted(result["drafts"], key=lambda p: result["editor_ranks"][p])
    for p in by_rank:
        print(
            f"  editor rank {result['editor_ranks'][p]:2d}"
            f"  |  judge {result['judge_totals'][p]:6.1f}"
            f"  |  {Path(p).name}"
        )

    if not result["passes_calibration"]:
        print("\n" + "!" * 60)
        print("CALIBRATION FAILED — rho below 0.7 threshold")
        print("!" * 60)
        print("Options:")
        print("  (a) Rewrite judge prompt with tighter anchor descriptions")
        print("  (b) Cut criteria that are pulling correlation down")
        print("  (c) Pool only Explodable drafts (--explodable-only flag)")
        print("  (d) Accept rubric as structural-only; handle taste manually")
        sys.exit(2)


if __name__ == "__main__":
    main()
