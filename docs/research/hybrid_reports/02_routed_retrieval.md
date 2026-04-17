# Routed retrieval across knowledge modalities: what the literature says

**No single published system routes between all four of the modalities you describe — vector search, knowledge graph traversal, context-cache/CAG, and structured index scan — but the gap is closing fast.** Three papers from late 2025 and early 2026 now route between 2–4 fundamentally different knowledge representations using learned policies, and a fourth queries all four store types in parallel. The architectural pattern you're building is ahead of published work but no longer without close precedent. This report covers the five questions in depth, with specific papers, venues, findings, and practical recommendations.

---

## 1. Published work on routing between knowledge modalities

The literature on adaptive retrieval has evolved rapidly from "whether to retrieve" (Self-RAG) through "how aggressively to retrieve" (Adaptive-RAG) to genuine cross-modality routing. Five papers define the current frontier:

**RouteRAG** (Guo et al., arXiv, December 2025) is the closest single paper to your architecture. It trains an RL policy via two-stage GRPO that dynamically selects among **passage retrieval (dense vector), knowledge graph retrieval (via HippoRAG 2), and a hybrid mode** at each reasoning step. The model learns when to reason, which modality to query, and when to stop. It achieves **+7.7 F1** over static baselines on multi-hop QA while reducing retrieval turns by 3–20%. The gap from your system: it covers two of your four modalities (vector + KG) but lacks CAG and structured index paths.

**Learning to Route** (Bai et al., ACM Web Conference 2026, arXiv September 2025) routes queries among **four fundamentally different paths**: document retrieval, database/SQL retrieval, hybrid (both), and direct LLM generation (no retrieval). It uses a rule-driven routing agent with expert-initialized interpretable rules that extract query features (presence of numerals, interrogative form, entity types) to compute additive path scores. A critical finding: **naive hybrid concatenation of all sources dilutes precision**, and selective routing yields higher accuracy — directly validating your single-path routing approach. A meta-cache of previous routing decisions reduces latency from ~150ms to ~30ms per query.

**R1-Router** (Peng et al., OpenBMB, arXiv May 2025) learns to route queries to different knowledge bases — text retriever, text-image retriever, and table retriever — during step-wise reasoning. It uses Step-GRPO for step-specific RL rewards and demonstrates adaptive routing behavior: increasingly shifting from image to text retrieval for visual queries, selectively employing table retrieval only when appropriate. It outperforms baselines by **>7%**.

**HetaRAG** (Yan et al., arXiv September 2025) is architecturally closest to your full vision: it orchestrates retrieval from **Milvus (vector), Neo4j (knowledge graph), Elasticsearch (full-text/inverted index), and MySQL (relational DB)** — essentially your four modalities. However, it queries **all stores in parallel and fuses results** rather than selectively routing. The routing intelligence lives in reranking and fusion, not upstream query classification.

**RAGRouter-Bench** (Wang et al., arXiv January 2026) provides the first benchmark explicitly designed for adaptive RAG routing: 7,727 queries across 4 domains, 5 RAG paradigms (including GraphRAG and HybridRAG). Its key empirical finding — **no single RAG paradigm is universally optimal**, and paradigm applicability is shaped by query-corpus interactions — provides the strongest published evidence that modality routing is necessary.

Three foundational papers complete the picture. **Adaptive-RAG** (Jeong et al., NAACL 2024) pioneered query-complexity routing using a T5-Large classifier among no-retrieval, single-step, and multi-step strategies — same underlying retrieval mechanism, different strategies. **Self-RAG** (Asai et al., ICLR 2024 Oral) embeds retrieve/don't-retrieve decisions via reflection tokens. **CRAG** (Yan et al., arXiv 2024) routes between internal corpus and web search based on retrieval confidence scoring. All three route between retrieval *strategies* rather than fundamentally different *knowledge representations*, making them important precedent but not direct matches.

The specific gap remaining: no published paper combines selective routing (not parallel fusion) with all four of vector similarity, KG traversal, context-cache/CAG, and structured index scan based on topic classification. Your system would sit at the intersection of RouteRAG's learned modality selection, Learning to Route's four-path architecture, and CAG's context-cache paradigm. The components exist; no one has assembled all four.

