# Blueprint for an AI research and content engine

**The most effective architecture for this system is a dual-pipeline LangGraph design with a hybrid-coordination pattern**: a research pipeline using an orchestrator-worker topology (planner → parallel researchers → synthesizer → critic), feeding a parameterized content pipeline through a shared PostgreSQL/pgvector knowledge base, coordinated by Celery + Redis with scheduled runs plus priority event interrupts. The minimum viable version requires **six agents across both pipelines**, two human-in-the-loop interrupt points, and roughly **30–45 minutes of daily operator oversight** once calibrated. Total infrastructure cost sits at **$100–200/month** for a solo operator. This blueprint is derived from documented production systems at Anthropic, Exa, S&P Global/Kensho, and NVIDIA, augmented by open-source implementations (GPT-Researcher, Stanford STORM, LangChain Open Deep Research) and practitioner reports on what actually breaks.

What follows is the complete architecture — agents, state schemas, graph structures, HITL patterns, voice layer, ingestion pipeline, operator UI, and a week-by-week build sequence.

---

## The research pipeline: six agents, one graph

The research pipeline follows the **orchestrator-worker pattern** that Anthropic's production system validated (their multi-agent approach outperformed single-agent Claude Opus 4 by **90.2%** on internal evaluations). The pipeline has six nodes in a LangGraph `StateGraph`:

**Research Planner** receives a research directive (either scheduled topic scan or operator-initiated query), decomposes it into independent research tasks, and specifies for each task: the objective, required output format, search strategy, and scope boundaries. This mirrors Exa's production system, which dynamically generates parallel tasks based on query complexity and processes hundreds of queries daily. The planner uses structured output (Pydantic model) to emit a list of `ResearchTask` objects.

**Researcher agents** (parallel fan-out, 2–5 instances) each receive a single `ResearchTask` and execute it using web search tools (Tavily or Exa), academic APIs (Semantic Scholar), and source-specific crawlers. Each researcher returns structured findings — atomic claims with source citations, confidence scores, and evidence excerpts. Critically, following Anthropic's lesson, researchers receive only their task specification and cleaned outputs from other tasks, never intermediate reasoning from the planner. This prevents context pollution.

**Synthesizer** receives all researcher outputs and performs three operations: deduplication (semantic similarity > 0.90 triggers merge), conflict detection (using Natural Language Inference to identify contradictions between findings), and KB integration assessment (vector search against existing KB entries to determine whether each finding is novel, supporting, or contradicting). The output is a structured list of `ProposedFinding` objects tagged with `new`, `supporting`, or `contradicting` status.

**Critic** evaluates each proposed finding against a hallucination rubric: Is the claim grounded in the cited sources? Does the confidence score match the evidence strength? Are there obvious logical gaps? This implements the Self-RAG grading pattern documented in production LangGraph systems — the critic uses an LLM to score groundedness and returns a pass/fail with reasoning for each finding. Findings that fail are routed back to a researcher for additional evidence gathering, with a maximum of two retry cycles to prevent infinite loops.

**Human Review Gate** uses LangGraph's `interrupt()` function to pause the pipeline and surface proposed findings to the operator. The interrupt payload includes the finding text, all source citations, confidence scores, tags, any contradiction flags, and the critic's assessment. The operator approves, rejects, edits, or requests more research via `Command(resume=...)`. This is one of two mandatory HITL touchpoints.

**KB Writer** takes approved findings and writes them to PostgreSQL — inserting new `findings` rows, creating `manifestation` records linking to source evidence, establishing `finding_relationships` with typed edges, and generating pgvector embeddings for similarity search.

The state schema for the research pipeline:

```python
class ResearchState(TypedDict):
    directive: str                           # Research topic or question
    tasks: list[ResearchTask]                # Decomposed research tasks
    raw_findings: Annotated[list[RawFinding], operator.add]  # From researchers
    proposed_findings: list[ProposedFinding]  # After synthesis
    critic_results: list[CriticAssessment]   # After critique
    approved_findings: list[ApprovedFinding]  # After human review
    retry_count: int                         # Prevent infinite loops
    status: str                              # Pipeline status tracking
```

The graph wiring uses **Command-based routing** (the pattern LangChain now recommends over conditional edges) so each node explicitly specifies its successor based on internal logic. The planner fans out to parallel researchers using LangGraph's `Send()` API. The critic routes back to researchers on failure or forward to the human review gate on pass.

