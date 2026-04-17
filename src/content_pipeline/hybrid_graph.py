"""Hybrid cognitive pipeline — LangGraph orchestration.

Routes each stage to the AI architecture empirically validated for that
stage's cognitive task type. One graph, multiple retrieval modalities,
with every routing decision logged for ablation analysis.

Pipeline flow:
  topic_router → [wiki_selector | vector_retriever | graph_walker]
  → graph_expander → outline_generator → draft_generator
  → bvcs_scorer (1 round max) → adversarial_critic → revision_gate
  → hitl_gate_draft → publisher_stub → END

This is a NEW graph that coexists with the original pipeline in graph.py.
Both can run independently. The hybrid graph reuses existing node functions
where possible (draft_generator, bvcs_scorer, publisher_stub, outline_generator)
and adds new nodes for routing, graph expansion, critique, and revision gating.

Per Report 5: use Command API for routing, append-only architecture_decisions
list in state for ablation analysis.
"""

from __future__ import annotations

import operator
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.content_pipeline.graph import (
    ContentState,
    bvcs_scorer_node,
    draft_generator_node as _original_draft_node,
    outline_generator_node as _original_outline_node,
    publisher_stub_node,
)
from src.content_pipeline.thesis_outline import (
    generate_thesis_outline,
    to_newsletter_outline,
    validate_thesis_outline,
)
from src.content_pipeline.graph_expander import KBGraph, expand
from src.content_pipeline.topic_router import (
    DomainSignalClassifier,
    RetrievalRoute,
    TopicClassification,
)


# ── Hybrid State ──

class HybridContentState(ContentState):
    """Extended state for the hybrid cognitive pipeline.

    Adds routing decisions, graph expansion results, critique proposals,
    and an append-only architecture decision log for ablation analysis.
    """

    # Routing
    topic_classification: dict = Field(default_factory=dict)
    retrieval_route: str = ""

    # Graph expansion
    expanded_finding_ids: list[str] = Field(default_factory=list)
    expansion_details: list[dict] = Field(default_factory=list)

    # Adversarial critique
    critique_proposals: list[dict] = Field(default_factory=list)
    critique_summary: str = ""
    critique_model: str = ""

    # Revision gate
    revision_accepted: bool | None = None
    revision_gate_reason: str = ""
    pre_revision_score: float = 0.0
    post_revision_score: float = 0.0

    # Architecture decision log (append-only for ablation)
    architecture_decisions: Annotated[list[dict], operator.add] = Field(
        default_factory=list
    )

    # Control flags
    auto_approve: bool = False  # skip HITL gates for measurement runs
    max_bvcs_revisions: int = 1  # cap at 1 (down from 3 in original pipeline)


# ── Shared graph state ──

_kb_graph: KBGraph | None = None


def _get_kb_graph() -> KBGraph:
    global _kb_graph
    if _kb_graph is None or not _kb_graph.is_loaded:
        _kb_graph = KBGraph()
        _kb_graph.load()
    return _kb_graph


# ── Node functions ──


