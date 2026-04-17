-- ============================================================
-- Explodable Knowledge Base Schema
-- PostgreSQL 16 + pgvector 0.8
-- Five entity types, six relationship types
-- Designed for cross-domain anxiety-graph retrieval
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE root_anxiety AS ENUM (
    'mortality',
    'isolation',
    'insignificance',
    'meaninglessness',
    'helplessness'
);

CREATE TYPE panksepp_circuit AS ENUM (
    'SEEKING',
    'RAGE',
    'FEAR',
    'LUST',
    'CARE',
    'PANIC_GRIEF',
    'PLAY'
);

CREATE TYPE circuit_affinity AS ENUM (
    'primary',
    'secondary',
    'contextual'
);

CREATE TYPE finding_provenance AS ENUM (
    'human',
    'ai_proposed',
    'ai_confirmed'
);

CREATE TYPE finding_status AS ENUM (
    'proposed',
    'active',
    'superseded',
    'merged',
    'rejected'
);

CREATE TYPE relationship_type AS ENUM (
    'supports',
    'contradicts',
    'qualifies',
    'extends',
    'subsumes',
    'reframes'
);

CREATE TYPE contradiction_resolution AS ENUM (
    'a_supersedes_b',
    'b_supersedes_a',
    'both_valid_different_scope',
    'merged_into_new',
    'unresolved'
);

CREATE TYPE source_type AS ENUM (
    'academic',
    'journalism',
    'book',
    'social_media',
    'government',
    'primary',
    'other'
);

CREATE TYPE confidence_level AS ENUM (
    'high',
    'medium',
    'low'
);

-- ============================================================
-- ENTITY 1: ROOT ANXIETY NODES
-- Fixed enumeration. Never user-created.
-- ============================================================

CREATE TABLE root_anxiety_nodes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anxiety         root_anxiety NOT NULL UNIQUE,
    description     TEXT NOT NULL,
    cultural_domains TEXT[] NOT NULL,  -- e.g. ['religion', 'legacy arts', 'heroism']
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Pre-defined circuit affinities for each root anxiety node
CREATE TABLE anxiety_circuit_affinities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anxiety         root_anxiety NOT NULL,
    circuit         panksepp_circuit NOT NULL,
    affinity        circuit_affinity NOT NULL,
    rationale       TEXT,
    UNIQUE (anxiety, circuit)
);

-- ============================================================
-- ENTITY 2: FINDINGS
-- Interpretive claims. The core KB unit.
-- ============================================================

CREATE TABLE findings (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- The claim itself
    claim               VARCHAR(280) NOT NULL,  -- Twitter-length: forces precision
    elaboration         TEXT NOT NULL,           -- Full explanation, no length limit

    -- Anxiety-graph positioning
    root_anxieties      root_anxiety[] NOT NULL
                            CHECK (cardinality(root_anxieties) BETWEEN 1 AND 2),
    primary_circuits    panksepp_circuit[]
                            CHECK (primary_circuits IS NULL OR
                                   cardinality(primary_circuits) <= 3),

    -- Epistemic metadata
    confidence_score    FLOAT NOT NULL
                            CHECK (confidence_score BETWEEN 0.0 AND 1.0),
    confidence_basis    TEXT NOT NULL,  -- Why this score was assigned
    confidence_level    confidence_level GENERATED ALWAYS AS (
                            CASE
                                WHEN confidence_score >= 0.75 THEN 'high'::confidence_level
                                WHEN confidence_score >= 0.45 THEN 'medium'::confidence_level
                                ELSE 'low'::confidence_level
                            END
                        ) STORED,

    -- Provenance
    provenance          finding_provenance NOT NULL DEFAULT 'ai_proposed',
    academic_discipline TEXT NOT NULL,  -- e.g. 'political psychology', 'consumer behavior'
    cultural_domains    TEXT[],         -- e.g. '{tribalism,ideology}' — from taxonomy vocabulary
    era                 TEXT,           -- e.g. '2020s', 'post-WWII', 'ancient'
    source_document     TEXT,           -- filename of research doc upload, NULL for pipeline findings
    status              finding_status NOT NULL DEFAULT 'proposed',

    -- Vector embedding (768-dim for text-embedding-3-small)
    embedding           vector(768),

    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at         TIMESTAMPTZ  -- NULL until operator approves
);

-- HNSW index for fast approximate nearest-neighbor search
CREATE INDEX findings_embedding_hnsw
    ON findings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Partial index: only active findings in retrieval
