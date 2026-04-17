# DEPRECATED — 2026-04-14

**This package is retained as a dormant dependency of `src/shared/drift_monitor.py`
but is no longer an active ingestion path.**

All KB findings enter via document upload (Deep Research docs processed
through chat, not via the autonomous research graph). The research pipeline
has been run exactly 3 times in the KB's entire history, all before
query telemetry was enabled, and none of those runs produced anything
currently in the KB.

## Why kept, not deleted

`src/shared/drift_monitor.py` imports `plan_research` and `research_task`
to use the research pipeline as the *subject* of its benchmark prompts.
Drift monitoring runs this package as a test harness. If drift_monitor
is also retired in a future phase, this entire package can be deleted.

## Do not review these files as part of project audits

They are isolated, self-contained, and not driving any active workflow.
Reviewing them is waste of tokens. The active ingestion path is:

1. User runs Deep Research in Claude Desktop or the web app
2. User pastes the markdown output or file path in chat
3. Claude Code runs extraction via `config/research_extraction_prompt.txt`
4. Findings validated against `src/kb/ingest_models.FindingInput`
5. Dedup + write via `src/kb/crud.KBStore.create_finding`
6. HITL review via chat, approve via `KBStore.approve_finding`
7. Relationship classification fires via `src/kb/relationship_classifier.classify_and_commit`

None of the above touches this package.

## Removed entry points (2026-04-14)

- `src/shared/tasks.py:run_research_pipeline` — Celery task deleted
- `src/operator_ui/api/research.py` — router deleted (manual trigger + document upload endpoints)
- `scripts/week1_gate_test.py`, `scripts/week4_mvp_gate_test.py` — historical, moved to `scripts/historical/`

## What remains

- Self-referential imports inside this package only (planner → researcher → synthesizer → critic → graph)
- `src/shared/drift_monitor.py` imports `plan_research` and `research_task`

## Revisit

Post-launch, when deciding whether to re-enable autonomous research runs
(Tier 2+ enhancement) or retire the entire package including drift_monitor.

## Status

- **Active code paths:** 0
- **Dormant imports:** 2 (both in drift_monitor.py)
- **Last active use:** 2026-04-08 (3 pipeline runs, all before migration 002 enabled query telemetry)
- **Recommendation:** ignore unless you are specifically working on drift monitoring or re-enabling autonomous research
