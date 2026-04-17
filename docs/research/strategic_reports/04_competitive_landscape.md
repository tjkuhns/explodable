# The moat is narrow, real, and mostly operational

**Bottom line:** No public entity — startup, lab, OSS project, or internal tool — has publicly claimed "per-stage cognitive architecture selection matched to cognitive task type" as described. The user's priority claim on the specific framing is defensible **today**. But the moat erodes fast: at least three entities (Microsoft GraphRAG, Glean, Gemini Deep Research) already ship systems that compose vector + graph + full-context in one pipeline, and two arXiv papers from late 2025 (HetaRAG, RouteRAG-RL) are one small conceptual step away. The evaluation harness scored 3/10 as a standalone moat — every component has 2024-era published prior art. The practical moat after publication is ~9–12 months of execution lead, not any artifact. If the user publishes Monday, they can still build a business around this — but only if they execute the DSPy/vLLM playbook (name the primitive, anchor an elite user, ship integrations, own the benchmark) in weeks 1–4, not month 6.

## Who is actually doing this, and what's the distinction

The closest public matches, ranked by how much they threaten the specific claim of "per-stage cognitive architecture selection matched to cognitive task type":

**Microsoft GraphRAG (HIGH threat).** The clearest public system composing vector indices, knowledge graphs, and hierarchical community reports (wiki-like) as distinct substrates in one pipeline. Offers Global Search, Local Search, and DRIFT Search modes. **But:** selection is *per-query mode*, not *per-stage within a single pipeline*. Microsoft's blog explicitly lists a "query router and lite-global search variant" as planned work — meaning they're closer to per-query routing than per-stage. Gap: they route between three modes of the same graph, not across fundamentally different substrates matched to cognitive task types. Adding per-stage logic is weeks of engineering once a team decides to.

**Glean (HIGH threat, different domain).** Enterprise search — explicitly runs one pipeline that composes vector embeddings, lexical/BM25, knowledge graph, and personalization graph. Publishes the pattern as "graph-scoped search: first narrow with graph, then vector similarity within subset." **But:** this is retrieve-then-refine within search, not a multi-stage content-generation pipeline with classification/discovery/synthesis/generation/critique stages. Different domain, different cognitive decomposition. Low overlap with content generation today.

**Google Gemini Deep Research (HIGH threat).** The ONLY frontier lab that publicly confirms composing long-context (1M tokens) with vector RAG in one pipeline, plus separating planner from task models. "Asynchronous task manager maintains shared state between the planner and task models." **But:** public writeups describe model-per-role, not substrate-per-cognitive-task. Internal capability almost certainly exceeds the public description — this is the single scariest unknown.

**HetaRAG (arXiv 2509.21336, Sep 2025).** Unifies vector (Milvus), graph (Neo4j), full-text (Elasticsearch), and relational (MySQL) into a single retrieval plane, "dynamically routing and fusing evidence." **But:** they run all four in parallel at query time and fuse outputs — they do not select architectures selectively per pipeline stage based on cognitive task type. Code is on GitHub (KnowledgeXLab/HetaRAG). A competent team forking this could add stage-selection logic in weeks. **This is the most direct academic predecessor and the fastest possible pivot.**

**RouteRAG-RL (Guo et al., arXiv:2512.09487, Dec 2025).** Trains an LLM with GRPO-style RL to route per-query among passage retrieval (DPR), graph retrieval (HippoRAG 2), and hybrid modes. **But:** it's per-query, per-turn routing during a single reasoning loop — not per-stage assignment in a multi-stage content-generation pipeline. The conceptual extension to per-stage is roughly one paper.

**Perplexity (MEDIUM-HIGH threat).** Documents multi-stage retrieval pipeline with different *retrieval methods per stage* (lexical prefilter → dense → cross-encoder rerank) plus model routing. This is legitimate per-stage architecture selection, but within the retrieval/ranking substrate — not across vector/graph/wiki/full-context.

**OpenAI Deep Research, Hebbia, Harvey AI, Anthropic multi-agent.** All confirm per-stage *model* selection and per-role *agent* specialization. None confirm per-stage retrieval substrate selection matched to cognitive task types. Threat is medium because internal tooling likely goes further than public writeups.

**Null findings (significant):** No GitHub repo or Show HN post found using the exact framing. No Y Combinator W24–W26 startup found claiming this. No job posting found at Anthropic/OpenAI/DeepMind/Meta/Microsoft using the phrases "multi-architecture pipeline," "stage-level optimization," or "cognitive task routing." Anthropic's "API Knowledge" engineering role is adjacent but generic.