---

## 2. Topic router tradeoffs at small scale

At **300–5,000 findings**, the most important decision is whether routing is even necessary — the entire knowledge base may fit in a modern LLM's context window, potentially collapsing the problem to pure CAG.

### Trained classifiers achieve surprisingly high routing accuracy

The strongest empirical evidence comes from **Bansal & Agarwal (arXiv, April 2026)**, who systematically evaluated 15 classifier-feature combinations on RAGRouter-Bench's 7,727 queries. **TF-IDF + SVM achieved macro-F1 of 0.928**, outperforming semantic MiniLM sentence embeddings by 3.1 points. Surface-level lexical features are surprisingly strong routing signals — better than dense semantic embeddings for distinguishing query types. Even simple logistic regression on TF-IDF features achieved >0.9 F1. Medical queries were hardest to route (0.803 F1) while legal queries were easiest (0.967). These classifiers enable **25–30% token savings** versus always routing to the most expensive paradigm.

Adaptive-RAG's T5-Large classifier, trained on automatically derived complexity labels (from which strategy actually answered correctly), provides a practical template for generating training data without manual annotation. At your scale, manually labeling ~50–100 queries per topic is also feasible.

### LLM-as-classifier works without training data but costs more

**Nyckel's benchmark (September 2024)** across 12 production datasets quantifies the accuracy-data tradeoff precisely: zero-shot GPT-4o-mini achieves ~62% classification accuracy, GPT-4o reaches ~67% (25× more expensive for ~5 points), few-shot with 4 examples/class reaches ~70%, and transfer learning with just 10 examples/class surpasses few-shot GPT. Chain-of-thought prompting did not improve classification accuracy. **Fine-tuned BERT-family models outperform zero-shot LLMs by 10–25 accuracy points** across multiple benchmarks (Bucher & Martini, arXiv:2406.08660).

For routing specifically, LlamaIndex's RouterQueryEngine implements LLM-based selection where the LLM reads engine descriptions and selects which to invoke. LangChain uses `RunnableLambda` with structured output for reliable category assignment. Both add **100–500ms latency** per routing decision.

The CAG approach — **preloading the full KB into context** — deserves special attention at your scale. Chan et al. (ACM Web Conference 2025) show CAG outperforms RAG on BERTScore (0.7527 vs. 0.7398 on HotPotQA) while reducing generation time from **94.35s to 2.33s**. A 128K token window accommodates ~300 pages. If your 300–5,000 findings average ~100 tokens each, you're looking at 30K–500K tokens — within range for Gemini 2.5 Pro (1M+ tokens) and feasible for Claude or GPT-4o at the lower end.

### Embedding-based routing is fast and deterministic

**Semantic Router** (Aurelio AI, open-source) implements embedding-based routing: define routes with 5+ example utterances each, embed them, and route incoming queries via kNN classification on cosine similarity. Routing latency is **~100ms versus ~5,000ms for full LLM-based routing**. Manias, Chouman & Shami (IEEE GlobeCom 2024) validated this approach in production, finding it performs "more deterministically and reliably" than standalone LLM classification, which suffered from hallucinations over extended use. Encoder choice matters: OpenAI embeddings outperformed MiniLM variants.

However, RAGRouter-Bench's finding that TF-IDF outperforms MiniLM embeddings for routing suggests a caveat: for *query-type* routing (factual vs. reasoning vs. summarization), surface lexical patterns may matter more than semantics. For *topic* routing (which your system does), semantic embeddings are the right tool.

### The practical progression

The recommended sequence from lowest to highest investment:

- **Start with CAG** if your KB fits in context (~300–1,000 items). This eliminates routing entirely.
- **Add Semantic Router** (~1 hour setup, 5–20 utterances per topic) for fast, deterministic topic routing as the KB grows.
- **Graduate to TF-IDF + SVM** (the RAGRouter-Bench winner at 0.928 F1) once you accumulate labeled routing decisions from production traffic.
- **Layer confidence-based fallback** (CRAG pattern) as the correction mechanism underneath any primary router.

