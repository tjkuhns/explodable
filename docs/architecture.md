# Explodable — Architecture

*Last verified against live code: 2026-04-18*

Every load-bearing claim here cites `file:line`. If a claim drifts from
the code, the code wins and this doc gets updated — not the other way
around.

---

## 1. Shape of the system

One active pipeline: **content generation**. A LangGraph `StateGraph`
produces long-form analytical essays, five-section Buyer Intelligence
Briefs, and short-form LinkedIn posts from a structured KB of
behavioral-science findings.

- Production graph: `src/content_pipeline/graph.py:671` — `build_content_graph()`
- Experimental graph: `src/content_pipeline/experimental/hybrid_graph.py:596` — `build_hybrid_graph()`

The two graphs coexist by design, separated at the directory level.
Production runs go through `graph.py` via Celery
(`src/shared/tasks.py:84`). The hybrid graph and its collaborators
(topic routing, graph expansion, adversarial critique, revision gate,
thesis outline) live in `src/content_pipeline/experimental/` —
measurement and ablation surface where architecture changes are
evaluated before being promoted into production. See
`src/content_pipeline/experimental/README.md` for the promotion
criteria.

The **research pipeline** in `src/research_pipeline/` is deprecated —
see `src/research_pipeline/DEPRECATED.md`. It remains on disk only as a
dormant import target for `src/shared/drift_monitor.py`. KB findings now
enter via Deep Research document upload + extraction through chat, not
the autonomous research graph.

---

## 2. Knowledge base

PostgreSQL 16 + pgvector 0.8, five entity tables plus taxonomy tables.

| Table | Purpose |
|---|---|
| `findings` | Claim + elaboration + root anxieties + primary circuits + confidence + embedding + provenance |
| `finding_manifestations` | Evidence instances attached to findings |
| `finding_relationships` | Typed edges (`supports`, `extends`, `qualifies`, `subsumes`, `reframes`, `contradicts`) with rationale |
| `contradiction_records` | Dedicated tracking with resolution state |
| `manifestations` | Source metadata for manifestations |
| `root_anxiety_nodes`, `anxiety_circuit_affinities` | Fixed taxonomy (5 anxieties × 7 Panksepp circuits) |

Schema DDL: `config/kb_schema.sql`. Migrations: `config/migrations/001_*.sql`
through `003_*.sql`.

**Embeddings and retrieval.** OpenAI `text-embedding-3-small`, 768-dim,
generated at write time. HNSW index `findings_embedding_hnsw`
(m=16, ef_construction=64, vector_cosine_ops). Dedup on write:
SHA-256 exact match, MinHash LSH near-duplicate, cosine > 0.90 semantic —
see `src/kb/dedup.py` and `src/kb/embeddings.py`.

**Current counts drift.** Query the database directly or run the
`load-state` skill for live numbers; do not cite from this document.

---

## 3. Content pipeline

Entrypoint: `build_content_graph()` in `src/content_pipeline/graph.py:671`.
State: `ContentState` (Pydantic, `graph.py:54`). Checkpointing: LangGraph
`PostgresSaver`.

Flow:

```
START → calendar_trigger → kb_retriever → content_selector
  → [standalone_post_generator | outline_generator]
  → outline_generator → hitl_gate_2_outline
  → (approve/edit → draft_generator, reject → END)
  → draft_generator → bvcs_scorer
  → (pass → hitl_gate_2_draft, fail → draft_revise loop, max 3)
  → hitl_gate_2_draft
  → (approve/edit → publisher_stub, reject → END)
  → publisher_stub → END
```

Three output types dispatched off `state.output_type`:

| Output type | Outline | Social variants | Length |
|---|---|---|---|
| `newsletter` | Full | X, LinkedIn, Substack Notes | 600–2500 words |
| `brief` | 5-section rigid | None | 1500–2500 words |
| `standalone_post` | Skipped | None | 300–500 words |

Explodable is the only active brand. The code still accepts a `brand` parameter and the `draft_generator` has prompt builders for a second "the_boulder" register, but the Boulder voice profile config was retired — invoking the pipeline with `brand="the_boulder"` will fail on missing voice profile. Single-brand operation is the intentional current state.

### Retrieval

`src/content_pipeline/retriever.py:284` — `retrieve_findings()`.

Multi-query expansion (3 LLM-generated variants) → semantic search per
variant via HNSW → dedup → decay-weighted scoring →
graph expansion via typed relationships.

- Semantic score: `0.7 × cosine_similarity + 0.3 × exp(-0.693 × age_days / 14)`
- Graph expansion (`retriever.py:175`): top-5 semantic results become
  PPR seeds. One-hop walk via `finding_relationships`. Neighbors scored
  by `seed_score × relationship_weight × edge_confidence`. Weights favor
  `contradicts` / `reframes` (narrative value) over `supports` (redundant).
