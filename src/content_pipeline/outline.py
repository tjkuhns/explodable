"""Outline Generator — generates outlines from selected findings.

Two output shapes:
- NewsletterOutline: long-form essay structure with opener, sections, closer.
  Used for both The Boulder and Explodable newsletters. Structure is
  brand-neutral in the schema — brand-specific patterns (Boulder's
  "Unexpected Juxtaposition" etc.) live in the system prompt, not in
  the output model.
- BriefOutline: 5-section diagnostic structure for Explodable Buyer
  Intelligence Briefs. Sections are rigid: Real Buying Decision, Anxiety
  Map, Buying Committee Dynamics, Messaging Gaps, Positioning Opportunity.

HITL interrupt for outline approval lives in the graph, not here.
"""

from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel, Field

from langchain_anthropic import ChatAnthropic

from src.content_pipeline.retriever import ScoredFinding

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


# ── Output models ──


class OutlineSection(BaseModel):
    """A single section in the newsletter outline."""

    section_number: int
    heading: str = Field(description="Internal heading for this section (not published — for operator review)")
    purpose: str = Field(description="What this section accomplishes in the Progressive Revelation arc")
    key_arguments: list[str] = Field(description="2-4 key arguments or points to make in this section")
    finding_indices: list[int] = Field(description="Which findings (by index) are used in this section")
    cross_domain_note: str | None = Field(
        default=None,
        description="If this section connects two domains, explain the connection",
    )


class NewsletterOutline(BaseModel):
    """Structured outline for a long-form newsletter (brand-neutral schema).

    Brand-specific structural patterns (e.g. Boulder's "Unexpected
    Juxtaposition" / "Lingering Exit" or Explodable's diagnostic opener)
    are specified in the system prompt, not in these field descriptions,
    so the same schema serves both brands without leaking Boulder's
    concepts into Explodable generations or vice versa.
    """

    title: str = Field(description="Working title — evocative, not descriptive. No clickbait.")
    subtitle: str | None = Field(default=None, description="Optional one-line subtitle")
    thesis: str = Field(description="The core insight in one sentence — what the reader will see differently after reading")
    opener_concept: str = Field(
        description="The opening move: how the piece begins. 1-2 sentences describing the opener approach."
    )
    sections: list[OutlineSection] = Field(
        description="3-5 body sections. Each delivers a finding with evidence and implication."
    )
    closer_concept: str = Field(
        description="The closing move: how the piece ends. One sentence."
    )
    estimated_word_count: int = Field(
        description="Estimated total word count."
    )


class BriefSection(BaseModel):
    """A single section of a Buyer Intelligence Brief.

    The brief has five rigid sections in fixed order. The LLM fills in
    purpose, arguments, and finding indices for each of the five slots.
    """

    section_number: int = Field(description="1-5, matching the five rigid brief sections")
    heading: str = Field(
        description=(
            "Must be one of: 'The Real Buying Decision', 'The Anxiety Map',"
            " 'The Buying Committee Dynamics', 'The Messaging Gaps',"
            " 'The Positioning Opportunity'."
        )
    )
    purpose: str = Field(description="What this section accomplishes in the diagnostic arc")
    key_arguments: list[str] = Field(description="2-4 specific claims this section will make, each grounded in a finding")
    finding_indices: list[int] = Field(description="Which findings (by index) are used in this section")


class BriefOutline(BaseModel):
    """Structured outline for an Explodable Buyer Intelligence Brief.

    Five rigid sections in fixed order. Unlike NewsletterOutline, briefs
    do not have openers/closers — they open diagnostically and end on
    the positioning opportunity.
    """

    title: str = Field(description="Brief title — specific to the client situation, not generic")
    client_context: str = Field(description="One-line summary of the client situation the brief addresses")
    core_diagnosis: str = Field(
        description=(
            "The core diagnostic claim in one sentence — what fear calculation"
            " is actually driving the stall/loss/pattern."
        )
    )
    sections: list[BriefSection] = Field(
        description="Exactly 5 sections in order: Real Buying Decision, Anxiety Map, Committee Dynamics, Messaging Gaps, Positioning Opportunity."
    )
    estimated_word_count: int = Field(
        description="Estimated total word count (target: 1500-2500)."
    )


# ── Generator ──

