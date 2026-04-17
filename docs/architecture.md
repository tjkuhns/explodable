# Explodable — Architecture

*Last verified against live code and DB: 2026-04-13*

This document describes the engine as it exists in the repo today. If a claim here drifts from the code, the code wins and this document gets updated — not the other way around. Every load-bearing claim cites `file:line`.

---

## 1. Shape of the system

Three surfaces share one knowledge base:

1. **Research pipeline** — LangGraph StateGraph, long-running, produces findings. (`src/research_pipeline/graph.py`)
2. **Content pipeline** — LangGraph StateGraph, long-running, produces newsletter drafts. (`src/content_pipeline/graph.py`)
3. **Brief endpoint** — FastAPI handler, synchronous, produces client-facing briefs on demand. (`src/operator_ui/api/generate.py:275`)

The research pipeline and content pipeline are full StateGraphs with checkpointing, HITL gates, and quality scoring. **The brief endpoint is not a pipeline.** It is a direct retrieval → LLM → response handler. This is the single most important architectural fact to remember: briefs and newsletters share a KB and a retriever and nothing else. Any future work on brief quality needs to either lift the brief into a real pipeline or accept the minimalism and work inside it.

All three surfaces are driven through the operator UI (FastAPI + React) at `src/operator_ui/`.

---

## 2. Knowledge base

### Storage

PostgreSQL 16 + pgvector 0.8. Container `explodable_postgres`, database `explodable`, user `explodable`. Fifteen tables — five for the KB itself, the rest for operator telemetry, LangGraph checkpointing, and benchmark state.

### Core entity tables

| Table | What it holds |
|---|---|
| `findings` | 280-char claim + elaboration, root anxieties (1–2), primary circuits (0–3), confidence score, confidence basis, academic discipline, era, cultural domains, provenance, status, 768-dim embedding, source document, timestamps |
| `finding_manifestations` | Citable evidence instances attached to findings |
| `finding_relationships` | Typed inter-finding edges — `supports`, `extends`, `qualifies`, `subsumes`, `reframes`, `contradicts` — with rationale |
| `contradiction_records` | Dedicated contradiction tracking with resolution state |
| `manifestations` | Domain/era/source/type metadata for manifestations |
| `root_anxiety_nodes`, `anxiety_circuit_affinities` | Fixed Layer 1 taxonomy (Panksepp circuits × five root anxieties) |

Schema DDL: `config/kb_schema.sql`. Migrations: `config/migrations/001_*.sql` through `003_*.sql`.

### Current state (2026-04-13)

- 273 active findings, 32 proposed, 1 superseded
- 480 typed relationships (supports 342, extends 101, qualifies 18, subsumes 11, reframes 6, contradicts 2)
- 370 manifestations
- 0 contradiction records
- Avg finding confidence: 0.817
- Top disciplines: social psychology (35), organizational psychology (33), behavioral economics (32), political psychology (25), buyer psychology (19)
- Anxiety distribution on active findings: helplessness 179, insignificance 136, isolation 92, meaninglessness 69, mortality 43

The graph is populated, not orphan. Relationships are real and typed.

### Embeddings and retrieval

OpenAI `text-embedding-3-small`, 768 dimensions, generated at KB write time. HNSW index: `findings_embedding_hnsw` (m=16, ef_construction=64, vector_cosine_ops). Dedup happens on write via SHA-256 (exact) + MinHash LSH (near-duplicate) + cosine >0.90 (semantic). See `src/kb/dedup.py` and `src/kb/embeddings.py`.

---

## 3. Research pipeline

**Entrypoint:** `build_research_graph()` in `src/research_pipeline/graph.py:509`. State: `ResearchState` (Pydantic).

**Nodes and edges** (`graph.py:518–538`):

```
START → planner → [researchers in parallel via Send]
      → synthesizer → critic
      → (conditional: retry_research → synthesizer, OR hitl_gate_1)
      → hitl_gate_1 → kb_writer → END
```

