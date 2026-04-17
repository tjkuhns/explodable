"""Structured JSON logging with daily rotation.

Uses structlog for structured JSON output.
Logs to ~/explodable/logs/ with daily rotation.
Log level: INFO in production, DEBUG available via LOG_LEVEL env var.

Events logged:
  - Pipeline triggers (research, content)
  - Agent calls (planner, researcher, synthesizer, critic)
  - KB writes (findings, manifestations, relationships)
  - HITL interrupts (gate 1, gate 2)
  - BVCS scores
  - Celery task start/end/failure
"""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import structlog
from dotenv import load_dotenv

load_dotenv()

LOG_DIR = Path.home() / "explodable" / "logs"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def setup_logging() -> None:
    """Configure structlog with JSON output to file and console.

    Call once at application startup. Safe to call multiple times.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, LOG_LEVEL, logging.INFO)

    # File handler — daily rotation, 30 days retention
    file_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / "explodable.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)

    # Console handler — same level
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)

    # Configure stdlib logging root
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Clear existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger. Call setup_logging() first."""
    return structlog.get_logger(name)


# Auto-configure on import if not already done
setup_logging()