LangGraph's **PostgresSaver** checkpointer persists state at every super-step boundary. This means if the pipeline fails at the synthesizer, it resumes exactly there — not from the beginning. The same checkpointer enables the human review gate to pause for hours or days and resume on a different machine. The checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) live in the same PostgreSQL instance as the KB, using connection pooling via `psycopg_pool.ConnectionPool` with `max_size=10`.

---

## What breaks in production research pipelines

Production practitioners report a consistent set of failure modes that don't appear in prototypes. **Rate limit cascades** are the most common: when an LLM provider returns 429 at step 7 of a workflow, the entire pipeline crashes and restarts from step 1 unless checkpointing and per-node retry policies are configured. LangGraph's built-in `RetryPolicy(max_attempts=3, initial_interval=1.0)` with exponential backoff handles transient failures, but rate limits across multiple concurrent researchers require a queue-per-domain architecture.

**The supervisor "telephone" problem** accounts for significant accuracy drops. LangChain's own benchmarks found that supervisor agents paraphrase sub-agent responses incorrectly, adding **30%+ latency** and introducing errors. The mitigation is direct: researchers write findings to structured state fields (not conversational messages), and the synthesizer reads structured data rather than interpreting natural language summaries.

**Silent LLM failures** are the most dangerous production issue. The agent doesn't crash — it makes the wrong call and moves on. A researcher retrieves an irrelevant source, extracts a plausible-but-wrong claim, and the pipeline propagates it. The critic node exists specifically to catch this, but the critic itself can fail silently. The defense-in-depth approach is: structured output validation at every node (Pydantic models that reject malformed data), source-claim verification in the critic, and human review as the final gate.

**State bloat** becomes a real problem with research pipelines. If each researcher returns full-text source documents in state, the checkpointer saves the entire state at every super-step — creating GB-scale checkpoint tables within days. The fix is to store large artifacts (full documents, PDFs, raw HTML) in external storage and pass only URLs and excerpts through state. Message trimming using LangGraph's `RemoveMessage` pattern caps conversation history.

**Agent drift** — documented in a 2026 paper (arXiv 2601.04170) — shows that **detectable degradation emerges after a median of 73 interactions**, accelerating over time. At 500 interactions, financial analysis agents showed 53.2% drift. The mitigation for a long-running research engine is periodic checkpoint resets and episodic memory consolidation (compressing interaction histories into summaries at regular intervals).

---

## The content pipeline: parameterized, brand-aware, eight stages

The content pipeline runs independently from the research pipeline, connected only through the shared KB. It uses a single LangGraph `StateGraph` that is invoked once per brand per publishing cadence — not four separate graphs. **Brand voice is a parameter, not a separate agent**, following the pattern used by Jasper, Typeface, and HubSpot in production multi-brand systems.

The eight nodes:

1. **Editorial Calendar Trigger** — Reads the brand's publishing schedule and topic queue. Determines what this issue should cover based on the brand's topic tags, what's new in the KB since the last issue, and any operator-specified themes.

2. **KB Retriever** — Queries pgvector with multi-query retrieval (generating 3–5 query variations from the editorial brief, retrieving for each, deduplicating). Filters by brand relevance tags and applies **decay-weighted scoring**: `0.7 × semantic_similarity + 0.3 × exp(-0.693 × age_days / 14)`. This solves the stale-KB problem where 18-month-old findings retrieve as well as yesterday's, despite being outdated. Also filters against a `content_generation_log` table to deprioritize findings already used in previous issues.

3. **Content Selector** — An LLM ranks retrieved findings by novelty, narrative potential, and audience relevance for this specific brand. Selects 5–8 findings to feature and identifies a narrative arc connecting them.

4. **Outline Generator** — Produces a structured outline: hook angle, section headings, key findings per section, CTA placement. **This is the second mandatory HITL interrupt point.** The operator reviews the outline and can redirect the narrative before the system generates 2,000 words in the wrong direction. This follows the pattern from the Towards Data Science LangGraph 201 tutorial, which places human checkpoints at query formulation and after initial research — the content-pipeline equivalent is outline approval.

5. **Draft Generator** — Generates the full newsletter with the brand's voice profile loaded as a structured system prompt. The voice profile is a YAML document specifying formality scale (1–5), humor scale, average sentence length, reading level, vocabulary rules (preferred terms, banned words), structural patterns (opener style, closer style), and 3–5 few-shot examples of on-brand writing. The same node generates platform-specific social posts using `tone_by_channel` parameters from the voice spec.

