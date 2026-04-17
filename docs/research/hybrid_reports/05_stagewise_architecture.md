# Stage-wise architecture selection for AI generation pipelines

**Selecting knowledge-access architecture per pipeline stage based on cognitive task type is a genuine research gap with clear publication potential.** No published work directly addresses this combination — per-stage architecture selection exists for RAG Q&A pipelines (AutoRAG), per-query routing is well-established (Adaptive-RAG, MBA-RAG), and cognitive-task framing has been connected to retrieval design (RAG+) — but nobody has assembled these pieces into a framework that maps generation pipeline stages to knowledge architectures by cognitive task type. The building blocks are all present; the synthesis is missing. Below is a detailed analysis of all five research questions.

---

## 1. The novelty scan reveals a clear gap between adjacent work

The most relevant existing work falls into three distinct categories, none of which covers the proposed approach.

**Per-stage module optimization (closest match).** AutoRAG (Kim et al., arXiv 2410.20878, October 2024) is the single closest paper. It models a RAG pipeline as a multi-stage graph — Query Expansion → Retrieval → Passage Augmentation → Reranking → Prompt Creation → Generation — and uses greedy stagewise search to select the best-performing module at each node. Critical distinction: AutoRAG optimizes *within* a standard RAG Q&A pipeline, selecting between variations of the same paradigm (BM25 vs. dense retrieval vs. hybrid), not between fundamentally different knowledge-access architectures (vector vs. graph vs. context-stuffing). It also optimizes per-dataset, not by cognitive task classification.

**Per-query adaptive routing (well-established but orthogonal).** Adaptive-RAG (Jeong et al., NAACL 2024) routes by query complexity into no-retrieval, single-hop, or multi-hop strategies. Self-RAG (Asai et al., ICLR 2024) generates reflection tokens deciding *when* to retrieve. CRAG (Yan et al., ICLR 2025) triggers corrective actions when initial retrieval fails. MBA-RAG (Tang et al., COLING 2025) treats retrieval methods as multi-armed bandit arms selected per query. EA-GraphRAG (arXiv 2602.03578, February 2025) routes between dense vector and graph-based retrieval using syntactic complexity scoring. All of these operate at the *query* level, not the *pipeline stage* level — this is the critical distinction. The unit of analysis in existing work is the incoming query; in the proposed work, it's the stage's cognitive task type.

**Cognitive-task-aware retrieval (emerging but incomplete).** RAG+ (Wang et al., EMNLP 2025) is the only paper found that explicitly connects cognitive task typology — specifically Bloom's Taxonomy and ACT-R cognitive architectures — to retrieval design. It distinguishes declarative memory (facts) from procedural memory (reasoning chains) and adds application-aware retrieval. However, it adds a single retrieval type rather than providing a full per-stage selection framework. The "Reasoning RAG via System 1/System 2" paper (arXiv 2506.10408, June 2025) maps RAG paradigms to dual-process cognitive theory but doesn't operationalize it as architecture selection.

**Enabling frameworks.** DSPy (Khattab et al., ICLR 2024) provides a programming model for composing multi-stage LM pipelines where different stages *can* use different modules, but prescribes no theory of which architecture fits which stage. The Modular RAG taxonomy (Gao et al., arXiv 2312.10997) conceptualizes swappable modules but doesn't empirically validate per-stage selection. RAGRouter-Bench (arXiv 2602.00296, February 2025) — the first benchmark for routing across five RAG paradigms — explicitly notes that "most work treats these paradigms as competing alternatives rather than context-dependent choices."

**The specific gap:** A framework that (a) classifies generation pipeline stages by cognitive task type, (b) maps those types to optimal knowledge-access architectures, and (c) empirically validates this mapping across a multi-stage content generation workflow does not exist in the published literature as of April 2026.

---

## 2. Ablation methodology borrows heavily from causal inference and mechanistic interpretability

Isolating each stage's contribution in a sequentially dependent pipeline is fundamentally a causal inference problem, and the most principled approaches come from outside traditional NLP methodology.

**Activation patching is the most directly applicable framework.** Developed within mechanistic interpretability (Geiger et al., NeurIPS 2021; Meng et al., NeurIPS 2022; Zhang & Nanda, ICLR 2024), activation patching works in three steps: run the pipeline with configuration A and cache all intermediate outputs; run with configuration B; at a specific stage, patch A's cached output into B's run and measure whether end-to-end quality changes. If patching stage K's output from the "good" configuration into the "bad" run restores quality, that stage is causally important. Two complementary variants exist: **denoising** (patch clean into corrupted, testing sufficiency) and **noising** (patch corrupted into clean, testing necessity). This directly addresses the core confound — whether a quality delta is attributable to stage 2 or to downstream adaptation.

