"""Celery application configuration.

Broker: Redis (CELERY_BROKER_URL)
Result backend: Redis (CELERY_RESULT_BACKEND)
Three queues: research (high priority), content (normal), monitoring (low)
Per-domain rate limiting: rate_limit='10/m' on web fetch tasks
Retry policy: exponential backoff with jitter, max 3 retries
"""

import os

from dotenv import load_dotenv

load_dotenv()

from celery import Celery
from celery.signals import worker_init
from kombu import Exchange, Queue
from psycopg import OperationalError as PsycopgOperationalError
from psycopg_pool import PoolTimeout

# ── App ──

app = Celery(
    "explodable",
    include=["src.shared.tasks"],  # auto-import task definitions on worker startup
)

app.config_from_object({
    # Broker & backend
    "broker_url": os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    "result_backend": os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),

    # Serialization
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],

    # Timezone
    "timezone": os.environ.get("OPERATOR_TIMEZONE", "America/New_York"),
    "enable_utc": True,

    # Queues — simplified to single content queue (2026-04-14 retirement)
    "task_queues": (
        Queue("content", Exchange("content"), routing_key="content"),
    ),
    "task_default_queue": "content",
    "task_default_exchange": "content",
    "task_default_routing_key": "content",

    # Retry policy — exponential backoff with jitter, max 3 retries
    # Only retry transient errors (network, connection, timeout).
    # Non-transient errors (ValueError, TypeError, ValidationError) fail immediately.
    "task_default_retry_delay": 60,
    "task_annotations": {
        "*": {
            "autoretry_for": (
                ConnectionError,
                TimeoutError,
                OSError,
                PsycopgOperationalError,
                PoolTimeout,
            ),
            "max_retries": 3,
            "retry_backoff": True,
            "retry_backoff_max": 600,
            "retry_jitter": True,
        },
    },

    # Rate limiting
    "worker_concurrency": 4,
    "task_acks_late": True,
    "worker_prefetch_multiplier": 1,

    # Result expiry
    "result_expires": 86400,  # 24 hours
})

# ── Task routing ──

@worker_init.connect
def on_worker_init(**kwargs):
    """Validate environment before the worker starts accepting tasks."""
    from src.shared.startup import validate_env
    validate_env()


app.conf.task_routes = {
    "src.shared.tasks.run_content_pipeline": {"queue": "content"},
    "src.shared.tasks.resume_content_pipeline": {"queue": "content"},
    "src.shared.tasks.run_benchmark_suite": {"queue": "content"},
}
