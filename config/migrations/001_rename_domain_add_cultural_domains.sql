-- Migration 001: Rename findings.domain to findings.academic_discipline,
--                add findings.cultural_domains TEXT[]
--
-- Context: findings.domain stored academic discipline labels (e.g. "social psychology").
-- root_anxiety_nodes.cultural_domains stored cultural sphere labels (e.g. "religion", "heroism").
-- These two taxonomies were unrelated, making cultural_domains coverage queries impossible.
-- This migration separates the axes explicitly and adds cultural_domains tagging to findings.
--
-- See: docs/taxonomy.md for full taxonomy definitions.
--
-- EXECUTED on 2026-04-11. Manifestations migration added below.
-- Requires coordinated updates to:
--   - src/kb/models.py (Finding, FindingCreate, FindingUpdate)
--   - src/kb/crud.py
--   - src/research_pipeline/ (synthesizer.py, critic.py, cli.py, graph.py)
--   - src/content_pipeline/ (outline.py, selector.py, graph.py, draft_generator.py)
--   - src/shared/drift_monitor.py
--   - src/operator_ui/api/ (findings.py, kb.py, queue.py, generate.py)
--   - src/operator_ui/frontend/src/pages/ (KBBrowserPage.jsx, ContradictionsPage.jsx, ResearchReviewPage.jsx)
--   - config/kb_schema.sql (canonical schema must be updated to match)

BEGIN;

-- 1. Rename the column
ALTER TABLE findings RENAME COLUMN domain TO academic_discipline;

-- 2. Rename the index
ALTER INDEX findings_domain RENAME TO findings_academic_discipline;

-- 3. Add cultural_domains column (nullable — existing findings will be backfilled separately)
ALTER TABLE findings ADD COLUMN cultural_domains TEXT[];

-- 4. Add index for cultural_domains array queries (GIN for @> containment checks)
CREATE INDEX findings_cultural_domains ON findings USING GIN (cultural_domains);

-- 5. Update the active_findings view to reflect the rename and include new column
DROP VIEW IF EXISTS active_findings;

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
        COUNT(DISTINCT fm.manifestation_id) AS manifestation_count,
        COUNT(DISTINCT fr_out.id) AS outbound_relationships,
        COUNT(DISTINCT fr_in.id) AS inbound_relationships
    FROM findings f
    LEFT JOIN finding_manifestations fm ON fm.finding_id = f.id
    LEFT JOIN finding_relationships fr_out ON fr_out.from_finding_id = f.id
    LEFT JOIN finding_relationships fr_in ON fr_in.to_finding_id = f.id
    WHERE f.status = 'active'
    GROUP BY f.id;

-- 6. Rename manifestations.domain to manifestations.academic_discipline
ALTER TABLE manifestations RENAME COLUMN domain TO academic_discipline;
ALTER INDEX manifestations_domain RENAME TO manifestations_academic_discipline;

COMMIT;
