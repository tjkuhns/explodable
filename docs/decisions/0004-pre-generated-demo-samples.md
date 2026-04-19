---
status: accepted
date: 2026-04-17
---
# ADR-0004: Hybrid demo — live KB, pre-generated essays

## Context

The Streamlit demo (`demo/app.py`, deployed at explodable.streamlit.app) is the portfolio's public showcase of the engine. A live demo lets visitors run arbitrary queries against the pipeline; a static demo only shows pre-chosen outputs. Running live pipeline inference on a public demo against a solo-operator API budget creates both cost exposure (arbitrary prompts burn credits) and quality variance (a bad prompt produces a bad sample that a hiring manager sees first).

## Options considered

- **Fully live demo** — visitors select a topic, pipeline runs end-to-end, essay appears. Maximum dynamism, unbounded cost, uncontrolled quality.
- **Fully static** — hardcoded sample essays only, no live elements. Zero cost, zero freshness, loses KB showcase.
- **Hybrid** — pre-generated curated essay samples with eval scores displayed, but the KB browser queries live Supabase and shows current finding counts.

## Decision

Hybrid. Five pre-generated essays (`demo/samples/T07.md`, `T14.md`, `T16.md`, `T27.md`, `T33.md` — topics chosen for density and domain spread) with full per-criterion judge scores in `demo/samples/_scores.json`. Live KB browser via Supabase REST API (`demo/app.py:250–281`). Static architecture diagram.

## Consequences

Zero runtime cost per visitor. Reproducible showcase — every visitor sees the same curated essays so the worst-case output is bounded. KB freshness visible in real time (finding counts, new findings, recent approvals). Demo honestly represents the engine's architecture without pretending to run live inference. The curation itself is quality signal — visitors see 5 strong outputs rather than the variable tail of 98 raw drafts in `drafts/`. Tradeoff: a curious hiring manager cannot run a novel topic; mitigated by the GitHub repo being runnable locally.
