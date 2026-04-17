# Postgres will handle your graph for years — here's the evidence

**For a behavioral-science knowledge base with ~5,000 nodes and ~8,000 edges, PostgreSQL recursive CTEs will deliver sub-5ms graph traversals — roughly 400× faster than your 2-second latency requirement.** The evidence from production benchmarks at scales 1,000–1,000,000× larger than yours unanimously supports this conclusion. Adding a second database at this scale introduces **40–60% more infrastructure engineering time** with zero measurable performance benefit. Below is the detailed technical analysis across all five questions, with specific benchmarks, version numbers, and practitioner sources.

---

## 1. Postgres recursive CTEs are absurdly fast at your scale

The most relevant benchmark comes from Alibaba Cloud, which tested PostgreSQL graph search on a **10-million-node, 5-billion-edge** graph (500 edges/node average). A 3-depth hop search from a single root node completed in **3.2 milliseconds**, returning 300 rows. Under load with 64 concurrent clients, average latency was **5.239ms** at **12,197 TPS**. Your graph is roughly 2,000× smaller in nodes and 625,000× smaller in edges.

Additional data points confirm this picture. A DEV.to practitioner benchmark on 50,000 rows with a depth-6 tree hierarchy showed **12ms** latency for recursive CTEs. The ExplainExtended benchmark demonstrated **4ms** for ancestor traversal on a **1-million-node** hierarchy. A personal knowledge graph practitioner building with <10K nodes reported that recursive CTEs at depth 2–3 take "**microseconds** — the performance argument for a graph engine simply doesn't exist."

For your specific graph (5,000 nodes, 8,000 edges, 1.6 edges/node average), a 3-hop traversal touches roughly **k + k² + k³ ≈ 1.6 + 2.6 + 4.1 ≈ 8 rows total**. With proper indexing, this completes in well under 1 millisecond. Your 2-second budget is overprovisioned by a factor of **400–2,000×**.

**Required indexes are non-negotiable.** Every source agrees: B-tree indexes on source and target foreign keys in your edge table are mandatory. Missing these is the single most common performance killer — one benchmark showed a **33× slowdown** (12ms → 400ms) from a missing `parent_id` index on a modest dataset. The minimum indexing setup:

```sql
CREATE INDEX idx_edges_source ON edges (source_id);
CREATE INDEX idx_edges_target ON edges (target_id);
-- Optional: composite primary key if edges are unique
ALTER TABLE edges ADD PRIMARY KEY (source_id, target_id);
```

The Alibaba benchmark also used PostgreSQL's `CLUSTER` command to physically order the edge table by source node, further reducing random I/O. For your scale this is unnecessary, but it's a useful optimization to know about.

**Density scaling is a non-issue in your range.** Going from 1.6 to 5 edges/node increases 3-hop working table size from ~4 rows to ~125 rows — trivial for PostgreSQL. The concern only becomes real at **50+ edges/node** with deep traversals, or when attempting "all paths" enumeration on dense graphs. The Yugabyte Bacon Numbers analysis warns that naïve all-paths enumeration on highly connected graphs (like IMDb) "will run for a very long time before crashing gracelessly with out-of-resource errors." For bounded queries with depth limits and cycle detection, this is avoidable.

**Known failure patterns** to watch for: recursive CTEs on cyclic graphs will loop forever without cycle detection — use PostgreSQL 14+'s built-in `CYCLE` clause or track visited nodes in an array. Weighted shortest path (Dijkstra) cannot be efficiently implemented because the working table cannot be priority-sorted within the recursive step. Unweighted shortest path works well with `LIMIT 1` thanks to breadth-first evaluation. The planner sometimes chooses sequential scans inside the recursive step on small tables; if this occurs, verify indexes exist and consider `SET enable_seqscan = off` for testing.

---

## 2. SurrealDB has critical durability and maturity gaps

