-- Migration 003: Add source_document column to findings.
--
-- Context: when findings are extracted from a research document upload
-- (markdown file from Claude Deep Research), we want to know which document
-- each finding came from. This enables batch review, batch rollback, and
-- provenance tracking for uploaded findings.
--
-- The column is nullable because existing findings and pipeline-generated
-- findings have no source document.

BEGIN;

ALTER TABLE findings ADD COLUMN source_document TEXT;

-- Partial index: only index non-null values, since most findings (pipeline-
-- generated and existing KB) will have NULL here.
CREATE INDEX findings_source_document ON findings (source_document)
    WHERE source_document IS NOT NULL;

COMMIT;
