"""LLM-as-judge scoring for consulting-quality analytical essays.

Built per the Phase 0 plan in docs/coherence_rework_plan.md. Uses Claude-Opus
as the judge, with a structured rubric loaded from config/rubrics/*.yaml.
Calibration target: Spearman rho >= 0.7 against editor rankings on a ranked
corpus of existing drafts.

Design choices:

* G-Eval style prompt structure (Liu et al., EMNLP 2023) — the only automated
  coherence metric that clears rho = 0.5 against human judgment. We cite the
  rubric criteria verbatim inside the prompt and force CoT reasoning before
  committing a score per criterion.
* BooookScore's 8-error taxonomy is NOT directly used as scoring categories —
  we use the 10 consulting-writing criteria from Report 5 instead, because the
  rubric is for consulting-quality output specifically, not generic coherence.
  But the BooookScore categories (discontinuity, salience, language, etc.) map
  naturally to several of our criteria and inform the prompt wording.
* Scores are integer 1-5 per criterion. Weighted criteria (per rubric yaml)
  get 1.5x multiplier in the total. Veto rule: any criterion scoring 1 flags
  the draft for manual review regardless of total.
* The judge is deterministic across runs (temperature=0, no sampling). This
  matters for calibration: we want rank order to be stable.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ── Types ──


@dataclass
class CriterionScore:
    """A single criterion score with the judge's reasoning."""

    criterion_id: str
    score: int  # 1..5
    reasoning: str  # CoT justification the judge wrote before committing the score

    def is_veto(self) -> bool:
        """Whether this score triggers the veto rule (score of 1)."""
        return self.score <= 1


@dataclass
class DraftScore:
    """Full rubric scoring for a single draft."""

    draft_path: str
    draft_word_count: int
    criterion_scores: list[CriterionScore]
    rubric_version: str
    rubric_path: str

    def total_unweighted(self) -> int:
        """Sum of raw criterion scores (out of 50 for a 10-criterion rubric)."""
        return sum(c.score for c in self.criterion_scores)

    def total_weighted(self, weights: dict[str, float]) -> float:
        """Weighted sum using per-criterion multipliers from the rubric."""
        total = 0.0
        for c in self.criterion_scores:
            multiplier = weights.get(c.criterion_id, 1.0)
            total += c.score * multiplier
        return total

    def vetoed_criteria(self) -> list[str]:
        """Criterion IDs that scored 1 (vetoed per the rubric rule)."""
        return [c.criterion_id for c in self.criterion_scores if c.is_veto()]

    def to_dict(self) -> dict:
        return {
            "draft_path": self.draft_path,
            "draft_word_count": self.draft_word_count,
            "rubric_version": self.rubric_version,
            "rubric_path": self.rubric_path,
            "total_unweighted": self.total_unweighted(),
            "vetoed_criteria": self.vetoed_criteria(),
            "criterion_scores": [
                {
                    "criterion_id": c.criterion_id,
                    "score": c.score,
                    "reasoning": c.reasoning,
                }
                for c in self.criterion_scores
            ],
        }


# ── Rubric loading ──


def load_rubric(rubric_path: Path | str) -> dict[str, Any]:
    """Load a rubric yaml file and return its parsed dict."""
    rubric_path = Path(rubric_path)
    with open(rubric_path) as f:
        rubric = yaml.safe_load(f)
    if "criteria" not in rubric:
        raise ValueError(f"Rubric at {rubric_path} is missing 'criteria' key")
    return rubric


def rubric_weights(rubric: dict[str, Any]) -> dict[str, float]:
    """Extract per-criterion weight multipliers from a rubric."""
    guidance = rubric.get("scoring_guidance", {}) or {}
    return guidance.get("weighted_criteria", {}) or {}


# ── Prompt builder ──


_JUDGE_SYSTEM_PROMPT = """You are an editorial judge evaluating long-form analytical essays \
for a high-ticket consulting practice ($8,000-$25,000 diagnostic engagements). \
Your evaluation uses a published rubric grounded in consulting-writing research \
(Minto Pyramid, BCG action-titles, David C. Baker's expertise tests, \
Roger Martin's integrative thinking, Harvard Kennedy School policy memo rubric, \
and Berger-Milkman sharing research).

You will be given a draft essay and a scoring rubric. For each criterion:

1. Read the criterion's name, description, and 1/3/5 anchor descriptions.
2. Think through the draft systematically: does it meet the criterion?
3. Write your reasoning in 2-4 sentences, citing specific phrases or moves from the draft.
4. Commit to an integer score from 1 to 5 based on the anchor descriptions.
5. Be strict. A score of 5 means "commanding" — the top quartile of analytical \
writing. A score of 3 means "competent." A score of 1 is a potential veto flag.

You must NOT score higher than 3 on any criterion where the evidence in the \
draft is ambiguous. Reserve 4 and 5 for criteria where the draft clearly \
demonstrates the move. If in doubt, score lower, not higher.

Return your scores as a JSON object matching the schema in the user prompt."""