**SurrealDB is not crash-safe by default.** A detailed August 2025 analysis by Harrison Burt revealed that SurrealDB's RocksDB and SurrealKV backends do not `fsync` data to disk by default. The `SURREAL_SYNC_DATA` environment variable defaults to `false`, meaning writes go to the OS page cache only. A power outage or crash can cause **total data loss or corruption**. This default behavior is documented only as "a single field in an HTML table" with no warning about crash safety implications. This alone is disqualifying for a production knowledge base. PostgreSQL, MySQL, and MongoDB all default to durable writes — SurrealDB's behavior here is a serious departure from industry norms.

**Database corruption was shipped in a release.** Version 2.3.0 (May 2025) included a bug that could corrupt the database when an UPDATE statement was stored within a function. SurrealDB's own release notes acknowledge: "We identified an issue in this release that can corrupt the database." Additional stability issues include crashes on DELETE operations with ~2M rows (GitHub #6327), crashes when running EXPLAIN (GitHub #6332, v2.3.7), and self-termination after extended operation (#5199).

**Production deployments are unverified.** SurrealDB's case studies page lists Saks Fifth Avenue, Tencent, Verizon, PolyAI, and others. However, **no independent case studies, conference talks, or blog posts from these companies corroborating the claims were found**. No verifiable independent production deployment reports exist on Reddit, Hacker News, or technical blogs. A GitHub community member noted: "Quick search on reddit shows a few users complain about abysmal performance, worse than Sqlite. Seeing SurrealDB claiming it's trusted by teams at big name companies raises my eyebrows."

**Zero vector or graph benchmarks exist.** SurrealDB has published no benchmarks comparing its HNSW vector search to pgvector at any scale. Their own benchmark blog (February 2025) explicitly states they have "not yet implemented relationships in crud-bench" and are only "looking into implementing the benchmarks from LDBC" for graph features. No third-party graph traversal benchmarks versus Neo4j exist at any scale. The HNSW indexes are in-memory, which raises questions about behavior under memory pressure.

**Community metrics suggest hype over adoption.** SurrealDB has ~31,900 GitHub stars but only ~6,500 Discord members. Compare this to Neo4j's ~14,000 stars but 250,000+ community members and 17 years of production use, or PostgreSQL's millions of users and 28+ years of battle-testing. The project is funded (€32M Series A) and actively developed (latest release v3.0.5, March 2026), but the BSL 1.1 license restricts certain commercial uses.

---

## 3. Neo4j adds overhead without benefit at your scale

**A minimal self-hosted Neo4j Docker deployment requires ~2GB RAM** — 512MB heap + 256MB pagecache + OS overhead. CPU: 1 core sufficient for single-user workloads. Disk inflation is severe: the UW benchmark showed 1GB CSV data expanding to **12.3GB on disk** in Neo4j versus ~1.3GB in Postgres. For <10K nodes, expect 50–200MB on disk. Neo4j switched to calendar versioning in 2025 (current images: `neo4j:2026.02.2`+).

**Community Edition has meaningful limitations.** Only offline backup via `neo4j-admin database dump` — the database must be stopped first, causing downtime. Only a single database is supported (no multi-tenancy). No role-based access control. The Cypher runtime is "Slotted" rather than Enterprise's "Pipelined" — roughly **2× slower**. No clustering or high availability. For a solo developer with a single small graph, these limitations are tolerable, but the offline-only backup requires workarounds (custom Docker entrypoint scripts with cron jobs).

**At <10K nodes, Neo4j provides zero performance advantage.** The University of Washington benchmark found PostgreSQL outperformed Neo4j in almost every query. Neo4j's advantages appeared **only with joins involving more than 5 tables on datasets exceeding 10GB**. On 1GB data with 1GB RAM, Neo4j ran out of memory on 4 of 7 queries while Postgres completed all. A Springer academic benchmark confirmed Neo4j's advantage materializes at **depth 4+**, where "RDBMSs cannot finish their processing in a certain time, namely stuck or terminated." CWI researchers extending DuckDB with graph query support found it **outperformed Neo4j by up to 10×** on LDBC Social Network Benchmark workloads.