def _build_outline_system_prompt(brand: str) -> str:
    """Build the outline system prompt from the brand's voice profile."""
    path = _CONFIG_DIR / f"voice_profile_{brand}.yaml"
    with open(path) as f:
        profile = yaml.safe_load(f)

    brand_info = profile.get("brand", {})
    tone = profile.get("tone", {})
    structure = profile.get("structure", {})
    patterns = profile.get("patterns", {})
    vocab = profile.get("vocabulary", {})

    name = brand_info.get("name", brand)
    tagline = brand_info.get("tagline", "")
    audience = brand_info.get("audience", "")

    # Build tone description from profile parameters
    tone_desc_parts = []
    if tone.get("humor", 0) >= 3.0:
        tone_desc_parts.append("darkly funny")
    if tone.get("earnestness", 0) >= 4.0:
        tone_desc_parts.append("rigorous")
    if tone.get("contrarianism", 0) >= 3.5:
        tone_desc_parts.append("contrarian")
    if tone.get("urgency", 0) >= 3.0:
        tone_desc_parts.append("urgent")
    if tone.get("formality", 0) >= 3.5:
        tone_desc_parts.append("precise")
    tone_desc = ", ".join(tone_desc_parts) if tone_desc_parts else "analytical, evidence-driven"

    # Extract structural patterns from newsletter config
    newsletter = patterns.get("newsletter", {})
    opener_rule = newsletter.get("opener_rule", "Start with a specific finding or reframe.")
    body_rule = newsletter.get("body_rule", "Each section delivers a finding with evidence and implication.")
    closer_rule = newsletter.get("closer_rule", "End on an implication, not a summary.")
    length = newsletter.get("length", "1500-2500 words")

    # Extract banned phrases
    banned = vocab.get("banned_words_absolute", [])
    banned_str = ", ".join(f'"{b}"' for b in banned[:10]) if banned else '"deep dive", "unpack", "in conclusion"'

    return f"""You are an outline generator for {name}, a newsletter{f' described as "{tagline}"' if tagline else ''}.

Voice: {tone_desc}.
Audience: {audience}.

Structural pattern:
- OPENER: {opener_rule}
- BODY: {body_rule}
- CLOSER: {closer_rule}

Target length: {length}

Rules:
- Title should be evocative, not descriptive. No clickbait.
- 3-5 body sections.
- At least one section MUST connect two different domains via a shared mechanism (cross-domain).
- Every finding must be used in at least one section.
- Map findings to sections by their index number (0-based).
- Never use banned phrases: {banned_str}.

You receive a set of findings. Design a newsletter outline that weaves them into a coherent narrative."""


def _format_findings_for_outline(findings: list[ScoredFinding]) -> str:
    """Format selected findings for the outline prompt."""
    parts = []
    for i, sf in enumerate(findings):
        f = sf.finding
        anxieties = [a.value for a in f.root_anxieties]
        circuits = [c.value for c in f.primary_circuits] if f.primary_circuits else []
        parts.append(
            f"Finding {i}:\n"
            f"  Claim: {f.claim}\n"
            f"  Elaboration: {f.elaboration[:300]}\n"
            f"  Academic discipline: {f.academic_discipline}\n"
            f"  Root anxieties: {', '.join(anxieties)}\n"
            f"  Circuits: {', '.join(circuits) if circuits else 'none'}\n"
            f"  Confidence: {f.confidence_score:.0%}"
        )
    return "\n\n".join(parts)


def _build_brief_outline_system_prompt(profile: dict) -> str:
    """Build the Buyer Intelligence Brief outline system prompt.

    Explodable-only. Uses Explodable voice profile. The brief has a rigid
    5-section structure, so the prompt's job is to make the LLM populate
    each of the five slots with client-specific content grounded in the
    provided findings.
    """
    brand = profile["brand"]
    vocab = profile.get("vocabulary", {})
    preferred = ", ".join(vocab.get("preferred_terms", []))
    banned_words = vocab.get("banned_words_absolute", [])
    banned_str = ", ".join(banned_words[:15])

    return f"""You are the outline planner for {brand['name']} Buyer Intelligence Briefs.

A Buyer Intelligence Brief is a diagnostic deliverable for a specific client situation. It has a rigid five-section structure. Your job is to plan which findings go in which section and what each section will argue.

THE FIVE SECTIONS (in this exact order):

1. The Real Buying Decision
What fear calculation is actually driving this purchase. What a bad decision costs the buyer personally, not organizationally. Be specific about psychological stakes.

2. The Anxiety Map
Which root anxieties are active in this category. Rank by prevalence. Each anxiety grounded in specific findings.

3. The Buying Committee Dynamics
Who is in the room. What each stakeholder is protecting. What triggers a stall. Uses ICP vocabulary (deal, pipeline, buying committee, stall).

4. The Messaging Gaps
Where current category messaging misfires. Specific, citable. Names the pattern the client is probably doing wrong.

5. The Positioning Opportunity
One concrete positioning angle. Not a tagline. A positioning thesis with evidence behind it. This is the "so what."

Rules:
- Exactly 5 sections. Exact headings as listed above. Exact order.
- Every finding must be used in at least one section.
- Map findings to sections by their index number (0-based).
- Every argument must be grounded in a specific finding — no generic claims.
- Use ICP vocabulary: deal, pipeline, stall, buying committee, win rate, no decision.
- Preferred terms: {preferred}
- Never use: {banned_str}
- The brief is diagnostic, not persuasive. Observations, not recommendations dressed as marketing.

You receive a client context and a set of findings. Plan the five sections so each one advances the diagnosis."""


