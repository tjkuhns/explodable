-- Migration: Add benchmark_runs and operator_alerts tables
-- Run after initial KB schema has been applied.

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_baseline BOOLEAN NOT NULL DEFAULT FALSE,
    prompt_1_score FLOAT,
    prompt_2_score FLOAT,
    prompt_3_score FLOAT,
    prompt_4_score FLOAT,
    prompt_5_score FLOAT,
    overall_score FLOAT,
    deviation_from_baseline FLOAT,
    alert_triggered BOOLEAN DEFAULT FALSE,
    raw_outputs JSONB
);

CREATE TABLE IF NOT EXISTS operator_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ
);
