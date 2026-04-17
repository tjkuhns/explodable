-- Migration 002: Add queries table for retrieval telemetry.
--
-- Context: append-only log of every KB retrieval (what was searched, what was
-- returned, by which pipeline/session). Enables product iteration, drift
-- monitoring, and future self-serve product analytics.
--
-- See: docs/explodable_v1_build_spec.md and docs/taxonomy.md for context.

BEGIN;

CREATE TABLE queries (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- What was asked
    query_text                  TEXT NOT NULL,
    query_embedding             vector(768),

    -- Filters applied at retrieval
    root_anxiety_filter         root_anxiety[],
    academic_discipline_filter  TEXT,
    cultural_domains_filter     TEXT[],
    status_filter               finding_status,
    min_confidence              FLOAT,

    -- What came back
    finding_ids_returned        UUID[] NOT NULL,
    similarity_scores           FLOAT[],
    relationship_types_present  relationship_type[],
    result_count                INTEGER NOT NULL,

    -- Context
    pipeline_source             TEXT NOT NULL,
    session_id                  UUID,
    brand                       TEXT,
    operator_id                 TEXT,

    -- Timing
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_ms                 INTEGER
);

CREATE INDEX queries_created_at ON queries (created_at DESC);
CREATE INDEX queries_pipeline_source ON queries (pipeline_source);
CREATE INDEX queries_session_id ON queries (session_id) WHERE session_id IS NOT NULL;
CREATE INDEX queries_result_count ON queries (result_count);

-- HNSW index on query embedding for semantic search across the query log itself
CREATE INDEX queries_embedding_hnsw
    ON queries USING hnsw (query_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

COMMIT;
