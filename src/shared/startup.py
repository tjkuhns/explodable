"""Startup validation — checks required environment variables before anything runs.

Wire into FastAPI lifespan and Celery worker_init signal.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "EXA_API_KEY",
    "POSTGRES_PASSWORD",
]


def validate_env() -> None:
    """Check that all required environment variables are set.

    Raises RuntimeError with the name of every missing variable.
    """
    missing = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in .env or export before starting."
        )
