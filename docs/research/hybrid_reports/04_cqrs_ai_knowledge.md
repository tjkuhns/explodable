# CQRS for AI knowledge systems: a pattern without a name

The architecture you describe — one Postgres write model projecting into pgvector embeddings, a graph read model, a compiled wiki index, a CAG XML cache, and a cluster index — **has no formal publication as a named pattern**. After searching academic databases, engineering blogs, conference proceedings, and open-source repositories across all five of your questions, the core finding is clear: you are operating at the intersection of well-established distributed systems architecture (CQRS, event sourcing, polyglot persistence) and emerging AI knowledge management practices, and **nobody has yet bridged these two bodies of work in a single publication**. The closest analogs exist as fragments — LangChain's multi-representation indexing, Notion's CDC fan-out architecture, Karpathy's compiled wiki pattern, and Anthropic's prompt caching documentation — but none assembles the complete picture you've built.

What follows is a precise accounting of what exists, what doesn't, and where published guidance ends and engineering inference begins.

---

## No one has named the "one write model, N read projections for LLM access" pattern

The most surprising gap in the literature is the complete absence of CQRS terminology in AI/RAG architecture discourse. Searching for "CQRS RAG," "CQRS knowledge base AI," "command query separation RAG," "polyglot persistence LLM," and "multi-representation knowledge store" yields **zero direct results** combining these concepts. The AI infrastructure community and the CQRS/DDD community have not yet cross-pollinated.

**Closest published matches, ranked by relevance:**

**Zilliz's CQRS glossary entry** applies CQRS to a single vector database (Milvus), separating vector insert commands from similarity search queries — but this is CQRS *within* one store, not across heterogeneous read models. **de Curtò et al. (2025)** in *Procedia Computer Science* formally study polyglot persistence (PostgreSQL + MongoDB + Neo4j + Redis) with LLMs, but with inverted data flow — the LLM queries *into* the databases rather than databases feeding LLM context. **LangChain's Multi-Vector Retriever** creates multiple representations of documents (summaries for retrieval, full text for synthesis) and is conceptually a read-model projection pattern, but lacks a formal write model and uses only vector-based representations. **Microsoft Azure AI Search's Knowledge Store** uses the term **"projections"** explicitly — table projections, object projections, file projections — to describe different representations of enriched content, making it structurally identical to CQRS read models, though Microsoft never uses CQRS framing in this context.

The strongest conceptual match from traditional software architecture is **Vladik Khononov's "Tackling Complexity in CQRS" (2017)**, which explicitly describes supporting "different querying models (search, graph, documents)" as a primary CQRS use case, with state-based projections as an alternative to event sourcing. This predates the AI era but maps directly onto your architecture. **GraphRAG approaches** (Neo4j, Microsoft Research, Zep's Graphiti) implicitly maintain multiple heterogeneous read representations — vector index + knowledge graph + BM25 full-text — but treat them as complementary retrieval strategies rather than formal read model projections from a canonical source.

**Verdict: No known publication — engineering inference.** Your architecture is a legitimate synthesis of established CQRS principles with modern AI knowledge access patterns. The concept exists in fragments across multiple communities, but no one has formalized or named it.

---

## Consistency across heterogeneous AI knowledge stores has one strong academic anchor

The multi-store consistency challenge — updating vector embeddings, graph, wiki index, XML cache, and cluster index when a finding changes — has more published coverage than the CQRS framing, though no single work addresses all five representations.

**The strongest academic reference** is **Prajapati's "LiveVectorLake" (arXiv:2601.05270, January 2025)**, which introduces a real-time versioned knowledge base architecture with content-addressable chunk-level CDC using SHA-256 hashing, dual-tier storage separating hot vector indices from cold versioned storage, and **ACID consistency across heterogeneous backends via write-ahead logging with compensating transactions**. It achieves 10–15% re-processing versus 100% for full re-indexing, with sub-100ms retrieval. However, it addresses only two stores (vector + data lake), not five.