| Node | File | Job |
|---|---|---|
| `planner` | `planner.py` | Decomposes directive into parallel research tasks (structured Pydantic output) |
| `researcher` | `researcher.py` | Per-task search + synthesis via Tavily/Exa/Semantic Scholar/web fetch. Max 3 tool calls. Parallel via LangGraph `Send`. |
| `synthesizer` | `synthesizer.py` | Deduplicates, detects conflicts, assigns root anxieties and circuits via structured output |
| `critic` | `critic.py` | Groundedness check at temperature 0. Requires `is_grounded=True` AND `source_coverage >= 70%` |
| `retry_research` | `graph.py` | Re-researches failed findings with revision suggestions. Deduplicates approved findings by claim hash. Max 2 retries. |
| `hitl_gate_1` | `graph.py` | LangGraph `interrupt()`. Operator approves/rejects/edits/requests more. |
| `kb_writer` | `graph.py` | Writes findings as `status=proposed`, then `approve_finding()` sets `status=active` and `approved_at=NOW()`. Generates embeddings at write time. |

**Checkpointing:** PostgresSaver. All state transitions persisted to `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations`.

**Also fed by:** `src/operator_ui/api/research.py` — document upload endpoint with LLM extraction. Operator uploads a research PDF/doc, backend extracts candidate findings, operator approves at HITL gate 1. This was added on 2026-04-11 (commits 37f39fa, 2220761, 8fe13fd) and is live — recent logs show `research_upload.started` and `research_upload.complete` events.

**Relationship classification** runs automatically on finding approval (commits 1329ca5, 4aa9bb1 from 2026-04-12). See `src/kb/relationship_classifier.py` and `config/relationship_classification_prompt.txt`. Prompt-cached to cut cost on repeated classification calls.

---

## 4. Content pipeline

**Entrypoint:** `build_content_graph()` in `src/content_pipeline/graph.py:362`. State: `ContentState`.

**Nodes and edges** (`graph.py:374–411`):

```
START → calendar_trigger → kb_retriever → content_selector
      → outline_generator → hitl_gate_2_outline
      → (conditional: draft_generator OR END)
      → draft_generator → bvcs_scorer
      → (conditional: draft_revise → bvcs_scorer, OR hitl_gate_2_draft)
      → hitl_gate_2_draft
      → (conditional: publisher_stub OR END)
      → publisher_stub → END
```

| Node | File | Job |
|---|---|---|
| `calendar_trigger` | `graph.py` | Entry from `config/editorial_calendar.yaml` — topic + brand in |
| `kb_retriever` | `retriever.py` | Multi-query retrieval. Score: `0.7 × semantic_similarity + 0.3 × exp(-0.693 × age_days / 14)`. Dedup across query variants. |
| `content_selector` | `selector.py` | Ranks retrieved findings by novelty / narrative / brand relevance |
| `outline_generator` | `outline.py` | Outline from selected findings |
| `hitl_gate_2_outline` | `graph.py` | `interrupt()`. Operator approves outline before draft generation. |
| `draft_generator` | `draft_generator.py` | Two-step: newsletter prose first (free-form, 6000 max_tokens), then social variants via `SocialVariants` structured output. Voice loaded from YAML at runtime. |
| `bvcs_scorer` | `bvcs.py` | Brand Voice Consistency Score. Automated dimensions + LLM-scored dimensions. Passes at ≥70. |
| `draft_revise` | `graph.py` | Auto-regenerates if BVCS <70. Max 3 attempts. Currently regenerates from scratch — revision feedback is computed but not threaded into the regeneration prompt. Known gap. |
| `hitl_gate_2_draft` | `graph.py` | `interrupt()`. Operator reviews final draft with source attribution. |
| `publisher_stub` | `graph.py` | Writes draft markdown to `drafts/` with frontmatter. Substack API integration deferred. |