The practical minimum scale where Neo4j meaningfully outperforms Postgres is **100K+ nodes with dense relationships and 4+ hop traversals**, or when you need graph-specific algorithms (PageRank, community detection, Louvain clustering) via the GDS library.

**Data sync between Postgres and Neo4j is the real cost.** The full CDC pipeline (Postgres WAL → Debezium → Kafka → Neo4j Kafka Connector) requires **4–5 additional containers** — ZooKeeper, Kafka, Kafka Connect, Debezium — and is massively over-engineered for <10K nodes. The deprecated `neo4j-streams` plugin has been replaced by the Neo4j Kafka Connector (v5.1), but official support requires Enterprise or AuraDB licensing. For a solo developer, **manual ETL (batch sync) is the only practical approach**: a simple script that periodically queries Postgres changes and upserts into Neo4j. For <10K nodes, a full re-import takes seconds. Dual-write without distributed transactions risks data divergence on partial failures.

---

## 4. Apache AGE is slower than recursive CTEs and nearly died

**Apache AGE nearly went to the Apache Attic in 2024–2025.** The Apache Board meeting minutes tell the story: zero commits to the project from September 2024 through May 2025. In February 2025, the board explicitly discussed whether "the project needs to go to the attic." An 18-month release gap separated v1.5.0 (March 2024) from v1.6.0 (September 2025). Activity has since partially recovered, with PG16 and PG17 releases shipping in late 2025 and a PG18-1.7.0 release following. But the project has only **19 committers and 13 PMC members**, with "very few organic non-committer contributions."

The corporate backing is uncertain. Bitnine Co., Ltd. — AGE's primary sponsor — was acquired by Directors Company in December 2024 and renamed to "SKAI Worldwide Co., Ltd." The new parent is **pivoting toward AI advertising and content production**, raising long-term sustainability questions.

**AGE is measurably slower than recursive CTEs, not faster.** A concrete benchmark by Sanjeev Singh (Medium, June 2025) compared AGE Cypher versus recursive CTEs on a 100-user social network with `EXPLAIN ANALYZE`. The recursive CTE completed a 4-hop friends-of-friends query in **1.614ms**; the equivalent AGE Cypher query took **~6.3ms** — roughly 4× slower. The author reported a "40× speed difference in favor of SQL recursive CTEs." AGE is architecturally incapable of outperforming CTEs because it stores graph data in **regular PostgreSQL heap tables with B-tree index lookups per hop** — it does not use index-free adjacency. Cypher queries are transpiled to PostgreSQL query trees at execution time, with the custom `agtype` data type adding serialization overhead. AGE is syntactic sugar with performance cost, not a query planner improvement.

**AGE and pgvector coexist without conflicts.** Multiple Docker images combining both extensions exist, and practitioners have confirmed they work together on PG16 and PG17. AGE requires `shared_preload_libraries = 'age'`; pgvector does not require shared preload. However, there is no native integration — you must query them through separate SQL interfaces (Cypher-in-SQL for AGE, standard SQL with `<=>` operators for pgvector).

