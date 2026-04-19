---
status: superseded-by-0001
date: 2026-04-06
---
# ADR-0007: Two-brand strategy (Boulder + Explodable) — superseded

## Context

Initial project positioning operated two brands from a single engine: Boulder as opinionated cultural analysis (absurdist-Machiavellian register for a wide audience of generalists), and Explodable as B2B buyer psychology (diagnostic register for fractional-CMO-audience-and-consulting-buyers). Shared KB, shared pipeline, separate voice profiles and rubrics.

## Options considered

- **Single brand** — concentrate engineering effort and audience growth on one voice; loses the range-across-verticals demonstration that was originally the competitive differentiator.
- **Two brands** — one engine, two voice profiles, staggered publishing (Boulder Tuesday, Explodable Thursday); demonstrates cross-domain range; splits engineering attention and editorial load.
- **Three brands+** — rejected immediately as unsustainable for a solo operator.

## Decision (2026-04-06)

Proceed two-brand. Accept the editorial load in exchange for range demonstration and audience surface area. Build voice profiles, BVCS rubrics, and editorial calendar for both.

## Consequences

Six Boulder-voice drafts shipped during this phase. Voice profile divergence required cross-brand contamination rules in prompts ("no Sisyphus, no Camus in Explodable"; "no diagnostic pipeline language in Boulder"). Editorial calendar doubled in scope. Boulder-adjacent voice residue remains in `draft_generator.py` (three residual prompt builders for the `the_boulder` brand argument) pending a follow-up cleanup pass.

**Superseded 2026-04-17 by ADR-0001** — see that ADR for the single-brand rationale. This decision record is preserved for history; do not re-propose a two-brand strategy without a new ADR that addresses what changed since ADR-0001.
