"""Embedding generation — pinned to locked model/version from shared/constants.

Model and dimensions are locked via EMBEDDING_MODEL_ID, EMBEDDING_MODEL_DIMS,
and EMBEDDING_MODEL_VERSION in src/shared/constants.py. Changing those values
requires a full KB reindex. See docs/RETIREMENT_PLAN.md for the post-launch
migration path to BGE-M3 or voyage-3-large.
"""

import os

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from src.shared.constants import (
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_DIMS,
    EMBEDDING_MODEL_VERSION,
)

_client: OpenAI | None = None

# Legacy names kept for any callers that import from this module
EMBEDDING_MODEL = EMBEDDING_MODEL_ID
EMBEDDING_DIMENSIONS = EMBEDDING_MODEL_DIMS


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding for the given text using the locked model config.

    Model and dimensions are pinned in src/shared/constants.py. Changing
    them requires re-embedding the entire KB.
    """
    client = _get_client()
    response = client.embeddings.create(
        input=text,
        model=EMBEDDING_MODEL_ID,
        dimensions=EMBEDDING_MODEL_DIMS,
    )
    return response.data[0].embedding


def get_embedding_version() -> str:
    """Return the locked embedding model version string for logging/telemetry."""
    return f"{EMBEDDING_MODEL_ID}@{EMBEDDING_MODEL_DIMS}d@{EMBEDDING_MODEL_VERSION}"
