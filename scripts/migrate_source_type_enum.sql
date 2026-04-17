-- Migration: Add industry_research and practitioner to source_type enum.
-- These are commonly used source types in B2B and applied research domains.

ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'industry_research';
ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'practitioner';