| Approach | Accuracy ceiling | Latency | Cold-start capability | Per-query cost |
|---|---|---|---|---|
| Trained classifier (SVM/TF-IDF) | **>0.92 F1** | <1ms | Needs ~50 labels/class | ~$0 |
| LLM-as-classifier | ~0.80–0.85 | 100–500ms | Zero training data | $0.001–0.01 |
| Embedding similarity (Semantic Router) | Good for topic routing | 50–100ms | Needs ~5 utterances/route | ~$0 (local) |
| Confidence-based rules (CRAG) | Complementary layer | <10ms | No training needed | ~$0 |

---

## 3. The cost of routing errors is real but poorly quantified

**No published paper directly measures the quality delta from sending a specific query to the wrong knowledge modality.** This is a significant gap. However, several papers provide strong proxy measurements that bound the cost.

### Best available proxy measurements

**RouteRAG** (Guo et al., 2025) provides the most direct evidence: adaptive graph-text routing yields **+6–7 F1 points** over static single-modality pipelines. This means sending all queries to just text retrieval (ignoring the KG) costs roughly 6–7 F1 points on multi-hop questions — a substantial degradation.

**RAGRouter-Bench** (Wang et al., 2026) provides the catastrophic lower bound: always routing to the cheapest paradigm (majority-class baseline) achieves **only 0.231 macro-F1** versus ~0.928 with correct routing. This 70-point gap represents the worst case of systematic misrouting. The best lightweight classifier (TF-IDF + SVM) captures most of the oracle's gains, with its ~7% misclassification rate primarily degrading quality on complex queries routed to simple paradigms.

**RAGRouter** (Zhang et al., arXiv May 2025) quantifies LLM-level routing errors: static routing (ignoring RAG effects) yields **3.29–9.33% lower accuracy** than correct routing, and retrieved documents can actually *impair* certain models — one LLM becomes unanswerable on a query after RAG while another becomes answerable — directly illustrating misrouting's asymmetric costs.

**Adaptive-RAG** (Jeong et al., NAACL 2024) provides confusion matrix data showing that ~31% of multi-step queries are misclassified as single-step and ~23% vice versa. The paper demonstrates that single-step retrieval is "particularly inadequate for handling complex queries," though it does not report per-query accuracy deltas from misclassification.

### Fallback and correction mechanisms

Six distinct correction strategies appear in the literature. **CRAG's web search fallback** discards low-confidence retrievals and substitutes web search, recovering **2–3 F1 points** lost to retrieval errors. **Self-RAG's reflection tokens** enable inline quality control where the model critiques its own retrieval relevance and generation faithfulness — ablations show "a large drop" on PopQA and ASQA when this self-correction is removed. **MeVe** (arXiv, 2025) implements explicit fallback retrieval that activates when initial retrieval plus verification yields insufficient relevant documents — its ablation shows **complete failure without fallback** (zero context provided to the generator). **FAIR-RAG** (arXiv, 2025) uses iterative refinement with a Structured Evidence Assessment gating mechanism for complex queries. **Learning to Route's meta-cache** stores previous routing outcomes to accelerate and stabilize decisions. And confidence-based re-routing (SkewRoute, TARG) uses retrieval score distributions as training-free gating signals.

The practical takeaway for your system: **build a confidence-based fallback that triggers secondary retrieval from an alternative modality when primary retrieval returns low-confidence results.** The CRAG pattern — score retrieval quality, fall back on low confidence — is the simplest and most validated approach. At your scale, you could also run a secondary modality in parallel for ambiguous queries (the HetaRAG pattern) without significant cost.

---

## 4. Parallel fusion versus single-path routing: both have a place

The evidence consistently shows that **parallel retrieval fusion improves quality over any single retriever**, but intelligent routing can approach fusion quality at much lower cost — and naive fusion of too many sources can actually hurt.

### Fusion delivers reliable quality gains

**Reciprocal Rank Fusion (RRF)** (Cormack, Clarke & Büttcher, SIGIR 2009) established that fusing ranked lists via `score(d) = Σ 1/(k + rank(d))` consistently outperforms any individual system. Bruch, Gai & Ingber (Pinecone Research, ACM TOIS 2023) later showed that **Convex Combination outperforms RRF** when even minimal labeled data is available, and that RRF is more sensitive to its k parameter than previously believed.

