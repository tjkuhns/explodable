"""Drift monitoring — weekly benchmark suite for agent drift detection.

Reads config/benchmark_prompts.md for the five prompts.
Runs each against the research pipeline (planner + researchers only — not full graph).
Scores each dimension per rubric via LLM.
Stores results in benchmark_runs table.
First successful run records as baseline.
Subsequent runs compare to baseline, alert if >15% single prompt or >10% overall.
Alerts written to operator_alerts table.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

import structlog
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from langchain_anthropic import ChatAnthropic

from src.kb.connection import get_connection
from src.research_pipeline.planner import plan_research
from src.research_pipeline.researcher import research_task

logger = structlog.get_logger()

_BENCHMARK_PATH = Path(__file__).parent.parent.parent / "config" / "benchmark_prompts.md"

# Thresholds from spec
SINGLE_PROMPT_DEVIATION_THRESHOLD = 0.15
OVERALL_DEVIATION_THRESHOLD = 0.10


# ── Prompt parsing ──


def _parse_benchmark_prompts() -> list[dict]:
    """Parse benchmark_prompts.md into structured prompt dicts."""
    if not _BENCHMARK_PATH.exists():
        raise FileNotFoundError(f"Benchmark prompts not found at {_BENCHMARK_PATH}")

    text = _BENCHMARK_PATH.read_text()
    prompts = []

    # Split by ## Prompt N: sections
    sections = re.split(r"## Prompt (\d+):", text)
    # sections[0] is header, then alternating: number, content
    for i in range(1, len(sections), 2):
        prompt_num = int(sections[i].strip())
        content = sections[i + 1] if i + 1 < len(sections) else ""

        # Extract input
        input_match = re.search(r"\*\*Input:\*\*\s*```\s*(.*?)```", content, re.DOTALL)
        input_text = input_match.group(1).strip() if input_match else ""

        # Extract scoring dimensions
        dims_match = re.search(
            r"\*\*Scoring dimensions:\*\*\s*(.*?)(?=\*\*Drift signal|\Z)",
            content, re.DOTALL
        )
        dimensions_text = dims_match.group(1).strip() if dims_match else ""

        # Parse dimensions: "- Name (0-25): Description"
        dimensions = []
        for line in dimensions_text.split("\n"):
            dim_match = re.match(r"- (.+?) \((\d+)–(\d+)\): (.+)", line.strip())
            if dim_match:
                dimensions.append({
                    "name": dim_match.group(1).strip(),
                    "min_score": int(dim_match.group(2)),
                    "max_score": int(dim_match.group(3)),
                    "description": dim_match.group(4).strip(),
                })

        # Extract expected output characteristics
        expected_match = re.search(
            r"\*\*Expected output characteristics:\*\*\s*(.*?)(?=\*\*Scoring dimensions|\Z)",
            content, re.DOTALL
        )
        expected = expected_match.group(1).strip() if expected_match else ""

        prompts.append({
            "number": prompt_num,
            "input": input_text,
            "dimensions": dimensions,
            "expected": expected,
        })

    return prompts


# ── Scoring ──


class PromptScore(BaseModel):
    """LLM-evaluated score for a single benchmark prompt."""
    dimension_scores: dict[str, int] = Field(description="Score per dimension name")
    total: int = Field(description="Total score 0-100")
    reasoning: str


def _run_benchmark_prompt(prompt_input: str) -> str:
    """Run a benchmark prompt through the research pipeline (planner + researchers).

    Uses planner and researchers directly — not the full graph — to avoid HITL.
    """
    plan = plan_research(prompt_input)
    results = []
    for task in plan.tasks[:3]:  # Cap at 3 tasks for benchmarks
        try:
            result = research_task(task)
            results.append({
                "task_id": result.task_id,
                "claim": result.claim,
                "elaboration": result.elaboration,
                "confidence_score": result.confidence_score,
                "confidence_basis": result.confidence_basis,
                "domain": result.domain,  # ResearchResult.domain — in-memory pipeline field, not DB column
                "sources": [s.model_dump() for s in result.sources],
            })
        except Exception as e:
            results.append({"task_id": task.task_id, "error": str(e)})

    return json.dumps({
        "topic": plan.topic,
        "root_anxiety_hints": plan.root_anxiety_hints,
        "results": results,
    }, indent=2)


def _score_prompt_output(
    output: str,
    dimensions: list[dict],
    expected: str,
) -> PromptScore:
    """Score a benchmark prompt's output against its rubric via LLM."""
    dims_text = "\n".join(
        f"- {d['name']} (0–{d['max_score']}): {d['description']}"
        for d in dimensions
    )

    from src.shared.constants import ANTHROPIC_MODEL
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.0,
        max_tokens=1000,
        max_retries=5,
    ).with_structured_output(PromptScore)

    result = llm.invoke([
        {
            "role": "system",
            "content": (
                "You are scoring research pipeline output against a benchmark rubric.\n"
                "Score each dimension independently. Total is the sum of all dimensions.\n\n"
                f"SCORING DIMENSIONS:\n{dims_text}\n\n"
                f"EXPECTED OUTPUT CHARACTERISTICS:\n{expected}"
            ),
        },
        {
            "role": "user",
            "content": f"Score this research pipeline output:\n\n{output}",
        },
    ])

    return result