**Known dealbreakers include:** `agtype` cannot directly cast to `json`/`jsonb` (must go through `varchar` first); a 50-property-pair limit per node/edge (from PostgreSQL's 100-argument function limit, partially fixed); every connection requires `LOAD 'age'` and `SET search_path` (operational hazard); EXPLAIN on DELETE operations is extremely slow; bulk loading via Cypher CREATE statements is very slow (must bypass Cypher and insert directly into underlying tables); and incomplete openCypher support compared to Neo4j's Cypher.

---

## 5. No performance wall exists at your scale — the migration can wait years

**The evidence unanimously indicates PostgreSQL will not hit a performance wall at your projected scale.** The Alibaba benchmark demonstrates **2.1ms response times on a graph 1,000× larger** than your 1–2 year projection (10M nodes, 5B edges). Your projected ~5,000 nodes with ~8,000 edges and 2–3 hop traversals will complete in sub-millisecond time. Even at **100× growth** (500K nodes, 800K edges), performance would remain in the low single-digit milliseconds with proper B-tree indexing.

The "start simple, migrate when needed" strategy is well-documented and widely endorsed. Martin Fowler's canonical polyglot persistence guidance states that adding a second database is justified only when there's a "demonstrable impedance mismatch causing measurable pain." A DEV Community practitioner guide quantifies the overhead: **"Expect 40–60% more infrastructure engineering time compared to a single well-tuned database."** For teams smaller than 8–10 engineers, "the operational burden likely outweighs the benefits."

**Concrete decision thresholds from the research:**

- **Node count**: PostgreSQL is competitive up to millions of nodes with proper indexing. Consider a graph DB above **100K+ densely connected nodes**
- **Traversal depth**: PostgreSQL handles 1–3 hops trivially; graph DBs start winning at **4+ hops** where "RDBMSs stuck or terminated" (Springer benchmark)
- **Join complexity**: PostgreSQL competitive up to ~5 table joins; Neo4j advantages appear with **>5 joins on >10GB datasets** (UW benchmark)
- **Graph density**: PostgreSQL comfortable to ~10–50 edges/node; beyond that, exponential fan-out makes deep traversals expensive in any database
- **Graph algorithms**: If you need PageRank, community detection, or Louvain clustering at scale, Neo4j's GDS library is genuinely superior regardless of graph size

**If you eventually need to migrate**, the path is straightforward. Postgres to Neo4j: CSV export via `COPY`, schema mapping (30–60 minutes of design), import via `LOAD CSV` or `neo4j-admin import`. For 5,000 nodes, total effort is **2–4 hours**. Postgres to SurrealDB: no automated migration tool exists; export to JSON Lines, transform to SurrealQL `CREATE`/`RELATE` statements, import via `surreal import`. Estimated effort: **4–8 hours** due to less mature tooling.

---

## Conclusion: the architecture decision is clear

Your five read models (vector similarity, graph traversal, compiled markdown, full-context XML, pre-computed clusters) can all live in PostgreSQL today without performance compromise. The graph traversal queries that concern you most will complete in **<5ms** — well within your 2-second budget by orders of magnitude. The key actions are practical, not architectural:

**B-tree indexes on edge foreign keys are the single highest-leverage optimization.** Without them, queries degrade 33×. With them, your graph is trivially fast. Consider `CLUSTER`ing your edge table by source node if you want to squeeze out additional I/O efficiency.

**SurrealDB is not ready for production.** The default crash-unsafety, unverified production deployments, zero published benchmarks for vector or graph workloads, and documented corruption bugs make it inappropriate for a knowledge base where data integrity matters. Revisit in 2–3 years.

**Apache AGE provides no performance benefit** — it's slower than the recursive CTEs it replaces, the project nearly died in 2024–2025, and its corporate backer is pivoting away. Its only value is Cypher syntax ergonomics, which doesn't justify the risks for a solo developer.

**Neo4j is a good database that you don't need yet.** The ~2GB RAM overhead, offline-only Community Edition backups, and data sync complexity add operational burden with zero measurable query performance improvement at <10K nodes. The crossover point — where Neo4j's index-free adjacency meaningfully outperforms PostgreSQL — is **100K+ densely connected nodes with 4+ hop traversals**.

The pragmatic path is to **stay on PostgreSQL, invest in proper indexing, and set concrete migration triggers**: sustained query latencies >100ms after optimization, regular traversal depths >4 hops, or need for graph-native algorithms like PageRank. At your projected growth rate, these triggers are unlikely to fire within 2 years — and if they do, migration to Neo4j is a 2–4 hour effort on a graph this size.