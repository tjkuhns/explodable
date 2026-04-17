-- Draft usage tracking table — records which findings were used in which drafts.
-- Used by content selector novelty scoring to avoid surfacing the same findings
-- across both The Boulder and Explodable publications.

CREATE TABLE IF NOT EXISTS draft_usage (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    finding_id      UUID NOT NULL REFERENCES findings (id) ON DELETE CASCADE,
    brand           TEXT NOT NULL,          -- 'the_boulder', 'explodable', etc.
    draft_path      TEXT,                   -- path to the published draft file
    used_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS draft_usage_finding_id ON draft_usage (finding_id);
CREATE INDEX IF NOT EXISTS draft_usage_brand ON draft_usage (brand);
CREATE INDEX IF NOT EXISTS draft_usage_used_at ON draft_usage (used_at DESC);