CREATE INDEX findings_active
    ON findings (root_anxieties, confidence_score DESC)
    WHERE status = 'active';

CREATE INDEX findings_academic_discipline ON findings (academic_discipline);
CREATE INDEX findings_cultural_domains ON findings USING GIN (cultural_domains);
CREATE INDEX findings_source_document ON findings (source_document)
    WHERE source_document IS NOT NULL;
CREATE INDEX findings_updated ON findings (updated_at DESC);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER findings_updated_at
    BEFORE UPDATE ON findings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- ENTITY 3: MANIFESTATIONS
-- Specific citable evidence that supports findings.
-- ============================================================

CREATE TABLE manifestations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    description     TEXT NOT NULL,
    academic_discipline TEXT NOT NULL,
    era             TEXT,
    source          TEXT NOT NULL,      -- Full citation or URL
    source_type     source_type NOT NULL,
    source_url      TEXT,
    source_date     DATE,

    -- Vector embedding
    embedding       vector(768),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX manifestations_embedding_hnsw
    ON manifestations USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX manifestations_academic_discipline ON manifestations (academic_discipline);
CREATE INDEX manifestations_source_type ON manifestations (source_type);

CREATE TRIGGER manifestations_updated_at
    BEFORE UPDATE ON manifestations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Join table: findings ↔ manifestations (many-to-many)
CREATE TABLE finding_manifestations (
    finding_id      UUID NOT NULL REFERENCES findings (id) ON DELETE CASCADE,
    manifestation_id UUID NOT NULL REFERENCES manifestations (id) ON DELETE CASCADE,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (finding_id, manifestation_id)
);

CREATE INDEX fm_manifestation_id ON finding_manifestations (manifestation_id);

-- ============================================================
-- ENTITY 4: INTER-FINDING RELATIONSHIPS
-- Six typed directed edges between findings.
-- Rationale is mandatory — no rationale, no relationship.
-- ============================================================

CREATE TABLE finding_relationships (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_finding_id UUID NOT NULL REFERENCES findings (id) ON DELETE CASCADE,
    to_finding_id   UUID NOT NULL REFERENCES findings (id) ON DELETE CASCADE,
    relationship    relationship_type NOT NULL,
    rationale       TEXT NOT NULL
                        CHECK (length(rationale) >= 20),  -- Enforce genuine rationale
    confidence      FLOAT NOT NULL DEFAULT 0.7
                        CHECK (confidence BETWEEN 0.0 AND 1.0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent self-referential relationships
    CHECK (from_finding_id != to_finding_id),
    -- Prevent duplicate relationships of the same type
    UNIQUE (from_finding_id, to_finding_id, relationship)
);

CREATE INDEX fr_from_finding ON finding_relationships (from_finding_id);
CREATE INDEX fr_to_finding ON finding_relationships (to_finding_id);
CREATE INDEX fr_relationship_type ON finding_relationships (relationship);

-- ============================================================
-- ENTITY 5: CONTRADICTION RECORDS
-- Tracks conflicts and resolution between findings.
-- ============================================================

CREATE TABLE contradiction_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    finding_a_id    UUID NOT NULL REFERENCES findings (id) ON DELETE CASCADE,
    finding_b_id    UUID NOT NULL REFERENCES findings (id) ON DELETE CASCADE,
    description     TEXT NOT NULL,      -- What exactly is contradictory
    resolution      contradiction_resolution NOT NULL DEFAULT 'unresolved',
    resolution_notes TEXT,              -- How/why it was resolved
    merged_finding_id UUID REFERENCES findings (id),  -- If merged_into_new
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (finding_a_id != finding_b_id),
    UNIQUE (finding_a_id, finding_b_id)
);

CREATE INDEX cr_finding_a ON contradiction_records (finding_a_id);
CREATE INDEX cr_finding_b ON contradiction_records (finding_b_id);
CREATE INDEX cr_unresolved ON contradiction_records (resolution)
    WHERE resolution = 'unresolved';

-- ============================================================
-- DEDUPLICATION SUPPORT
-- SHA-256 hash index for exact-match dedup before embedding check
-- ============================================================

ALTER TABLE findings ADD COLUMN claim_hash TEXT
    GENERATED ALWAYS AS (encode(sha256(claim::bytea), 'hex')) STORED;
CREATE UNIQUE INDEX findings_claim_hash ON findings (claim_hash);