The most actionable practitioner work comes from **Adrien Obernesser at DBI Services (February 2026)**, who published a detailed three-tier architecture for event-driven embedding versioning with pgvector. The key insight: using Debezium's before/after images to determine if a change warrants re-embedding **eliminates 60–80% of unnecessary embedding API calls**. He provides SQL schemas, trigger code, and a monitoring framework covering both infrastructure health (queue depth, latency) and retrieval quality (precision@k, nDCG). **RisingWave's April 2026 blog** demonstrates the same CDC-to-embedding pipeline as a streaming materialized view, calculating that for a corpus with **1% daily change rate, streaming is approximately 100× cheaper** on embedding API costs than full batch re-indexing.

**The closest industry analog to your full architecture is Notion's data lake**, documented by Thomas Chow and Nathan Louie. Notion's production system is exactly the "single write model → fan-out to multiple heterogeneous read models" pattern: **PostgreSQL (480 shards) → Debezium CDC → Kafka → fan-out to Snowflake, Elasticsearch, Vector Database, and Key-Value stores**. They handle 90% update-heavy workloads with ingestion latency reduced from days to minutes. Critically, Notion has *not* published how they ensure consistency across these downstream stores — their blog focuses on the data lake infrastructure, not cross-store consistency guarantees.

The recommended pattern for your system, assembled from these sources, is the **Transactional Outbox + CDC fan-out**:

| Component | Pattern | Source |
|---|---|---|
| Write → Event stream | Transactional Outbox + Debezium CDC | Chris Richardson; Debezium docs |
| Event distribution | Kafka topic, one consumer group per read model | Confluent; Notion case study |
| Vector refresh | CDC → change significance filter → selective re-embedding | DBI Services (Obernesser 2026) |
| Graph refresh | CDC consumer → graph mutation | Polyglot persistence literature |
| Wiki/markdown refresh | CDC consumer → incremental compilation | Karpathy LLM KB pattern |
| CAG XML invalidation | CDC consumer → full cache rebuild | Standard cache-aside; Anthropic docs |
| Consistency model | Eventual consistency with per-read-model lag monitoring | CQRS (Fowler); LiveVectorLake |

**Verdict: Partially published.** The CDC-to-vector pipeline is well-documented. The CDC fan-out pattern is established in distributed systems and demonstrated at scale by Notion. But consistency guarantees across all five of your specific representation types (vector + graph + wiki + XML cache + cluster index) remain **no known publication — engineering inference**.

---

## At 300–5,000 records, Postgres materialized views win decisively over separate stores

This question has the clearest published consensus of all five. Multiple authoritative sources — including a **Postgres Core Team member**, major Postgres-as-a-service companies, and independent practitioners — converge on the same answer: at your scale, use Postgres for everything.

**Sophie Alpert's "Materialized views are obviously useful" (August 2025)** provides the strongest argument against separate stores. She walks through a realistic scenario where a team starts with a SQL query, adds Redis for performance, then must add cache invalidation, incremental updates, and eventually Kafka for consistency — producing thousands of lines of fragile code that a single materialized view declaration replaces. Your cluster index (anxiety_tag × cultural_domain grouping) is a textbook materialized view use case. At 5,000 records, `REFRESH MATERIALIZED VIEW CONCURRENTLY` takes milliseconds.

**Dave Page (Postgres Core Team member, creator of pgAdmin)** wrote in his 2025 RAG server series: "If you're already running PostgreSQL — and let's face it, you probably are — adding RAG capabilities to your existing infrastructure makes a lot of sense." **Supabase** explicitly markets unified vector + relational storage. **Neon** built `pgrag`, an extension handling the entire RAG pipeline without leaving psql. **Christopher Samiullah** invokes Dan McKinley's "Choose Boring Technology" essay, arguing you "don't have to spend one of your precious innovation tokens on a vector DB."

The published scale thresholds are consistent: **pgvector is adequate for under 5 million vectors** (Encore, 2026), and with HNSW indexes it matches or beats dedicated vector databases at 1M scale. Even Qdrant — a competing vector database vendor — concedes that pgvector works when your dataset is under ~1M vectors and Postgres is already central to your stack. You are **200–3,000× below these thresholds**.