**Checkpointing:** PostgresSaver, same backend as research pipeline.

**Voice configuration:**
- `config/voice_profile_the_boulder.yaml` + `config/bvcs_rubric_the_boulder.yaml`
- `config/voice_profile_explodable.yaml` + `config/bvcs_rubric_explodable.yaml`

**Current draft output:** Six drafts in `drafts/`, all dated 2026-04-06, all scoring 81/100 BVCS, all ~1500–1600 words. No drafts since 2026-04-06 — the pipeline is idle, not broken.

---

## 5. Brief endpoint (the non-pipeline)

**Entrypoint:** `POST /api/generate/brief` at `src/operator_ui/api/generate.py:275`.

**Flow:**

```
request (client_context, vertical?, root_anxiety_filter?)
  → retrieve_findings(topic=client_context, top_k=12, min_confidence=0.45, root_anxiety_filter=...)
  → _format_findings_for_brief(findings)
  → _build_brief_prompt(voice_profile_explodable)
  → Claude Sonnet 4 call
  → return raw brief text in JSON response
```

What this path *does not* have:
- No selector ranking beyond retriever score — whatever the retriever returns is what the LLM sees
- No outline generation before prose
- No BVCS scoring
- No revision loop
- No HITL gates
- No persistence — briefs are returned in the HTTP response and never written to disk unless the operator saves them manually
- No paragraph-level citation threading — findings are passed as "Finding 1", "Finding 2" in the prompt, LLM is instructed not to invent facts, but there is no post-hoc citation linking

The content endpoint `POST /api/generate/content` at `generate.py:334` is similarly minimal — also not the content pipeline StateGraph. Both generation endpoints are synchronous, fast, client-facing paths intended for interactive use from the operator UI.

**Client-side guardrails** added 2026-04-12 (commit 10df218): 50-char minimum on `client_context`, 10-char minimum on content topic. Intended to prevent vague prompts that produce vague output.

**Implication:** Briefs in their current form are a one-shot LLM call over 12 semantically-retrieved findings. The content pipeline's quality machinery does not touch them. If briefs become the core commercial product, this is the architectural gap that matters.

---

## 6. Operator UI

**Backend:** FastAPI at `src/operator_ui/api/main.py`. Routers registered (`main.py:53–59`):

| Router | File | Surface |
|---|---|---|
| `findings` | `findings.py` | Finding CRUD, approval, bulk operations |
| `drafts` | `drafts.py` | Draft listing, inspection |
| `kb` | `kb.py` | KB browser — findings, relationships, search |
| `queue` | `queue.py` | Operator work queue (ranked) |
| `ws` | `ws.py` | WebSocket for real-time updates |
| `generate` | `generate.py` | Brief + content generation endpoints |
| `research` | `research.py` | Research document upload + extraction |

Health check: `GET /api/health` at `main.py:62`.

**Frontend:** React + Vite at `src/operator_ui/frontend/`. Screens match the backend surfaces: work queue, research review, KB browser, content review, contradictions, performance feedback.

---

## 7. Infrastructure

| Layer | Choice |
|---|---|
| Orchestration | Python 3.12 + LangGraph 1.1.6 |
| Checkpointing | LangGraph PostgresSaver (requires `langgraph-checkpoint-postgres` package, separate from `langgraph`) |
| Storage | PostgreSQL 16 + pgvector 0.8 |
| Task queue | Celery + Redis |
| Scheduling | Celery Beat + PostgreSQL `LISTEN/NOTIFY` for priority events |
| Search tools | Tavily, Exa (exa-py SDK, not in LangChain integrations), Semantic Scholar API, httpx |
| Embeddings | OpenAI `text-embedding-3-small`, 768-dim |
| Dev env | WSL2 Ubuntu 24.04 on Windows 11, Docker Desktop, pyenv-managed Python |
| Cost | ~$130–200/month infrastructure |