**Causal mediation analysis provides the formal framework.** Vig, Gehrmann, and Belinkov (NeurIPS 2020) adapted causal mediation analysis from epidemiology to decompose NLP model behavior into direct effects (input → output) and indirect effects (input → mediator → output). For a pipeline, each stage is a mediator. The total effect of changing stage K decomposes into the *natural direct effect* (stage K's output changes, downstream stages adapt naturally) and the *natural indirect effect* (downstream stages respond differently to K's changed output). A comprehensive survey — "The Quest for the Right Mediator" (Computational Linguistics, 2025) — provides a taxonomy of these methods.

**Standard ablation dramatically overestimates component importance.** Li and Janson (NeurIPS 2024, "Optimal Ablation for Interpretability") showed that naive ablation methods (zero, mean, or resample ablation) overestimate component importance — optimal ablation accounts for only **11.1%** of zero ablation's measured effect for the median component. The choice of *what to replace the component with* is itself a major confound. For pipeline stages, this means comparing "stage with architecture A" vs. "stage with architecture B" is more meaningful than "stage present" vs. "stage removed."

**Shapley values handle attribution in sequential pipelines.** ShapleyPipe (arXiv 2510.27168, 2025) introduces **position-specific Shapley values** that account for order-dependence — the same operator contributes differently depending on its pipeline position. It uses hierarchical decomposition to reduce complexity from exponential to polynomial. This is directly applicable to an 8-stage pipeline where you need to fairly attribute end-to-end quality to each stage's architecture choice.

**Practical recommendation for an 8-stage pipeline — a four-phase protocol:**

- **Phase 1 (Screening):** Run a Plackett-Burman design — **12 runs** for 8 binary factors (current vs. alternative architecture per stage). This identifies which stages have the largest main effects on end-to-end quality. Many stages may barely matter.
- **Phase 2 (Interaction detection):** For the top 4–5 stages from Phase 1, run a **Resolution V fractional factorial** (16–32 runs) to estimate all two-way interactions free of confounding. Alternatively, compute SHAP interaction values via Monte Carlo Shapley (~1,000 permutations).
- **Phase 3 (Causal confirmation):** For key stages, apply the activation patching protocol — run with config A and B, cache intermediates, patch specific stages, test both necessity and sufficiency.
- **Phase 4 (Compensatory effect detection):** For stages suspected of compensating for each other (e.g., adversarial critique masking weak retrieval), test double ablation: degrade both simultaneously and check for super-additivity (Δ_both > Δ_retrieval + Δ_critique).

The biggest methodological gap: **no published NLP paper has applied formal mediation analysis or activation patching to a multi-model, multi-stage generation system**. All existing work applies these methods within single neural networks. Extending them to discrete pipeline stages where each stage may use a different LLM/retriever is open territory — and is itself a methodological contribution worth documenting.

---

## 3. Handling interaction effects without combinatorial explosion

The interaction problem — better retrieval makes outline generation easier while adversarial critique compensates for weaker retrieval — is well-studied in Design of Experiments but almost never applied in NLP pipeline evaluation.

**Fractional factorial designs are the established solution.** For 8 stages with 2 architecture levels each, full factorial requires **256 runs**. A Resolution IV fractional factorial (2^(8-4)) requires only **16 runs** and estimates all main effects free of two-factor interaction confounding. The key assumption enabling this aggressive fractionation is the **sparsity of effects principle**: in most systems, main effects dominate, two-factor interactions are secondary, and higher-order interactions are negligible. For an 8-stage pipeline, a two-factor approximation requires estimating only 37 parameters (1 grand mean + 8 main effects + 28 two-way interactions) instead of 256.

**Variance-based sensitivity analysis (Sobol indices) quantifies interaction involvement.** Sobol indices decompose total output variance into first-order indices S_i (variance from factor i alone) and total-order indices S_i^T (variance from factor i including all interactions). The gap S_i^T − S_i directly measures how much a stage participates in interactions. Computable with ~80 evaluations for 8 factors using Saltelli sampling — highly practical.

**Bayesian optimization handles the full search implicitly.** Model the pipeline's end-to-end quality as a black-box function of architecture choices. A Gaussian Process surrogate captures correlations between stages, including interactions. Typically **50–100 evaluations** suffice to find near-optimal configurations for 8 binary factors. Tools like Optuna or SMAC implement this directly.

