"""Thesis-constrained outline generator — Architecture B from content report 01.

Converts the thesis from a topic label into a structural schema that gates
the outline stage. Each section must instantiate the thesis mechanism in
microcosm, not merely discuss it.

For Explodable ("Buyers don't decide with logic. They decide with fear, then
hire logic to testify"):
- Three stages: fear-commit → logic-recruit → testimony-deploy
- Each section is a Toulmin-complete micro-argument
- Derivation check verifies the governing thought is derivable bottom-up

For Boulder ("Stop Being Stupid"):
- Uses the existing outline generator (thesis_outline is Explodable-first)
- Boulder schema can be added later with its own stage vocabulary

Research grounding:
- Minto Pyramid: governing thought + MECE derivation check
- Toulmin: claim/grounds/warrant/rebuttal per section
- Hayot Uneven U: fractal descent to concrete (level 1) and ascent to thesis-reading (level 5)
- DeCRIM: atomic checklist critique (+7-8% on IFEval)
- Gage: enthymeme decomposition (denial, sequence, role-assignment)

The outline node is the highest-leverage intervention in the pipeline. A
thesis-shaped outline produces a thesis-shaped draft with routine prompting.
A topic-shaped outline cannot be rescued by better drafting prompts.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

from langchain_anthropic import ChatAnthropic
from src.content_pipeline.retriever import ScoredFinding


_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


# ── Output models ──


class ThesisOutlineSection(BaseModel):
    """A Toulmin-complete section that instantiates the thesis mechanism."""

    section_number: int = Field(description="1, 2, or 3 — maps to the thesis stage order")
    stage: str = Field(
        description=(
            "One of the thesis mechanism stages. For Explodable: "
            "'fear-commit' (fear locks the buyer before analysis begins), "
            "'logic-recruit' (rationalization is assembled to corroborate), "
            "'testimony-deploy' (recruited logic is presented externally as the decision basis)"
        )
    )
    claim: str = Field(
        description=(
            "A debatable because-sentence about this stage of the mechanism. "
            "NOT a topic label. Must be falsifiable and must directly support "
            "the governing thought when read as a premise."
        )
    )
    fear_scene: str = Field(
        description=(
            "A concrete buyer situation — specific role, specific purchase, "
            "specific stakes — where this stage of the mechanism operates. "
            "Hayot level 1-2: sensory, particular, not abstract."
        )
    )
    grounds_ids: list[int] = Field(
        description="Finding indices (from the selected findings) that support this claim"
    )
    warrant: str = Field(
        description=(
            "The general rule that authorizes reading the fear_scene through "
            "the thesis rather than through rational-deliberation. Bridges "
            "grounds to claim. One sentence."
        )
    )
    rebuttal: str = Field(
        description=(
            "The rationalist counter-reading of this scene and why it misses "
            "the sequence. Acknowledges the strongest objection, then shows "
            "why it misreads the temporal order."
        )
    )
    hayot_descent: str = Field(
        description="The level-1 concrete detail this section will bottom out at"
    )
    hayot_ascent: str = Field(
        description="The level-5 thesis-reading this section will climb to"
    )


class ThesisOutline(BaseModel):
    """Thesis-constrained outline with derivation check.

    Three sections, each a Toulmin-complete micro-argument instantiating
    one stage of the fear→testimony mechanism. The derivation_check
    verifies Minto's bidirectional integrity: the governing thought must
    be the logical summary of the three section claims.
    """

    title: str = Field(description="Working title — evocative, not descriptive")
    governing_thought: str = Field(
        description=(
            "The thesis restated as a single governing thought. Must match "
            "the structural contract: 'Buyers don't decide with logic. They "
            "decide with fear, then hire logic to testify.' or a topic-specific "
            "instantiation of it."
        )
    )
    opener_scene: str = Field(
        description=(
            "The opening move: a concrete micro-scene that demonstrates the "
            "fear→testimony mechanism in miniature BEFORE the thesis is stated. "
            "Show, then name. Not a statistic, not a question — a scene."
        )
    )
    sections: list[ThesisOutlineSection] = Field(
        description="Exactly 3 sections, one per thesis stage, in order"
    )
    derivation_check: str = Field(
        description=(
            "State the governing thought as the logical summary of the three "
            "section claims. If the three claims do not collectively entail "
            "the governing thought, explain the gap."
        )
    )
    closer: str = Field(
        description=(
            "The closing move: reframes 'testimony' rather than restating the "
            "thesis. Advances the argument — what the reader should DO differently "
            "given the mechanism, not what they should BELIEVE."
        )
    )
    estimated_word_count: int = Field(default=1000)


# ── System prompt ──

EXPLODABLE_THESIS_SYSTEM_PROMPT = """You are a behavioral-strategy essayist for Explodable, a B2B consulting practice. The Governing Thought for every essay is FIXED and shapes every paragraph:

