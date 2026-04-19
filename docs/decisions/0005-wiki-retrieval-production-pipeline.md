---
status: accepted
date: 2026-04-16
---
# ADR-0005: Wiki-style index retrieval for production, hybrid pipeline for measurement

## Context

The initial content pipeline used vector retrieval + selector. Research (phase0 reports) surfaced two alternatives worth testing: Cache-Augmented Generation (CAG — full KB in context, ~115K tokens) and wiki-style index scanning (pre-compiled markdown index, per-finding files loaded on demand). The Phase 1 bakeoff tested all three on 5 frozen topics (dense, medium-sparse, cross-domain, sparse-stress, out-of-distribution) scored by the calibrated judge.

## Options considered

- **Pipeline A (current stack)** — retrieval + selector + outline + draft. Mean weighted score 32.3 across 5 topics. Strong on dense/medium, weak on cross-domain (23.0 on T3).
- **Pipeline B (CAG)** — full KB in system prompt with edge-loaded ordering. Mean 26.3. Lost on every topic; model appeared to suffer selection paralysis at 115K-token KB size.
- **Pipeline C (Wiki)** — markdown index (~41K tokens) + on-demand per-finding files. Mean 32.0 (statistically indistinguishable from Pipeline A) with +9 on T3 cross-domain. No voice profile, no outline stage, no BVCS revision.

## Decision

Adopt Wiki-style retrieval as the production pattern with thesis-constrained outline on top (the hybrid approach). Production pipeline (`src/content_pipeline/graph.py`) uses retrieval + graph expansion + thesis outline (Architecture B: fear-commit → logic-recruit → testimony-deploy). Experimental pipeline (`src/content_pipeline/experimental/hybrid_graph.py`) adds topic routing, adversarial critique, and revision gating for measurement runs.

## Consequences

CAG retired decisively — documented as a publishable negative result on long-form generation (published CAG evaluations are QA-only). Hybrid achieved +13 on T3 cross-domain vs Pipeline A (full hybrid, N=1). N=50 replication confirmed the effect with wide variance (mean 32.2, interval 27.7–36.7). Wiki index scales linearly (~130 tokens/finding); at 5,000 findings the index is ~650K tokens, cacheable at 1M context. Per-draft cost ~$0.03 (Wiki alone, Phase 1 bakeoff) vs ~$0.30 for Pipeline A. Thesis outline is the largest measured effect (+8 at N=50 for Explodable topics). Full results in `docs/phase1_results.md`; Phase 2 N=50 data in `logs/phase2_n50/_results.json`.