## The 6-month pivot risk is concentrated in five places

Ranked by scariest for priority claim:

1. **HetaRAG authors (KnowledgeXLab).** Already have the four-substrate infrastructure built. Writing a follow-up paper that swaps parallel fusion for per-stage selection is the natural next publication. Estimated pivot: **2–4 months to arXiv**. This is the single highest-risk entity.

2. **Microsoft GraphRAG team.** Already shipping three query modes. Publicly roadmapped "query router." A per-stage variant within GraphRAG would be a natural v2.0 blog post. Estimated pivot: **3–6 months**.

3. **Stanford DSPy (Khattab, Zaharia) and CMU/UW NLP groups.** DSPy modules already support heterogeneous retrievers; the compiler (MIPROv2, GEPA) could in principle optimize over retriever choice per module. No public indication this is a current project. If they decide to, a DSPy paper with stage-level architecture selection shipped as a first-class optimizer is **3–6 months** away and would carry Stanford-affiliation weight that overwhelms solo-founder publication.

4. **LangGraph / LlamaIndex Workflows.** Both frameworks already let users manually compose heterogeneous retrievers per node. Neither has an opinionated "per-stage cognitive architecture selection" primitive today. If either ships one as a blog post + reference template, it instantly becomes the de facto pattern. Estimated pivot: **<3 months** once they decide. LangChain specifically has a history of fast-follows on every new pattern (Adaptive-RAG, CRAG, Self-RAG all got LangGraph reference implementations within weeks of publication).

5. **Contextual AI (Douwe Kiela).** RAG 2.0 marketing emphasizes end-to-end optimization. Per-stage architecture selection is a natural extension of their "jointly optimize retriever and generator" framing. No public signal they're working on it, but they have the team and funding to ship in **3–6 months** if they choose to.

## Frontier lab internal tooling: evidence-thin, but not absent

**Confirmed publicly:**
- Anthropic's multi-agent research system (Jun 2025) uses different model tiers per stage (Opus orchestration, Sonnet retrieval, CitationAgent) and per-stage memory-access modes (persistent file memory when context >200k, ephemeral subagent context, shared tool-based search). But all subagents use the same tool-calling-over-search paradigm.
- OpenAI Deep Research API composes gpt-4.1 (clarification, rewriting) with o3-deep-research (execution) and exposes web search + vector file_search + MCP servers simultaneously.
- Google's Gemini Deep Research publicly states both long-context and RAG are used in one pipeline.

**Inferred but not confirmed:** Internal tooling at every frontier lab almost certainly exceeds public descriptions. Labs have every incentive to build and no incentive to publish the specific formulation. **The honest assessment is that the user cannot rule out that Anthropic or Google has a version of this internally today.** Public publication establishes priority against the public literature; it does not establish priority against private tooling. But private tooling doesn't compete for mindshare, citations, or the category-naming right — so from a practical moat perspective, the priority claim is still live.

**No smoking-gun job postings.** Searches for "multi-architecture pipeline," "stage-level optimization," "cognitive task routing," and "heterogeneous retrieval evaluation" returned nothing at Anthropic, OpenAI, DeepMind, Meta, or Microsoft as of April 2026. This is a useful absence — if labs were staffing a team specifically for this, job postings would usually leak the framing.

## The eval harness is not the moat

The user's calibrated LLM-as-judge (Spearman ρ = 0.841 vs 5-model editorial panel) uses methodology whose every component has published 2024-era prior art:

- **Multi-model panel as reference**: PoLL (Cohere, 2024 — "Replacing Judges with Juries"), Prometheus-2 (ICLR 2024, used 5 evaluator LMs on BiGGen-Bench — almost exactly the "5-model editorial panel").
- **Inter-rater + outlier drop**: Cascaded Selective Evaluation (ICLR 2025), AUTOCALIBRATE (2023).
- **Rank-correlation calibration**: "Judge's Verdict Benchmark" (arXiv 2510.09738, Oct 2025) formalizes the r≥0.80 + κ test as the entry bar — 36 of 54 frontier LLMs already pass it against humans.
- **Per-stage scoring instrumentation**: LangSmith spans, Phoenix OpenTelemetry, Braintrust scorers, DeepEval DAGs, Inspect AI with native multi-model grader — all support this out of the box.