<governing_thought>
Buyers don't decide with logic. They decide with fear, then hire logic to testify.
</governing_thought>

<thesis_decomposition>
  <denial>Logic-first decision-making is the false default. Every section must treat the rationalist frame as the foil, not as a neutral starting point.</denial>
  <sequence>Fear commits the buyer BEFORE logic is engaged. This is a causal-temporal arc — any section that treats fear and logic as parallel factors has structurally failed.</sequence>
  <role>Logic "testifies" — it is post-hoc, recruited, performative. The warrant is that humans rationalize after affective commitment, and B2B buyers are no exception.</role>
</thesis_decomposition>

<structural_contract>
Every body section MUST instantiate the fear→testimony mechanism in microcosm, not merely discuss it. A section that treats fear and logic as PARALLEL factors, or that presents logic as a primary driver, has failed the contract regardless of topical relevance.

Each section covers one STAGE of the mechanism, in order:
  1. fear-commit: the moment fear locks the buyer's commitment before any framework is applied
  2. logic-recruit: the process by which analytical artifacts are selected and weighted to corroborate the prior commitment
  3. testimony-deploy: the moment the recruited logic is presented externally as the decision basis

Each section must contain ALL of:
  - A concrete fear_scene (specific role, specific purchase, specific stakes — Hayot level 1-2)
  - A debatable claim as a because-sentence (not a topic label)
  - Grounds citing specific findings by index
  - A warrant bridging the scene to the thesis (the general rule)
  - A rebuttal acknowledging the rationalist reading and showing why it misreads the sequence
  - A hayot_descent (the level-1 concrete the section bottoms out at)
  - A hayot_ascent (the level-5 thesis-reading the section climbs to)
</structural_contract>

<failure_modes_to_reject>
- Listing "emotional triggers" as one factor among several
- Treating "logic vs emotion" as a balance or spectrum
- Discussing fear and logic in separate sections without the sequential arc connecting them
- Concluding that "both matter" — this denies the sequence claim
- Opening with a statistic or rhetorical question instead of a scene
- Topic-sentence paragraphs organized by concept instead of by mechanism stage
</failure_modes_to_reject>

