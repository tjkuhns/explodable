"""Revision gate: Pareto filter for critique-driven revisions.

Scores the original draft and the proposed revision via the Phase 0
calibrated judge, then applies a strict Pareto filter: the revision is
accepted ONLY if it improves at least one rubric criterion without
degrading any other.

Design grounded in Report 3 (docs/research/hybrid_reports/03_adversarial_critique.md):

* Huang et al. (ICLR 2024): GPT-3.5 corrected 7.6% of incorrect responses
  while turning 8.8% of correct ones incorrect — net negative without gating.
* Kotte et al. (2026): "aggressive" rewriting has a 42.4% harm rate.
* ART (Shridhar et al., NAACL 2024): trained gating models outperform self-
  selection by LLMs — but our calibrated judge (ρ = 0.841) serves as the gate.
* Default is "don't change it." The burden of proof is on the revision.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

for line in open(Path(__file__).resolve().parent.parent.parent / ".env"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.content_pipeline.eval.judge import (
    CriterionScore,
    DraftScore,
    load_rubric,
    rubric_weights,
    score_draft,
)


RUBRIC_PATH = Path("config/rubrics/analytical_essay.yaml")
REGRESSION_TOLERANCE = 0.0  # no regression allowed; set to 0.5 if small dips acceptable


@dataclass
class GateDecision:
    accepted: bool
    reason: str
    original_weighted: float
    revised_weighted: float
    improved_criteria: list[str]
    regressed_criteria: list[str]
    unchanged_criteria: list[str]
    original_scores: dict[str, int]
    revised_scores: dict[str, int]


def _score_to_dict(draft_score: DraftScore) -> dict[str, int]:
    """Extract {criterion_id: score} from a DraftScore."""
    return {cs.criterion_id: cs.score for cs in draft_score.criterion_scores}


def evaluate_revision(
    original_path: str,
    revised_path: str,
    rubric_path: Path = RUBRIC_PATH,
    tolerance: float = REGRESSION_TOLERANCE,
) -> GateDecision:
    """Score both drafts and apply the Pareto filter.

    Returns a GateDecision indicating whether the revision should be accepted.

    The Pareto criterion: a revision is accepted if:
    1. At least one criterion score IMPROVED (revised > original)
    2. NO criterion score REGRESSED by more than `tolerance` (revised < original - tolerance)

    If both conditions are met, the revision is accepted. Otherwise, the
    original draft is preserved.
    """
    rubric = load_rubric(rubric_path)
    weights = rubric_weights(rubric)

    original_score = score_draft(original_path, rubric_path)
    revised_score = score_draft(revised_path, rubric_path)

    orig_dict = _score_to_dict(original_score)
    rev_dict = _score_to_dict(revised_score)

    improved: list[str] = []
    regressed: list[str] = []
    unchanged: list[str] = []

    for cid in orig_dict:
        orig_val = orig_dict[cid]
        rev_val = rev_dict.get(cid, orig_val)
        if rev_val > orig_val:
            improved.append(cid)
        elif rev_val < orig_val - tolerance:
            regressed.append(cid)
        else:
            unchanged.append(cid)

    orig_weighted = round(original_score.total_weighted(weights), 1)
    rev_weighted = round(revised_score.total_weighted(weights), 1)

    if not improved:
        return GateDecision(
            accepted=False,
            reason="no criteria improved",
            original_weighted=orig_weighted,
            revised_weighted=rev_weighted,
            improved_criteria=improved,
            regressed_criteria=regressed,
            unchanged_criteria=unchanged,
            original_scores=orig_dict,
            revised_scores=rev_dict,
        )

    if regressed:
        return GateDecision(
            accepted=False,
            reason=f"regression on: {', '.join(regressed)}",
            original_weighted=orig_weighted,
            revised_weighted=rev_weighted,
            improved_criteria=improved,
            regressed_criteria=regressed,
            unchanged_criteria=unchanged,
            original_scores=orig_dict,
            revised_scores=rev_dict,
        )

    return GateDecision(
        accepted=True,
        reason=f"improved: {', '.join(improved)}",
        original_weighted=orig_weighted,
        revised_weighted=rev_weighted,
        improved_criteria=improved,
        regressed_criteria=regressed,
        unchanged_criteria=unchanged,
        original_scores=orig_dict,
        revised_scores=rev_dict,
    )


def revision_gate(
    original_draft: str,
    revised_draft: str,
    rubric_path: Path = RUBRIC_PATH,
    tolerance: float = REGRESSION_TOLERANCE,
) -> tuple[str, GateDecision]:
    """Run the Pareto gate on two draft strings, return (chosen_draft, decision).

    Writes both to temp files for the judge, then cleans up. Returns the
    text of whichever draft passes the gate (original if revision rejected).
    """
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(original_draft)
        orig_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(revised_draft)
        rev_path = f.name

    try:
        decision = evaluate_revision(orig_path, rev_path, rubric_path, tolerance)
    finally:
        os.unlink(orig_path)
        os.unlink(rev_path)

    chosen = revised_draft if decision.accepted else original_draft
    return chosen, decision