**Critical caveat on the 0.841 number:** it's measured against a 5-LLM panel, not against humans. LLM-vs-LLM correlations run 0.1–0.3 higher than LLM-vs-human because frontier models share training-data biases. Against humans, the same judge likely correlates in the 0.60–0.75 range, which is competent but not SOTA. G-Eval hit 0.514 vs humans on summarization; Prometheus-2 runs 0.6–0.7; an iteratively-refined judge paper (Prolific 2025) reports 0.843 vs humans — the user's number is equivalent to good applied engineering, not a research breakthrough.

**Replication cost:** 5 judge models × 1,000 calibration samples × $0.01–0.05/judgment = $50–$250 per run; all-in including iteration: <$10K. Time: 3–6 weeks for two competent engineers. **The calibration methodology is not defensible IP.**

What IS defensible within the eval layer: (1) the domain-specific golden dataset of labeled editorial examples, (2) the stage-specific failure taxonomy derived from production incidents, (3) the regression-blocking CI integration tied to business metrics. These compound with time; the calibration math does not.

## Realistic replication timeline after open publication

Historical base rates from comparable cases:

| System | Gap to first credible reproduction | Full parity |
|---|---|---|
| Chain-of-Thought (prompt only) | 0–4 weeks | weeks |
| FlashAttention (code + paper) | 2–6 months adoption | n/a — original was open |
| GraphRAG (code July 2024) | 4–8 weeks for integrations | ~5–6 months (GraphRAG 1.0) |
| DSPy | ~6–12 months to ecosystem | 12–18 months to forks |
| DeepSeek-R1 distillation (no data) | 1 week for evals | ~4 months for step-1 parity |
| Constitutional AI (paper only) | ~14 months | 14+ months |
| RLHF/InstructGPT | 4–6 months to first open impl | ~6 months |

The user's pipeline has the two properties that historically **stretch** replication: a calibrated LLM-as-judge (the single hardest class of components to reproduce, per R1 and CAI precedents) and multi-component hyperparameter interactions (Pareto gating + adversarial critique — analogous to DSPy's MIPROv2 or CAI's critique-revise loop, both notoriously tacit).

**Projection for a well-funded 3–5 engineer competitor team, assuming full open publication of code + 16 reports + ablation data:**
- Months 0–1: reproduce headline numbers on toy inputs
- Months 1–3: routing rules and outline generator working on their own data
- Months 3–6: adversarial critique + Pareto gating at demo quality — **this is where most will stall** on tacit tuning
- Months 6–9: rebuilding judge calibration on their corpus, tuning thresholds, discovering non-obvious component interactions
- Months 9–12: production hardening, their own trustworthy eval harness

**Median replication time: 9–12 months to production parity. A working-but-inferior version: 3–5 months.** A well-funded lab with a prior RAG+eval codebase could compress to 4–6 months. A team without LLM pipeline experience could easily take 18+ months.

## The moves that actually build the moat

The DSPy, vLLM, and LlamaIndex case studies all point to the same playbook. For a solo/small-team founder publishing novel research who wants product/consulting revenue, these moves compound — ordered by how badly skipping them costs you later:

**Weeks 1–4 (do NOW, cannot recover later):**

First, name the primitive. DSPy built "Signatures" and "Teleprompters"; vLLM built "PagedAttention." Every blog post that uses your vocabulary pays you a distribution tax forever. If the user's concept is still called "per-stage cognitive architecture selection," that's a mouthful — pick something terse, sticky, and citable (e.g., "Stage-Aware Routing," "Cognitive Profiles," "Per-Stage Architecture Protocol"). Publish the vocabulary in week 1.

Second, ship the trifecta on the same day: arXiv paper + plain-English blog + GitHub repo with 3–5 runnable Colab notebooks. Hugging Face's BERT-in-one-week story, Jerry Liu's first GPT-Index commit, and vLLM's LMSYS deployment all followed this shape. A paper without runnable code is an academic artifact; a repo without a paper is a tutorial; the combination is infrastructure.

Third, anchor one elite halo user. W&B anchored OpenAI; vLLM anchored LMSYS/Vicuna. Send twenty cold emails to AI content pipeline teams (Perplexity, Hebbia, Harvey, Cursor, vertical-AI startups) offering free implementation in exchange for a published case study. One named reference customer on the README is worth more than 5,000 GitHub stars.

Fourth, ship integration PRs into LangGraph, LlamaIndex, and DSPy — into *their* repos, not yours. Passive distribution on someone else's growth curve is the W&B playbook, and it compounds every time those frameworks gain a user.