RisingWave's 2026 architecture blog offers a powerful reframe: **"Think of embeddings as a materialized view over raw data."** This conceptual lens directly supports keeping your embeddings, cluster index, and wiki index as Postgres materialized views rather than maintaining separate stores.

**When to migrate to separate stores** (from published sources): vector count exceeds ~1M, high-concurrency filtered vector search with complex metadata predicates, multi-tenant isolation requirements, or team growth requiring independently scalable search infrastructure. None of these conditions apply at your scale.

**Verdict: Published guidance — strong consensus.** No source specifically addresses "materialized views for anxiety_tag × cultural_domain cluster indexes," but the general guidance is unambiguous: at 300–5,000 records, Postgres materialized views are optimal over separate file/cache stores.

---

## Event sourcing for AI knowledge bases is being reinvented under other names

No publication explicitly titled "Event Sourcing for AI Knowledge Base Versioning" exists. But the pattern is independently emerging from at least four directions, none of which use the event sourcing label.

**Karpathy's LLM Wiki pattern (April 2026)** is structurally closest to event sourcing: an immutable `raw/` layer (source documents never modified), a `wiki/` layer of LLM-generated pages, and critically, an **append-only `log.md` recording every ingest, page update, and contradiction found**. Git provides version history. This architecture — immutable inputs, append-only operation log, derived views rebuilt from source — maps directly onto event sourcing's core abstractions.

**Zep's Graphiti framework** (11K+ GitHub stars) implements temporal context graphs where **facts have validity windows — when they became true and when they were superseded — rather than being deleted**. Every entity traces back to source "episodes" (the equivalent of events). This is append-only, temporal, and provenance-tracked — event sourcing by any other name.

**LanceDB's time-travel RAG tutorial** demonstrates point-in-time retrieval: querying any historical version of a knowledge base for A/B testing, regulatory auditing, and instant rollback. The underlying Lance format uses append-only columnar storage. **Clamp**, an open-source tool, provides Git-like commands (`clamp commit`, `clamp checkout`, `clamp history`) for vector database versioning, enabling rollback of "poisoned RAG indexes instantly without re-embedding."

**Krystian Safjan's "Version Your Vectors" (February 2026)** is the clearest articulation of *why* RAG systems need event sourcing capabilities — debugging retrieval drift, data drift detection, **EU AI Act compliance** (enforcement August 2026), A/B testing embedding models with rollback, and counterfactual replay against historical index states. He defines a comprehensive "version manifest" including corpus hash, chunk strategy, embedding model version, and prompt template version.

At the infrastructure level, **lakeFS (which acquired DVC in November 2025)** provides Git-like branching, commits, and rollbacks for data at petabyte scale. A practitioner article describes using lakeFS to version the document store in a RAG system, storing commit hashes alongside embeddings in Qdrant. On the vendor side, **EventSourcing.ai** (by the native web GmbH) and **Akka's blog** ("Event Sourcing: The Backbone of Agentic AI" by Kevin Hoffman) explicitly connect event sourcing to AI — but focus on event sourcing as a data source *for* AI models, not event-sourcing the knowledge base *itself*.

**Verdict: No known publication under the event sourcing label — but the pattern is independently emerging.** The gap is the framing: nobody has connected well-established event sourcing from DDD/CQRS with AI knowledge base management as a unified architecture. The tools exist (lakeFS, LanceDB time-travel, Clamp, Graphiti), the need is documented (Safjan, EU AI Act compliance), and the pattern is being reinvented (Karpathy). Formally naming this connection represents a genuine contribution opportunity.

---

## CAG cache economics strongly favor your architecture at 115K tokens

This question has the most concrete published guidance, anchored by the **original CAG paper (Chan et al., arXiv:2412.15605, December 2024; ACM Web Conference 2025)** and **Anthropic's official prompt caching documentation**.