def generate_outline(
    findings: list[ScoredFinding],
    brand: str = "the_boulder",
    output_type: str = "newsletter",
    client_context: str | None = None,
) -> NewsletterOutline | BriefOutline:
    """Generate an outline from selected findings.

    Args:
        findings: Selected findings from the Content Selector.
        brand: 'the_boulder' or 'explodable'. Loads the matching voice profile.
        output_type: 'newsletter' (default) or 'brief'. Briefs are Explodable-only.
        client_context: Required for briefs — the specific client situation
            the brief diagnoses. Ignored for newsletters.

    Returns:
        NewsletterOutline for newsletters, BriefOutline for briefs.
    """
    from src.shared.constants import ANTHROPIC_MODEL

    if output_type == "brief":
        if brand != "explodable":
            raise ValueError(
                f"Briefs are Explodable-only. Got brand='{brand}'. "
                "The Boulder produces opinionated cultural analysis, not diagnostic briefs."
            )
        if not client_context:
            raise ValueError(
                "client_context is required for brief outlines — the brief must be"
                " specific to a client situation, not a generic topic."
            )

        path = _CONFIG_DIR / "voice_profile_explodable.yaml"
        with open(path) as f:
            profile = yaml.safe_load(f)

        # max_retries=5 tolerates Anthropic 529/429 with exponential backoff
        # (1s, 2s, 4s, 8s, 16s). Default is 2 which isn't enough for peak hours.
        llm = ChatAnthropic(
            model=ANTHROPIC_MODEL,
            temperature=0.4,
            max_tokens=3000,
            max_retries=5,
        ).with_structured_output(BriefOutline)

        findings_text = _format_findings_for_outline(findings)
        system_prompt = _build_brief_outline_system_prompt(profile)

        result = llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Plan a five-section Buyer Intelligence Brief.\n\n"
                        f"CLIENT CONTEXT:\n{client_context}\n\n"
                        f"FINDINGS ({len(findings)} available):\n\n"
                        f"{findings_text}"
                    ),
                },
            ]
        )
        return result

    # Newsletter path (default)
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.5,
        max_tokens=3000,
        max_retries=5,
    ).with_structured_output(NewsletterOutline)

    findings_text = _format_findings_for_outline(findings)
    system_prompt = _build_outline_system_prompt(brand)

    result = llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Generate a newsletter outline from these {len(findings)} findings:\n\n"
                    f"{findings_text}"
                ),
            },
        ]
    )
    return result


# ── CLI display for HITL gate 2 (outline review) ──


def display_outline(outline: NewsletterOutline, findings: list[ScoredFinding]) -> None:
    """Display the outline for operator review."""
    print(f"\n{'='*80}")
    print(f"  NEWSLETTER OUTLINE")
    print(f"{'='*80}")
    print(f"  Title: {outline.title}")
    if outline.subtitle:
        print(f"  Subtitle: {outline.subtitle}")
    print(f"  Thesis: {outline.thesis}")
    print(f"  Est. words: {outline.estimated_word_count}")
    print()
    print(f"  OPENER — The Unexpected Juxtaposition")
    print(f"  {outline.opener_concept}")
    print()

    for section in outline.sections:
        cross = " [CROSS-DOMAIN]" if section.cross_domain_note else ""
        print(f"  SECTION {section.section_number}: {section.heading}{cross}")
        print(f"  Purpose: {section.purpose}")
        print(f"  Arguments:")
        for arg in section.key_arguments:
            print(f"    - {arg}")
        finding_refs = []
        for idx in section.finding_indices:
            if idx < len(findings):
                finding_refs.append(f"F{idx}: {findings[idx].finding.claim[:50]}...")
        print(f"  Findings: {', '.join(f'F{i}' for i in section.finding_indices)}")
        for ref in finding_refs:
            print(f"    {ref}")
        if section.cross_domain_note:
            print(f"  Cross-domain: {section.cross_domain_note}")
        print()

    print(f"  CLOSER — The Lingering Exit")
    print(f"  {outline.closer_concept}")
    print(f"{'='*80}")


def get_outline_decision() -> dict:
    """Prompt operator for outline approval."""
    while True:
        print()
        print("  Actions: [a]pprove  [r]eject  [e]dit")
        choice = input("  > ").strip().lower()

        if choice in ("a", "approve"):
            return {"action": "approve"}
        elif choice in ("r", "reject"):
            reason = input("  Reason for rejection: ").strip()
            return {"action": "reject", "reason": reason}
        elif choice in ("e", "edit"):
            print("  Enter new title (or Enter to keep):")
            new_title = input("  title> ").strip()
            print("  Enter new thesis (or Enter to keep):")
            new_thesis = input("  thesis> ").strip()
            print("  Any other notes for the draft generator:")
            notes = input("  notes> ").strip()
            result = {"action": "edit"}
            if new_title:
                result["title"] = new_title
            if new_thesis:
                result["thesis"] = new_thesis
            if notes:
                result["notes"] = notes
            return result
        else:
            print("  Invalid choice. Use a/r/e.")