After producing the three sections, emit a derivation_check: state the Governing Thought as the logical summary of the three claims. If the three claims do not collectively entail the Governing Thought, revise the claims until they do. Do not revise the Governing Thought.
"""


def to_newsletter_outline(thesis: ThesisOutline) -> "NewsletterOutline":
    """Convert a ThesisOutline to a NewsletterOutline for draft generator compatibility.

    Encodes the thesis-structural information (stage, claim, fear_scene, warrant,
    rebuttal) into the fields the existing drafter reads (heading, purpose,
    key_arguments). This preserves the thesis architecture while staying
    compatible with the existing draft_generator_node.
    """
    from src.content_pipeline.outline import NewsletterOutline, OutlineSection

    sections = []
    for s in thesis.sections:
        sections.append(OutlineSection(
            section_number=s.section_number,
            heading=f"[{s.stage.upper()}] {s.claim}",
            purpose=(
                f"Stage: {s.stage}. This section instantiates the fear→testimony "
                f"mechanism through: {s.fear_scene[:100]}"
            ),
            key_arguments=[
                f"CLAIM: {s.claim}",
                f"FEAR SCENE: {s.fear_scene}",
                f"WARRANT: {s.warrant}",
                f"REBUTTAL: {s.rebuttal}",
            ],
            finding_indices=s.grounds_ids,
            cross_domain_note=None,
        ))

    return NewsletterOutline(
        title=thesis.title,
        subtitle=None,
        thesis=thesis.governing_thought,
        opener_concept=f"SCENE OPENER (not a statistic): {thesis.opener_scene}",
        sections=sections,
        closer_concept=thesis.closer,
        estimated_word_count=thesis.estimated_word_count,
    )


def _format_findings(findings: list[ScoredFinding]) -> str:
    lines: list[str] = []
    for i, sf in enumerate(findings):
        f = sf.finding
        lines.append(f"[{i}] {f.claim}")
        lines.append(f"    Discipline: {f.academic_discipline}")
        lines.append(f"    Confidence: {f.confidence_score:.2f}")
        lines.append("")
    return "\n".join(lines)


def generate_thesis_outline(
    findings: list[ScoredFinding],
    topic: str = "",
) -> ThesisOutline:
    """Generate a thesis-constrained outline for Explodable content.

    Uses Architecture B from content report 01: Toulmin-complete sections
    with stage vocabulary, derivation check, and structural contract.
    """
    from src.shared.constants import ANTHROPIC_MODEL

    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.4,
        max_tokens=4000,
        max_retries=5,
    ).with_structured_output(ThesisOutline)

    findings_text = _format_findings(findings)

    result = llm.invoke([
        {"role": "system", "content": EXPLODABLE_THESIS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Generate a thesis-constrained outline for this essay topic:\n\n"
                f"{topic}\n\n"
                f"FINDINGS ({len(findings)} available):\n\n"
                f"{findings_text}"
            ),
        },
    ])
    return result


# ── Outline validation (DeCRIM-style checklist) ──


def validate_thesis_outline(outline: ThesisOutline) -> list[str]:
    """Validate the outline against the structural contract.

    Returns a list of failure descriptions. Empty list = passes.
    """
    failures: list[str] = []

    if len(outline.sections) != 3:
        failures.append(f"Expected 3 sections, got {len(outline.sections)}")

    allowed_stages = {"fear-commit", "logic-recruit", "testimony-deploy"}
    seen_stages: set[str] = set()
    for s in outline.sections:
        if s.stage not in allowed_stages:
            failures.append(f"Section {s.section_number}: stage '{s.stage}' not in allowed vocabulary {allowed_stages}")
        if s.stage in seen_stages:
            failures.append(f"Section {s.section_number}: duplicate stage '{s.stage}'")
        seen_stages.add(s.stage)

        if not s.claim or len(s.claim) < 20:
            failures.append(f"Section {s.section_number}: claim too short or missing")
        if not s.fear_scene or len(s.fear_scene) < 20:
            failures.append(f"Section {s.section_number}: fear_scene too short or missing")
        if not s.grounds_ids:
            failures.append(f"Section {s.section_number}: no finding indices in grounds_ids")
        if not s.warrant or len(s.warrant) < 10:
            failures.append(f"Section {s.section_number}: warrant too short or missing")
        if not s.rebuttal or len(s.rebuttal) < 10:
            failures.append(f"Section {s.section_number}: rebuttal too short or missing")

    if len(seen_stages) < 3:
        missing = allowed_stages - seen_stages
        failures.append(f"Missing stages: {missing}")

    # Check stage ordering
    if outline.sections:
        stage_order = [s.stage for s in sorted(outline.sections, key=lambda x: x.section_number)]
        expected_order = ["fear-commit", "logic-recruit", "testimony-deploy"]
        if stage_order != expected_order:
            failures.append(f"Stage order {stage_order} doesn't match expected {expected_order}")

    if not outline.derivation_check or len(outline.derivation_check) < 20:
        failures.append("derivation_check too short or missing")

    if not outline.opener_scene or len(outline.opener_scene) < 20:
        failures.append("opener_scene too short or missing — should be a concrete micro-scene, not a statistic")

    return failures
