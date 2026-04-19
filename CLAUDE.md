# CLAUDE.md — Explodable

Orientation for Claude Code sessions working in this repo. Keep this file short and load-bearing. Move details into ADRs (`docs/decisions/`) or code docstrings.

## What this project is

An AI content engine that produces long-form analytical essays on B2B buyer psychology, grounded in a curated knowledge base of behavioral-science findings. Two pipelines share one KB:

- **Production** (`src/content_pipeline/graph.py`) — Wiki-style retrieval → thesis-constrained outline → draft → BVCS revision → HITL gate → publish.
- **Experimental** (`src/content_pipeline/experimental/hybrid_graph.py`) — adds topic routing, adversarial critique, and revision gating for measurement runs.

Quality is measured by a calibrated LLM-as-judge (`src/content_pipeline/eval/judge.py`) against a 7-model editorial panel — ρ = 0.841 at the panel's own ceiling. Methodology in `docs/eval-methodology.md`.

## What this project is NOT

- Not a consulting practice. Not a GEO audit product. Not a two-brand operation. Not frontier-lab-targeted. Not SBIR-funded. See the retired/rejected ADRs below; re-proposing any of these without a new ADR is a protocol violation.
- Not currently calibrated against human reviewers. Disclosed everywhere it appears. Next methodology upgrade; not blocking publication.

## Primary goal

Land a role in Agentic Engineering / Applied AI Engineer / AI Solutions Engineer / Forward Deployed Engineer / DevRel at an AI-native mid-tier company. The engine + GitHub repo is portfolio evidence for that goal. Published essays are the distribution surface.

## Operating model

Claude Code is the operator. No web UI. Operator surface is five skills at `.claude/skills/` (`load-state`, `ingest-research`, `review-findings`, `generate-content`, `kb-query`) backed by a minimal FastAPI. See ADR-0002.

## Decisions index

Read the ADR before re-litigating. All decisions live at `docs/decisions/NNNN-*.md` with MADR-lite frontmatter (`status`, `date`, optional `supersedes`).

| #    | Decision                                               | Status             |
| ---- | ------------------------------------------------------ | ------------------ |
| 0001 | Single brand, Explodable-only                          | accepted           |
| 0002 | Claude Code as operator, not a React UI                | accepted           |
| 0003 | Eval harness as scalable validation (no human panel)   | accepted           |
| 0004 | Hybrid demo — live KB, pre-generated essays            | accepted           |
| 0005 | Wiki retrieval for production, hybrid for measurement  | accepted           |
| 0006 | Issue-first OSS contribution (Braintrust autoevals)    | accepted           |
| 0007 | Two-brand strategy (Boulder + Explodable)              | superseded-by-0001 |
| 0008 | Generative Engine Optimization (GEO) as focus area     | rejected           |
| 0009 | SBIR Phase I funding                                   | rejected           |
| 0010 | Consulting commercial direction                        | retired            |

Status vocabulary: `accepted` | `superseded-by-NNNN` | `rejected` | `retired`. Never edit a non-accepted ADR's body to reverse it — write a new ADR that supersedes it.

To add a decision, use `/adr` (see `.claude/commands/adr.md`) or copy `docs/decisions/TEMPLATE.md`.

## How to work in this codebase

- **Verify before claiming.** Don't quote finding counts, build status, or file contents from memory — `git log`, `ls`, `grep`, or open the file. If a user pushes back, re-run the verifying tool before defending.
- **Prefer editing to creating.** No new `STATUS.md`, `NOTES.md`, `PLAN.md` files — the conversation, ADRs, and code docstrings are the record.
- **Delete or move retired artifacts the same session.** Stale code and docs with "shelved" or "deprecated" labels get re-surfaced by future sessions as if live. Move to `.internal/archive/` (gitignored) or delete outright.
- **`.internal/` is gitignored and out of scope.** Reference for the operator only; do not treat its contents as authoritative. If `.internal/` contradicts this file or an ADR, this file wins.
- **Don't overclaim.** "Builds evaluated AI systems" — not "invented," not "novel." Lead with measured results, not adjectives.
- **Cross-domain KB is the domain expertise.** 305 anxiety-indexed findings × 763 typed relationships × 24 cultural domains is the layer that distinguishes this from "wired up LangGraph." Don't flatten it to generic RAG.

## Session protocols

**Start.** Read this file. Scan `docs/decisions/` headers for any ADRs with `date` newer than your memory. If `.claude/handoff.md` exists and is non-empty, read it — it is the previous session's sign-off.

**End.** If the session made decisions that will affect future work, write them to an ADR before ending. If work is mid-flight, overwrite `.claude/handoff.md` with a short status (what was done, what's next, open questions). Otherwise leave it empty.

## Stack

- Python 3.11, Poetry, FastAPI (4 endpoints), Celery, LangGraph, Supabase Postgres, Streamlit (demo).
- Tests: pytest, 59 unit tests across `eval/judge.py`, `revision_gate.py`, `citation_processor.py`, `topic_router.py`. CI at `.github/workflows/test.yml`.
- Config: `config/` (rubrics, voice profiles, editorial calendar). Rubrics are YAML; judge reads them at runtime.
- Deploy surfaces: GitHub repo (proof layer), `explodable.streamlit.app` (demo, ADR-0004), `explodable.io` (site), LinkedIn (primary distribution channel).

## Pointers

- `docs/architecture.md` — current pipeline shape with `file:line` refs.
- `docs/eval-methodology.md` — judge calibration + disclosed limits.
- `docs/phase1_results.md` / `logs/phase2_n50/_results.json` — bakeoff and N=50 data.
- `docs/code_judge_braintrust_proposal.md` + [autoevals#185](https://github.com/braintrustdata/autoevals/issues/185) — OSS contribution in flight (ADR-0006).
