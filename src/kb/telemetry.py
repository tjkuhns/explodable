"""Retrieval telemetry — append-only log of every KB query.

Call `log_query` after any retrieval. Non-blocking (errors are logged and swallowed)
so telemetry failures never break the pipeline that called it.
"""

from typing import Iterable, Sequence
from uuid import UUID

import structlog
from psycopg import Connection

log = structlog.get_logger()


def log_query(
    conn: Connection,
    *,
    query_text: str,
    pipeline_source: str,
    finding_ids_returned: Sequence[str | UUID],
    query_embedding: list[float] | None = None,
    root_anxiety_filter: list[str] | None = None,
    academic_discipline_filter: str | None = None,
    cultural_domains_filter: list[str] | None = None,
    status_filter: str | None = None,
    min_confidence: float | None = None,
    similarity_scores: list[float] | None = None,
    relationship_types_present: list[str] | None = None,
    session_id: str | UUID | None = None,
    brand: str | None = None,
    operator_id: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Log a query to the queries table. Non-blocking — failures are swallowed.

    Args:
        conn: Active psycopg Connection.
        query_text: Raw query string.
        pipeline_source: Which system fired the query (content_pipeline,
            research_pipeline, manual, drift_monitor, product).
        finding_ids_returned: UUIDs returned by the retrieval, in order.
        query_embedding: Optional 768-dim query vector.
        root_anxiety_filter: Which root_anxiety values were restricted to.
        academic_discipline_filter: Discipline filter, if any.
        cultural_domains_filter: Cultural domain filter array, if any.
        status_filter: finding_status filter (usually 'active').
        min_confidence: Confidence floor applied.
        similarity_scores: Parallel array to finding_ids_returned.
        relationship_types_present: Which relationship types existed among the
            returned findings. Caller computes this.
        session_id: UUID grouping multi-query sessions (e.g., content pipeline's
            three query variants share a session_id).
        brand: Which brand the pipeline was generating for (the_boulder, explodable).
        operator_id: Reserved for self-serve product phase.
        duration_ms: End-to-end retrieval latency.
    """
    try:
        result_ids = [str(fid) for fid in finding_ids_returned]
        result_count = len(result_ids)

        conn.execute(
            """
            INSERT INTO queries (
                query_text, query_embedding,
                root_anxiety_filter, academic_discipline_filter,
                cultural_domains_filter, status_filter, min_confidence,
                finding_ids_returned, similarity_scores, relationship_types_present,
                result_count, pipeline_source, session_id, brand, operator_id,
                duration_ms
            ) VALUES (
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s
            )
            """,
            (
                query_text,
                query_embedding,
                root_anxiety_filter,
                academic_discipline_filter,
                cultural_domains_filter,
                status_filter,
                min_confidence,
                result_ids,
                similarity_scores,
                relationship_types_present,
                result_count,
                pipeline_source,
                str(session_id) if session_id else None,
                brand,
                operator_id,
                duration_ms,
            ),
        )
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log.warning(
            "query_telemetry.log_failed",
            error=str(e),
            pipeline_source=pipeline_source,
        )


def compute_relationship_types_present(
    conn: Connection,
    finding_ids: Iterable[str | UUID],
) -> list[str]:
    """Return the distinct relationship types among the given finding IDs.

    Helper for callers that want to populate `relationship_types_present`.
    """
    ids = [str(fid) for fid in finding_ids]
    if not ids:
        return []
    try:
        cur = conn.execute(
            """
            SELECT DISTINCT relationship::text
            FROM finding_relationships
            WHERE from_finding_id = ANY(%s::uuid[])
               OR to_finding_id = ANY(%s::uuid[])
            """,
            (ids, ids),
        )
        return [row[0] for row in cur.fetchall()]
    except Exception as e:
        log.warning("query_telemetry.relationship_scan_failed", error=str(e))
        return []