ALTER TABLE manifestations ADD COLUMN description_hash TEXT
    GENERATED ALWAYS AS (encode(sha256(description::bytea), 'hex')) STORED;
CREATE UNIQUE INDEX manifestations_description_hash ON manifestations (description_hash);

-- ============================================================
-- VIEWS
-- ============================================================

-- Active findings with confidence level for operator interface
CREATE VIEW active_findings AS
    SELECT
        f.id,
        f.claim,
        f.elaboration,
        f.root_anxieties,
        f.primary_circuits,
        f.confidence_score,
        f.confidence_level,
        f.academic_discipline,
        f.cultural_domains,
        f.era,
        f.provenance,
        f.approved_at,
        COUNT(fm.manifestation_id) AS manifestation_count,
        COUNT(fr_out.id) AS outbound_relationships,
        COUNT(fr_in.id) AS inbound_relationships
    FROM findings f
    LEFT JOIN finding_manifestations fm ON fm.finding_id = f.id
    LEFT JOIN finding_relationships fr_out ON fr_out.from_finding_id = f.id
    LEFT JOIN finding_relationships fr_in ON fr_in.to_finding_id = f.id
    WHERE f.status = 'active'
    GROUP BY f.id;

-- Unresolved contradictions for operator dashboard
CREATE VIEW unresolved_contradictions AS
    SELECT
        cr.id,
        cr.description,
        cr.created_at,
        fa.claim AS finding_a_claim,
        fa.confidence_score AS finding_a_confidence,
        fb.claim AS finding_b_claim,
        fb.confidence_score AS finding_b_confidence
    FROM contradiction_records cr
    JOIN findings fa ON fa.id = cr.finding_a_id
    JOIN findings fb ON fb.id = cr.finding_b_id
    WHERE cr.resolution = 'unresolved'
    ORDER BY cr.created_at DESC;

-- ============================================================
-- ENTITY 6: QUERIES (retrieval telemetry)
-- Append-only log of every KB query. Populated by content_pipeline,
-- research_pipeline, manual calls, and future product surfaces.
-- ============================================================

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
CREATE INDEX queries_embedding_hnsw
    ON queries USING hnsw (query_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================================
-- SEED DATA: Root anxiety nodes
-- ============================================================

INSERT INTO root_anxiety_nodes (anxiety, description, cultural_domains) VALUES
('mortality',       'Fear of death and non-existence; the awareness that life is finite',
 ARRAY['religion', 'legacy arts', 'heroism', 'immortality technology', 'medicine']),
('isolation',       'Fear of being alone, disconnected, or excluded from community',
 ARRAY['tribalism', 'nationalism', 'romantic love', 'social media', 'friendship']),
('insignificance',  'Fear that one''s life, actions, or existence do not matter',
 ARRAY['achievement culture', 'wealth', 'fame', 'competitive systems', 'legacy']),
('meaninglessness', 'Fear that existence has no inherent purpose or coherent narrative',
 ARRAY['philosophy', 'science', 'ideology', 'conspiracy theories', 'narrative art', 'religion']),
('helplessness',    'Fear of lacking agency or control over one''s circumstances',
 ARRAY['political movements', 'rebellion', 'technology', 'authoritarianism', 'addiction']);

-- Seed circuit affinities (primary only — secondary/contextual added during research)
INSERT INTO anxiety_circuit_affinities (anxiety, circuit, affinity, rationale) VALUES
('mortality',       'FEAR',         'primary',   'Direct activation of threat-detection circuitry'),
('mortality',       'SEEKING',      'secondary',  'Drives legacy-building and meaning-seeking behavior'),
('isolation',       'PANIC_GRIEF',  'primary',   'Separation distress is the core mammalian bonding alarm'),
('isolation',       'CARE',         'secondary',  'Isolation anxiety motivates care-seeking and giving'),
('insignificance',  'SEEKING',      'primary',   'Achievement drive is SEEKING circuit in social context'),
('insignificance',  'RAGE',         'secondary',  'Perceived disrespect activates rage circuits'),
('meaninglessness', 'SEEKING',      'primary',   'Meaning-seeking is the default mode of the SEEKING circuit'),
('meaninglessness', 'PLAY',         'contextual', 'Play and creativity are responses to meaninglessness'),
('helplessness',    'FEAR',         'primary',   'Loss of control activates the same circuits as physical threat'),
('helplessness',    'RAGE',         'secondary',  'Helplessness frequently converts to rage as a coping response');
