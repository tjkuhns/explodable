# Experimental pipeline modules

These modules power `hybrid_graph.py` — the measurement / ablation
pipeline used to evaluate architecture changes before they're promoted
into the production `graph.py`.

## Contents

| Module | Purpose |
|---|---|
| `hybrid_graph.py` | LangGraph StateGraph with topic routing, graph expansion, adversarial critique, and a revision gate. Used for benchmark runs. |
| `topic_router.py` | Classifies topics on (domain coverage × cross-domain × density) and routes to the retrieval modality empirically best for that combination. |
| `graph_expander.py` | Personalized PageRank + MMR diversity reranking over the finding-relationships graph. |
| `adversarial_critic.py` | Different-model critic (Gemini Flash preferred over OpenAI over Anthropic Opus) producing atomic critique proposals. |
| `revision_gate.py` | Pareto filter: accepts a revision only if ≥1 criterion improves via the calibrated judge and none regress. Module fully implemented + unit-tested; the graph-node integration in `hybrid_graph.py` is stubbed in the high-severity branch (see `docs/architecture.md` §5). |
| `thesis_outline.py` | Explodable Architecture B — Toulmin-complete sections over `fear-commit → logic-recruit → testimony-deploy` stage vocabulary with structural contract validation. |

## The production / experimental boundary

- **Production** (`src/content_pipeline/graph.py`): the path used by
  `POST /api/generate/content` → `src/shared/tasks.py::run_content_pipeline`.
  Stable. Touched only after benchmark-validated changes.
- **Experimental** (this directory): where architecture changes are
  evaluated against the calibrated judge (ρ = 0.782 Sonnet / ρ = 0.841
  Opus, with the post-hoc outlier-drop caveat documented in
  `docs/eval-methodology.md`). Scripts like
  `scripts/phase2_run_n50.py` run the hybrid graph against the N=50
  test set to measure deltas.

## Promotion criteria

A module or mechanism graduates from experimental to production when:

1. Its effect is measured against the calibrated judge on the N=50
   test set, with confidence intervals.
2. The win is either (a) a direct quality improvement (≥ +3 points on
   the primary rubric) or (b) an ablation result that meaningfully
   changes the production architecture's design (e.g. the CAG negative
   result).
3. The cost and latency tradeoffs are characterized.
4. A pull request moves the code into `graph.py` or a production
   collaborator, updates `docs/architecture.md`, and runs the N=50
   benchmark pre/post to confirm no regression.

## What is NOT in this directory

Everything in `src/content_pipeline/` outside of `experimental/` is
production — `graph.py`, `retriever.py`, `selector.py`, `outline.py`,
`draft_generator.py`, `bvcs.py`, `citation_processor.py`, and the
`eval/` subpackage. The calibrated judge lives in `eval/judge.py` and
is shared by both production and experimental code.