6. **Voice Compliance Scorer** — Scores the draft against the voice profile across five dimensions: vocabulary compliance, sentence structure, tone alignment, terminology usage, and formality level. Produces an overall Brand Voice Consistency Score (BVCS). If the score falls below 70 and fewer than 3 revision attempts have occurred, routes to a revision node that regenerates with corrective instructions. If 3 attempts have been exhausted, forces to human review regardless.

7. **Human Review Gate** — Interrupt with the full draft, voice score, source attributions (each paragraph annotated with contributing KB findings), and social post variants. The operator approves, edits, requests revision with notes, or rejects.

8. **Publisher** — Pushes approved content to beehiiv via the Create Post API endpoint (`POST /publications/{pub_id}/posts`), using either the `blocks` format for structured content or `body_content` for HTML. Creates the post with `status: "draft"` initially, then schedules via `scheduled_at` timestamp on operator confirmation. The beehiiv Enterprise plan is required for API post creation (currently in beta).

The content pipeline state:

```python
class ContentState(TypedDict):
    brand_id: str
    brand_voice_profile: dict              # Loaded from config at invocation
    editorial_brief: dict                  # Topic, publish date, constraints
    kb_findings: list[dict]                # Retrieved from KB
    selected_findings: list[dict]          # After ranking
    outline: str                           # Structured outline
    outline_approved: bool                 # HITL checkpoint
    draft: str                             # Full newsletter text
    social_posts: dict                     # {platform: content}
    voice_score: float                     # BVCS
    revision_count: int                    # Cap at 3
    source_attributions: list[dict]        # Finding→paragraph mapping
    beehiiv_post_id: Optional[str]         # After publish
    status: str
```

---

## Shared knowledge base and pipeline coordination

The KB schema maps directly to the user's design: five root anxiety nodes, seven Panksepp circuits as substrate, findings as interpretive claims, manifestations as citable evidence, inter-finding relationships with six typed edges, and contradiction resolution records. All tables live in PostgreSQL with pgvector handling embedding storage and similarity search via HNSW indexes.

**Pipeline coordination uses the hybrid pattern** — scheduled runs via Celery Beat plus priority event interrupts via PostgreSQL LISTEN/NOTIFY. The research pipeline runs on a 4-hour cycle. Each brand's content pipeline runs on its own schedule (staggered 1–2 hours apart to prevent resource contention and allow sequential review). When the research pipeline writes a finding with `importance_score > 0.8`, a PostgreSQL trigger fires `pg_notify('new_kb_entry', ...)`, and a Python listener conditionally enqueues a priority content generation task for relevant brands.

```sql
CREATE OR REPLACE FUNCTION notify_new_kb_entry()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify('new_kb_entry', json_build_object(
    'entry_id', NEW.id,
    'topic', NEW.topic_tag,
    'importance_score', NEW.importance_score
  )::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

**State isolation is critical.** The research pipeline and content pipeline each maintain their own state tables (`research_pipeline_state`, `content_pipeline_state`). The KB is the only shared coupling point, and the data flow is unidirectional: research writes, content reads. The content pipeline uses a **high-water mark pattern** — tracking its own cursor (`last_kb_entry_processed`) rather than reading the research pipeline's state.

Celery runs three separate queues: `research` (1 worker), `content` (2 workers), and `priority` (shared with content workers). Separate workers per queue ensure research processing can't block content generation. `task_acks_late=True` and `worker_prefetch_multiplier=1` ensure tasks aren't lost on worker crash.

PostgreSQL with pgvector handles concurrent reads and writes well at this scale. Benchmarks show pgvector achieving **1,589 QPS at 90% recall** when searching 50M embeddings, with predictable performance under concurrent load due to PostgreSQL's process-based architecture. For a KB of 10K–100K entries with 1536-dimensional embeddings, the HNSW index fits easily in ~60–600MB of `shared_buffers`. The version 0.8.0 iterative scan feature solves the overfiltering problem when combining vector similarity with metadata filters.

---

## The voice layer specification

The minimum viable voice specification that produces consistent output across four brands is a structured YAML document per brand, loaded at generation time:

```yaml
brand_voice_profile:
  identity:
    brand_name: "Brand X"
    personality_traits: ["contrarian", "data-driven", "accessible"]
  voice_parameters:
    formality_scale: 3          # 1=casual, 5=formal
    humor_scale: 2
    sentence_length_avg: 14     # words
    paragraph_length_max: 4     # sentences
    reading_level: "Grade 8-10"
    use_contractions: true
  vocabulary:
    preferred_terms: {"artificial intelligence": "AI", "utilize": "use"}
    banned_words: ["synergy", "leverage", "game-changing"]
  tone_by_channel:
    newsletter: {formality: 3, humor: 3, directness: 5}
    linkedin: {formality: 4, humor: 2, directness: 3}
    x: {formality: 2, humor: 4, directness: 5}
    substack_notes: {formality: 2, humor: 3, directness: 4}
  examples:
    on_brand: ["3-5 paragraphs of exemplary content"]
    off_brand: ["3-5 paragraphs showing what to avoid"]