The CAG paper establishes that preloading all relevant documents into the LLM's context window and precomputing the KV cache eliminates retrieval entirely, matching or surpassing RAG on HotPotQA and SQuAD benchmarks for "manageable" knowledge bases. Your **~115K tokens is firmly in CAG territory** — well within Claude's context window and within the demonstrated effective range.

**Anthropic's current pricing** makes the economics stark. On Claude Sonnet 4.6, a **cache read costs $0.30/MTok versus $3.00/MTok for standard input — a 90% discount**. For your 115K-token cache:

| Scenario | Cost per request |
|---|---|
| No caching (standard input) | **$0.345** |
| Cache write (5-minute TTL, 1.25× base) | $0.431 |
| Cache write (1-hour TTL, 2× base) | $0.690 |
| Cache hit (read) | **$0.035** |

**Breakeven is just 2 queries within 5 minutes** (or 3 queries within 1 hour). Since the TTL resets on every cache hit, a steady query stream keeps the cache warm indefinitely. At 100 queries/day assuming one cache write, your daily cost drops from **$34.50 to approximately $3.90** — an 89% reduction.

The most actionable practitioner reference is **ProjectDiscovery's "How We Cut LLM Costs by 59%" (April 2026)**, which achieved a **91.8% cache hit rate on 9.8 billion tokens served from cache**. Their critical technique — the **"relocation trick"** — moves all dynamic content (timestamps, runtime variables, working memory) out of the cached system prompt into a `<system-reminder>` block appended as a user message. This keeps the knowledge base prefix byte-identical across requests. For your XML cache, this means: sort findings deterministically by ID, exclude version counters and timestamps from the cached block, and put any changing metadata in a tail section outside the cached prefix.

**Cache refresh at your scale is trivially cheap.** A full 115K-token rebuild costs ~$0.43 on Sonnet 4.6 with 5-minute TTL. Even 10 rebuilds per day cost only $4.30 — negligible against per-query savings. Anthropic's system **does not support partial cache updates** — any change to content within a cache breakpoint invalidates it entirely — but at your update frequency and cache write cost, full rebuilds are the correct strategy.

For the hybrid CAG+RAG question, a **tiered approach** is published in "Enhancing CAG with Adaptive Contextual Compression" (arXiv:2505.08261): cache stable knowledge as the foundation, trigger lightweight retrieval only for knowledge gaps. The decision boundary for switching from pure CAG to hybrid is when your KB exceeds the context window, update frequency becomes hourly or faster, or "lost-in-the-middle" quality degradation appears at your token count.

**Verdict: Mostly published.** Anthropic's pricing and TTL mechanics are documented. The CAG paper and practitioner case studies provide strong guidance. Cache refresh scheduling and XML structure optimization for cached prompts are **engineering inference**, not formally published — but the cost math is straightforward and the ProjectDiscovery relocation trick is production-validated at scale.

---

## What this research means for your architecture

Across all five questions, a consistent picture emerges. Your system implements a well-grounded architectural pattern that the industry has not yet named or formalized. The individual components — CQRS read projections, CDC-driven consistency, materialized views, temporal versioning, prompt caching — each have published foundations. But their **composition into a unified architecture for AI knowledge management is novel**.

Three specific opportunities stand out. First, at your scale of 300–5,000 findings, the published consensus overwhelmingly supports keeping everything in Postgres — materialized views for cluster indexes and wiki compilations, pgvector for embeddings, and CDC or triggers for event propagation. Second, your CAG cache economics are strongly favorable, with breakeven at just 2 queries and ~90% cost reduction at steady state. Third, the absence of formal publication means there is a genuine opportunity to document this pattern — particularly the CQRS framing for multi-representation AI knowledge stores and the event sourcing connection for KB versioning. The EU AI Act's August 2026 enforcement deadline will make auditability and temporal traceability requirements concrete, and your architecture is well-positioned to address them.

The closest published analog to your full system is Notion's Postgres → Debezium → Kafka → multi-store fan-out architecture, but even Notion hasn't published their cross-store consistency mechanisms. The formal naming of this pattern — something like "CQRS for AI Knowledge Projection" or "Polyglot Read Models for LLM Access" — remains an open contribution.