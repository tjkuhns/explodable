"""Pipeline router — state reads and HITL gate resume for content pipeline runs.

GET  /api/pipeline/state/{thread_id}   — current state of a pipeline thread
POST /api/pipeline/resume/{thread_id}  — resume a paused thread with a decision

The content pipeline uses LangGraph's interrupt() mechanism at HITL gates 2
(outline) and 2b (draft). These endpoints let the operator UI observe the
paused state and provide the decision needed to continue.

Phase 1c scope: in-session flow only. The operator kicks off a run from the
generator page, polls state until the pipeline pauses at a HITL gate, reviews
the payload inline, POSTs a decision, then continues polling until the next
gate or completion. Listing all paused threads across the system is deferred
to a later phase.

State shape returned by /state/{thread_id}:
  {
    status: "running" | "awaiting_outline_review" | "awaiting_draft_review" | "complete" | "error",
    thread_id: str,
    current_node: str | null,
    # When awaiting_outline_review:
    outline?: dict,
    findings_summary?: list,
    # When awaiting_draft_review:
    draft?: dict,
    bvcs_result?: dict,
    revision_count?: int,
    # When complete:
    published_path?: str,
    # When error:
    error?: str
  }
"""

import os
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

log = structlog.get_logger()


# ── Models ──


class ResumeRequest(BaseModel):
    """Operator decision for resuming a paused pipeline thread.

    action: 'approve' | 'reject' | 'edit'
    Additional fields are decision-specific:
    - 'approve': no additional fields required
    - 'reject': optional 'reason' string
    - 'edit': 'title'/'thesis'/'core_diagnosis' for outline edits,
              'newsletter_edits' for draft edits
    """

    action: str
    reason: str | None = None
    title: str | None = None
    thesis: str | None = None
    core_diagnosis: str | None = None
    newsletter_edits: str | None = None
    notes: str | None = None


# ── Checkpointer context ──


class _CheckpointerContext:
    """Context manager that creates a PostgresSaver for pipeline state access.

    Mirrors the implementation in src/shared/tasks.py so backend endpoints
    and Celery tasks share the same checkpoint backend.
    """

    def __init__(self):
        self._conn = None
        self.checkpointer = None

    def __enter__(self):
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver

        password = os.environ["POSTGRES_PASSWORD"]
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        conn_string = f"postgresql://explodable:{password}@{host}:{port}/explodable"

        self._conn = psycopg.connect(conn_string, autocommit=True)
        self.checkpointer = PostgresSaver(self._conn)
        return self.checkpointer

    def __exit__(self, *exc):
        if self._conn and not self._conn.closed:
            self._conn.close()
        return False


def _serialize_finding(sf) -> dict:
    """Serialize a ScoredFinding for JSON response."""
    f = sf.finding
    return {
        "id": str(f.id),
        "claim": f.claim,
        "elaboration": f.elaboration,
        "academic_discipline": f.academic_discipline,
        "confidence_score": f.confidence_score,
        "root_anxieties": [a.value if hasattr(a, "value") else str(a) for a in f.root_anxieties],
        "score": sf.score if hasattr(sf, "score") else None,
    }


def _serialize_outline(outline) -> dict:
    """Serialize a NewsletterOutline or BriefOutline for JSON response."""
    if outline is None:
        return None
    # Pydantic v2 model_dump handles nested models
    return outline.model_dump(mode="json")


def _serialize_draft(draft) -> dict:
    """Serialize a DraftResult for JSON response."""
    if draft is None:
        return None
    # Citations field added 2026-04-14 (Session 2 Citations API adoption).
    # Serialize the list of Citation objects as dicts so they cross the HTTP
    # boundary intact — earlier versions of this serializer dropped the field
    # silently, which made "0 citations" look like a generation failure.
    citations_raw = getattr(draft, "citations", None) or []
    citations = []
    for c in citations_raw:
        if hasattr(c, "model_dump"):
            citations.append(c.model_dump())
        elif isinstance(c, dict):
            citations.append(c)
    return {
        "newsletter": draft.newsletter,
        "x_post": draft.x_post,
        "x_thread": draft.x_thread,
        "linkedin": draft.linkedin,
        "substack_notes": draft.substack_notes,
        "citations": citations,
    }