```

Research across enterprise content platforms confirms: **don't tell the AI to "write in brand voice" — encode voice as structured, measurable data.** The four-layer implementation is: structured system prompt with the voice profile → dynamically selected few-shot examples (best-performing pieces for similar topics) → rule-based post-generation validators (banned word check, sentence length, formality scoring) → engagement-driven feedback loop (findings in high-performing newsletters boost the patterns that produced them).

Voice drift detection uses a weekly **Brand Voice Consistency Score** across all output. The primary causes of drift in practice are: attention decay in transformers (persona prompts at the start of context windows receive less attention as the window fills), model provider updates silently changing baseline behavior, and prompt erosion as content briefs become more complex. The correction protocol: periodically reinject the persona prompt in fresh context, monitor BVCS weekly, alert on >10% deviation, and retrain few-shot examples with recent on-brand content.

**Prompting is sufficient for four brands.** Fine-tuning makes economic sense only at thousands of pieces monthly. The cost delta between well-structured prompting (which uses ~500 extra tokens per generation for the voice profile) and fine-tuning (which requires 200–500+ training examples per brand and retraining on model updates) strongly favors prompting at newsletter scale.

---

## Ingestion architecture: triage, extract, deduplicate, integrate

The ingestion subsystem feeds the research pipeline and operates continuously. It uses a **triage-first pattern** that routes incoming URLs to the appropriate tool based on content complexity:

- **Simple web pages** → Jina Reader (`r.jina.ai/URL` → clean Markdown)
- **JavaScript-heavy sites** → Firecrawl or Crawl4AI (headless browser rendering)
- **Academic papers** → Semantic Scholar API (primary: 225M+ papers, free with API key at 100 req/sec) + arXiv OAI-PMH (daily incremental harvest)
- **Social platforms** → Apify Actors (X/Twitter at ~$0.0005/trend, LinkedIn via dedicated scrapers)
- **RSS feeds** → `feedparser` library on schedule
- **PDFs** → PyMuPDF for text extraction, Nougat for complex layouts

Deduplication operates at three levels: **exact** (SHA-256 hash of normalized text — catches byte-identical duplicates), **near-duplicate** (MinHash with Locality-Sensitive Hashing — catches reformatted versions), and **semantic** (embedding cosine similarity > 0.90 in pgvector — catches paraphrased content). The `ingested_content` table enforces `UNIQUE(source_id, content_hash)` to prevent reprocessing.

When a new document clears dedup, the extraction pipeline runs: Markdown conversion → LLM-based structured extraction (GPT-4o-mini extracting atomic claims with JSON schema output) → chunking at 512 tokens with 100-token overlap → embedding generation → KB integration. Integration checks each extracted claim against existing KB findings using vector similarity. Matches above 0.85 cosine similarity trigger an NLI check: entailment increments evidence count and boosts confidence; contradiction flags for the contradiction dashboard.

**Rate limits break first** as source volume scales. At ~10K pages/day across 50+ sources, individual domains start returning 429s. The mitigation is per-domain throttling in Celery task queues (`rate_limit='10/m'` per domain), exponential backoff with jitter on errors, and staggered scheduling that distributes requests across the full allowed window.

**Realistic cost estimate for a solo operator**: Crawl4AI self-hosted ($0 software + $20–50/mo VPS), Tavily search ($30/mo for 4K searches), Semantic Scholar + arXiv (free), Apify Starter ($29/mo), OpenAI API for extraction + synthesis ($50–100/mo), embeddings ($5–10/mo), PostgreSQL self-hosted ($0 on same VPS), VPS for pipeline orchestration ($20–40/mo). **Total: $150–260/month.**

---

## Human-in-the-loop: two gates, 45 minutes daily

The system has exactly **two mandatory HITL interrupt points**, both using LangGraph's `interrupt()` function with PostgresSaver checkpointing:

1. **Research review gate** — After the critic passes proposed findings, before KB write. The operator sees each finding with its claim text, source citations, confidence score, tags, critic assessment, and any contradiction flags. Actions: approve, reject, edit, request more research. This is implemented as a batch review — findings accumulate overnight and the operator processes the queue in the morning session.

2. **Content review gate** — After voice compliance scoring passes, before publish. The operator sees the full newsletter draft with source attributions (each paragraph annotated with contributing KB findings), the voice compliance score, and social post variants. Actions: approve for send, edit inline, request revision with notes, reject.

LangGraph's `interrupt()` works by raising a special `GraphInterrupt` exception, causing the runtime to save complete graph state to the PostgreSQL checkpointer and mark the thread as interrupted. **No resources are consumed while waiting.** The pipeline can resume hours, days, or weeks later on a different machine. The resume pattern:

```python
def research_review(state: ResearchState) -> Command[Literal["kb_writer", END]]:
    decision = interrupt({
        "findings": state["proposed_findings"],
        "critic_results": state["critic_results"],
        "action": "Review proposed findings. Approve, reject, or edit each."
    })
    approved = [f for f in decision["findings"] if f["status"] == "approved"]
    return Command(
        update={"approved_findings": approved},
        goto="kb_writer" if approved else END
    )
