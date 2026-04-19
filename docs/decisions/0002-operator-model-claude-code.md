---
status: accepted
date: 2026-04-14
---
# ADR-0002: Claude Code as operator, not a React UI

## Context

The pipeline originally shipped with a React frontend (7 pages across ~3,000 LOC) backed by 7 FastAPI routers for finding review, KB browsing, draft approval, queue management, contradictions, and WebSocket updates. A solo operator using the system daily found the click-through overhead higher than the actual review work.

## Options considered

- **Maintain the full React UI** — supports multi-user, survives headcount growth, but no other users exist or are planned.
- **Simplify the UI** — fewer pages, less styling; still a React/Vite stack to maintain.
- **Replace the UI with Claude Code skills** — chat-native operator surface via `.claude/skills/` (load-state, ingest-research, review-findings, generate-content, kb-query) backed by a minimal FastAPI (4 endpoints: health + pipeline state + pipeline resume + content dispatch).

## Decision

Delete the React frontend entirely. Keep FastAPI at 4 endpoints. Build 5 chat-native skills in `.claude/skills/` that replicate the operator interactions at the same decision gates. Delayed BVCS score disclosure (enforced via skill-level discipline) replaces the old UI's 85%-scroll trigger.

## Consequences

~3,500 LOC deleted. Operator is Claude Code. No multi-user support (not needed). KB browsing loses the Cytoscape graph view — acknowledged in the retirement plan as a post-launch deferral. Chat is now the operator interface, which makes the operator experience visible in `.claude/` as architectural evidence. Documented in `.internal/archive/docs/RETIREMENT_PLAN.md`.