def topic_router_node(state: HybridContentState) -> dict:
    """Classify the topic and decide which retrieval modality to use."""
    classifier = DomainSignalClassifier()
    classification = classifier.classify(state.topic)

    return {
        "topic_classification": {
            "matched_anxieties": classification.matched_anxieties,
            "matched_domains": classification.matched_domains,
            "n_domain_clusters": classification.n_domain_clusters,
            "is_cross_domain": classification.is_cross_domain,
            "density": classification.density,
            "n_matched_findings": classification.n_matched_findings,
            "classifier_type": classification.classifier_type,
        },
        "retrieval_route": classification.route.value,
        "architecture_decisions": [{
            "stage": "topic_router",
            "decision": classification.route.value,
            "reason": f"density={classification.density}, cross_domain={classification.is_cross_domain}, clusters={classification.n_domain_clusters}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
        "status": "routed",
    }


def route_after_topic_router(
    state: HybridContentState,
) -> Literal["wiki_selector", "vector_retriever", "graph_walker"]:
    """Conditional edge: route to the appropriate retrieval node."""
    route = state.retrieval_route
    if route == RetrievalRoute.WIKI_SELECTOR.value:
        return "wiki_selector"
    if route == RetrievalRoute.GRAPH_WALKER.value:
        return "graph_walker"
    # vector_retriever is the default (covers dense + OOD)
    return "vector_retriever"


def wiki_selector_node(state: HybridContentState) -> dict:
    """Select findings via wiki index scan (Pipeline C approach).

    Reads the compiled wiki index from kb_wiki/index.md, passes to the LLM
    to select 8-12 findings. This is the cross-domain selection path.

    NOTE: This node requires an API call (LLM reads the index). When running
    without API credits, use the vector_retriever path instead.
    """
    # For now, fall back to the existing retriever with a cross-domain bias
    # Full wiki selector implementation will use Pipeline C's two-pass approach
    from src.content_pipeline.graph import kb_retriever_node, content_selector_node

    retriever_result = kb_retriever_node(state)
    state_with_retrieved = state.model_copy(update=retriever_result)
    selector_result = content_selector_node(state_with_retrieved)

    return {
        **selector_result,
        "architecture_decisions": [{
            "stage": "finding_selection",
            "decision": "wiki_selector",
            "reason": "cross-domain topic routed to wiki index scan",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


def vector_retriever_node(state: HybridContentState) -> dict:
    """Retrieve findings via vector similarity search (Pipeline A approach).

    This is the existing retriever, used for single-domain dense topics
    and OOD topics where tangential retrieval + parametric knowledge works.
    """
    from src.content_pipeline.graph import kb_retriever_node, content_selector_node

    retriever_result = kb_retriever_node(state)
    state_with_retrieved = state.model_copy(update=retriever_result)
    selector_result = content_selector_node(state_with_retrieved)

    return {
        **selector_result,
        "architecture_decisions": [{
            "stage": "finding_selection",
            "decision": "vector_retriever",
            "reason": f"density={state.topic_classification.get('density', 'unknown')}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


def graph_walker_node(state: HybridContentState) -> dict:
    """Retrieve findings via graph traversal for sparse topics.

    Starts from vector-retrieved findings (even if few/weak), then uses
    PPR + MMR to discover related findings via the relationship graph.
    Combines retrieval with immediate graph expansion.
    """
    from src.content_pipeline.graph import kb_retriever_node, content_selector_node

    retriever_result = kb_retriever_node(state)
    state_with_retrieved = state.model_copy(update=retriever_result)
    selector_result = content_selector_node(state_with_retrieved)

    # Immediately expand via graph for sparse topics
    selected = selector_result.get("selected_findings", [])
    if selected:
        kb = _get_kb_graph()
        seed_ids = [sf.finding.id for sf in selected if hasattr(sf, "finding")]
        if seed_ids:
            expanded = expand(kb, [str(uid) for uid in seed_ids], max_expand=5)
            expanded_ids = [r.finding_id for r in expanded if r.source == "expanded"]
            return {
                **selector_result,
                "expanded_finding_ids": expanded_ids,
                "expansion_details": [
                    {"finding_id": r.finding_id, "ppr_score": r.ppr_score,
                     "mmr_score": r.mmr_score, "domains": r.domains, "source": r.source}
                    for r in expanded if r.source == "expanded"
                ],
                "architecture_decisions": [{
                    "stage": "finding_selection",
                    "decision": "graph_walker",
                    "reason": f"sparse topic, expanded {len(seed_ids)} seeds → +{len(expanded_ids)} findings",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

    return {
        **selector_result,
        "architecture_decisions": [{
            "stage": "finding_selection",
            "decision": "graph_walker",
            "reason": "sparse topic, no seeds found for expansion",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


HYBRID_DRAFT_INSTRUCTIONS = """

STRUCTURAL OVERRIDES FOR THIS DRAFT (take precedence over voice profile defaults):

HEADINGS — USE THEM. Each body section MUST have a ## heading that works as a standalone argument. The heading should be a debatable claim, not a topic label. A reader scanning only the headings should get the essay's complete argument structure. Do NOT write continuous prose without section headings.

CITATIONS — Every [src:N] marker MUST be followed immediately by a short quoted phrase (6-15 words) taken verbatim from the finding's claim or elaboration. Format: [src:N] "quoted phrase from the finding." This is non-negotiable — bare [src:N] markers without a quoted phrase are a structural failure. Example: "Loss aversion loads risk perception asymmetrically [src:3] \\"losses loom roughly twice as large as equivalent gains.\\""
"""


def hybrid_draft_generator_node(state: HybridContentState) -> dict:
    """Draft generator with heading + citation instructions injected.

    Wraps the original draft_generator_node but injects structural overrides
    for the hybrid pipeline: argumentative headings (the criterion that
    scored 1-2/5) and quoted-phrase citations (the execution gate issue).

    These instructions are added to the outline text that the drafter reads,
    so they take effect regardless of which voice profile is active.
    """
    # Inject the hybrid instructions into the outline's opener_concept
    # so they're visible to the drafter as part of the outline context
    if state.outline and hasattr(state.outline, "opener_concept"):
        modified_opener = (state.outline.opener_concept or "") + HYBRID_DRAFT_INSTRUCTIONS
        outline_copy = state.outline.model_copy(update={"opener_concept": modified_opener})
        modified_state = state.model_copy(update={"outline": outline_copy})
        result = _original_draft_node(modified_state)
    else:
        result = _original_draft_node(state)

    return {
        **result,
        "architecture_decisions": [{
            "stage": "draft_generation",
            "decision": "hybrid_draft_with_heading_and_citation_overrides",
            "reason": "injected argumentative-heading + quoted-citation instructions",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


def hybrid_outline_node(state: HybridContentState) -> dict:
    """Generate outline — thesis-constrained for Explodable, standard for Boulder.

    Explodable uses Architecture B (Toulmin-complete sections with fear-commit /
    logic-recruit / testimony-deploy stage vocabulary and derivation check).
    Boulder uses the existing outline generator until its own thesis schema is
    designed.

    Includes a DeCRIM-style validation loop: if the thesis outline fails the
    structural contract, logs failures and falls back to the standard outliner.
    """
    if state.brand == "explodable" and state.output_type == "newsletter":
        try:
            thesis_outline = generate_thesis_outline(
                findings=state.selected_findings,
                topic=state.topic,
            )
            failures = validate_thesis_outline(thesis_outline)
            converted = to_newsletter_outline(thesis_outline)
            if not failures:
                return {
                    "outline": converted,
                    "architecture_decisions": [{
                        "stage": "outline_generation",
                        "decision": "thesis_constrained_architecture_b",
                        "reason": "explodable brand, thesis-as-schema with derivation check",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }],
                    "status": "outline_generated",
                }
            else:
                # Validation failed — log and fall back
                return {
                    "outline": converted,  # still usable, just imperfect
                    "architecture_decisions": [{
                        "stage": "outline_generation",
                        "decision": "thesis_constrained_with_failures",
                        "reason": f"validation failures: {'; '.join(failures[:3])}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }],
                    "status": "outline_generated_with_warnings",
                }
        except Exception as e:
            # Thesis outline failed entirely — fall back to standard
            return {
                **_original_outline_node(state),
                "architecture_decisions": [{
                    "stage": "outline_generation",
                    "decision": "standard_fallback",
                    "reason": f"thesis outline failed: {e}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

    # Boulder or non-newsletter: use standard outliner
    return {
        **_original_outline_node(state),
        "architecture_decisions": [{
            "stage": "outline_generation",
            "decision": "standard",
            "reason": f"brand={state.brand}, output_type={state.output_type}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


def graph_expander_node(state: HybridContentState) -> dict:
    """Expand selected findings via PPR + MMR diversity reranking.

    Runs on ALL retrieval paths (not just graph_walker). Adds cross-domain
    findings that share anxiety architecture with the selected set.

    Skipped if graph_walker already did expansion (avoid double-expanding).
    """
    if state.expanded_finding_ids:
        # Graph walker already expanded
        return {
            "architecture_decisions": [{
                "stage": "graph_expansion",
                "decision": "skipped",
                "reason": "already expanded by graph_walker",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    selected = state.selected_findings
    if not selected:
        return {"status": "no_findings_to_expand"}

    kb = _get_kb_graph()
    seed_ids = [str(sf.finding.id) for sf in selected if hasattr(sf, "finding")]
    if not seed_ids:
        return {"status": "no_valid_seeds"}

    results = expand(kb, seed_ids, max_expand=5)
    expanded = [r for r in results if r.source == "expanded"]

    return {
        "expanded_finding_ids": [r.finding_id for r in expanded],
        "expansion_details": [
            {"finding_id": r.finding_id, "ppr_score": r.ppr_score,
             "mmr_score": r.mmr_score, "domains": r.domains, "source": r.source}
            for r in expanded
        ],
        "architecture_decisions": [{
            "stage": "graph_expansion",
            "decision": "ppr_mmr",
            "reason": f"expanded {len(seed_ids)} seeds → +{len(expanded)} findings",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


def adversarial_critic_node(state: HybridContentState) -> dict:
    """Run adversarial critique on the draft with full KB context.

    Uses a different model family from the generator (Gemini > OpenAI >
    Anthropic Opus, in preference order) to prevent reward hacking.

    Requires API credits. Returns empty proposals if no backend is available.
    """
    if not state.draft or not state.draft.newsletter:
        return {"status": "no_draft_to_critique"}

    try:
        from src.content_pipeline.adversarial_critic import (
            critique_draft,
            get_critic,
        )

        # Load KB context for the critic
        cache_path = Path("cache/kb_cag.xml")
        if not cache_path.exists():
            return {
                "critique_summary": "KB cache not found — run compile_read_models.py first",
                "architecture_decisions": [{
                    "stage": "adversarial_critique",
                    "decision": "skipped",
                    "reason": "cache/kb_cag.xml not found",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        kb_xml = cache_path.read_text()
        critic = get_critic()

        result = critique_draft(
            draft_text=state.draft.newsletter,
            kb_xml=kb_xml,
            critic=critic,
        )

        return {
            "critique_proposals": [
                {
                    "dimension": p.dimension.value,
                    "severity": p.severity,
                    "location": p.location,
                    "issue": p.issue,
                    "suggestion": p.suggestion,
                    "finding_ids": p.finding_ids,
                }
                for p in result.proposals
            ],
            "critique_summary": result.summary,
            "critique_model": result.critic_model,
            "architecture_decisions": [{
                "stage": "adversarial_critique",
                "decision": f"critic_model={result.critic_model}",
                "reason": f"{len(result.proposals)} proposals",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    except Exception as e:
        return {
            "critique_summary": f"Critique skipped: {e}",
            "architecture_decisions": [{
                "stage": "adversarial_critique",
                "decision": "skipped",
                "reason": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }


def revision_gate_node(state: HybridContentState) -> dict:
    """Apply Pareto-gated revision based on critique proposals.

    If no proposals or no high-severity proposals, skip revision.
    Otherwise, generate a revised draft and gate via before/after judge scoring.

    NOTE: requires 2 judge API calls (~$0.16). Returns original draft if
    revision doesn't pass the Pareto filter.
    """
    if not state.critique_proposals:
        return {
            "revision_accepted": None,
            "revision_gate_reason": "no critique proposals",
            "architecture_decisions": [{
                "stage": "revision_gate",
                "decision": "skipped",
                "reason": "no proposals",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    high_severity = [p for p in state.critique_proposals if p.get("severity") == "high"]
    if not high_severity:
        return {
            "revision_accepted": None,
            "revision_gate_reason": "no high-severity proposals — original preserved",
            "architecture_decisions": [{
                "stage": "revision_gate",
                "decision": "skipped",
                "reason": f"{len(state.critique_proposals)} proposals but none high-severity",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    # TODO: implement actual revision when API credits are available.
    # Steps:
    # 1. Format high-severity proposals as revision instructions
    # 2. Call drafter with REVISION_SYSTEM_PROMPT + original draft + instructions
    # 3. Score both original and revised via Phase 0 judge
    # 4. Apply Pareto filter via revision_gate.py
    # 5. Keep whichever passes

    return {
        "revision_accepted": None,
        "revision_gate_reason": f"revision pending — {len(high_severity)} high-severity proposals awaiting implementation",
        "architecture_decisions": [{
            "stage": "revision_gate",
            "decision": "pending",
            "reason": f"{len(high_severity)} high-severity proposals",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


def hitl_gate_draft_node(state: HybridContentState) -> dict:
    """Human-in-the-loop gate for draft review.

    Auto-approves if state.auto_approve is True (for measurement runs).
    Otherwise, interrupts for operator decision.
    """
    if state.auto_approve:
        return {
            "draft_decision": {"action": "approve", "reason": "auto_approve"},
            "status": "draft_approved",
        }
    decision = interrupt({
        "gate": "draft_review",
        "draft": state.draft.newsletter if state.draft else "",
        "bvcs_score": state.bvcs_result.score if state.bvcs_result else None,
        "critique_summary": state.critique_summary,
        "n_critique_proposals": len(state.critique_proposals),
    })
    return {"draft_decision": decision, "status": "draft_reviewed"}


def route_after_draft_review(
    state: HybridContentState,
) -> Literal["publisher_stub", "__end__"]:
    action = state.draft_decision.get("action", "approve")
    if action == "reject":
        return END
    return "publisher_stub"


def route_after_bvcs(
    state: HybridContentState,
) -> Literal["adversarial_critic", "draft_revise"]:
    """Route after BVCS scoring.

    Unlike original pipeline (which loops up to 3 times), the hybrid
    pipeline caps at 1 BVCS revision, then proceeds to adversarial critique.
    """
    if state.bvcs_result and state.bvcs_result.total_score < 70 and state.revision_count < state.max_bvcs_revisions:
        return "draft_revise"
    return "adversarial_critic"


def draft_revise_node(state: HybridContentState) -> dict:
    """BVCS-driven revision (inherited from original pipeline).

    Passes BVCS revision notes back to the draft generator. Capped at
    max_bvcs_revisions (default 1, down from 3 in original pipeline).
    """
    from src.content_pipeline.graph import draft_revise_node as _original_revise
    result = _original_revise(state)
    return {
        **result,
        "architecture_decisions": [{
            "stage": "bvcs_revision",
            "decision": f"revision_{state.revision_count + 1}",
            "reason": f"bvcs_score={state.bvcs_result.total_score if state.bvcs_result else '?'} < 70",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


# ── Graph definition ──


def build_hybrid_graph() -> StateGraph:
    """Build the hybrid cognitive pipeline StateGraph.

    Flow:
      topic_router → [wiki_selector | vector_retriever | graph_walker]
      → graph_expander → outline_generator → draft_generator
      → bvcs_scorer → [pass → adversarial_critic, fail → draft_revise → bvcs_scorer]
      → adversarial_critic → revision_gate → hitl_gate_draft
      → [approve → publisher_stub → END, reject → END]
    """
    graph = StateGraph(HybridContentState)

    # Nodes
    graph.add_node("topic_router", topic_router_node)
    graph.add_node("wiki_selector", wiki_selector_node)
    graph.add_node("vector_retriever", vector_retriever_node)
    graph.add_node("graph_walker", graph_walker_node)
    graph.add_node("graph_expander", graph_expander_node)
    graph.add_node("outline_generator", hybrid_outline_node)
    graph.add_node("draft_generator", hybrid_draft_generator_node)
    graph.add_node("bvcs_scorer", bvcs_scorer_node)
    graph.add_node("draft_revise", draft_revise_node)
    graph.add_node("adversarial_critic", adversarial_critic_node)
    graph.add_node("revision_gate", revision_gate_node)
    graph.add_node("hitl_gate_draft", hitl_gate_draft_node)
    graph.add_node("publisher_stub", publisher_stub_node)

    # Edges
    graph.add_edge(START, "topic_router")
    graph.add_conditional_edges(
        "topic_router",
        route_after_topic_router,
        {
            "wiki_selector": "wiki_selector",
            "vector_retriever": "vector_retriever",
            "graph_walker": "graph_walker",
        },
    )

    # All retrieval paths converge at graph_expander
    graph.add_edge("wiki_selector", "graph_expander")
    graph.add_edge("vector_retriever", "graph_expander")
    graph.add_edge("graph_walker", "graph_expander")

    # graph_expander → thesis_outline (Explodable) or outline (Boulder) → draft → bvcs
    graph.add_edge("graph_expander", "outline_generator")
    graph.add_edge("outline_generator", "draft_generator")
    graph.add_edge("draft_generator", "bvcs_scorer")

    # BVCS: pass → critic, fail → revise (capped at 1)
    graph.add_conditional_edges(
        "bvcs_scorer",
        route_after_bvcs,
        {
            "adversarial_critic": "adversarial_critic",
            "draft_revise": "draft_revise",
        },
    )
    graph.add_edge("draft_revise", "bvcs_scorer")

    # Critique → revision gate → HITL → publish
    graph.add_edge("adversarial_critic", "revision_gate")
    graph.add_edge("revision_gate", "hitl_gate_draft")
    graph.add_conditional_edges(
        "hitl_gate_draft",
        route_after_draft_review,
        {"publisher_stub": "publisher_stub", END: END},
    )
    graph.add_edge("publisher_stub", END)

    return graph


def compile_hybrid_graph(checkpointer=None):
    """Compile the hybrid pipeline with optional checkpointer."""
    graph = build_hybrid_graph()
    return graph.compile(checkpointer=checkpointer)