```

Critical implementation rules: never wrap `interrupt()` in try/except (it works via exception), keep interrupt calls in consistent order within a node (matching is index-based), and ensure any code before `interrupt()` is idempotent (the node restarts from the beginning on resume).

**Rubber-stamping is the most dangerous failure mode.** The review interface implements five anti-fatigue patterns drawn from documented production cases:

- **Batch approve for high-confidence items** (>90%) with a single action, but require individual review for items below 85%. This prevents fatigue on obvious approvals without compromising quality on edge cases.
- **Delayed disclosure** — Show the newsletter draft before revealing the voice compliance score, forcing the operator to form an independent impression before anchoring to the AI's assessment.
- **Random spot-checks** — Periodically present a finding the system has already validated as correct but present it as "pending." If the operator rubber-stamps without review, surface a gentle verification notification. This keeps review skills sharp.
- **Decision impact tracking** — Show engagement data flowing back: "3 findings you approved last week appeared in newsletters with 42% open rate (above your average)." This gives the operator evidence that their review work matters.
- **Progressive trust escalation** — New content types start in full-review mode. As the operator's rejection rate drops below 5% for a category, offer to auto-approve that category with periodic spot-checks. This lets the system earn autonomy while maintaining a regression mechanism if quality degrades.

**Realistic daily time commitment in steady state: 30–45 minutes.** This breaks down as: 10–15 minutes on the research review queue (processing 10–20 findings, batch-approving high-confidence items), 10–15 minutes on content review (1–2 newsletter drafts), 5 minutes on contradiction triage (if any), and 3–5 minutes on a performance check. A new system will require 2–3 hours daily during the first 30–60 days of calibration. Time drops as trust data accumulates and auto-approve patterns are identified.

---

## The operator interface: five screens, queue-first design

The operator UI is built on **FastAPI (backend) + React (frontend) + PostgreSQL**, using the FastAPI full-stack template as a starting point. React is necessary (not Streamlit or Gradio) because the system requires rich text editing, split-pane layouts, graph visualization, inline annotations, and real-time queue updates — all of which are difficult or impossible in Streamlit's reactive rerender model.

**Landing page**: The default view is not a green "all clear" dashboard. It is a **ranked work queue** showing items requiring decisions: X new findings pending review, Y newsletters in draft, Z contradictions flagged, with urgency indicators. The operator's job is to work the queue.

**Research review screen**: Prioritized card queue sorted by `confidence_gap × topic_relevance × recency`. Each card shows claim text, confidence score (color-coded: green ≥85%, amber 60–84%, red <60%), inline source citations with clickable links, tags, contradiction flags, and a collapsible agent reasoning trace. Actions: approve, reject, edit, merge with existing entry, request more research. A right sidebar shows related existing KB entries for novelty assessment. Backend: `GET /api/findings/pending`, `PATCH /api/findings/{id}`.

**KB browser**: Three views — graph (Cytoscape.js with FCose layout, nodes sized by confidence, colored by topic cluster, edges colored by relationship type), list (searchable/filterable table), and cluster (grouped by topic with expandable sections). Progressive disclosure: start at cluster level, click to expand to individual findings. Finding detail panel shows full text, all sources, confidence history, which newsletters used this finding, and engagement data from those uses. Backend: `GET /api/kb/graph?cluster={id}&depth={n}`, `GET /api/kb/search?q={text}&semantic=true`.

**Content review screen**: Split-pane layout — newsletter preview (60% width) on the left, source attribution panel (40%) on the right. Each paragraph has margin annotations showing contributing KB findings; hovering highlights both the text passage and the corresponding finding card. Voice compliance score displayed as a prominent badge after the operator reads the draft (delayed disclosure). Diff view available for comparing revision versions. Social post variants shown below. Built with TipTap for rich text editing, `react-diff-viewer-continued` for version comparison. Backend: `GET /api/content/drafts?brand={id}`, `PATCH /api/content/drafts/{id}`, `POST /api/content/drafts/{id}/approve`.

**Contradiction dashboard**: Side-by-side comparison of conflicting findings. Left panel and right panel each show full finding text, confidence score, sources, date, and usage count. Conflicting text spans are highlighted with connecting lines between panels. AI-generated explanation of the specific contradiction with its own confidence score. Resolution actions: keep A/archive B, keep B/archive A, keep both with context tags, merge into synthesized finding, defer for more research, dismiss as false positive. Backend: `GET /api/contradictions/active`, `POST /api/contradictions/{id}/resolve`.

**Performance feedback panel**: Time-series charts (Recharts) showing open rates, CTR, and subscriber growth per brand. Topic engagement heat map (topics vs. brands, color intensity = engagement). Finding effectiveness scatter plot (confidence score vs. average engagement when used — revealing overvalued and undervalued findings). The feedback loop runs as a weekly Celery task: pull beehiiv analytics 48–72 hours post-send, map engagement metrics to source KB findings via the `content_generation_log`, adjust finding confidence scores (+2–5 points for top-quartile newsletter appearances, -1–2 for bottom-quartile, slow decay for unused findings).

---

## Complete agent roster and responsibilities

| Agent | Pipeline | Responsibility | LLM | Tools |
|-------|----------|---------------|-----|-------|
| **Research Planner** | Research | Decomposes directives into parallel research tasks | GPT-4o / Claude Sonnet | None (reasoning only) |
| **Researcher** (×2–5) | Research | Executes individual research tasks, returns structured findings | GPT-4o-mini | Tavily/Exa search, Semantic Scholar API, web fetch |
| **Synthesizer** | Research | Deduplicates, detects conflicts, assesses KB integration | GPT-4o | pgvector similarity search, NLI model |
| **Critic** | Research | Validates groundedness, scores evidence strength | GPT-4o | Source verification tools |
| **Content Generator** | Content | Generates outlines, drafts, and social posts with brand voice | GPT-4o / Claude Sonnet | KB retrieval, voice profile loader |
| **Voice Scorer** | Content | Evaluates voice compliance, produces BVCS | GPT-4o-mini | Rule-based validators |

Note: The Research Planner and Synthesizer could be merged into a single orchestrator node for the MVP, reducing to **five agents**. The KB Writer and Publisher are deterministic nodes (not LLM-powered agents), as are the KB Retriever, Content Selector, and Editorial Calendar Trigger.

---

## Build sequence: what gets built first

**The minimum viable version that proves the core loop works end-to-end requires three things**: a research pipeline that can ingest a source and produce an approved KB entry, a content pipeline that can query that entry and produce a newsletter draft, and a human review interface that lets the operator approve both. Everything else is optimization.

**Phase 1 — Core loop (weeks 1–4):**
- Week 1: PostgreSQL schema (findings, manifestations, relationships, contradictions), pgvector setup, basic FastAPI endpoints, React shell with landing page
- Week 2: Research pipeline MVP in LangGraph — Planner + single Researcher + Synthesizer + KB Writer, with `interrupt()` before KB write. Use MemorySaver initially, PostgresSaver by end of week
- Week 3: Content pipeline MVP — KB Retriever + Draft Generator (with hardcoded voice profile) + Publisher stub, with `interrupt()` before publish. Build research review screen and content review screen in React
- Week 4: Wire Celery + Redis for scheduling. Connect beehiiv API. Run the full loop: scheduled research → human approval → KB write → scheduled content generation → human approval → beehiiv draft

**Phase 2 — Multi-agent and multi-brand (weeks 5–8):**
- Week 5: Parallel researcher fan-out (2–3 researchers). Add Critic node. Upgrade to structured source quality scoring
- Week 6: Voice layer — implement YAML voice profiles for all 4 brands, voice compliance scorer, revision loop
- Week 7: KB browser with Cytoscape.js. Contradiction dashboard. Finding relationship management
- Week 8: Ingestion subsystem — source registry, triage routing, dedup pipeline, Semantic Scholar integration

**Phase 3 — Feedback loops and polish (weeks 9–12):**
- Week 9: beehiiv analytics integration, finding effectiveness scoring, confidence feedback loop
- Week 10: Anti-fatigue patterns (spot-checks, delayed disclosure, progressive trust escalation)
- Week 11: Social post generation (X, LinkedIn, Substack Notes variants), editorial calendar automation
- Week 12: Performance optimization, cost monitoring via LangSmith, load testing, documentation

**What gets deferred**: Fine-tuning for brand voice (prompting is sufficient at this scale), mobile-responsive review interface, multi-user support, automated A/B testing of voice parameters, and real-time streaming of research results (batch is fine for a solo operator).

---

## Infrastructure and local development setup

The entire system runs on a single VPS for development and early production:

```yaml
# docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    volumes: [pgdata:/var/lib/postgresql/data]
    ports: ['5432:5432']
  redis:
    image: redis:7-alpine
    command: ['redis-server', '--appendonly', 'yes']
  worker-research:
    build: .
    command: celery -A engine worker -Q research -c 1
  worker-content:
    build: .
    command: celery -A engine worker -Q content,priority -c 2
  beat:
    build: .
    command: celery -A engine beat
  api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
  frontend:
    build: ./frontend
    ports: ['3000:3000']