- Can be disabled via `enable_graph_expansion=False` for benchmarking.

### Selection

`src/content_pipeline/selector.py:161` — `select_findings()`.

For newsletters and briefs:
`score = 0.4 × retrieval + 0.2 × novelty + 0.2 × narrative_potential + 0.2 × brand_relevance`.

For standalone posts: weights shift to novelty (0.3) and narrative (0.25)
because short-form needs a single sharp seed.

- Novelty: `exp(-usage_count × 0.3)` via the `draft_usage` table
- Narrative potential: relationship density in the KB
- Brand relevance: scaled by voice profile tone parameters

Guarantees at least one cross-domain finding per selection if any exist.

### Outline

- `src/content_pipeline/outline.py` — standard outline generator
  (brand-neutral schema). Used by the production graph.
- `src/content_pipeline/experimental/thesis_outline.py` — Explodable
  Architecture B: Toulmin-complete sections over a `fear-commit →
  logic-recruit → testimony-deploy` stage vocabulary, with derivation
  check and structural contract validation. Used by the hybrid graph
  for Explodable newsletters.

### Draft generation

`src/content_pipeline/draft_generator.py:1062` — `generate_draft()`.
Dispatches on (brand, output_type). The module ships six prompt
builders — Explodable's three output types plus three residual
builders for a second "the_boulder" register — but only Explodable is
exercised in production. Invoking with `brand="the_boulder"` now
fails at `load_voice_profile()` because the Boulder voice YAML was
retired. The residual builders remain as dead code pending a
follow-up pass.

Three citation modes controlled by env flags:

| Flag | Mode | Notes |
|---|---|---|
| `USE_HYBRID_CITATIONS=true` | Inline `[src:N]` markers, post-processed into markdown footnotes via `citation_processor.py` | **Default.** Preserves voice profile, produces clickable URLs. |
| `USE_CITATIONS_API=true` | Anthropic Citations API | Disabled by default — voice profile overrides Citations API metadata instructions when they compete. |
| Neither | ChatAnthropic legacy path | Fallback. No per-span citations. |

System prompt cached at 1-hour TTL so multi-draft sessions amortize the
voice-profile prompt (2–3K tokens) at 10% of normal input cost after
the first call.

### BVCS — voice compliance scoring

`src/content_pipeline/bvcs.py:315` — `score_draft()`.

Brand-agnostic dispatcher. Automated handlers for `banned_phrase_check`,
`mechanics` (sentence/paragraph length, reading level), and
`length_compliance`. All other dimensions route to LLM scoring via the
rubric's `scoring_prompt` field. Unknown automated dimensions fall
through to LLM scoring with a structured warning logged.

Threshold: 70/100. Revision notes generated on fail and fed back to
`draft_generator.py` for retry (max 3 loops in the production graph,
max 1 in the hybrid graph).

### HITL gates

Two gates use LangGraph `interrupt()` and pause until the operator
resumes via `POST /api/pipeline/resume/{thread_id}`:

1. **Outline review** after `outline_generator` (`graph.py:204`)
2. **Draft review** after `bvcs_scorer` (`graph.py:344`)

Resume decisions flow through `src/shared/tasks.py:127` —
`resume_content_pipeline` — which uses LangGraph `Command(resume=...)`
to continue from the interrupt point.

### Publisher

`src/content_pipeline/graph.py:501` — `publisher_stub_node()`.

Writes drafts as markdown files to:
- `~/explodable/drafts/` (newsletters, with social variants appended)
- `~/explodable/briefs/` (briefs, no social variants)
- `~/explodable/posts/` (standalone LinkedIn posts)

Citation post-processing: if the draft contains `[src:N]` markers,
`citation_processor.process_citations()` transforms them into markdown
footnotes with URL-linked sources before the file is written. Usage is
logged to `draft_usage` for the novelty scorer.

Substack API integration deferred. No `drafts` DB table — draft
listing is currently filesystem-backed.

---

## 4. Evaluation

`src/content_pipeline/eval/judge.py` — LLM-as-judge with flat-schema
`tool_use` for structured scoring. Deterministic (temperature=0).

Calibration methodology: `docs/eval-methodology.md`.

- Opus judge (`claude-opus-4-20250514`): ρ = 0.841 vs. the 5-model
  tight cluster at calibration time
- Sonnet judge (`claude-sonnet-4-20250514`): ρ = 0.782, 8× cheaper per
  call. **This is the production judge.**

**Known calibration limit.** The 5-model ground truth was derived by
dropping 2 outlier models (Claude Deep Research and Qwen) *after*
observing disagreement. A pre-registered protocol would specify drop
criteria in advance. The ρ = 0.841 number is real but inflated by
post-hoc selection. Full disclosure in the methodology writeup.