**The compensatory masquerade problem requires targeted detection.** When adversarial critique compensates for weak retrieval, standard single-component ablation *underestimates* retrieval's importance because critique hides the deficit. Detection requires comparing single ablation against double ablation: if degrading retrieval alone drops quality by 5 points but degrading both retrieval and critique drops it by 20 points, the 15-point gap reveals compensatory interaction. This concept is well-documented in neuroscience-inspired ablation literature but has never been formally applied to LLM pipelines.

**The FACTORS framework (arXiv 2509.10825, 2025)** combines factorial decomposition with Shapley-based attribution, includes uncertainty quantification, and handles unbalanced evaluation logs — but has only been tested on regression/classification benchmarks, not generative pipelines. Applying it to an 8-stage content generation pipeline would be novel.

| Method | Runs needed (8 stages, 2 levels) | Interaction information | Practical feasibility |
|--------|--------------------------------|----------------------|---------------------|
| Full factorial | 256 | All interactions | Expensive but possible |
| Resolution IV fractional | 16 | Main effects + confounded 2-way | Very practical |
| Plackett-Burman screening | 12 | Main effects only | Best for initial screening |
| Sobol sensitivity | ~80 | First + total order indices | Practical |
| Bayesian optimization | 50–100 | Implicit in surrogate model | Very practical |
| Monte Carlo Shapley | ~8,000 evaluations | Full attribution | Moderate cost |

---

## 4. Publishability is strong for a workshop paper and plausible for Findings

**Genuine novelty exists in three dimensions.** First, per-stage architecture selection in a content generation pipeline (not Q&A) based on cognitive task type has no direct precedent. Second, the 8-stage pipeline itself — topic classification through quality scoring — is substantially more complex than the standard retrieve-generate-answer setup that dominates RAG literature. Third, a calibrated 10-criterion LLM judge with **ρ = 0.841** against a 5-model ground truth panel (internal ρ ≈ 0.83) is a strong empirical result; most published LLM-as-judge work reports lower human-LLM agreement.

**The key positioning move is against Adaptive-RAG.** Adaptive-RAG routes by *query complexity*; this work routes by *pipeline stage cognitive type*. Their unit of analysis is the incoming query; yours is the generation task. This is a clean, citable distinction that reviewers will immediately understand. Secondary positioning against MMOA-RAG (NeurIPS 2025), which jointly optimizes pipeline modules with multi-agent RL but doesn't select between fundamentally different knowledge-access architectures per stage.

**Reviewers will expect specific evidence.** A per-stage architecture comparison matrix (rows = stages, columns = architectures, cells = quality scores with confidence intervals) is essential. Statistical significance tests for architecture differences at each stage, not just "X wins on stage Y." End-to-end comparison showing the per-stage-optimized pipeline outperforms any uniform-architecture baseline. Cost/latency analysis. At least one additional content domain for generalizability. Error analysis showing what failure types each architecture produces at each stage.

**Target venues and timing:**

- **EMNLP 2025** (November 2025, Suzhou): ARR May cycle with commit around August. Strong fit for Findings track. The evaluation/methodology angle fits well.
- **ACL 2026** (July 2026, San Diego): ARR cycles through early 2026. Main conference or workshops.
- **SIGIR 2026**: Strong fit for retrieval-focused evaluation work.
- **Eval4RAG workshop** (ran at ECIR 2025; likely to recur at ECIR 2026): Nearly perfect thematic fit.
- **NeurIPS 2026 workshops**: Watch for RAG/evaluation-focused workshops; CFPs typically in September.

**Recommended framing:** "Cognitive-Task-Aware Architecture Selection for Multi-Stage Generation Pipelines: An Empirical Study." Lead with the empirical finding (different architectures win on different stages), not the system description. Do *not* frame it as "we built a system with LangGraph" or "RAG vs. CAG" — the contribution is the per-stage analysis methodology and its results. The calibrated evaluation harness is a secondary contribution worth highlighting.

**What pushes this from workshop to conference paper:** Adding the ablation methodology (Phase 1–4 protocol from Section 2) as a methodological contribution alongside the empirical findings. If the paper both proposes the cognitive-task-level selection framework *and* demonstrates a principled ablation method for validating it in sequentially dependent pipelines, it addresses two gaps simultaneously and becomes substantially stronger.

---

## 5. LangGraph routing patterns for stage-wise architecture selection

