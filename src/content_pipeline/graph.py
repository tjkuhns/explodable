"""Content Pipeline — LangGraph StateGraph.

Nodes: calendar_trigger → kb_retriever → content_selector → outline_generator
       → hitl_gate_2 (outline) → draft_generator → bvcs_scorer
       → [auto-revise if <70, max 3] → hitl_gate_2 (draft) → publisher_stub

State: ContentState (Pydantic) — all inter-node data in structured fields
Checkpointing: PostgresSaver
Publisher stub: writes draft to ~/explodable/drafts/ as markdown
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import yaml
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from src.content_pipeline.retriever import ScoredFinding, retrieve_findings
from src.content_pipeline.selector import select_findings
from src.content_pipeline.outline import (
    BriefOutline,
    NewsletterOutline,
    generate_outline,
)
from src.content_pipeline.draft_generator import DraftResult, generate_draft, generate_standalone_draft
from src.content_pipeline.bvcs import BVCSResult, score_draft


# ── Config loading ──

_CALENDAR_PATH = Path(__file__).parent.parent.parent / "config" / "editorial_calendar.yaml"


def _load_calendar() -> dict:
    if not _CALENDAR_PATH.exists():
        raise FileNotFoundError(f"Editorial calendar not found at {_CALENDAR_PATH}")
    with open(_CALENDAR_PATH) as f:
        return yaml.safe_load(f)


# ── State ──


class ContentState(BaseModel):
    """Structured state for the content pipeline. No conversational fields."""

    # Input
    topic: str = ""
    brand: str = "the_boulder"
    # Output type determines which prompt builders and which output shape:
    # - "newsletter": long-form essay + social variants
    # - "brief": Explodable Buyer Intelligence Brief, 5-section
    #   diagnostic structure, no social variants
    output_type: str = "newsletter"
    # Only used for output_type="brief": the specific client situation the
    # brief addresses. Required for briefs, ignored for newsletters.
    client_context: str = ""

    # Calendar config (loaded at trigger)
    retrieval_config: dict = Field(default_factory=dict)

    # Retriever output
    retrieved_findings: list[ScoredFinding] = Field(default_factory=list)

    # Selector output
    selected_findings: list[ScoredFinding] = Field(default_factory=list)

    # Outline — NewsletterOutline for newsletters, BriefOutline for briefs
    outline: NewsletterOutline | BriefOutline | None = None
    outline_decision: dict = Field(default_factory=dict)

    # Draft
    draft: DraftResult | None = None

    # BVCS
    bvcs_result: BVCSResult | None = None
    revision_count: int = 0

    # Draft review
    draft_decision: dict = Field(default_factory=dict)

    # Publisher
    published_path: str = ""

    # Metadata
    started_at: str = ""
    completed_at: str = ""
    status: str = "pending"


# ── Node functions ──


def calendar_trigger_node(state: ContentState) -> dict:
    """Load editorial calendar config for the brand."""
    calendar = _load_calendar()
    brand_config = calendar["brands"].get(state.brand, {})
    retrieval = brand_config.get("retrieval", {})

    return {
        "retrieval_config": retrieval,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "triggered",
    }


def kb_retriever_node(state: ContentState) -> dict:
    """Retrieve findings from KB using multi-query expansion and decay-weighted scoring."""
    from src.kb.connection import get_connection

    config = state.retrieval_config
    min_confidence = config.get("min_confidence", 0.45)
    max_findings = config.get("max_findings_per_draft", 8)

    with get_connection() as conn:
        results = retrieve_findings(
            conn,
            topic=state.topic,
            top_k=max_findings * 2,  # retrieve extra, selector narrows
            min_confidence=min_confidence,
        )

    return {"retrieved_findings": results, "status": "retrieved"}


def content_selector_node(state: ContentState) -> dict:
    """Select and rank findings for the draft.

    For newsletters and briefs: returns up to max_findings findings with
    at least one cross-domain guaranteed. For standalone_post: returns
    exactly one seed finding heavily biased toward cross-domain +
    novelty + narrative potential.
    """
    from src.kb.connection import get_connection

    max_findings = state.retrieval_config.get("max_findings_per_draft", 8)

    with get_connection() as conn:
        selected = select_findings(
            conn,
            state.retrieved_findings,
            max_findings=max_findings,
            brand=state.brand,
            output_type=state.output_type,
        )

    return {"selected_findings": selected, "status": "selected"}


def standalone_post_generator_node(state: ContentState) -> dict:
    """Generate a standalone short-form LinkedIn post directly from the seed finding.

    This node exists so standalone posts can skip outline generation and
    outline HITL review — they're too short to benefit from outline
    planning. The selector guarantees one finding in state.selected_findings
    when output_type=standalone_post.
    """
    if not state.selected_findings:
        raise ValueError("standalone_post_generator_node requires at least one selected finding")

    seed = state.selected_findings[0]
    draft = generate_standalone_draft(seed, brand=state.brand)
    return {"draft": draft, "status": "standalone_post_generated"}


def outline_generator_node(state: ContentState) -> dict:
    """Generate outline from selected findings. Dispatches on output_type.

    Note: this node is NOT called for output_type='standalone_post' — that
    path skips outline generation entirely via the conditional edge after
    content_selector.
    """
    outline = generate_outline(
        state.selected_findings,
        brand=state.brand,
        output_type=state.output_type,
        client_context=state.client_context or None,
    )
    return {"outline": outline, "status": "outline_generated"}


def route_after_selector(state: ContentState) -> str:
    """Route based on output_type after content selection.

    Standalone posts skip outline generation and outline HITL review,
    going directly to standalone_post_generator. Newsletters and briefs
    take the full outline → HITL → draft path.
    """
    if state.output_type == "standalone_post":
        return "standalone_post_generator"
    return "outline_generator"


def hitl_gate_2_outline_node(state: ContentState) -> dict:
    """HITL gate 2 (outline): operator reviews and approves outline before draft.

    Payload shape differs by output_type:
    - newsletter: includes thesis, opener_concept, closer_concept
    - brief: includes client_context, core_diagnosis (no opener/closer)
    """
    outline = state.outline
    findings_summary = []
    for i, sf in enumerate(state.selected_findings):
        findings_summary.append({
            "index": i,
            "claim": sf.finding.claim,
            "academic_discipline": sf.finding.academic_discipline,
            "confidence": sf.finding.confidence_score,
        })

    base_payload = {
        "type": "outline_review",
        "output_type": state.output_type,
        "title": outline.title,
        "sections": [s.model_dump() for s in outline.sections],
        "estimated_word_count": outline.estimated_word_count,
        "findings": findings_summary,
        "message": "Review outline. Actions: approve, reject, edit",
    }

    if isinstance(outline, BriefOutline):
        base_payload.update({
            "client_context": outline.client_context,
            "core_diagnosis": outline.core_diagnosis,
        })
    else:
        # NewsletterOutline
        base_payload.update({
            "thesis": outline.thesis,
            "opener_concept": outline.opener_concept,
            "closer_concept": outline.closer_concept,
        })

    decision = interrupt(base_payload)

    return {"outline_decision": decision, "status": "outline_reviewed"}


def route_after_outline_review(state: ContentState) -> str:
    """Route based on outline review decision."""
    action = state.outline_decision.get("action", "reject")
    if action == "approve":
        return "draft_generator"
    elif action == "edit":
        return "draft_generator"  # Apply edits and proceed
    else:
        return END  # Rejected — pipeline stops


def draft_generator_node(state: ContentState) -> dict:
    """Generate draft from outline and findings. Dispatches on output_type."""
    outline = state.outline

    # Apply any edits from outline review. Only fields present on the
    # specific outline type get applied.
    if state.outline_decision.get("action") == "edit":
        updates = {}
        if "title" in state.outline_decision:
            updates["title"] = state.outline_decision["title"]
        # Newsletter-only edit fields
        if isinstance(outline, NewsletterOutline) and "thesis" in state.outline_decision:
            updates["thesis"] = state.outline_decision["thesis"]
        # Brief-only edit fields
        if isinstance(outline, BriefOutline) and "core_diagnosis" in state.outline_decision:
            updates["core_diagnosis"] = state.outline_decision["core_diagnosis"]
        if updates:
            outline = outline.model_copy(update=updates)

    draft = generate_draft(
        outline,
        state.selected_findings,
        brand=state.brand,
        output_type=state.output_type,
    )
    return {"draft": draft, "status": "draft_generated"}


def bvcs_scorer_node(state: ContentState) -> dict:
    """Score the draft against the brand's voice rubric.

    Passes output_type so length-sensitive dimensions (length_compliance)
    apply the right word-count targets for briefs and standalone posts.
    """
    result = score_draft(
        state.draft.newsletter,
        brand=state.brand,
        output_type=state.output_type,
    )
    return {"bvcs_result": result, "status": "bvcs_scored"}


def route_after_bvcs(state: ContentState) -> str:
    """Route based on BVCS score: auto-revise if <70 and retries remain, else HITL."""
    if state.bvcs_result.passed:
        return "hitl_gate_2_draft"
    if state.revision_count < 3:
        return "draft_revise"
    # Max retries — proceed to HITL anyway, operator can decide
    return "hitl_gate_2_draft"


def draft_revise_node(state: ContentState) -> dict:
    """Revise draft based on BVCS feedback. Passes revision notes to the draft generator."""
    # Notify operator UI that revision is happening
    try:
        from src.shared.notifications import notify_bvcs_revision_needed
        notify_bvcs_revision_needed(
            thread_id=state.started_at or "unknown",
            bvcs_score=state.bvcs_result.total_score if state.bvcs_result else 0,
            revision_count=state.revision_count + 1,
        )
    except Exception:
        pass  # Notification failure must not block the pipeline

    outline = state.outline
    revision_notes = state.bvcs_result.revision_notes if state.bvcs_result else None

    draft = generate_draft(
        outline,
        state.selected_findings,
        revision_notes=revision_notes,
        brand=state.brand,
        output_type=state.output_type,
    )

    return {
        "draft": draft,
        "revision_count": state.revision_count + 1,
        "bvcs_result": None,
        "status": f"revision_{state.revision_count + 1}",
    }


def hitl_gate_2_draft_node(state: ContentState) -> dict:
    """HITL gate 2 (draft): operator reviews final draft with source attributions.

    BVCS score is in the data but UI enforces delayed disclosure
    (score shown after operator reads 85% of draft).
    """
    # Notify operator UI that draft is ready for review
    try:
        from src.shared.notifications import notify_content_draft_ready
        notify_content_draft_ready(
            thread_id=state.started_at or "unknown",
            title=state.outline.title if state.outline else "Untitled",
            bvcs_score=state.bvcs_result.total_score if state.bvcs_result else 0,
        )
    except Exception:
        pass  # Notification failure must not block the pipeline

    # Standalone posts have no outline — derive a title from the seed finding.
    if state.outline and getattr(state.outline, "title", None):
        title = state.outline.title
    elif state.selected_findings:
        title = state.selected_findings[0].finding.claim[:80]
    else:
        title = "Untitled"

    decision = interrupt({
        "type": "draft_review",
        "title": title,
        "output_type": state.output_type,
        "newsletter_length_words": len(state.draft.newsletter.split()),
        "bvcs_score": state.bvcs_result.total_score if state.bvcs_result else None,
        "bvcs_passed": state.bvcs_result.passed if state.bvcs_result else None,
        "revision_count": state.revision_count,
        "message": "Review draft. BVCS score will be shown after reading. Actions: approve, reject, edit",
    })

    return {"draft_decision": decision, "status": "draft_reviewed"}


def route_after_draft_review(state: ContentState) -> str:
    """Route based on draft review decision."""
    action = state.draft_decision.get("action", "reject")
    if action == "approve":
        return "publisher_stub"
    elif action == "edit":
        return "publisher_stub"  # Apply edits and publish
    else:
        return END  # Rejected


def _render_sources_appendix(outline, selected_findings, draft=None) -> str:
    """Render a Sources section that maps findings to where they were used.

    Two modes:
    1. If the draft has structured citations (Citations API path), uses
       those citations to show the exact cited spans and which finding
       each span resolves to. Higher precision than section-level mapping.
    2. Fallback to the outline's section.finding_indices mapping — the
       pre-2026-04-14 approach. Section-level precision, zero additional
       LLM calls. Used when citations list is empty (ChatAnthropic path).

    Both modes work for NewsletterOutline and BriefOutline.
    """
    lines = ["\n---\n\n## Sources\n"]

    # Build a finding_index → Finding mapping we can resolve citations against
    findings_by_index: dict[int, object] = {
        i: sf for i, sf in enumerate(selected_findings)
    }

    draft_citations = getattr(draft, "citations", None) or []
    use_citations_mode = bool(draft_citations)

    if use_citations_mode:
        # Mode 1: Citations API output. Group citations by finding index,
        # deduplicate by cited_text, then render one entry per finding with
        # the exact quoted spans Claude pulled into the draft.
        citations_by_finding: dict[int, list[object]] = {}
        for c in draft_citations:
            idx = getattr(c, "document_index", -1)
            if idx < 0 or idx not in findings_by_index:
                continue
            citations_by_finding.setdefault(idx, []).append(c)

        for i, sf in enumerate(selected_findings):
            f = sf.finding
            discipline = getattr(f, "academic_discipline", "unknown")
            confidence = int(float(getattr(f, "confidence_score", 0.0)) * 100)
            claim = getattr(f, "claim", "")
            source_document = getattr(f, "source_document", None)

            query_variant = getattr(sf, "query_variant", "") or ""
            via_graph = query_variant.startswith("graph:")
            via_marker = f" · via graph ({query_variant})" if via_graph else ""

            lines.append(f"**Finding {i + 1}** — {discipline} · {confidence}%{via_marker}")
            lines.append(f"  {claim}")

            citations_for_finding = citations_by_finding.get(i, [])
            if citations_for_finding:
                # Dedupe cited spans — Claude sometimes cites the same passage
                # from multiple points in the draft
                seen = set()
                cited_spans = []
                for c in citations_for_finding:
                    span = (getattr(c, "cited_text", "") or "").strip()
                    if span and span not in seen:
                        seen.add(span)
                        cited_spans.append(span)
                if cited_spans:
                    lines.append(f"  *Cited {len(cited_spans)} time(s):*")
                    for span in cited_spans[:3]:  # cap at 3 to avoid noise
                        # Truncate long spans
                        display = span if len(span) <= 160 else span[:157] + "..."
                        lines.append(f"  > {display}")
                    if len(cited_spans) > 3:
                        lines.append(f"  > *(+{len(cited_spans) - 3} more cited span(s))*")
            else:
                lines.append(f"  *Provided as source but not explicitly cited in the draft*")

            if source_document:
                lines.append(f"  *Source document: {source_document}*")
            lines.append("")

        return "\n".join(lines)

    # Mode 2: outline section.finding_indices fallback (pre-Citations API path)
    sections = getattr(outline, "sections", None) or []
    finding_to_sections: dict[int, list[str]] = {}
    for section in sections:
        for idx in getattr(section, "finding_indices", None) or []:
            finding_to_sections.setdefault(idx, []).append(section.heading)

    for i, sf in enumerate(selected_findings):
        f = sf.finding
        discipline = getattr(f, "academic_discipline", "unknown")
        confidence = int(float(getattr(f, "confidence_score", 0.0)) * 100)
        claim = getattr(f, "claim", "")
        source_document = getattr(f, "source_document", None)

        query_variant = getattr(sf, "query_variant", "") or ""
        via_graph = query_variant.startswith("graph:")
        via_marker = f" · via graph ({query_variant})" if via_graph else ""

        lines.append(f"**Finding {i + 1}** — {discipline} · {confidence}%{via_marker}")
        lines.append(f"  {claim}")

        sections_used = finding_to_sections.get(i, [])
        if sections_used:
            lines.append(f"  *Used in: {', '.join(sections_used)}*")
        if source_document:
            lines.append(f"  *Source document: {source_document}*")
        lines.append("")

    return "\n".join(lines)


def publisher_stub_node(state: ContentState) -> dict:
    """Publisher stub: write draft to the correct output directory.

    Newsletters → ~/explodable/drafts/ with social variants appended.
    Briefs → ~/explodable/briefs/ without social variants (they're private
    deliverables, not multi-platform content).

    Citation processing: if the draft contains [src:N] markers from the
    hybrid inline-marker pattern (see docs/CITATION_ARCHITECTURE.md), the
    citation_processor transforms them into markdown footnotes with
    URL-linked source definitions at the bottom. If no markers are
    present (legacy / Citations API path), the section-level sources
    appendix is used as fallback.
    """
    is_brief = state.output_type == "brief"
    is_standalone = state.output_type == "standalone_post"
    if is_brief:
        output_dir_name = "briefs"
    elif is_standalone:
        output_dir_name = "posts"
    else:
        output_dir_name = "drafts"
    output_dir = Path.home() / "explodable" / output_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    # Standalone posts have no outline — derive the slug from the seed
    # finding's claim so filenames are informative rather than generic.
    if state.outline and getattr(state.outline, "title", None):
        slug_source = state.outline.title
    elif state.selected_findings:
        slug_source = state.selected_findings[0].finding.claim[:50]
    else:
        slug_source = output_dir_name.rstrip("s")
    slug = slug_source.lower().replace(" ", "_").replace("/", "_")[:40]
    filename = f"{timestamp}_{slug}.md"
    filepath = output_dir / filename

    # Apply any operator edits to the main body text
    main_text = state.draft.newsletter
    if state.draft_decision.get("action") == "edit":
        edits = state.draft_decision.get("newsletter_edits", "")
        if edits:
            main_text = edits  # Full replacement if operator provided edited text

    # Hybrid citation post-processing: transform [src:N] markers into
    # markdown footnote refs + build a footnote definitions block with
    # URL-linked source definitions. If no markers are present, this
    # is a no-op and the legacy section-level sources appendix runs below.
    hybrid_footnote_block = ""
    try:
        from src.content_pipeline.citation_processor import (
            process_citations,
            extract_markers,
        )
        marker_count = len(extract_markers(main_text))
        if marker_count > 0 and state.selected_findings:
            from src.kb.connection import get_connection as _gc
            with _gc() as _citation_conn:
                annotated_text, footnote_block, citation_report = process_citations(
                    main_text, state.selected_findings, _citation_conn
                )
            main_text = annotated_text
            hybrid_footnote_block = footnote_block
            import structlog
            structlog.get_logger().info(
                "publisher.citation_processor",
                markers_found=citation_report.markers_found,
                markers_resolved=citation_report.markers_resolved,
                markers_with_url=citation_report.markers_with_url,
                missing_url_count=len(citation_report.missing_url_findings),
                warning_count=len(citation_report.warnings),
            )
    except Exception as e:
        import structlog
        structlog.get_logger().warning(
            "publisher.citation_processor_failed",
            error=str(e),
            error_type=type(e).__name__,
        )

    # Build the full output file
    bvcs_info = ""
    if state.bvcs_result:
        bvcs_info = f"BVCS Score: {state.bvcs_result.total_score}/100 ({'PASS' if state.bvcs_result.passed else 'FAIL'})\n"
        bvcs_info += f"Revisions: {state.revision_count}\n"

    # Standalone posts have no outline — derive a title from the seed finding
    # (truncated claim) for the frontmatter/heading.
    if state.outline and getattr(state.outline, "title", None):
        doc_title = state.outline.title
    elif state.selected_findings:
        doc_title = state.selected_findings[0].finding.claim[:80]
    else:
        doc_title = output_dir_name.rstrip("s").title()

    output = (
        f"---\n"
        f"title: \"{doc_title}\"\n"
        f"brand: {state.brand}\n"
        f"output_type: {state.output_type}\n"
        f"generated: {datetime.now(timezone.utc).isoformat()}\n"
        f"word_count: {len(main_text.split())}\n"
        f"{bvcs_info}"
        f"---\n\n"
        f"# {doc_title}\n\n"
        f"{main_text}\n"
    )

    # Sources appendix:
    # - If the hybrid citation post-processor produced a footnote block
    #   (inline [src:N] markers were present in the draft), use that — it
    #   renders as markdown footnotes with URL-linked source definitions.
    # - Otherwise fall back to the section-level finding_indices mapping
    #   via _render_sources_appendix, which also handles the Citations API
    #   path via draft.citations.
    if hybrid_footnote_block:
        output += hybrid_footnote_block
    elif state.outline and state.selected_findings:
        output += _render_sources_appendix(
            state.outline, state.selected_findings, draft=state.draft
        )

    # Newsletters get social variants appended. Briefs and standalone posts
    # do not — briefs are private deliverables, and standalone posts ARE the
    # social content (no derivative variants needed).
    if not is_brief and not is_standalone and state.draft.x_post:
        output += (
            f"\n---\n\n"
            f"## Social Variants\n\n"
            f"### X Post\n{state.draft.x_post}\n\n"
            f"### X Thread\n"
        )
        for i, post in enumerate(state.draft.x_thread, 1):
            output += f"{i}. {post}\n\n"
        output += (
            f"### LinkedIn\n{state.draft.linkedin}\n\n"
            f"### Substack Notes\n{state.draft.substack_notes}\n"
        )

    filepath.write_text(output)

    # Log finding usage for novelty scoring
    try:
        from src.kb.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                for sf in state.selected_findings:
                    cur.execute(
                        """
                        INSERT INTO draft_usage (finding_id, brand, draft_path)
                        VALUES (%s, %s, %s)
                        """,
                        (str(sf.finding.id), state.brand, str(filepath)),
                    )
            conn.commit()
    except Exception:
        import structlog
        structlog.get_logger().warning("publisher.draft_usage_logging_failed", path=str(filepath))

    return {
        "published_path": str(filepath),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
    }


# ── Graph construction ──


def build_content_graph() -> StateGraph:
    """Build the content pipeline StateGraph.

    Flow: calendar_trigger → kb_retriever → content_selector → outline_generator
          → hitl_gate_2_outline → [approve/edit → draft_generator, reject → END]
          → bvcs_scorer → [pass → hitl_gate_2_draft, fail → draft_revise loop]
          → hitl_gate_2_draft → [approve/edit → publisher_stub, reject → END]
          → publisher_stub → END
    """
    graph = StateGraph(ContentState)

    # Add nodes
    graph.add_node("calendar_trigger", calendar_trigger_node)
    graph.add_node("kb_retriever", kb_retriever_node)
    graph.add_node("content_selector", content_selector_node)
    graph.add_node("outline_generator", outline_generator_node)
    graph.add_node("hitl_gate_2_outline", hitl_gate_2_outline_node)
    graph.add_node("draft_generator", draft_generator_node)
    graph.add_node("standalone_post_generator", standalone_post_generator_node)
    graph.add_node("bvcs_scorer", bvcs_scorer_node)
    graph.add_node("draft_revise", draft_revise_node)
    graph.add_node("hitl_gate_2_draft", hitl_gate_2_draft_node)
    graph.add_node("publisher_stub", publisher_stub_node)

    # Edges
    graph.add_edge(START, "calendar_trigger")
    graph.add_edge("calendar_trigger", "kb_retriever")
    graph.add_edge("kb_retriever", "content_selector")

    # After selector, route based on output_type:
    # - newsletter/brief → outline_generator → outline HITL → draft_generator
    # - standalone_post  → standalone_post_generator (skip outline + outline HITL)
    graph.add_conditional_edges(
        "content_selector",
        route_after_selector,
        {
            "outline_generator": "outline_generator",
            "standalone_post_generator": "standalone_post_generator",
        },
    )

    graph.add_edge("outline_generator", "hitl_gate_2_outline")
    graph.add_conditional_edges(
        "hitl_gate_2_outline",
        route_after_outline_review,
        {"draft_generator": "draft_generator", END: END},
    )
    graph.add_edge("draft_generator", "bvcs_scorer")
    # Standalone posts converge at bvcs_scorer too
    graph.add_edge("standalone_post_generator", "bvcs_scorer")
    graph.add_conditional_edges(
        "bvcs_scorer",
        route_after_bvcs,
        {
            "hitl_gate_2_draft": "hitl_gate_2_draft",
            "draft_revise": "draft_revise",
        },
    )
    graph.add_edge("draft_revise", "bvcs_scorer")
    graph.add_conditional_edges(
        "hitl_gate_2_draft",
        route_after_draft_review,
        {"publisher_stub": "publisher_stub", END: END},
    )
    graph.add_edge("publisher_stub", END)

    return graph


def compile_content_graph(checkpointer=None):
    """Compile the content pipeline with optional checkpointer."""
    graph = build_content_graph()
    return graph.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    import sys
    import json

    if "--test-run" not in sys.argv:
        print("Usage: python -m src.content_pipeline.graph --test-run [--verbose]")
        sys.exit(1)

    verbose = "--verbose" in sys.argv

    from langgraph.checkpoint.memory import MemorySaver

    print("Compiling content graph with MemorySaver...")
    pipeline = compile_content_graph(checkpointer=MemorySaver())

    topic = "How loss aversion shapes both consumer behavior and political decision-making"
    print(f"Running test topic: {topic[:80]}...")

    thread_id = "test-run-content"
    config = {"configurable": {"thread_id": thread_id}}

    for event in pipeline.stream(
        {"topic": topic, "brand": "the_boulder"},
        config=config,
        stream_mode="updates",
    ):
        for node, update in event.items():
            if isinstance(update, dict):
                status = update.get("status", "")
                print(f"  Node: {node} → {status}")
                if verbose and node == "kb_retriever":
                    findings = update.get("retrieved_findings", [])
                    print(f"    Retrieved {len(findings)} findings")
            else:
                print(f"  Node: {node} → interrupted (HITL gate)")

    state = pipeline.get_state(config)
    print(f"\nPipeline paused at: {list(state.next) if state.next else 'END'}")
    print(json.dumps({"status": "test_complete", "paused_at": list(state.next) if state.next else []}, indent=2))