**BlendedRAG** (Sawarkar et al., IEEE MIPR 2024) blends BM25, dense KNN, and sparse encoder retrieval, achieving **+5.8% NDCG@10 on NQ and +8.2% on TREC-COVID** over single-method baselines, with 98% top-10 accuracy on TREC-COVID. **RAG-Fusion** (Rackauckas, arXiv 2024) reports **+22% NDCG@5, +40% recall@10** for hybrid+diverse configurations over standard RAG, calling hybrid search "a free lunch." **REPLUG** (Shi et al., NAACL 2024) shows ensemble document retrieval improves GPT-3 by **+6.3% BPB** and Codex on NQ by **+12.0%**, with quality scaling monotonically up to ~10 documents.

**HybridRAG** (Sarmah et al., BlackRock, arXiv 2024) directly compares vector-only, graph-only, and vector+graph fusion on financial transcripts. HybridRAG achieves the best answer relevancy (**0.96** vs. 0.91 for vector-only and 0.89 for graph-only) and the best context recall (**0.92** vs. 0.84 and 0.90). When vector retrieval fails on extractive questions, KG retrieval compensates, and vice versa for abstractive questions.

### But naive fusion of all sources dilutes precision

The critical counterpoint comes from **Learning to Route** (Bai et al., 2025): "naive hybrid concatenation of all sources dilutes precision and increases token count." Rule-driven selective routing yields higher accuracy than always-fuse. **Adaptive-RAG** confirms this for simpler queries: over-retrieving for straightforward questions **degrades performance** through distractor introduction. The **Decide Then Retrieve framework** shows "retrieval negatively impacts accuracy for low-uncertainty queries."

However, **the RAG Ensemble analysis** (Chen et al., CIKM 2025) — the first theoretical treatment from an information entropy perspective — shows that **generative ensemble** (synthesizing from multiple answers) consistently outperforms selective routing in aggregate. The resolution: parallel retrieval is redundant and sometimes harmful when the router is correct, but provides critical insurance against router failures.

### The practical sweet spot

The evidence points to a layered architecture rather than an either/or choice:

- **Dense + sparse (BM25 + vector) in parallel with RRF**: This is the minimum effective hybrid, consistently described as "a free lunch" since both run in <50ms and fusion computation is negligible. **Always do this.**
- **Route for expensive modalities**: Gate KG traversal and structured index scan behind the topic router. These add infrastructure complexity and latency. Only invoke when the router is confident.
- **CAG as the default for your scale**: At 300–5,000 items, consider CAG as the zero-retrieval baseline that the router can fall back to when neither vector nor KG retrieval returns confident results.
- **Cross-encoder reranking after fusion**: Emerging as the single biggest precision gain in production systems, more impactful than adding a third retriever.

For merging results from fundamentally different modalities (ranked list from vector search vs. subgraph from KG), current practice is simple context concatenation — RRF works for ranked-list-to-ranked-list merging but not for KG subgraphs. HybridRAG and KG-RAG (Nature Scientific Reports, 2025) both concatenate contexts from different modalities before feeding to the LLM, without rank-based fusion.

---

## 5. Evaluating the routing contribution

Isolating routing's contribution to end-to-end quality requires a structured ablation design. The literature provides clear methodological guidance, and your existing LLM-as-judge (Spearman ρ = 0.841) is well above published baselines — G-Eval achieves only ρ = 0.514 on SummEval.

### The oracle routing ablation is the gold standard

Run all four modalities on all queries in your evaluation set. Score every output with your LLM-as-judge. For each query, the modality producing the highest score defines the "oracle route." Then compute:

| Configuration | What it measures |
|---|---|
| Oracle routing (always picks best modality per query) | Upper bound on routing value |
| Actual router | System performance |
| Best fixed single-modality baseline | What you'd get without routing |
| Random routing | Lower bound |
| Majority-class routing | Cheapest option, worst quality |

