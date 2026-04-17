"""DEPRECATED 2026-04-14 — see src/research_pipeline/DEPRECATED.md

Critic agent. Dormant dependency of drift_monitor. Validates groundedness
of proposed findings against cited sources. No longer an active ingestion path.

Input: ProposedFinding + original sources
Validates: every claim in the finding traces to a cited source
Failed findings route back to Researcher (max 2 retries)
Output: CriticResult(approved, rationale, finding)
"""

from dotenv import load_dotenv

load_dotenv()

import json

from pydantic import BaseModel, Field, field_validator

from langchain_anthropic import ChatAnthropic

from src.research_pipeline.synthesizer import ProposedFinding
from src.research_pipeline.researcher import Source


# ── Output models ──


class GroundednessCheck(BaseModel):
    """LLM assessment of whether a claim is grounded in its sources."""

    is_grounded: bool = Field(
        default=False,
        description="True if the claim and elaboration are fully supported by the cited sources",
    )
    grounded_portions: list[str] = Field(
        default_factory=list,
        description="Parts of the claim/elaboration that ARE supported by sources, as a JSON array of strings",
    )
    ungrounded_portions: list[str] = Field(
        default_factory=list,
        description="Parts of the claim/elaboration that are NOT supported by any source, as a JSON array of strings",
    )

    @field_validator("grounded_portions", "ungrounded_portions", mode="before")
    @classmethod
    def coerce_to_list(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            return [v] if v.strip() else []
        return v

    source_coverage: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of the claim that is covered by cited sources (0.0-1.0)",
    )
    reasoning: str = Field(
        default="",
        description="Step-by-step explanation of the groundedness assessment",
    )


class CriticResult(BaseModel):
    """Output from the Critic agent."""

    approved: bool
    rationale: str
    finding: ProposedFinding
    groundedness_score: float = Field(
        ge=0.0, le=1.0, description="How well-grounded the finding is in sources"
    )
    revision_suggestions: list[str] = Field(
        default_factory=list,
        description="Specific suggestions for improving the finding if not approved",
    )
    retry_count: int = Field(
        default=0, description="How many times this finding has been reviewed"
    )


# ── Critic agent ──

CRITIC_SYSTEM_PROMPT = """You are a fact-checking critic for an intelligence engine. Your job is to verify that proposed findings are GROUNDED in their cited sources.

A finding is grounded when:
1. The core claim can be directly traced to evidence in the cited sources
2. The elaboration does not introduce unsupported assertions
3. The confidence score is appropriate given the source quality and agreement

A finding is NOT grounded when:
1. The claim makes assertions that go beyond what the sources actually say
2. The elaboration introduces speculation presented as fact
3. The confidence score is inflated relative to actual evidence
4. Key claims have no corresponding source evidence

Be rigorous but fair. Findings based on well-established research with strong source support should pass. Findings that extrapolate beyond their sources or overstate conclusions should fail.

For each ungrounded portion, explain specifically what would need to change or what additional evidence would be needed."""

APPROVAL_THRESHOLD = 0.70  # Source coverage must be >= 70% to auto-approve


def _format_sources(sources: list[Source]) -> str:
    """Format sources for the critic's review."""
    parts = []
    for i, s in enumerate(sources, 1):
        parts.append(
            f"Source {i}:\n"
            f"  URL: {s.url}\n"
            f"  Title: {s.title}\n"
            f"  Type: {s.source_type}\n"
            f"  Snippet: {s.snippet}\n"
            f"  Reliability: {s.reliability_note}"
        )
    return "\n\n".join(parts)


def critique_finding(
    finding: ProposedFinding, retry_count: int = 0
) -> CriticResult:
    """Validate a proposed finding against its cited sources.

    Args:
        finding: The proposed finding to validate.
        retry_count: How many times this finding has already been reviewed.

    Returns:
        CriticResult with approval status, rationale, and revision suggestions.
    """
    from src.shared.constants import ANTHROPIC_MODEL
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.0,
        max_tokens=1500,
        max_retries=5,
    ).with_structured_output(GroundednessCheck)

    sources_text = _format_sources(finding.sources)

    check = llm.invoke(
        [
            {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"PROPOSED FINDING:\n"
                    f"Claim: {finding.claim}\n"
                    f"Elaboration: {finding.elaboration}\n"
                    f"Confidence score: {finding.confidence_score}\n"
                    f"Confidence basis: {finding.confidence_basis}\n"
                    f"Academic discipline: {finding.academic_discipline}\n\n"
                    f"CITED SOURCES:\n{sources_text}\n\n"
                    f"Assess whether this finding is grounded in the cited sources."
                ),
            },
        ]
    )

    approved = check.is_grounded and check.source_coverage >= APPROVAL_THRESHOLD

    revision_suggestions = []
    if not approved:
        if check.ungrounded_portions:
            for portion in check.ungrounded_portions:
                revision_suggestions.append(f"Ungrounded: {portion}")
        if check.source_coverage < APPROVAL_THRESHOLD:
            revision_suggestions.append(
                f"Source coverage too low ({check.source_coverage:.0%}). "
                f"Need >= {APPROVAL_THRESHOLD:.0%}."
            )

    rationale = check.reasoning
    if approved:
        rationale = f"APPROVED (coverage: {check.source_coverage:.0%}). {rationale}"
    else:
        rationale = f"REJECTED (coverage: {check.source_coverage:.0%}). {rationale}"

    return CriticResult(
        approved=approved,
        rationale=rationale,
        finding=finding,
        groundedness_score=check.source_coverage,
        revision_suggestions=revision_suggestions,
        retry_count=retry_count,
    )


def critique_findings(
    findings: list[ProposedFinding],
) -> list[CriticResult]:
    """Critique a batch of proposed findings.

    Returns a CriticResult for each finding. Failed findings include
    revision_suggestions for the retry loop (max 2 retries, enforced by the graph).
    """
    return [critique_finding(f) for f in findings]
