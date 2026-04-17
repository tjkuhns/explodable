"""Generate router — content pipeline dispatch endpoint.

Single endpoint: POST /api/generate/content — queue a content pipeline run.
Accepts topic, brand, output_type (newsletter, brief, or standalone_post),
and client_context (required for briefs). Returns task_id + thread_id.
Caller polls /api/pipeline/state/{thread_id} until HITL gate or completion.

The legacy /api/generate/brief wrapper was retired on 2026-04-14. Briefs
are now dispatched through /api/generate/content with output_type='brief'.
"""

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/generate", tags=["generate"])

log = structlog.get_logger()


class ContentRequest(BaseModel):
    """Unified content generation request across all output types."""

    topic: str = Field(
        ...,
        min_length=10,
        description=(
            "Topic / research question used for KB retrieval. Specific topics"
            " produce better content — generic queries retrieve incoherent"
            " finding sets. Minimum 10 characters."
        ),
    )
    brand: str = Field(
        default="the_boulder",
        description="'the_boulder' or 'explodable'",
    )
    output_type: str = Field(
        default="newsletter",
        description=(
            "'newsletter' (long-form essay, either brand), 'brief'"
            " (Explodable-only 5-section diagnostic deliverable), or"
            " 'standalone_post' (300-500 word LinkedIn post from one"
            " cross-domain seed finding, skips outline review)."
        ),
    )
    client_context: str | None = Field(
        default=None,
        description=(
            "Required for output_type='brief': the specific client situation"
            " the brief addresses (minimum 20 characters). Ignored for newsletters."
        ),
    )


class PipelineRunResponse(BaseModel):
    """Async response for a queued pipeline run."""

    task_id: str
    thread_id: str
    status: str
    topic: str
    brand: str
    output_type: str
    note: str


def _validate_content_request(body: ContentRequest) -> None:
    """Validate a ContentRequest. Raises HTTPException on failure."""
    if body.brand not in ("the_boulder", "explodable"):
        raise HTTPException(
            status_code=400,
            detail=f"brand must be 'the_boulder' or 'explodable', got '{body.brand}'",
        )

    if body.output_type not in ("newsletter", "brief", "standalone_post"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"output_type must be 'newsletter', 'brief', or"
                f" 'standalone_post', got '{body.output_type}'"
            ),
        )

    if body.output_type == "brief":
        if body.brand != "explodable":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Briefs are Explodable-only. The Boulder produces opinionated"
                    " cultural analysis, not diagnostic briefs. Use brand='explodable'"
                    " with output_type='brief'."
                ),
            )
        if not body.client_context or len(body.client_context.strip()) < 20:
            raise HTTPException(
                status_code=400,
                detail=(
                    "client_context is required for briefs (minimum 20 characters)."
                    " Describe the specific client situation the brief addresses."
                ),
            )


@router.post("/content", response_model=PipelineRunResponse)
def generate_content(body: ContentRequest) -> PipelineRunResponse:
    """Queue a content pipeline run for any brand / output type.

    The pipeline runs retrieval → selector → outline → HITL gate 2 (outline
    review) → draft → BVCS → HITL gate 2 (draft review) → publisher. Returns
    immediately with a task_id and thread_id. Poll /api/pipeline/state/{thread_id}
    to observe progress and reach HITL gates.
    """
    _validate_content_request(body)

    from src.shared.tasks import run_content_pipeline

    topic = body.topic.strip()
    task = run_content_pipeline.delay(
        topic=topic,
        brand=body.brand,
        output_type=body.output_type,
        client_context=(body.client_context or "").strip(),
    )

    log.info(
        "content_pipeline.manual_trigger_queued",
        task_id=task.id,
        topic=topic,
        brand=body.brand,
        output_type=body.output_type,
    )

    return PipelineRunResponse(
        task_id=task.id,
        thread_id=f"content-{task.id}",
        status="queued",
        topic=topic,
        brand=body.brand,
        output_type=body.output_type,
        note=(
            "Pipeline queued. It will run retrieval → selector → outline and pause"
            " at HITL gate 2 for outline review. After approval, it continues"
            " through draft generation → BVCS scoring → second HITL review →"
            " publisher. Poll /api/pipeline/state/{thread_id} for progress."
        ),
    )