Fifth, dominate one social channel daily. Harrison Chase did it on Twitter for LangChain; Jerry Liu for LlamaIndex; Khattab via Stanford seminars. Pick X/Twitter, post once a day, make the founder the avatar.

**Months 2–6 (compound on foundation):**

Publish a weekly head-to-head benchmark chart — your system vs. single-architecture baseline on one task type per week. **Empirical data is the user's unfair advantage** because a well-funded wrapper competitor can clone the code but not the 16 reports of accumulated failure-mode knowledge. Weekly drumbeat converts this asset into permanent distribution.

Start 2–3 paid consulting engagements at $15K–$50K each, with contractual rights to publish anonymized learnings. Each becomes a case study, an enterprise logo, and sharpened domain knowledge. Don't wait for product-market fit — sell the service while the product matures.

Own the leaderboard. Whoever defines how to measure success in a category controls it — MTEB for embeddings, SWE-bench for code agents, HELM for general eval. A "State of Per-Stage Pipelines" annual benchmark, published with code and a public Hugging Face Space, makes the user the scorekeeper. This is the highest-leverage single move for category ownership.

Monetize the observability/operational layer. The LangChain → LangSmith, W&B, and Hugging Face → Inference/Enterprise Hub pattern is now standard: keep the core OSS, sell the closed hosted product with accumulated run data. Ship a $49–499/month self-serve tier plus enterprise tier by month 5, with three paying customers before scaling.

**What NOT to do.** Don't optimize for GitHub stars (vanity, not moat). Don't build a broad "framework for everything" — LangChain's permanent reputation problem. Don't open a Discord before you have ~300 stars of actual interest. Don't delay monetization waiting for scale. Don't neglect the naming window — if someone else names your concept first, you lose that rent forever.

## The post-publication stress test

After full publication on Monday, here is what remains defensible and what becomes commodity:

**Commoditized within 3 months:** the per-stage routing rules themselves (they're IF-statements once published), the concept that different stages benefit from different architectures (now cited everywhere), the ρ=0.841 calibration math, the Pareto gating mechanism in principle.

**Defensible for 6–12 months:** the empirical ablation data showing which architecture wins for which cognitive task on which domain (this is the 16-reports asset and it's genuinely hard to reproduce without rerunning the experiments), the calibrated judge as tuned for *your* domain, the thesis-constrained outline generator with its specific constraint language, the tacit knowledge of what breaks and why.

**Potentially defensible for 18+ months:** the category vocabulary (if named well and evangelized), the reference customer logos and case studies, the benchmark/leaderboard ownership if the user establishes it first, the accumulated trace/run data if a hosted product ships, the community around the project if genuinely cultivated.

**Not defensible at all:** the methodology as intellectual property, academic priority in the abstract sense against unpublished frontier-lab internal tooling.

**The honest answer to "if we publish Monday, can we still build a business by Friday":** yes, but only if by "Friday" the user means "the next six months of execution." The idea alone is not the business — it never was. The business is the flywheel of empirical data, reference customers, named vocabulary, leaderboard, and hosted product. Every one of those requires months of concentrated work that a competitor restarts from zero even with full access to the publication.

## Conclusion: a narrow, short moat that closes without speed

The user is correct that no one has publicly claimed per-stage cognitive architecture selection matched to cognitive task type as described. The priority claim is real and live against public literature. But the moat is narrow in three ways. First, the idea is one small conceptual step from HetaRAG and RouteRAG-RL — two published papers from late 2025 that solve adjacent problems with similar components. Second, the evaluation harness is competent applied engineering, not a research moat — replicable in weeks. Third, the replication timeline after open publication is 9–12 months for a well-funded team, not the multi-year moat some research systems enjoy.

The practical moat after publication is not the artifact — it's operational execution. The entities that win AI infrastructure categories (Hugging Face, Weights & Biases, LangChain, DSPy, LlamaIndex, Ollama, vLLM) all did the same things in the first six months: named the primitives, anchored elite users, shipped integrations into existing frameworks, published relentlessly, owned a vocabulary, monetized an operational layer. None of them won because they had secret code. They won because they executed the category-ownership playbook faster than anyone else.

**The single most important insight:** the user should stop thinking about the moat as "did we get there first" and start thinking about it as "can we be the reference implementation and the scorekeeper of this category by month six." That is achievable. Publishing accelerates it rather than erodes it — but only if week one includes a name, a runnable repo, an anchor user outreach campaign, and integration PRs into LangGraph and LlamaIndex. If the user publishes without those four moves in the same week, a better-resourced competitor can and probably will out-execute them within twelve months.