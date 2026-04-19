#!/usr/bin/env python3
"""Code quality judge — scores Python files against a structured rubric.

Adapts the essay evaluation harness methodology to code review.
Uses Gemini Flash (free tier) as the judge to demonstrate cross-model
generalizability and avoid Anthropic API costs.

Usage:
    python scripts/score_code.py src/content_pipeline/graph_expander.py
    python scripts/score_code.py src/content_pipeline/*.py
    python scripts/score_code.py src/content_pipeline/ --summary
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


RUBRIC_PATH = Path("config/rubrics/python_code_quality.yaml")


@dataclass
class CriterionScore:
    criterion_id: str
    criterion_name: str
    score: int
    reasoning: str
    weight: float


@dataclass
class CodeScore:
    file_path: str
    criteria: list[CriterionScore]
    veto_flags: list[str]
    summary: str

    def total_unweighted(self) -> int:
        return sum(c.score for c in self.criteria)

    def total_weighted(self) -> float:
        return sum(c.score * c.weight for c in self.criteria)

    def max_weighted(self) -> float:
        return sum(5 * c.weight for c in self.criteria)


def load_rubric(path: Path = RUBRIC_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def check_veto_rules(code: str, rubric: dict) -> list[str]:
    """Check for veto-rule violations (patterns that flag regardless of score)."""
    flags = []
    for rule in rubric.get("veto_rules", []):
        pattern = rule["pattern"]
        if pattern in code:
            # Skip false positives for the "except Exception:" rule
            # when it's re-raised or handled properly
            if pattern == "except:" and "except Exception" in code:
                continue
            flags.append(f"VETO: {rule['reason']} (pattern: '{pattern}')")
    return flags


def build_judge_prompt(rubric: dict) -> str:
    """Build the system prompt for the code quality judge."""
    criteria_text = ""
    for c in rubric["criteria"]:
        criteria_text += f"\n### {c['id']}: {c['name']} (weight: {c['weight']}x)\n"
        criteria_text += f"{c['description'].strip()}\n"
        criteria_text += f"Score anchors:\n"
        for level, desc in c["anchors"].items():
            criteria_text += f"  {level}/5: {desc.strip()}\n"

    return f"""You are a senior Python code reviewer evaluating code quality against a structured rubric.

Score the provided Python file on each criterion using a 1-5 integer scale. For each criterion, provide:
1. A score (1-5)
2. One sentence of reasoning citing a specific line or pattern from the code

The rubric focuses on SUBJECTIVE quality dimensions that automated linters cannot assess. Do not comment on PEP 8 formatting, import order, or whitespace — those are handled by Ruff/Black. Focus on the human-readable qualities: naming, structure, architecture, documentation intent, error handling philosophy, and testability.

Be calibrated: a 3 is competent production code. A 5 is exceptional — code you'd point a junior developer to as a reference. A 1 is code that would be rejected in review.

RUBRIC:
{criteria_text}

Return a JSON object with exactly this shape, nothing else:

{{
  "scores": [
    {{"criterion_id": "naming_clarity", "score": <1-5>, "reasoning": "<one sentence>"}},
    {{"criterion_id": "readability_structure", "score": <1-5>, "reasoning": "<one sentence>"}},
    {{"criterion_id": "architectural_fit", "score": <1-5>, "reasoning": "<one sentence>"}},
    {{"criterion_id": "documentation_quality", "score": <1-5>, "reasoning": "<one sentence>"}},
    {{"criterion_id": "error_handling", "score": <1-5>, "reasoning": "<one sentence>"}},
    {{"criterion_id": "testability", "score": <1-5>, "reasoning": "<one sentence>"}}
  ],
  "summary": "<2-3 sentence overall assessment>"
}}

