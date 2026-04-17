-- CQRS read model materialization for the hybrid cognitive pipeline.
--
-- Creates materialized views and a version-tracking table so the pipeline
-- knows when read models are stale. Refresh is triggered by
-- scripts/compile_read_models.py or manually via REFRESH MATERIALIZED VIEW.
--
-- Per Report 4 (docs/research/hybrid_reports/04_cqrs_ai_knowledge.md):
-- Postgres materialized views win decisively at our scale (300-5000 findings)
-- over separate stores. "Choose Boring Technology."

-- Read Model 5: Cluster index (anxiety × domain matrix)
-- Groups findings by primary anxiety and cultural domain, with counts and
-- avg confidence per cell. Used by the topic router and vector retriever
-- to scope searches within the right cluster.

DROP MATERIALIZED VIEW IF EXISTS mv_cluster_index CASCADE;

CREATE MATERIALIZED VIEW mv_cluster_index AS
SELECT
    unnest(f.root_anxieties)::text AS anxiety,
    unnest(COALESCE(f.cultural_domains, ARRAY[]::text[])) AS domain,
    count(*) AS finding_count,
    round(avg(f.confidence_score)::numeric, 3) AS avg_confidence,
    array_agg(f.id ORDER BY f.confidence_score DESC) AS finding_ids
FROM findings f
WHERE f.status = 'active'
GROUP BY anxiety, domain
ORDER BY anxiety, finding_count DESC;

CREATE UNIQUE INDEX ON mv_cluster_index (anxiety, domain);

-- Read Model 2 (augmented): Pre-computed 1-hop neighborhood per finding.
-- For each active finding, stores the IDs and relationship types of all
-- directly connected findings. Avoids a recursive CTE for simple 1-hop
-- lookups (the graph expander still uses igraph for PPR, but downstream
-- stages can use this for fast neighbor checks).

DROP MATERIALIZED VIEW IF EXISTS mv_finding_neighbors CASCADE;

CREATE MATERIALIZED VIEW mv_finding_neighbors AS
SELECT
    f.id AS finding_id,
    array_agg(DISTINCT
        CASE
            WHEN fr.from_finding_id = f.id THEN fr.to_finding_id
            ELSE fr.from_finding_id
        END
    ) AS neighbor_ids,
    array_agg(DISTINCT fr.relationship::text) AS relationship_types,
    count(DISTINCT fr.id) AS edge_count
FROM findings f
LEFT JOIN finding_relationships fr
    ON (fr.from_finding_id = f.id OR fr.to_finding_id = f.id)
WHERE f.status = 'active'
GROUP BY f.id;

CREATE UNIQUE INDEX ON mv_finding_neighbors (finding_id);

-- Version tracking table: records when each read model was last refreshed
-- and the KB state hash at that time, so the pipeline can detect staleness.

CREATE TABLE IF NOT EXISTS read_model_versions (
    model_name TEXT PRIMARY KEY,
    compiled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kb_hash TEXT NOT NULL,
    finding_count INTEGER NOT NULL,
    notes TEXT
);

-- Initialize version records (will be updated by compile_read_models.py)
INSERT INTO read_model_versions (model_name, kb_hash, finding_count, notes)
VALUES
    ('mv_cluster_index', 'initial', 0, 'Created by setup_read_models.sql'),
    ('mv_finding_neighbors', 'initial', 0, 'Created by setup_read_models.sql'),
    ('wiki_index', 'initial', 0, 'Compiled to kb_wiki/index.md'),
    ('cag_xml_cache', 'initial', 0, 'Compiled to logs/phase1_bakeoff/pipeline_b/kb_snapshot.xml'),
    ('vector_embeddings', 'initial', 0, 'findings.embedding column (pgvector)')
ON CONFLICT (model_name) DO NOTHING;