def _serialize_bvcs(bvcs_result) -> dict:
    """Serialize a BVCSResult for JSON response."""
    if bvcs_result is None:
        return None
    return {
        "total_score": bvcs_result.total_score,
        "passed": bvcs_result.passed,
        "immediate_fail": bvcs_result.immediate_fail,
        "revision_notes": bvcs_result.revision_notes,
        "dimension_scores": {
            name: {
                "score": d.score,
                "max_score": d.max_score,
                "method": d.method,
                "notes": d.notes,
            }
            for name, d in bvcs_result.dimension_scores.items()
        },
    }


# ── State read ──


@router.get("/state/{thread_id}")
def get_pipeline_state(thread_id: str) -> dict[str, Any]:
    """Read the current state of a content pipeline thread.

    Returns a status-driven shape that the frontend can switch on:
    running / awaiting_outline_review / awaiting_draft_review / complete / error.

    Paused threads include the interrupt payload (outline or draft) so the
    operator UI can render it inline for review. Completed threads include
    the published path.
    """
    try:
        from src.content_pipeline.graph import compile_content_graph

        with _CheckpointerContext() as checkpointer:
            pipeline = compile_content_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}
            state = pipeline.get_state(config)
    except Exception as e:
        log.error("pipeline.state_read_failed", thread_id=thread_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read pipeline state: {type(e).__name__}: {e}",
        )

    # No checkpoint exists yet. This is normal for the first few seconds
    # after a task is queued — Celery has the task but no node has run and
    # written a checkpoint yet. Return a starting status so the frontend
    # keeps polling instead of bailing with a 404.
    if state is None or not state.values:
        log.debug(
            "pipeline.state.not_yet_checkpointed",
            thread_id=thread_id,
            state_is_none=state is None,
            has_values=bool(state and state.values),
        )
        return {
            "thread_id": thread_id,
            "status": "starting",
            "current_node": None,
            "note": (
                "Pipeline task queued. No checkpoint yet — either Celery"
                " hasn't picked up the task, or the first node is still"
                " executing. Keep polling; state will populate within"
                " a few seconds."
            ),
        }

    values = state.values
    next_nodes = list(state.next) if state.next else []

    # Extract common fields safely — values may be a dict from checkpointer
    def _get(key: str, default=None):
        if isinstance(values, dict):
            return values.get(key, default)
        return getattr(values, key, default)

    topic = _get("topic", "")
    brand = _get("brand", "the_boulder")
    output_type = _get("output_type", "newsletter")
    current_status = _get("status", "pending")
    published_path = _get("published_path", "")
    revision_count = _get("revision_count", 0)

    base = {
        "thread_id": thread_id,
        "topic": topic,
        "brand": brand,
        "output_type": output_type,
        "internal_status": current_status,
        "current_node": next_nodes[0] if next_nodes else None,
        "revision_count": revision_count,
    }

    # Not paused — either still running or done
    if not next_nodes:
        if published_path:
            return {
                **base,
                "status": "complete",
                "published_path": published_path,
                "draft": _serialize_draft(_get("draft")),
                "bvcs_result": _serialize_bvcs(_get("bvcs_result")),
                "outline": _serialize_outline(_get("outline")),
            }
        # No next nodes and no published path — either running or error
        return {**base, "status": "running"}

    # Paused — but we need to distinguish three cases:
    #   1. Actually at a HITL gate with an interrupt pending (review state)
    #   2. Paused before a node because the previous one errored (error state)
    #   3. Between nodes during normal execution (running state)
    #
    # The signal for (1) is state.tasks having non-empty interrupts. The signal
    # for (2) is state.tasks having a task with an error set. LangGraph's
    # state.next by itself is ambiguous — it just means "the next scheduled
    # node", not "paused at an interrupt in that node".
    current_node = next_nodes[0]

    # Check for task-level errors first. If any task has an error, the pipeline
    # failed and the checkpoint reflects the last successful state. Expose that
    # as a clean error status instead of pretending to be at a review gate.
    task_error = None
    has_pending_interrupt = False
    try:
        for task in (state.tasks or ()):
            if getattr(task, "error", None):
                task_error = str(task.error)
            interrupts = getattr(task, "interrupts", None) or ()
            if interrupts:
                has_pending_interrupt = True
    except Exception:
        pass

    if task_error is not None:
        return {
            **base,
            "status": "error",
            "error": task_error,
            "failed_before_node": current_node,
        }

    # Only treat as a HITL review if current_node is an exact match for one
    # of the interrupt nodes. Substring matching is unsafe because 'outline'
    # is a substring of 'outline_generator', 'draft' is a substring of
    # 'draft_generator', etc.
    if current_node == "hitl_gate_2_outline":
        outline = _get("outline")
        # If the outline is None at this point, the outline generator
        # errored before producing a value but LangGraph hasn't marked the
        # task with an error yet (or the error is from a downstream retry
        # budget exhaustion). Either way, there's nothing to review.
        if outline is None:
            return {
                **base,
                "status": "error",
                "error": (
                    "Pipeline reached the outline HITL gate but no outline"
                    " was produced. This usually means outline generation"
                    " failed after exhausting retries — check the Celery"
                    " worker logs for Anthropic API errors."
                ),
                "failed_before_node": current_node,
            }
        selected_findings = _get("selected_findings", []) or []
        findings_summary = []
        for i, sf in enumerate(selected_findings):
            try:
                findings_summary.append({
                    "index": i,
                    **_serialize_finding(sf),
                })
            except Exception:
                pass
        return {
            **base,
            "status": "awaiting_outline_review",
            "outline": _serialize_outline(outline),
            "findings_summary": findings_summary,
        }

    if current_node == "hitl_gate_2_draft":
        draft = _get("draft")
        if draft is None:
            return {
                **base,
                "status": "error",
                "error": (
                    "Pipeline reached the draft HITL gate but no draft was"
                    " produced. Draft generation or revision exhausted retries."
                    " Check the Celery worker logs."
                ),
                "failed_before_node": current_node,
            }
        return {
            **base,
            "status": "awaiting_draft_review",
            "draft": _serialize_draft(draft),
            "bvcs_result": _serialize_bvcs(_get("bvcs_result")),
            "outline": _serialize_outline(_get("outline")),
        }

    # Not at a known HITL gate. state.next points to some other node, which
    # means either (a) the pipeline is executing between nodes and we caught
    # it mid-flight, or (b) the previous node errored and the pipeline is
    # stuck before current_node. Without a task-level error we can't tell
    # cleanly, so report as running and let the frontend keep polling.
    return {
        **base,
        "status": "running",
        "paused_before": current_node,
    }


