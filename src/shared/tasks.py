"""Celery tasks for the content pipeline — operator-triggered only.

Task functions remain callable via Celery, but Celery Beat schedule is
intentionally empty. No autonomous API calls. Every pipeline run is
explicitly triggered by operator action.

Manual trigger:
- Content pipeline: POST /api/generate/content (src/operator_ui/api/generate.py)

Resume trigger:
- Content pipeline HITL gates: POST /api/pipeline/resume/{thread_id}
  (src/operator_ui/api/pipeline.py)

On-demand drift monitoring:
- python -m src.shared.drift_monitor --run-now
  (or invoke run_benchmark_suite via `celery call` if needed)

Retired 2026-04-14 (retirement branch):
- run_research_pipeline — research pipeline graph is deprecated; no longer
  exposed as a Celery task. The src/research_pipeline/ package remains
  importable as a dormant dependency of drift_monitor.py.
- run_performance_feedback — was a stub; performance feedback loop is
  deferred until a newsletter platform is live.

Previously scheduled entries (all removed 2026-04-13 Phase 0):
- research-pipeline-daily
- content-pipeline-tuesday-boulder, content-pipeline-thursday-explodable
- performance-feedback-monday
- drift-monitoring-sunday

To re-enable autonomous scheduling, add entries to app.conf.beat_schedule —
but first reconcile with docs/gtm_notes.md which commits to operator-driven mode.
"""

import structlog

from src.shared.celery_app import app

logger = structlog.get_logger()


# ── Celery Beat schedule — intentionally empty ──

app.conf.beat_schedule = {}

app.conf.beat_schedule_filename = "logs/celerybeat-schedule"


# ── Task definitions ──


@app.task(bind=True, name="src.shared.tasks.run_content_pipeline", rate_limit="10/m")
def run_content_pipeline(
    self,
    topic: str | None = None,
    brand: str = "the_boulder",
    output_type: str = "newsletter",
    client_context: str = "",
):
    """Run the content pipeline. Queued on 'content' (normal priority).

    Args:
        topic: Topic / research question. Required for all output types.
        brand: 'the_boulder' or 'explodable'.
        output_type: 'newsletter' (default) or 'brief'. Briefs are
            Explodable-only and require client_context.
        client_context: Specific client situation the brief addresses.
            Required for briefs, ignored for newsletters.

    Pipeline runs to HITL gate 2 (outline) and waits for operator review.
    """
    logger.info(
        "content_pipeline.started",
        topic=topic,
        brand=brand,
        output_type=output_type,
        task_id=self.request.id,
    )

    if not topic:
        topic = _load_content_topic()

    try:
        from src.content_pipeline.graph import compile_content_graph

        with _CheckpointerContext() as checkpointer:
            pipeline = compile_content_graph(checkpointer=checkpointer)

            thread_id = f"content-{self.request.id}"
            config = {"configurable": {"thread_id": thread_id}}

            initial_state = {
                "topic": topic,
                "brand": brand,
                "output_type": output_type,
                "client_context": client_context,
            }

            for event in pipeline.stream(
                initial_state,
                config=config,
                stream_mode="updates",
            ):
                for node, update in event.items():
                    logger.info("content_pipeline.node_complete", node=node, task_id=self.request.id)

            state = pipeline.get_state(config)
            logger.info(
                "content_pipeline.paused_at_hitl",
                thread_id=thread_id,
                next_node=state.next,
                task_id=self.request.id,
            )

            return {
                "status": "awaiting_review",
                "thread_id": thread_id,
                "paused_at": list(state.next) if state.next else [],
            }

    except Exception as e:
        logger.error("content_pipeline.failed", error=str(e), task_id=self.request.id)
        raise


@app.task(bind=True, name="src.shared.tasks.resume_content_pipeline", rate_limit="20/m")
def resume_content_pipeline(self, thread_id: str, decision: dict):
    """Resume a paused content pipeline thread with an operator decision.

    Loads the pipeline with the persistent checkpointer, uses LangGraph's
    Command(resume=...) to continue from the interrupt, and runs forward
    until the next interrupt or completion.

    Args:
        thread_id: The thread_id the paused run is indexed under (e.g.
            'content-<task_id>' from the initial run).
        decision: Operator's decision payload. Shape depends on which gate:
            - outline gate: {action: 'approve'|'reject'|'edit', ...edit fields}
            - draft gate: {action: 'approve'|'reject'|'edit', ...edit fields}
    """
    logger.info(
        "content_pipeline.resume_started",
        thread_id=thread_id,
        action=decision.get("action"),
        task_id=self.request.id,
    )

    try:
        from src.content_pipeline.graph import compile_content_graph
        from langgraph.types import Command

        with _CheckpointerContext() as checkpointer:
            pipeline = compile_content_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}

            # Resume the paused graph with the operator's decision.
            # LangGraph's Command(resume=...) replays from the interrupt and
            # continues forward until the next interrupt or completion.
            for event in pipeline.stream(
                Command(resume=decision),
                config=config,
                stream_mode="updates",
            ):
                for node, update in event.items():
                    logger.info(
                        "content_pipeline.resume.node_complete",
                        node=node,
                        thread_id=thread_id,
                        task_id=self.request.id,
                    )

            state = pipeline.get_state(config)
            paused_at = list(state.next) if state.next else []
            logger.info(
                "content_pipeline.resume_complete",
                thread_id=thread_id,
                paused_at=paused_at,
                task_id=self.request.id,
            )

            return {
                "status": "complete" if not paused_at else "awaiting_review",
                "thread_id": thread_id,
                "paused_at": paused_at,
            }

    except Exception as e:
        logger.error(
            "content_pipeline.resume_failed",
            thread_id=thread_id,
            error=str(e),
            task_id=self.request.id,
        )
        raise


@app.task(bind=True, name="src.shared.tasks.run_benchmark_suite")
def run_benchmark_suite(self):
    """Weekly drift monitoring: run benchmark prompts, compare to baseline.

    Queued on 'monitoring' (low priority). Sunday 03:00 ET.
    Implemented in step 3d (drift_monitor.py).
    """
    logger.info("benchmark_suite.started", task_id=self.request.id)

    try:
        from src.shared.drift_monitor import run_benchmarks

        result = run_benchmarks()
        logger.info(
            "benchmark_suite.completed",
            task_id=self.request.id,
            overall_score=result.get("overall_score"),
            alert_triggered=result.get("alert_triggered", False),
        )
        return result

    except Exception as e:
        logger.error("benchmark_suite.failed", error=str(e), task_id=self.request.id)
        raise


# ── Helpers ──


class _CheckpointerContext:
    """Context manager that creates a PostgresSaver and closes its connection on exit."""

    def __init__(self):
        self._conn = None
        self.checkpointer = None

    def __enter__(self):
        import os
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver

        password = os.environ["POSTGRES_PASSWORD"]
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        conn_string = f"postgresql://explodable:{password}@{host}:{port}/explodable"

        self._conn = psycopg.connect(conn_string, autocommit=True)
        self.checkpointer = PostgresSaver(self._conn)
        self.checkpointer.setup()
        return self.checkpointer

    def __exit__(self, *exc):
        if self._conn and not self._conn.closed:
            self._conn.close()
        return False


def _load_content_topic() -> str:
    """Load a content topic. In production, driven by KB content gaps and editorial calendar."""
    return "What patterns in human behavior connect politics, consumer culture, and technology?"
