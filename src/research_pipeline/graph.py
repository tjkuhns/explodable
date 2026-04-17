"""DEPRECATED 2026-04-14 — see src/research_pipeline/DEPRECATED.md

Research Pipeline — LangGraph StateGraph. Dormant dependency of drift_monitor.
No longer an active ingestion path. Do not review as part of project audits.

Nodes: planner → researchers (parallel via Send) → synthesizer → critic → hitl_gate_1 → kb_writer
State: ResearchState (Pydantic) — all inter-node data in structured fields, never conversational
Checkpointing: PostgresSaver — every node transition persisted
HITL gate 1: interrupt() after critic. Resumes on operator action.
Max 2 retries for failed findings routed back to researchers.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, interrupt, Command

from src.research_pipeline.planner import (
    ResearchPlan,
    ResearchTask,
    plan_research,
)
from src.research_pipeline.researcher import (
    ResearchResult,
    research_task,
)
from src.research_pipeline.synthesizer import (
    SynthesisResult,
    ProposedFinding,
    Conflict,
    synthesize,
)
from src.research_pipeline.critic import (
    CriticResult,
    critique_finding,
)
from src.kb.models import (
    FindingCreate,
    FindingStatus,
    FindingProvenance,
    RootAnxiety,
    PankseppCircuit,
)


# ── State ──


def _merge_research_results(
    existing: list[ResearchResult], new: list[ResearchResult]
) -> list[ResearchResult]:
    """Reducer: merge parallel researcher results into a single list."""
    return existing + new


class ResearchState(BaseModel):
    """Structured state for the research pipeline. No conversational fields."""

    # Input
    directive: str = ""

    # Planner output
    plan: ResearchPlan | None = None

    # Researcher outputs (accumulated via reducer)
    research_results: Annotated[list[ResearchResult], _merge_research_results] = Field(
        default_factory=list
    )

    # Synthesizer output
    synthesis: SynthesisResult | None = None

    # Critic output
    critic_results: list[CriticResult] = Field(default_factory=list)
    retry_count: int = 0

    # HITL gate 1 output
    operator_decisions: list[dict] = Field(default_factory=list)

    # KB write results
    written_finding_ids: list[str] = Field(default_factory=list)
    contradictions_written: int = 0

    # Pipeline metadata
    started_at: str = ""
    completed_at: str = ""
    status: str = "pending"


# ── Node functions ──


def planner_node(state: ResearchState) -> dict:
    """Decompose the research directive into parallel tasks."""
    plan = plan_research(state.directive)
    return {
        "plan": plan,
        "started_at": datetime.utcnow().isoformat(),
        "status": "planning_complete",
    }


def researcher_node(state: ResearchState | dict) -> dict:
    """Execute a single research task. Invoked in parallel via Send."""
    import structlog
    logger = structlog.get_logger()

    # Send passes a raw dict, not a ResearchState — handle both
    if isinstance(state, dict):
        plan_data = state["plan"]
        if isinstance(plan_data, dict):
            task = ResearchTask(**plan_data["tasks"][0])
        else:
            task = plan_data.tasks[0]
    else:
        task = state.plan.tasks[0]

    try:
        result = research_task(task)
        return {"research_results": [result]}
    except Exception as e:
        logger.error("researcher_node.failed", task_id=task.task_id, error=str(e))
        # Return empty so other parallel researchers can still succeed
        return {"research_results": []}


def route_to_researchers(state: ResearchState) -> list[Send]:
    """Fan out to parallel researcher nodes, one per task."""
    sends = []
    for task in state.plan.tasks:
        # Send a state dict with a plan containing only this one task.
        # LangGraph merges this into a ResearchState for the researcher node.
        sends.append(
            Send(
                "researcher",
                {
                    "directive": state.directive,
                    "plan": ResearchPlan(
                        topic=state.plan.topic,
                        root_anxiety_hints=state.plan.root_anxiety_hints,
                        tasks=[task],
                        rationale=state.plan.rationale,
                    ).model_dump(),
                },
            )
        )
    return sends


def synthesizer_node(state: ResearchState) -> dict:
    """Deduplicate and detect conflicts across research results."""
    import structlog
    logger = structlog.get_logger()

    # Filter out any empty/broken results from failed researchers
    valid_results = [r for r in state.research_results if r.claim]
    if not valid_results:
        logger.warning("synthesizer_node.no_valid_results")
        from src.research_pipeline.synthesizer import SynthesisResult
        return {"synthesis": SynthesisResult(proposed_findings=[], conflicts=[]), "status": "synthesis_complete"}

    synthesis = synthesize(valid_results)
    return {"synthesis": synthesis, "status": "synthesis_complete"}


def critic_node(state: ResearchState) -> dict:
    """Validate groundedness of proposed findings from synthesis.

    On retries, only critiques new findings from synthesis. Already-approved
    findings are in state.critic_results (set by retry_research_node).
    We deduplicate by claim to prevent accumulation across retries.
    """
    # Already-approved findings carried forward from retries
    approved_claims = set()
    carried_forward = []
    for cr in state.critic_results:
        if cr.approved and cr.finding.claim not in approved_claims:
            carried_forward.append(cr)
            approved_claims.add(cr.finding.claim)

    # Critique only new findings (skip if already approved)
    new_results = []
    for finding in state.synthesis.proposed_findings:
        if finding.claim and finding.claim not in approved_claims:
            try:
                result = critique_finding(finding, retry_count=state.retry_count)
                new_results.append(result)
            except Exception as e:
                import structlog
                structlog.get_logger().error("critic_node.finding_failed", claim=finding.claim[:60], error=str(e))

    return {
        "critic_results": carried_forward + new_results,
        "status": "critic_complete",
    }


def route_after_critic(state: ResearchState) -> str:
    """Route based on critic results: retry failed findings or proceed to HITL."""
    has_failures = any(not cr.approved for cr in state.critic_results)
    can_retry = state.retry_count < 2

    if has_failures and can_retry:
        return "retry_research"
    return "hitl_gate_1"


def retry_research_node(state: ResearchState) -> dict:
    """Re-run research for findings that failed critic review.

    Takes revision suggestions from the critic and creates new research tasks.
    Preserves already-approved critic results so they aren't re-evaluated.
    Max 2 retries enforced by route_after_critic.
    """
    approved = [cr for cr in state.critic_results if cr.approved]
    failed = [cr for cr in state.critic_results if not cr.approved]

    # Build new tasks from failed findings using revision suggestions
    new_tasks = []
    for i, cr in enumerate(failed):
        suggestions = "; ".join(cr.revision_suggestions) if cr.revision_suggestions else "Find stronger sources"
        new_tasks.append(
            ResearchTask(
                task_id=f"retry_{state.retry_count + 1}_{i}",
                query=f"{cr.finding.claim}. Additional context needed: {suggestions}",
                search_keywords=cr.finding.claim.split()[:5],
                expected_domain=cr.finding.academic_discipline,
                source_priority=["academic", "journalism", "book"],
            )
        )

    # Run new research tasks (only the failed ones)
    new_results = []
    for task in new_tasks:
        try:
            result = research_task(task)
            new_results.append(result)
        except Exception as e:
            import structlog
            structlog.get_logger().error("retry_research.task_failed", task_id=task.task_id, error=str(e))

    return {
        "research_results": new_results,
        "critic_results": approved,  # Preserve approved, clear failed
        "synthesis": None,
        "retry_count": state.retry_count + 1,
        "status": f"retry_{state.retry_count + 1}",
    }


def hitl_gate_1_node(state: ResearchState) -> dict:
    """Human-in-the-loop gate 1: operator reviews proposed findings.

    Interrupts execution. Operator approves/rejects/edits each finding.
    Resumes with operator decisions.
    """
    # Prepare findings for operator review
    pending_findings = []
    for cr in state.critic_results:
        if cr.approved:
            pending_findings.append(
                {
                    "claim": cr.finding.claim,
                    "elaboration": cr.finding.elaboration,
                    "root_anxieties": cr.finding.root_anxieties,
                    "primary_circuits": cr.finding.primary_circuits,
                    "confidence_score": cr.finding.confidence_score,
                    "confidence_basis": cr.finding.confidence_basis,
                    "academic_discipline": cr.finding.academic_discipline,
                    "sources": [s.model_dump() for s in cr.finding.sources],
                    "groundedness_score": cr.groundedness_score,
                    "kb_status": cr.finding.kb_status,
                }
            )

    # Notify operator UI that findings are ready for review
    try:
        from src.shared.notifications import notify_research_findings_ready
        notify_research_findings_ready(
            thread_id=state.started_at or "unknown",
            finding_count=len(pending_findings),
        )
    except Exception:
        pass  # Notification failure must not block the pipeline

    # Interrupt and wait for operator input
    # Returns list of dicts: [{"action": "approve"|"reject"|"edit"|"request_more", ...}, ...]
    operator_decisions = interrupt(
        {
            "type": "research_review",
            "findings": pending_findings,
            "message": f"{len(pending_findings)} finding(s) pending review. Actions: approve, reject, edit, request_more",
        }
    )

    return {
        "operator_decisions": operator_decisions,
        "status": "hitl_gate_1_complete",
    }


def kb_writer_node(state: ResearchState) -> dict:
    """Write operator-approved findings to the KB with embeddings and relationships."""
    written_ids = []
    contradictions_written = 0

    # The HITL gate only shows critic-approved findings to the operator.
    # operator_decisions[i] maps to the i-th critic-approved finding.
    critic_approved = [cr for cr in state.critic_results if cr.approved]

    findings_to_write = []
    findings_request_more = []
    # Track which ProposedFinding each written finding came from, for contradiction mapping
    finding_to_source: dict[str, object] = {}  # written_id → ProposedFinding

    for i, decision in enumerate(state.operator_decisions):
        if i >= len(critic_approved):
            break

        action = decision.get("action", "reject")
        if action == "approve":
            findings_to_write.append(critic_approved[i].finding)
        elif action == "edit":
            finding = critic_approved[i].finding
            edited = finding.model_copy(
                update={
                    k: v
                    for k, v in decision.items()
                    if k != "action" and v is not None
                }
            )
            findings_to_write.append(edited)
        elif action == "request_more":
            findings_request_more.append(critic_approved[i].finding)
        # action == "reject" → silently skip (intentional)

    # Write approved/edited findings to KB
    try:
        from src.kb.connection import get_connection
        from src.kb.crud import KBStore
        from src.kb.embeddings import generate_embedding

        with get_connection() as conn:
            store = KBStore(conn)

            # Write approved findings as active
            for finding in findings_to_write:
                root_anxieties = [
                    RootAnxiety(a) for a in finding.root_anxieties
                ]
                circuits = None
                if finding.primary_circuits:
                    circuits = [
                        PankseppCircuit(c) for c in finding.primary_circuits
                    ]

                embedding = generate_embedding(finding.claim)

                create_data = FindingCreate(
                    claim=finding.claim,
                    elaboration=finding.elaboration,
                    root_anxieties=root_anxieties,
                    primary_circuits=circuits,
                    confidence_score=finding.confidence_score,
                    confidence_basis=finding.confidence_basis,
                    provenance=FindingProvenance.AI_CONFIRMED,
                    academic_discipline=finding.academic_discipline,
                    status=FindingStatus.PROPOSED,
                    embedding=embedding,
                )

                try:
                    result = store.create_finding(create_data)
                    # Approve: sets status='active' and approved_at=NOW()
                    store.approve_finding(result.id)
                    written_ids.append(str(result.id))
                    # Track source ProposedFinding for contradiction mapping
                    finding_to_source[str(result.id)] = finding
                except ValueError as e:
                    written_ids.append(f"dedup_skipped: {e}")

            # Write request_more findings as proposed (not approved) for re-research
            for finding in findings_request_more:
                root_anxieties = [
                    RootAnxiety(a) for a in finding.root_anxieties
                ]
                circuits = None
                if finding.primary_circuits:
                    circuits = [
                        PankseppCircuit(c) for c in finding.primary_circuits
                    ]

                embedding = generate_embedding(finding.claim)

                create_data = FindingCreate(
                    claim=finding.claim,
                    elaboration=finding.elaboration,
                    root_anxieties=root_anxieties,
                    primary_circuits=circuits,
                    confidence_score=finding.confidence_score,
                    confidence_basis=f"[NEEDS MORE RESEARCH] {finding.confidence_basis}",
                    provenance=FindingProvenance.AI_PROPOSED,
                    academic_discipline=finding.academic_discipline,
                    status=FindingStatus.PROPOSED,
                    embedding=embedding,
                )

                try:
                    result = store.create_finding(create_data, skip_dedup=True)
                    written_ids.append(f"request_more:{result.id}")
                    import structlog
                    structlog.get_logger().info(
                        "kb_writer.request_more",
                        finding_id=str(result.id),
                        claim=finding.claim[:80],
                    )
                except Exception as e:
                    written_ids.append(f"request_more_error: {e}")

            # Write detected conflicts as contradiction_records + contradicts relationships.
            # Conflicts reference task_ids; map them to written finding UUIDs via source_task_ids.
            if state.synthesis and state.synthesis.conflicts:
                from src.kb.models import (
                    ContradictionRecordCreate,
                    FindingRelationshipCreate,
                    RelationshipType,
                )

                # Build task_id → finding_id lookup from findings that were actually written
                task_to_finding: dict[str, str] = {}
                for fid, source_pf in finding_to_source.items():
                    for task_id in source_pf.source_task_ids:
                        task_to_finding[task_id] = fid

                import structlog
                log = structlog.get_logger()

                for conflict in state.synthesis.conflicts:
                    fid_a = task_to_finding.get(conflict.task_id_a)
                    fid_b = task_to_finding.get(conflict.task_id_b)

                    # Both findings must have been written to create a contradiction record
                    if not fid_a or not fid_b or fid_a == fid_b:
                        continue

                    try:
                        from uuid import UUID as _UUID
                        store.create_contradiction(ContradictionRecordCreate(
                            finding_a_id=_UUID(fid_a),
                            finding_b_id=_UUID(fid_b),
                            description=(
                                f"[{conflict.conflict_type}] {conflict.explanation}"
                            ),
                        ))
                        # Also create a contradicts relationship for graph visualization
                        try:
                            store.create_relationship(FindingRelationshipCreate(
                                from_finding_id=_UUID(fid_a),
                                to_finding_id=_UUID(fid_b),
                                relationship=RelationshipType.CONTRADICTS,
                                rationale=(
                                    f"NLI conflict detection ({conflict.conflict_type}): "
                                    f"{conflict.explanation}"
                                )[:500],
                                confidence=0.85,
                            ))
                        except Exception as rel_e:
                            log.warning(
                                "kb_writer.contradicts_rel_failed",
                                error=str(rel_e),
                            )
                        contradictions_written += 1
                        log.info(
                            "kb_writer.contradiction_recorded",
                            finding_a_id=fid_a,
                            finding_b_id=fid_b,
                            conflict_type=conflict.conflict_type,
                        )
                    except Exception as e:
                        log.warning(
                            "kb_writer.contradiction_failed",
                            error=str(e),
                            finding_a_id=fid_a,
                            finding_b_id=fid_b,
                        )

    except Exception as e:
        written_ids.append(f"kb_write_error: {e}")

    return {
        "written_finding_ids": written_ids,
        "contradictions_written": contradictions_written,
        "completed_at": datetime.utcnow().isoformat(),
        "status": "complete",
    }


# ── Graph construction ──


def build_research_graph() -> StateGraph:
    """Build the research pipeline StateGraph.

    Flow: planner → researchers (parallel) → synthesizer → critic
          → [retry if needed] → hitl_gate_1 → kb_writer
    """
    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("critic", critic_node)
    graph.add_node("retry_research", retry_research_node)
    graph.add_node("hitl_gate_1", hitl_gate_1_node)
    graph.add_node("kb_writer", kb_writer_node)

    # Edges
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", route_to_researchers)
    graph.add_edge("researcher", "synthesizer")
    graph.add_edge("synthesizer", "critic")
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {"retry_research": "retry_research", "hitl_gate_1": "hitl_gate_1"},
    )
    graph.add_edge("retry_research", "synthesizer")
    graph.add_edge("hitl_gate_1", "kb_writer")
    graph.add_edge("kb_writer", END)

    return graph


def compile_research_graph(checkpointer=None):
    """Compile the research pipeline with optional checkpointer.

    For production: pass PostgresSaver as checkpointer.
    For testing: pass MemorySaver or None.
    """
    graph = build_research_graph()
    return graph.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    import sys
    import json

    if "--test-run" not in sys.argv:
        print("Usage: python -m src.research_pipeline.graph --test-run")
        sys.exit(1)

    from langgraph.checkpoint.memory import MemorySaver

    print("Compiling research graph with MemorySaver...")
    pipeline = compile_research_graph(checkpointer=MemorySaver())

    directive = "Research the psychological mechanism behind status quo bias in consumer decisions"
    print(f"Running test directive: {directive[:80]}...")

    thread_id = "test-run"
    config = {"configurable": {"thread_id": thread_id}}

    for event in pipeline.stream(
        {"directive": directive},
        config=config,
        stream_mode="updates",
    ):
        for node, update in event.items():
            if isinstance(update, dict):
                status = update.get("status", "")
                print(f"  Node: {node} → {status}")
            else:
                print(f"  Node: {node} → interrupted (HITL gate)")

    state = pipeline.get_state(config)
    print(f"\nPipeline paused at: {list(state.next) if state.next else 'END'}")
    print(json.dumps({"status": "test_complete", "paused_at": list(state.next) if state.next else []}, indent=2))