def _format_criterion(criterion: dict) -> str:
    """Format a single criterion for the judge prompt."""
    scale = criterion["scale"]
    weight_note = ""
    if criterion.get("weight"):
        weight_note = f" [weighted {criterion['weight']}x]"
    return f"""### {criterion['id']}: {criterion['name']}{weight_note}

**What it measures:** {criterion['what_it_measures'].strip()}

**Scoring anchors:**
- **1 (fail):** {scale[1]}
- **3 (competent):** {scale[3]}
- **5 (commanding):** {scale[5]}
"""


def build_judge_prompt(draft_text: str, rubric: dict[str, Any]) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for the judge call.

    The user prompt contains the full draft and the rubric as formatted markdown.
    Structured output is enforced via Claude's tool_use — the caller passes the
    tool schema from build_judge_tool_schema() and extracts scores from the
    tool_use block instead of parsing freeform JSON.
    """
    criteria_md = "\n\n".join(_format_criterion(c) for c in rubric["criteria"])

    user_prompt = f"""# Draft to evaluate

<draft>
{draft_text}
</draft>

# Rubric

{criteria_md}

# Task

Score every criterion using the `record_rubric_scores` tool. Write 2-4 sentences \
of reasoning citing specific phrases or moves from the draft BEFORE committing a \
score. Be strict. Reserve 4 and 5 for criteria where the draft clearly \
demonstrates the move; if in doubt, score lower."""

    return _JUDGE_SYSTEM_PROMPT, user_prompt


def build_judge_tool_schema(rubric: dict[str, Any]) -> dict:
    """Build an Anthropic tool_use schema that forces one entry per criterion.

    Design note: the schema uses FLAT parallel arrays of primitive types
    (strings and integers) rather than a nested array of objects. Claude
    Opus occasionally serializes nested-object array fields as JSON strings
    when responding via tool_use — with unescaped inner quotes in reasoning
    text, making the stringified output unparseable. Flat primitive arrays
    don't trigger that failure mode.

    The schema declares one field per criterion, named after the criterion
    ID, plus a parallel reasoning field. Claude has no ambiguity about
    which score maps to which criterion.
    """
    properties: dict[str, Any] = {}
    required: list[str] = []
    for c in rubric["criteria"]:
        cid = c["id"]
        properties[f"{cid}__reasoning"] = {
            "type": "string",
            "description": (
                f"2-4 sentences of reasoning for '{c['name']}', citing specific "
                "phrases or moves from the draft, written before committing a score."
            ),
        }
        properties[f"{cid}__score"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": 5,
            "description": f"Integer 1-5 for '{c['name']}' per the criterion's anchor descriptions.",
        }
        required.append(f"{cid}__reasoning")
        required.append(f"{cid}__score")

    return {
        "name": "record_rubric_scores",
        "description": (
            "Record the judge's scores for every criterion in the rubric. "
            "Fill in a reasoning and score field for each criterion."
        ),
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


# ── Claude invocation ──


def _claude_client():
    """Lazy Anthropic client so importing this module doesn't require the key."""
    from anthropic import Anthropic

    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _extract_tool_use_scores(resp, rubric: dict[str, Any]) -> list[dict]:
    """Pull criterion scores from Claude's tool_use response block.

    The flat-schema tool input has keys like `{criterion_id}__score` and
    `{criterion_id}__reasoning`. We collapse those into the list-of-dicts
    shape the rest of the module expects.
    """
    tool_input = None
    for block in resp.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "record_rubric_scores"
        ):
            tool_input = block.input
            break
    if tool_input is None:
        raise ValueError(
            "Judge response contained no record_rubric_scores tool_use block. "
            f"Stop reason: {resp.stop_reason}"
        )

    # Some Claude responses deliver tool input as a JSON string rather than
    # a parsed dict. Tolerate both.
    if isinstance(tool_input, str):
        tool_input = json.loads(tool_input)

    records = []
    for c in rubric["criteria"]:
        cid = c["id"]
        records.append(
            {
                "criterion_id": cid,
                "reasoning": tool_input[f"{cid}__reasoning"],
                "score": int(tool_input[f"{cid}__score"]),
            }
        )
    return records


