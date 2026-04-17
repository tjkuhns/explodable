# SetR in production: what practitioners actually report

**No public operational knowledge about SetR or DPS exists.** Both papers (SetR, July 2025; DPS, August 2025) remain purely academic — zero blog posts, GitHub issues, HN threads, or postmortems reference either system in production. The SetR fine-tuned weights are not even public; OptiSet (January 2026) had to benchmark against a zero-shot version. Everything below is drawn from analogous systems sharing the same derive-requirements → match → select structure: CRAG deployments, agentic RAG pipelines, and multi-step retrieval with query decomposition.

## Requirement derivation breaks on vague inputs and drifts on rewrites

**(a)** The "derive information requirements" phase fails in two documented ways. First, **semantic drift**: a CRAG production deployment found that vague user queries like *"does the thing work with sso"* were rewritten into formal language that retrieved wrong documents entirely — "How do I cancel my subscription?" became "steps to terminate a service agreement," pulling legal docs instead of user guides. The fix was a cosine-similarity gate (≥0.85 between original and rewrite; below that, discard), which cut rewrite volume 60% ([Adeliyi, Medium, Mar 2026](https://medium.com/@tommyadeliyi/why-most-rag-systems-fail-in-production-and-how-to-fix-them-82cde6782b50)). Second, **error propagation through decomposition**: RT-RAG documented cascading failures where a single misidentified entity in an early sub-question poisoned every downstream answer ([arXiv 2601.11255](https://arxiv.org/pdf/2601.11255)). Beyond **3 sub-queries**, practitioners report diminishing returns — more decomposition just adds latency without accuracy gains ([dev.to/sreeni5018](https://dev.to/sreeni5018/multi-query-retriever-rag-how-to-dramatically-improve-your-ais-document-retrieval-accuracy-5892)).

## Fallback when no candidate covers a requirement

**(b)** The dominant production pattern is **three-tier confidence routing** from CRAG: high-confidence → generate; medium → rerank then generate; low → explicit "I don't know" or web-search fallback. One deployment's initial fallback rate was **35%** — far too high — reduced to **12%** by loosening the relevance threshold and adding a reranker before the fallback decision ([Adeliyi](https://medium.com/@tommyadeliyi/why-most-rag-systems-fail-in-production-and-how-to-fix-them-82cde6782b50)). A critical finding from Google Research: RAG **paradoxically reduces abstention** — Gemma's incorrect-answer rate jumped from 10.2% (no context) to 66.1% when given insufficient context, because retrieved passages inflate model confidence ([Google Research blog](https://research.google/blog/deeper-insights-into-retrieval-augmented-generation-the-role-of-sufficient-context/)).

## Two LLM calls cost $0.06–0.31 per query and 2–12 seconds

**(c)** Across 109 production deployments, standard single-retrieval queries cost **$0.06–0.09** and take **~0.6s**; complex multi-hop queries requiring two retrieval iterations cost **$0.18–0.31** and take **2.4–12s** depending on call count ([Jahanzaib, dev.to, Apr 2026](https://dev.to/jahanzaibai/agentic-rag-the-complete-production-guide-nobody-else-wrote-386o)). Model tiering — small models for routing/grading, large for generation — cuts latency **35–45%**. An FAQ bot with 200 Q&A pairs saw standard RAG at 0.4s/94% accuracy versus agentic at 3s/96%: **8× cost for 2 percentage points** ([ByteByteGo](https://blog.bytebytego.com/p/how-agentic-rag-works)).

## Rollbacks happen, mostly driven by disproportionate complexity

**(d)** The best-documented rollback: **Anthropic's Claude Code abandoned RAG + vector DB** entirely in favor of agentic grep/glob search, citing simplicity, reliability, and outright better performance — confirmed by creator Boris Cherny ([X post](https://x.com/bcherny/status/2017824286489383315)). A CRAG practitioner reported a **full feature rollback** after hallucinated answers from stale documents caused three support escalations ([Adeliyi](https://medium.com/@tommyadeliyi/why-most-rag-systems-fail-in-production-and-how-to-fix-them-82cde6782b50)). A SitePoint anecdote captures the pattern: a developer spent two weeks building RAG for 200 pages that fit in a single Gemini prompt ([SitePoint](https://www.sitepoint.com/long-context-vs-rag-1m-token-windows/)).

## At ~300 documents, you may not need retrieval at all

**(e)** No formal minimum pool size exists in the literature. However, Anthropic's official guidance is unambiguous: **below ~200K tokens (~500 pages), skip RAG and stuff everything into context** ([Anthropic blog](https://www.anthropic.com/news/contextual-retrieval)). The MODE paper (arXiv 2509.00100) found traditional index-retrieve-rerank pipelines are a **"poor fit"** for corpora of 100–500 chunks, recommending cluster-and-route instead ([MODE paper](https://arxiv.org/html/2509.00100v1)). Your 300 findings at ~1,000 words each total roughly **400K tokens** — right at the boundary. Set selection specifically degrades because sparse embedding space means the same few documents surface repeatedly, and chunk-boundary errors are amplified when each chunk represents a larger share of total knowledge.

---

## Three operational recommendations for Phase-1

1. **Benchmark context-stuffing first.** At ~400K tokens, your entire KB likely fits in a single Claude or Gemini call with prompt caching. Build this as your baseline before investing in SetR-style decomposition — multiple practitioners report it wins outright for corpora under 500 pages, at a fraction of the complexity.

2. **If you implement requirement derivation, cap at 3 sub-requirements and add a similarity gate.** Discard any derived requirement whose embedding similarity to the original query falls below 0.85. This single check eliminated 60% of semantic-drift failures in production CRAG systems and directly prevents the over-decomposition that RT-RAG documented.

3. **Ship a confidence-gated "I don't know" path from day one.** Google's research shows retrieved context makes LLMs *less* likely to abstain, not more. Wire a reranker score threshold that routes low-confidence queries to an explicit refusal rather than a hallucinated answer — tune the threshold to keep fallback rate between 10–15%.