"""PostgreSQL connection pool using psycopg3."""

import os
from contextlib import contextmanager
from typing import Generator

from psycopg_pool import ConnectionPool
from psycopg import Connection
from dotenv import load_dotenv

load_dotenv()

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Get or create the connection pool singleton."""
    global _pool
    if _pool is None:
        password = os.environ["POSTGRES_PASSWORD"]
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        conninfo = (
            f"host={host} port={port} dbname=explodable "
            f"user=explodable password={password}"
        )
        _pool = ConnectionPool(
            conninfo=conninfo,
            min_size=2,
            max_size=10,
            open=True,
        )
    return _pool


@contextmanager
def get_connection() -> Generator[Connection, None, None]:
    """Get a connection from the pool."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