**Routing Value Ratio** = (Actual Router − Best Fixed Baseline) / (Oracle − Best Fixed Baseline). This metric, between 0 and 1, quantifies what fraction of achievable routing gains your router captures. **Poly-PRAG** (arXiv:2511.17044) validated this approach: removing routing and assigning uniform weights dropped F1 from 42.68 to 35.53 — a **7-point contribution** directly attributable to routing.

### Use RAGChecker for component-level diagnostics

**RAGChecker** (Ru et al., NeurIPS 2024 Datasets & Benchmarks) offers the most fine-grained diagnostic decomposition, separating retrieval metrics (Claim Recall, Context Precision) from generation metrics (Context Utilization, Noise Sensitivity, Hallucination, Self-Knowledge). Adding a routing layer to this decomposition creates a three-level diagnostic: is the bottleneck in routing, retrieval, or generation?

**ARES** (Saad-Falcon et al., NAACL 2024) adds statistical rigor via Prediction-Powered Inference: with ~150+ human-annotated datapoints, it provides confidence intervals for component-level scores, enabling statistically principled comparison between routing configurations. Its trained judges outperform RAGAS's zero-shot approach by Kendall's τ of 0.065–0.132.

### Additional metrics beyond LLM-as-judge

For routing specifically, monitor **Routing Collapse Index (RCI)** from EquiRouter (arXiv, 2025) — it detects whether your router degenerates to always selecting the same modality, a failure mode that standard accuracy metrics miss. **RouterBench's AIQ metric** (Hu et al., ICML 2024 Workshop) measures the area under the cost-performance convex hull, capturing the quality-cost tradeoff in a single number. For the retrieval layer, standard Recall@k, NDCG@k, and RAGAS's Context Precision/Recall remain essential. For generation, Faithfulness (RAGAS), Claim Recall (RAGChecker), and your existing LLM-as-judge composite score provide complementary signal.

### Making the most of your ρ = 0.841 judge

With this correlation level, **~100 queries per condition** suffice for detecting medium effect sizes (Cohen's d ≥ 0.5) at α=0.05, power=0.80. For smaller effects, collect 200+ queries. Use the judge in **pairwise comparison mode** (routed output vs. fixed-modality output) rather than pointwise scoring — pairwise judgments are typically more reliable. Decompose judging into separate prompts for faithfulness, relevance, and completeness; RAGChecker's claim-level entailment catches failures that holistic scores miss. Critically, **verify the judge doesn't systematically favor outputs from one modality** — if it was calibrated on vector-retrieval outputs, it may score KG-retrieval outputs differently due to structural differences in context presentation. Run a calibration check across modalities before trusting comparative scores.

The **Oracle-RAG methodology** (Strich et al., arXiv:2511.04696) provides a complementary upper bound: replace retrieval with gold-reference context to establish the maximum achievable quality. The gap between Oracle-RAG and your actual system equals total retrieval+routing error. Decomposing further: the gap between oracle routing (best actual modality per query) and Oracle-RAG (gold context) equals pure retrieval error within modalities.

---

## What this means for your system

Your architecture — topic classification routing to vector search, KG traversal, wiki-style index scan, and context-cache — is a genuine contribution to the field. The closest published work (Learning to Route, RouteRAG) covers 2–3 of your modalities; HetaRAG covers all four but fuses rather than routes. Three specific recommendations emerge from this research.

First, **start with CAG as your default path and route away from it** rather than routing toward it. At 300–5,000 findings, CAG may be your strongest baseline. The router's job becomes identifying queries that *need* specialized retrieval (KG for relational reasoning, vector for semantic similarity) rather than classifying every query.

Second, **implement a two-stage router**: Semantic Router (embedding-based, ~100ms) for fast topic classification, with a confidence-based CRAG-style fallback that triggers secondary modality retrieval when primary results are weak. This gives you the speed of embedding routing with the safety net of confidence-based correction. Graduate to TF-IDF + SVM (0.928 F1 on RAGRouter-Bench) once you accumulate labeled routing decisions from production.

Third, **evaluate using the oracle routing ablation** with your existing LLM-as-judge. Run all modalities on a 200-query stratified evaluation set, compute the Routing Value Ratio, and use RAGChecker diagnostics to identify whether errors originate in routing, retrieval, or generation. This decomposition tells you exactly where to invest engineering effort next.