No markdown code fences. No prose before or after. Just the JSON."""


def score_file(file_path: str, rubric: dict) -> CodeScore:
    """Score a single Python file using Gemini Flash."""
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY in .env")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    code = Path(file_path).read_text()

    # Check veto rules first
    veto_flags = check_veto_rules(code, rubric)

    # Build prompt and score
    system_prompt = build_judge_prompt(rubric)
    user_prompt = f"Score this Python file:\n\nFile: {file_path}\n\n```python\n{code}\n```"

    response = model.generate_content(
        f"{system_prompt}\n\n{user_prompt}",
        generation_config={"temperature": 0},
    )

    # Parse response
    raw = response.text.strip()
    if raw.startswith("```"):
        import re
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    data = json.loads(raw)

    # Build weight map from rubric
    weight_map = {c["id"]: c.get("weight", 1.0) for c in rubric["criteria"]}

    criteria = []
    name_map = {c["id"]: c["name"] for c in rubric["criteria"]}
    for s in data["scores"]:
        criteria.append(CriterionScore(
            criterion_id=s["criterion_id"],
            criterion_name=name_map.get(s["criterion_id"], s["criterion_id"]),
            score=s["score"],
            reasoning=s["reasoning"],
            weight=weight_map.get(s["criterion_id"], 1.0),
        ))

    return CodeScore(
        file_path=file_path,
        criteria=criteria,
        veto_flags=veto_flags,
        summary=data.get("summary", ""),
    )


def print_score(score: CodeScore):
    """Print a formatted score report for a single file."""
    print(f"\n{'='*60}")
    print(f"  {score.file_path}")
    print(f"{'='*60}")
    print(f"  Weighted: {score.total_weighted():.1f}/{score.max_weighted():.1f}")
    print(f"  Unweighted: {score.total_unweighted()}/30")
    print()

    for c in score.criteria:
        bar = "█" * c.score + "░" * (5 - c.score)
        weight_str = f" (×{c.weight})" if c.weight != 1.0 else ""
        print(f"  {bar} {c.score}/5  {c.criterion_name}{weight_str}")
        print(f"         {c.reasoning}")

    if score.veto_flags:
        print()
        for flag in score.veto_flags:
            print(f"  ⚠️  {flag}")

    print()
    print(f"  {score.summary}")
    print()


def main():
    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning)

    parser = argparse.ArgumentParser(description="Score Python code quality against a calibrated rubric")
    parser.add_argument("paths", nargs="+", help="Python files or directories to score")
    parser.add_argument("--summary", action="store_true", help="show summary table only")
    parser.add_argument("--json", action="store_true", help="output raw JSON")
    args = parser.parse_args()

    # Collect files
    files = []
    for p in args.paths:
        path = Path(p)
        if path.is_file() and path.suffix == ".py":
            files.append(str(path))
        elif path.is_dir():
            files.extend(str(f) for f in sorted(path.rglob("*.py"))
                        if "__pycache__" not in str(f) and "__init__" not in str(f))

    if not files:
        print("No Python files found.")
        return 1

    rubric = load_rubric()
    scores: list[CodeScore] = []

    for i, f in enumerate(files):
        print(f"[{i+1}/{len(files)}] scoring {f}...", end=" ", flush=True)
        try:
            score = score_file(f, rubric)
            scores.append(score)
            print(f"{score.total_weighted():.1f}/{score.max_weighted():.1f}")
        except Exception as e:
            print(f"ERROR: {e}")

    if args.json:
        output = []
        for s in scores:
            output.append({
                "file": s.file_path,
                "weighted": s.total_weighted(),
                "unweighted": s.total_unweighted(),
                "criteria": {c.criterion_id: {"score": c.score, "reasoning": c.reasoning}
                            for c in s.criteria},
                "veto_flags": s.veto_flags,
                "summary": s.summary,
            })
        print(json.dumps(output, indent=2))
        return 0

    if args.summary and len(scores) > 1:
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"{'File':<45} {'Score':<10} {'Max':<8}")
        print("-" * 63)
        for s in sorted(scores, key=lambda x: -x.total_weighted()):
            name = Path(s.file_path).name
            print(f"  {name:<43} {s.total_weighted():<10.1f} {s.max_weighted():.1f}")
        avg = sum(s.total_weighted() for s in scores) / len(scores)
        max_possible = scores[0].max_weighted() if scores else 0
        print("-" * 63)
        print(f"  {'MEAN':<43} {avg:<10.1f} {max_possible:.1f}")
        return 0

    for score in scores:
        print_score(score)

    if len(scores) > 1:
        avg = sum(s.total_weighted() for s in scores) / len(scores)
        print(f"Mean weighted score across {len(scores)} files: {avg:.1f}/{scores[0].max_weighted():.1f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
