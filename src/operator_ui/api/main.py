"""FastAPI application — Explodable operator interface backend.

Runs on localhost:8000. Minimal surface after the 2026-04-14 retirement
collapse: just the pipeline dispatch and state-read endpoints needed for
chat-driven operation. Everything else (KB browser, findings CRUD, drafts
CRUD, queue, WebSocket, research upload, usage reporting) was retired —
the operator model is now Claude Code driving the KB directly, not a
human clicking through browser screens.

Endpoints:
    GET  /api/health
    POST /api/generate/content       → queue content pipeline run
    GET  /api/pipeline/state/{id}    → read LangGraph checkpoint state
    POST /api/pipeline/resume/{id}   → resume at HITL gate with decision
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.shared.logging import setup_logging
from src.shared.startup import validate_env

setup_logging()
validate_env()

from src.operator_ui.api.generate import router as generate_router
from src.operator_ui.api.pipeline import router as pipeline_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    yield
    from src.kb.connection import close_pool
    close_pool()


app = FastAPI(
    title="Explodable Operator API",
    version="2.0.0",  # 2.0 = post-retirement, chat-driven operator model
    lifespan=lifespan,
)

app.include_router(generate_router)
app.include_router(pipeline_router)


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}