---

## 5. Adversarial critique + revision gate (hybrid graph only)

These stages live in the hybrid graph, not the production graph.

- `src/content_pipeline/experimental/adversarial_critic.py:304` —
  `critique_draft()`. Uses a different model family from the
  generator (Gemini Flash preferred over OpenAI, over Anthropic Opus)
  per Pan et al. (2024): same-model critique inflates self-scored
  quality.
- `src/content_pipeline/experimental/revision_gate.py:142` —
  `revision_gate()`. Pareto filter via the calibrated judge. A
  revision is accepted only if at least one criterion improves and
  none regress.

The production content pipeline uses BVCS scoring for voice compliance
and the standard HITL gate for quality judgment. Adversarial critique
is experimental.

---

## 6. Operator UI (FastAPI backend)

Post-retirement minimal surface. Two routers, three endpoints.

| Router | File | Endpoints |
|---|---|---|
| `generate` | `src/operator_ui/api/generate.py` | `POST /api/generate/content` |
| `pipeline` | `src/operator_ui/api/pipeline.py` | `GET /api/pipeline/state/{id}`, `POST /api/pipeline/resume/{id}` |

Entry: `src/operator_ui/api/main.py:39`. Health: `GET /api/health` at
`main.py:49`.

Everything else — KB browser, findings CRUD, drafts listing, queue,
WebSocket, research upload, usage reporting — was retired 2026-04-14.
The operator model is now Claude Code driving the KB directly via
scripts and chat, not a human clicking through browser screens.

---

## 7. Infrastructure

| Layer | Choice |
|---|---|
| Runtime | Python 3.12, LangGraph 1.1+ |
| Checkpointing | LangGraph `PostgresSaver` (via `langgraph-checkpoint-postgres`) |
| Storage | PostgreSQL 16 + pgvector 0.8 |
| Task queue | Celery + Redis |
| Scheduling | Celery Beat schedule intentionally empty (`tasks.py:44`) — all runs are operator-triggered |
| Embeddings | OpenAI `text-embedding-3-small`, 768-dim |
| Dev env | WSL2 Ubuntu 24.04 on Windows 11, Docker Desktop |

Docker compose: `docker/docker-compose.yml`. Cost envelope:
~$130–200/month infrastructure + per-call Anthropic/OpenAI/Gemini
charges.

---

## 8. Known gaps

These are real gaps in the repo as of 2026-04-18. Honesty here is
load-bearing for everything else in this document — if the gaps are
stated accurately, the rest of the doc is trustworthy.

1. **Test coverage is partial.** `tests/` covers four portable modules
   (`eval/judge.py`, `experimental/revision_gate.py`,
   `citation_processor.py`, `experimental/topic_router.py`) with 59
   unit tests that run without API or DB dependencies. The rest of
   `src/content_pipeline/` — graph nodes, `draft_generator.py`,
   `bvcs.py`, `retriever.py`, `selector.py`, `outline.py`,
   `experimental/thesis_outline.py`, `experimental/graph_expander.py`,
   `publisher_stub` — is still untested. Target: 60%+ coverage before
   production launch.

2. **Disk-backed drafts, not DB.** No `drafts` table. Cross-draft
   queries require filesystem grep. Revisit if draft count grows past
   a few hundred or operator workflow needs SQL.

3. **Documentation hygiene.** This doc drifted against code between
   2026-04-13 and 2026-04-18 because the 2026-04-14 retirement task
   was scoped to code only. Retirement tasks in this repo should
   include a "grep docs for mentions of the deleted modules and
   reconcile" subtask going forward.

### Resolved 2026-04-18

- **Production/experimental boundary made explicit.** Moved
  `hybrid_graph.py`, `topic_router.py`, `graph_expander.py`,
  `adversarial_critic.py`, `revision_gate.py`, and `thesis_outline.py`
  into `src/content_pipeline/experimental/`. Production `graph.py`
  does not import from experimental. Imports in `scripts/` and
  `tests/` updated. See `experimental/README.md` for the promotion
  criteria.
- **`.env` parsing duplication** — replaced with `python-dotenv` calls
  in `adversarial_critic.py`, `graph_expander.py`,
  `scripts/score_code.py`.
- **Parser bug in `adversarial_critic.py`** — `parse_critique()` now
  returns `(proposals, data)` so `critique_draft` reads `summary` from
  the already-parsed dict instead of re-parsing with broken `lstrip`.
- **Dead CLI code in `outline.py`** — `display_outline()` /
  `get_outline_decision()` removed (unreachable since HITL flows
  through LangGraph `interrupt()`).
- **Dead branch in `topic_router.py`** density classifier collapsed.