def score_draft(
    draft_path: Path | str,
    rubric_path: Path | str = "config/rubrics/analytical_essay.yaml",
    model: str = "claude-opus-4-6",
    max_tokens: int = 4096,
) -> DraftScore:
    """Score a draft against a rubric using Claude-as-judge.

    Reads the draft from disk, builds the judge prompt, calls Claude with
    temperature=0, parses the JSON response, returns a DraftScore.
    """
    draft_path = Path(draft_path)
    rubric_path = Path(rubric_path)
    draft_text = draft_path.read_text()
    word_count = len(draft_text.split())
    rubric = load_rubric(rubric_path)

    system_prompt, user_prompt = build_judge_prompt(draft_text, rubric)
    tool_schema = build_judge_tool_schema(rubric)

    client = _claude_client()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": "record_rubric_scores"},
    )

    score_records = _extract_tool_use_scores(resp, rubric)

    # Validate we got every criterion
    expected_ids = {c["id"] for c in rubric["criteria"]}
    returned_ids = {r["criterion_id"] for r in score_records}
    missing = expected_ids - returned_ids
    if missing:
        raise ValueError(f"Judge skipped criteria: {missing}")

    criterion_scores = [
        CriterionScore(
            criterion_id=r["criterion_id"],
            score=int(r["score"]),
            reasoning=r["reasoning"],
        )
        for r in score_records
    ]

    return DraftScore(
        draft_path=str(draft_path),
        draft_word_count=word_count,
        criterion_scores=criterion_scores,
        rubric_version=rubric.get("version", "unknown"),
        rubric_path=str(rubric_path),
    )


# ── Calibration: rank correlation ──


def spearman_rank_correlation(ranks_a: list[float], ranks_b: list[float]) -> float:
    """Compute Spearman's rank correlation coefficient between two rankings.

    ranks_a[i] and ranks_b[i] are rankings (or scores from which rankings can
    be derived) for the same set of items in the same order. Returns rho in
    [-1, 1]. Ties are handled by average rank.
    """
    if len(ranks_a) != len(ranks_b):
        raise ValueError("rank lists must have equal length")
    if len(ranks_a) < 2:
        raise ValueError("need at least 2 items to compute rank correlation")

    def _rank(xs: list[float]) -> list[float]:
        sorted_indices = sorted(range(len(xs)), key=lambda i: xs[i])
        ranks = [0.0] * len(xs)
        i = 0
        while i < len(xs):
            j = i
            while j + 1 < len(xs) and xs[sorted_indices[j + 1]] == xs[sorted_indices[i]]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[sorted_indices[k]] = avg_rank
            i = j + 1
        return ranks

    ra = _rank(ranks_a)
    rb = _rank(ranks_b)
    n = len(ra)
    mean_a = sum(ra) / n
    mean_b = sum(rb) / n
    num = sum((ra[i] - mean_a) * (rb[i] - mean_b) for i in range(n))
    den_a = sum((ra[i] - mean_a) ** 2 for i in range(n)) ** 0.5
    den_b = sum((rb[i] - mean_b) ** 2 for i in range(n)) ** 0.5
    if den_a == 0 or den_b == 0:
        return 0.0
    return num / (den_a * den_b)


def calibrate(
    editor_rankings: dict[str, int],
    judge_scores: dict[str, DraftScore],
    rubric: dict[str, Any],
) -> dict[str, Any]:
    """Compare editor rankings to judge scores, report Spearman rho.

    editor_rankings maps draft_path -> integer rank (1 = best). judge_scores
    maps draft_path -> DraftScore. Returns a dict with rho, pass/fail against
    the 0.7 calibration threshold, and per-criterion agreement stats.
    """
    shared = sorted(set(editor_rankings) & set(judge_scores))
    if len(shared) < 3:
        raise ValueError(
            f"Need at least 3 drafts in both editor_rankings and judge_scores, got {len(shared)}"
        )

    weights = rubric_weights(rubric)

    # Editor ranks: lower = better, so higher score in the comparison.
    # Invert so rank=1 becomes the highest value for correlation.
    editor_values = [-editor_rankings[p] for p in shared]
    judge_values = [judge_scores[p].total_weighted(weights) for p in shared]

    rho = spearman_rank_correlation(editor_values, judge_values)

    return {
        "n": len(shared),
        "spearman_rho": rho,
        "passes_calibration": rho >= 0.7,
        "threshold": 0.7,
        "drafts": shared,
        "editor_ranks": {p: editor_rankings[p] for p in shared},
        "judge_totals": {p: judge_scores[p].total_weighted(weights) for p in shared},
    }
