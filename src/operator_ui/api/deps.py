"""Shared dependencies for FastAPI routes."""

from contextlib import contextmanager
from typing import Generator

from psycopg import Connection

from src.kb.connection import get_connection as _get_connection
from src.kb.crud import KBStore


def get_db() -> Generator[Connection, None, None]:
    """FastAPI dependency: yields a DB connection from the pool."""
    with _get_connection() as conn:
        yield conn


def get_store(conn: Connection) -> KBStore:
    """Create a KBStore from a connection."""
    return KBStore(conn)