**The Command API is the recommended pattern for this use case.** It atomically updates state and routes in a single node function, eliminating the separation between "record the architecture decision" and "dispatch to the backend." This is the newer LangGraph API and handles the exact requirement of persisting decisions while routing:

```python
from langgraph.types import Command
from typing import Literal

STAGE_ROUTING_CONFIG = {
    "topic_classification": "index_scan",
    "finding_selection": "pgvector",
    "graph_expansion": "graph_traversal",
    "outline_generation": "graph_traversal",
    "draft_writing": "full_context",
    "adversarial_critique": "pgvector",
    "revision": "full_context",
    "quality_scoring": "index_scan",
}

def stage_router(state) -> Command[Literal["pgvector", "graph_traversal",
                                            "full_context", "index_scan"]]:
    stage = state["current_stage"]
    chosen = STAGE_ROUTING_CONFIG[stage]
    return Command(
        update={
            "active_backend": chosen,
            "architecture_decisions": [
                {"stage": stage, "backend": chosen, "timestamp": now()}
            ]
        },
        goto=chosen
    )
```

**Persist architecture decisions in an append-only state list.** Use `Annotated[list[dict], operator.add]` as the reducer for `architecture_decisions` — each stage's router appends its decision, creating a full audit trail visible to all downstream nodes and automatically persisted by the Postgres checkpointer. This enables downstream stages to condition on upstream architecture choices (e.g., if graph expansion used graph traversal, the outline generator knows relational structure is available) and provides a complete record for ablation analysis via `graph.get_state_history(config)`.

**Use conditional branches, not subgraphs, for architecture backends.** For an 8-stage pipeline where each stage selects one backend, flat conditional branches are cleaner than nested subgraphs. Subgraphs add parent-child state mapping complexity, have known issues with Command navigation (GitHub issues #2940, #3362), and are overkill when each backend is essentially a single retrieval function. The exception: if a backend becomes multi-step internally (e.g., graph traversal requiring entity extraction → traversal → aggregation), wrap *that specific backend* in a subgraph while keeping simple backends as flat nodes.

**The recommended graph structure for each stage:**

```
stage_N_router → [pgvector | graph_traversal | full_context | index_scan]
    → stage_N_processor → stage_N+1_router → ...
```

Each `stage_N_router` reads `current_stage` from state, looks up the empirically-determined best architecture, logs the decision, and dispatches. All backend branches converge to `stage_N_processor` which handles the stage's core logic with the retrieved context.

**Critical gotchas to avoid.** Do not mix Command routing with static `add_edge` on the same node — both will execute, causing dual dispatch. Always type-annotate Command return types for LangGraph Studio visualization. Use the "Pointer State Pattern" to avoid checkpoint bloat: store document IDs/references in state rather than full retrieved text, since the Postgres checkpointer creates a new checkpoint at every super-step across 8 stages. Separate input/output schemas from internal state using `StateGraph(InternalState, input_schema=InputState, output_schema=OutputState)` to keep routing metadata private.

**Real-world precedent exists for dual-backend routing** in the official LangGraph Adaptive RAG tutorial (routes between vectorstore and web search), Neo4j's GraphRAG workflow (routes between vector similarity and Cypher graph queries), and FalkorDB's hybrid query implementation. None of these implement 4-way routing across fundamentally different architectures at 8 pipeline stages — this is where the engineering novelty lies.

---

## Conclusion: three actionable paths forward

The research reveals three distinct contributions that can be pursued independently or combined. **The empirical contribution** — demonstrating that architecture selection at the cognitive-task level outperforms uniform-architecture pipelines — is the most immediately publishable finding and requires completing the per-stage comparison matrix with statistical rigor. **The methodological contribution** — a principled ablation protocol for sequentially dependent generation pipelines, combining fractional factorial screening with activation patching and compensatory effect detection — fills a gap that no existing NLP paper addresses and strengthens any publication significantly. **The systems contribution** — the Command-API routing pattern with append-only decision logging in LangGraph — is implementation work that supports reproducibility but is not a paper contribution on its own.

The strongest publication strategy combines the first two: frame the paper around the empirical finding with the ablation methodology as the evaluation backbone. Position explicitly against Adaptive-RAG (per-query routing) and MMOA-RAG (joint optimization) to establish the novelty of per-stage, cognitive-task-typed architecture selection. Target ARR submission for EMNLP 2025 Findings or ACL 2026, with Eval4RAG 2026 as a workshop backup. The ρ = 0.841 calibrated judge is publishable evidence in its own right — consider whether the judge methodology deserves a separate short paper or belongs integrated into the main contribution.