# ── Resume ──


@router.post("/resume/{thread_id}")
def resume_pipeline_run(thread_id: str, body: ResumeRequest) -> dict[str, Any]:
    """Resume a paused content pipeline thread with the operator's decision.

    Queues the resume as a Celery task so the FastAPI request returns
    immediately. The task runs the pipeline forward from the interrupt
    point until the next gate or completion. The operator polls
    /api/pipeline/state/{thread_id} to observe progress.
    """
    if body.action not in ("approve", "reject", "edit"):
        raise HTTPException(
            status_code=400,
            detail=f"action must be 'approve', 'reject', or 'edit', got '{body.action}'",
        )

    decision: dict[str, Any] = {"action": body.action}
    if body.reason:
        decision["reason"] = body.reason
    if body.title:
        decision["title"] = body.title
    if body.thesis:
        decision["thesis"] = body.thesis
    if body.core_diagnosis:
        decision["core_diagnosis"] = body.core_diagnosis
    if body.newsletter_edits:
        decision["newsletter_edits"] = body.newsletter_edits
    if body.notes:
        decision["notes"] = body.notes

    # Imported lazily so Celery broker connection isn't forced at import time
    from src.shared.tasks import resume_content_pipeline

    task = resume_content_pipeline.delay(thread_id=thread_id, decision=decision)
    log.info(
        "pipeline.resume_queued",
        thread_id=thread_id,
        action=body.action,
        task_id=task.id,
    )
    return {
        "task_id": task.id,
        "thread_id": thread_id,
        "status": "resume_queued",
        "decision": decision,
    }