```

**Monthly costs**: VPS 4GB RAM/2 vCPU ($20–40), OpenAI API ($50–100), Tavily search ($30), Apify ($29), self-hosted PostgreSQL/Redis ($0 on same VPS). **Total: $130–200/month.** The primary cost variable is LLM usage — multi-agent systems consume roughly **15× more tokens than single chat interactions** (per Anthropic's data), so extraction and synthesis should use GPT-4o-mini ($0.15/1M input tokens) wherever possible, reserving GPT-4o or Claude Sonnet for planning, critique, and final content generation.

---

## What is proven versus plausible versus speculative

**Proven** (documented in production systems): The orchestrator-worker multi-agent pattern works at scale (Anthropic, Exa, Kensho). LangGraph's interrupt/resume pattern is production-ready with PostgresSaver. Parameterized brand voice via structured system prompts produces consistent output across multiple brands (Jasper, Typeface, HubSpot). Decay-weighted retrieval scoring solves the stale-KB problem. Parallel researcher fan-out cuts research time by up to 90%. Agent drift emerges after ~73 interactions and requires periodic resets.

**Plausible** (supported by strong analogies but not documented at exactly this configuration): Running four brand content pipelines from a single shared KB via Celery scheduling with priority interrupts. Using pgvector for both KB storage and dedup similarity search in the same database. The specific five-screen operator UI design (no documented case of exactly this interface, but each screen follows established patterns from adjacent domains).

**Speculative** (reasonable design choices without direct precedent): The engagement-to-confidence feedback loop (beehiiv analytics adjusting KB finding confidence scores) — the mechanism is sound but no documented system feeds newsletter engagement data back into a research KB's confidence scoring. The specific anxiety-node/Panksepp-circuit KB schema as an organizing principle for AI research synthesis — this is domain-specific and untested at this abstraction level. The 30–45 minute daily oversight target for a four-brand operation — this is extrapolated from solo operator reports managing 8–12 client accounts with AI assistance, but the specific research-to-content workflow hasn't been benchmarked.

The architecture is designed so the proven components carry the system while the plausible and speculative elements can be validated incrementally during the Phase 1 core loop — before committing to the full build.