Docker volumes are currently Docker-managed named volumes (`explodable_postgres`, `explodable_redis`). Migration to external SSD is pending hardware availability.

---

## 8. Known architectural gaps

These are the real gaps remaining as of 2026-04-13. Several items previously
listed in this section have since been resolved — kept in a separate
"resolved" list below for reference.

### Open gaps

1. **No paragraph-level source annotations.** Draft generator produces prose
   with no per-paragraph finding mapping. The publisher now writes a Sources
   appendix using the outline's section → finding_indices mapping (see
   `_render_sources_appendix` in `graph.py`), which gives section-level
   provenance for free. Paragraph-level precision would require a second
   LLM annotation pass — deferred until operator use tells us whether
   section-level is sufficient. File if needed: `src/content_pipeline/draft_generator.py`.

2. **HITL gates in content pipeline require daily-use seasoning.** Code
   exists, interrupts fire correctly, state endpoint surfaces review
   payloads properly, resume task wires LangGraph Command(resume=...)
   correctly. One full end-to-end run validated on 2026-04-13 producing
   The Veto Machine Boulder essay at BVCS 91/100. But one run is not
   robust data — edge cases (BVCS revision cycle exhausting 3 attempts,
   operator edit applied mid-flight, retriever returning <4 findings,
   Anthropic 529s during resume) have not been exercised. Not a code
   gap, an operational gap. Resolves through use.

3. **Publisher writes to disk, not postgres.** Drafts live as markdown
   files in `~/explodable/drafts/` (newsletters) and `~/explodable/briefs/`
   (briefs). The operator UI's draft review (`drafts.py`) reads from
   disk, not from a `drafts` DB table. Works but means draft history,
   cross-draft search, and finding-to-draft queries require filesystem
   grep rather than SQL. Low priority — revisit if draft count grows
   past a few hundred or if operator workflow needs SQL queries across
   drafts.

### Resolved gaps (kept for reference)

These were listed as open in earlier versions of this document but are
now implemented. Left here so future sessions can verify they're still
working and don't regress.

- **Brief endpoint bypass** — resolved 2026-04-13 by Phase 1b (`3738806`).
  `POST /api/generate/brief` and `/api/generate/content` both now queue
  `run_content_pipeline` via Celery with `output_type` parameter. The
  stripped-down synchronous prompt builders in `generate.py` were
  deleted.

- **Retrieval was semantic-only** — resolved 2026-04-13 in `retriever.py`
  by adding `_expand_via_relationships()`. The retriever now takes the
  top 5 semantic results as seeds, walks one hop along
  `finding_relationships` edges, and surfaces up to 6 neighbors scored by
  seed_score × relationship_weight × edge_confidence. Contradicts and
  reframes edges score highest (most narrative value), supports lowest
  (most redundant). This is the cross-domain retrieval moat the business
  thesis depends on. Can be disabled via `enable_graph_expansion=False`
  for benchmarking.

- **BVCS revision regenerates from scratch** — already resolved by an
  earlier commit (predates this document). `generate_draft()` accepts a
  `revision_notes` parameter and prepends it to the user message with
  an explicit "REVISION — the previous draft failed voice compliance.
  Address these specific issues:" framing. The earlier claim that this
  was broken was stale.

- **Content selector novelty stubbed at 1.0** — already resolved.
  `_novelty_score()` in `selector.py` reads from `draft_usage` table
  with `math.exp(-usage_count * decay_factor)` scoring. Publisher writes
  usage rows on every approved draft. Verified live (8 usage rows exist
  in the table after today's Boulder run).

- **HITL gates unverified** — now partially validated. One full run
  through gate 1 (outline review) and gate 2 (draft review) completed
  successfully. Seasoning gap remains per item 2 above.

These gaps are the real work remaining on the engine itself. Everything
else is business execution (GTM, website, outreach), not architecture.