# ── Database operations ──


def _ensure_benchmark_tables(conn) -> None:
    """Auto-create benchmark_runs and operator_alerts tables if they don't exist."""
    migration_path = Path(__file__).parent.parent.parent / "scripts" / "migrate_benchmark_tables.sql"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'benchmark_runs')"
        )
        has_benchmark = cur.fetchone()[0]
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'operator_alerts')"
        )
        has_alerts = cur.fetchone()[0]

    if has_benchmark and has_alerts:
        return

    logger.info("drift_monitor.running_migration", tables_missing=True)
    sql = migration_path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("drift_monitor.migration_complete")


def _get_baseline(conn) -> dict | None:
    """Get the baseline benchmark run."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM benchmark_runs WHERE is_baseline = TRUE ORDER BY run_date DESC LIMIT 1"
        )
        return cur.fetchone()


def _save_run(
    conn,
    scores: list[float],
    overall: float,
    deviation: float | None,
    is_baseline: bool,
    alert_triggered: bool,
    raw_outputs: dict,
) -> UUID:
    """Save a benchmark run to the database."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO benchmark_runs (
                is_baseline, prompt_1_score, prompt_2_score, prompt_3_score,
                prompt_4_score, prompt_5_score, overall_score,
                deviation_from_baseline, alert_triggered, raw_outputs
            ) VALUES (
                %(is_baseline)s, %(p1)s, %(p2)s, %(p3)s, %(p4)s, %(p5)s,
                %(overall)s, %(deviation)s, %(alert)s, %(raw)s
            ) RETURNING id
            """,
            {
                "is_baseline": is_baseline,
                "p1": scores[0] if len(scores) > 0 else None,
                "p2": scores[1] if len(scores) > 1 else None,
                "p3": scores[2] if len(scores) > 2 else None,
                "p4": scores[3] if len(scores) > 3 else None,
                "p5": scores[4] if len(scores) > 4 else None,
                "overall": overall,
                "deviation": deviation,
                "alert": alert_triggered,
                "raw": json.dumps(raw_outputs),
            },
        )
        row = cur.fetchone()
        conn.commit()
        return row["id"]


def _create_alert(conn, alert_type: str, severity: str, message: str) -> None:
    """Write an alert to the operator_alerts table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operator_alerts (alert_type, severity, message)
            VALUES (%s, %s, %s)
            """,
            (alert_type, severity, message),
        )
        conn.commit()

    logger.warning("drift_alert.created", alert_type=alert_type, severity=severity, message=message)


# ── Main entry point ──


def run_benchmarks() -> dict:
    """Run the full benchmark suite. Called by Celery task on Sunday 03:00 ET.

    1. Parse benchmark prompts
    2. Run each through the research pipeline
    3. Score each output against its rubric
    4. Compare to baseline (or record baseline on first run)
    5. Alert if deviation exceeds thresholds

    Returns dict with scores, deviation, and alert status.
    """
    # Ensure benchmark tables exist before proceeding
    with get_connection() as conn:
        _ensure_benchmark_tables(conn)

    prompts = _parse_benchmark_prompts()
    logger.info("benchmarks.started", prompt_count=len(prompts))

    scores = []
    raw_outputs = {}

    for prompt in prompts:
        num = prompt["number"]
        logger.info("benchmarks.running_prompt", prompt_number=num)

        try:
            output = _run_benchmark_prompt(prompt["input"])
            score_result = _score_prompt_output(
                output, prompt["dimensions"], prompt["expected"]
            )
            # Normalize to 0-100
            total = min(100, max(0, score_result.total))
            scores.append(total)
            raw_outputs[f"prompt_{num}"] = {
                "score": total,
                "dimensions": score_result.dimension_scores,
                "reasoning": score_result.reasoning,
                "output_preview": output[:2000],
            }
            logger.info("benchmarks.prompt_scored", prompt_number=num, score=total)

        except Exception as e:
            logger.error("benchmarks.prompt_failed", prompt_number=num, error=str(e))
            scores.append(0.0)
            raw_outputs[f"prompt_{num}"] = {"error": str(e)}

    overall = sum(scores) / len(scores) if scores else 0.0

    # Compare to baseline and store
    with get_connection() as conn:
        baseline = _get_baseline(conn)

        if baseline is None:
            # First run — record as baseline
            run_id = _save_run(
                conn, scores, overall,
                deviation=None, is_baseline=True,
                alert_triggered=False, raw_outputs=raw_outputs,
            )
            logger.info("benchmarks.baseline_recorded", run_id=str(run_id), overall=overall)
            return {
                "status": "baseline_recorded",
                "run_id": str(run_id),
                "scores": scores,
                "overall_score": overall,
                "is_baseline": True,
                "alert_triggered": False,
            }

        # Compare to baseline
        baseline_scores = [
            baseline.get(f"prompt_{i}_score", 0) or 0
            for i in range(1, 6)
        ]
        baseline_overall = baseline.get("overall_score", 0) or 0

        # Check deviations
        alert_triggered = False
        alert_messages = []

        overall_deviation = abs(overall - baseline_overall) / baseline_overall if baseline_overall > 0 else 0
        if overall_deviation > OVERALL_DEVIATION_THRESHOLD:
            alert_triggered = True
            alert_messages.append(
                f"Overall drift: {overall:.1f} vs baseline {baseline_overall:.1f} "
                f"({overall_deviation:.1%} deviation, threshold {OVERALL_DEVIATION_THRESHOLD:.0%})"
            )

        for i in range(len(scores)):
            if i < len(baseline_scores) and baseline_scores[i] > 0:
                dev = abs(scores[i] - baseline_scores[i]) / baseline_scores[i]
                if dev > SINGLE_PROMPT_DEVIATION_THRESHOLD:
                    alert_triggered = True
                    alert_messages.append(
                        f"Prompt {i+1} drift: {scores[i]:.1f} vs baseline {baseline_scores[i]:.1f} "
                        f"({dev:.1%} deviation, threshold {SINGLE_PROMPT_DEVIATION_THRESHOLD:.0%})"
                    )

        # Save run
        run_id = _save_run(
            conn, scores, overall,
            deviation=overall_deviation, is_baseline=False,
            alert_triggered=alert_triggered, raw_outputs=raw_outputs,
        )

        # Create alerts if needed
        if alert_triggered:
            severity = "critical" if overall_deviation > 0.20 else "warning"
            message = "Agent drift detected:\n" + "\n".join(alert_messages)
            _create_alert(conn, "agent_drift", severity, message)

        logger.info(
            "benchmarks.completed",
            run_id=str(run_id),
            overall=overall,
            deviation=overall_deviation,
            alert_triggered=alert_triggered,
        )

    return {
        "status": "completed",
        "run_id": str(run_id),
        "scores": scores,
        "overall_score": overall,
        "baseline_overall": baseline_overall,
        "deviation": overall_deviation,
        "is_baseline": False,
        "alert_triggered": alert_triggered,
        "alert_messages": alert_messages,
    }


if __name__ == "__main__":
    import sys
    import json as _json

    if "--run-now" in sys.argv:
        result = run_benchmarks()
        print(_json.dumps(result, indent=2))
    else:
        print("Usage: python -m src.shared.drift_monitor --run-now")
        sys.exit(1)
