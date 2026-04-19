---
status: accepted
date: 2026-04-17
---
# ADR-0001: Single brand, Explodable-only

## Context

The project ran as a two-brand operation for months — Boulder (opinionated cultural analysis) and Explodable (B2B buyer psychology) — sharing one engine, two voice profiles, staggered publishing cadence. Strategic reappraisal on 2026-04-17 shifted the project's goal from commercial consulting practice to AI-engineering portfolio + employment.

## Options considered

- **Continue two-brand** — maximize audience surface area but split engineering attention, voice tuning, editorial calendar, and content QA between two registers.
- **Merge registers** — single voice covering both cultural and commercial content; loses the specificity that made each voice distinctive.
- **Shelve one brand, focus the other** — concentrate engine evolution, KB tuning, and content production on a single audience.

## Decision

Shelve Boulder. All engineering, KB evolution, content production, and voice tuning targets Explodable only. Explodable becomes the primary portfolio artifact and the single content stream.

## Consequences

Boulder voice YAML retired (see `.internal/archive/config/`). Boulder prompt builders remain in `draft_generator.py` as residual dead code pending a follow-up cleanup pass — invoking the pipeline with `brand="the_boulder"` now fails at voice profile load. Six Boulder-voice drafts from earlier production runs remain in `drafts/`; they are not in the publishing queue. Content audience narrows to B2B buyer-psychology readership + technical hiring managers reviewing the portfolio. Supersedes ADR-0007.
