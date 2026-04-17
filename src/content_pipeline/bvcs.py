"""Voice Compliance Scorer (BVCS) — scores drafts against a brand rubric.

Reads config/bvcs_rubric_{brand}.yaml at runtime. Fails if missing.

Brand-agnostic: dimensions are enumerated dynamically from whatever's in
the rubric, and dispatched by the dimension's `method` field (automated
vs scored). This lets the same scorer serve brands with structurally
different rubrics (Boulder has humor_integration; Explodable has
forwarding_artifact_present and length_compliance instead).

Known automated dimensions (dispatched to specific handlers):
  - banned_phrase_check — regex scan for banned phrases + immediate fails
  - mechanics — sentence/paragraph length + reading level (Boulder)
  - length_compliance — word count target check (Explodable)

All other dimensions are treated as LLM-scored using the rubric's
dimension-specific scoring_prompt.

Output: BVCSResult(total_score, dimension_scores, passed, revision_notes)
If score < rubric pass_threshold: revision notes passed to Draft Generator
for retry (max 3). Score delayed disclosure enforced by UI, not pipeline.
"""

import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import yaml
import textstat
from pydantic import BaseModel, Field

from langchain_anthropic import ChatAnthropic


# ── Output models ──


class DimensionScore(BaseModel):
    name: str
    score: float
    max_score: float
    method: str = Field(description="'automated' or 'scored'")
    notes: str = ""


class BVCSResult(BaseModel):
    total_score: int = Field(ge=0, le=100)
    dimension_scores: dict[str, DimensionScore]
    passed: bool
    revision_notes: str = ""
    immediate_fail: bool = False


# ── Rubric loading ──

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def load_rubric(brand: str = "the_boulder") -> dict:
    """Load the BVCS rubric YAML for the specified brand at runtime.

    Pattern: config/bvcs_rubric_{brand}.yaml
    Fails loudly if missing — do not fall back to defaults.
    """
    rubric_path = _CONFIG_DIR / f"bvcs_rubric_{brand}.yaml"
    if not rubric_path.exists():
        raise FileNotFoundError(
            f"BVCS rubric not found at {rubric_path} for brand '{brand}'. "
            "Pipeline cannot proceed without rubric — do not fall back to defaults."
        )
    with open(rubric_path) as f:
        return yaml.safe_load(f)


# ── Automated dimensions ──


def _score_banned_phrases(text: str, dim: dict, output_type: str = "newsletter") -> DimensionScore:
    """Automated: banned phrase check. Uses dimension weight from rubric.

    output_type is accepted for signature consistency with other automated
    handlers but does not affect banned-phrase detection.
    """
    weight = int(dim.get("weight", 10))
    banned = dim.get("banned_phrases", [])
    immediate_fails = dim.get("immediate_fail_phrases", [])

    text_lower = text.lower()
    found = []
    immediate_fail_found = []

    for phrase in banned:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        matches = pattern.findall(text)
        if matches:
            found.append(f"{phrase} ({len(matches)}x)")

    for phrase in immediate_fails:
        if phrase.lower() in text_lower:
            immediate_fail_found.append(phrase)

    # Score: start at weight, -1 per instance, min 0
    score = max(0, weight - len(found))

    notes = ""
    if found:
        notes = f"Banned phrases found: {'; '.join(found)}"
    if immediate_fail_found:
        notes += f" IMMEDIATE FAIL: {', '.join(immediate_fail_found)}"

    return DimensionScore(
        name="banned_phrase_check",
        score=score,
        max_score=weight,
        method="automated",
        notes=notes if notes else "No banned phrases detected.",
    )


def _score_mechanics(text: str, dim: dict, output_type: str = "newsletter") -> DimensionScore:
    """Automated: sentence length, paragraph length, reading level. Uses dimension weight.

    output_type is accepted for signature consistency with other automated
    handlers but does not affect mechanics scoring — sentence/paragraph/
    reading-level targets apply to all output types.
    """
    weight = int(dim.get("weight", 10))
    targets = dim["targets"]

    score = weight
    notes_parts = []

    # Sentence length
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip() and len(s.split()) > 1]
    if sentences:
        avg_sent_len = sum(len(s.split()) for s in sentences) / len(sentences)
        target_min = targets["avg_sentence_length"]["min"]
        target_max = targets["avg_sentence_length"]["max"]
        if avg_sent_len < target_min or avg_sent_len > target_max:
            score -= 2
            notes_parts.append(f"Avg sentence length {avg_sent_len:.1f} words (target {target_min}-{target_max})")
        else:
            notes_parts.append(f"Avg sentence length {avg_sent_len:.1f} words (OK)")

    # Paragraph length
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if paragraphs:
        para_lengths = []
        for p in paragraphs:
            # Skip section breaks and headings
            if p.startswith("#") or p.strip() == "---":
                continue
            sents = [s for s in re.split(r'[.!?]+', p) if s.strip() and len(s.split()) > 1]
            if sents:
                para_lengths.append(len(sents))

        if para_lengths:
            max_para = max(para_lengths)
            max_allowed = targets["max_paragraph_sentences"]
            if max_para > max_allowed:
                score -= 2
                notes_parts.append(f"Longest paragraph: {max_para} sentences (max {max_allowed})")
            else:
                notes_parts.append(f"Paragraph lengths OK (max {max_para})")

    # Reading level
    if len(text) > 100:
        grade = textstat.flesch_kincaid_grade(text)
        grade_min = targets["reading_level_grade"]["min"]
        grade_max = targets["reading_level_grade"]["max"]
        if grade < grade_min or grade > grade_max:
            score -= 2
            notes_parts.append(f"Reading level grade {grade:.1f} (target {grade_min}-{grade_max})")
        else:
            notes_parts.append(f"Reading level grade {grade:.1f} (OK)")

    # Exclamation marks
    excl_count = text.count("!")
    if excl_count > 0:
        score -= min(excl_count * 2, score)  # -2 per instance, don't go below 0
        notes_parts.append(f"Exclamation marks: {excl_count} (0 allowed)")

    return DimensionScore(
        name="mechanics",
        score=max(0, score),
        max_score=weight,
        method="automated",
        notes="; ".join(notes_parts),
    )


def _score_length_compliance(text: str, dim: dict, output_type: str = "newsletter") -> DimensionScore:
    """Automated: word count target check. Used by the Explodable rubric.

    Targets depend on output_type — the rubric YAML specifies newsletter
    targets (600-1200 words for Explodable), but standalone posts and briefs
    have their own length expectations. Overriding here avoids per-output-type
    rubric files or duplicated dimensions.

    - newsletter: rubric-defined targets (Explodable default 600-1200)
    - brief:      1500-2500 words
    - standalone_post: 300-500 words
    """
    weight = int(dim.get("weight", 5))
    targets = dim.get("targets", {})

    if output_type == "standalone_post":
        min_words, max_words = 300, 500
    elif output_type == "brief":
        min_words, max_words = 1500, 2500
    else:
        min_words = int(targets.get("min_words", 600))
        max_words = int(targets.get("max_words", 1200))

    word_count = len(text.split())
    slack = int(min(min_words, max_words) * 0.10)

    if min_words <= word_count <= max_words:
        score = weight
        notes = f"Word count {word_count} (in target range {min_words}-{max_words} for {output_type})"
    elif (min_words - slack) <= word_count <= (max_words + slack):
        score = int(weight * 0.6)  # 3/5 or equivalent
        notes = f"Word count {word_count} (within 10% of range {min_words}-{max_words} for {output_type})"
    else:
        score = 0
        notes = f"Word count {word_count} outside range {min_words}-{max_words} for {output_type} by more than 10%"

    return DimensionScore(
        name="length_compliance",
        score=score,
        max_score=weight,
        method="automated",
        notes=notes,
    )


# ── LLM-scored dimensions ──


class LLMDimensionScore(BaseModel):
    score: int = Field(description="Score for this dimension")
    reasoning: str = Field(description="Brief explanation of the score")


def _score_dimension_llm(
    text: str,
    dimension_name: str,
    scoring_prompt: str,
    max_score: int,
    canonical_examples: dict,
) -> DimensionScore:
    """Score a single dimension via Claude with the rubric prompt."""
    from src.shared.constants import ANTHROPIC_MODEL
    # BVCS fires 6-7 dimension scoring calls per draft, so retry tolerance
    # matters here even more than in single-call sites. max_retries=5 with
    # exponential backoff (1s, 2s, 4s, 8s, 16s) handles transient Anthropic
    # 529/429 without crashing the whole scoring run.
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.0,
        max_tokens=500,
        max_retries=5,
    ).with_structured_output(LLMDimensionScore)

    # Build calibration context from canonical examples
    cal = ""
    if canonical_examples:
        cal = "\n\nCALIBRATION — these passages score 90%+ on voice compliance:\n"
        for section, example in canonical_examples.items():
            cal += f"\n{section.upper()}:\n{example.strip()}\n"

    result = llm.invoke(
        [
            {
                "role": "system",
                "content": (
                    f"You are scoring a newsletter draft on the dimension: {dimension_name}.\n"
                    f"Score on a 0–{max_score} scale.\n\n"
                    f"RUBRIC:\n{scoring_prompt}"
                    f"{cal}"
                ),
            },
            {
                "role": "user",
                "content": f"Score this draft:\n\n{text}",
            },
        ]
    )

    # Clamp score to valid range
    clamped = max(0, min(result.score, max_score))

    return DimensionScore(
        name=dimension_name,
        score=clamped,
        max_score=max_score,
        method="scored",
        notes=result.reasoning,
    )


# ── Main scorer ──


_AUTOMATED_HANDLERS = {
    "banned_phrase_check": _score_banned_phrases,
    "mechanics": _score_mechanics,
    "length_compliance": _score_length_compliance,
}


def score_draft(
    newsletter_text: str,
    brand: str = "the_boulder",
    output_type: str = "newsletter",
) -> BVCSResult:
    """Score a draft against the voice rubric for the specified brand.

    Dimensions are enumerated from the rubric dynamically. Each dimension's
    `method` field dispatches to either an automated handler or the LLM
    scorer. Unknown automated dimensions fall through to LLM scoring with
    a warning.

    output_type is threaded through to automated handlers so length-
    sensitive dimensions (e.g. length_compliance) can apply the correct
    word count targets per output shape:
      newsletter:      rubric-defined targets (600-1200 for Explodable)
      brief:           1500-2500 words
      standalone_post: 300-500 words

    Returns BVCSResult with total score, per-dimension breakdown, and revision notes.
    """
    rubric = load_rubric(brand)
    dimensions = rubric["dimensions"]
    canonical_examples = rubric.get("canonical_examples", {})
    revision_instructions = rubric.get("revision_instructions", {})

    scores: dict[str, DimensionScore] = {}

    for name, dim in dimensions.items():
        method = dim.get("method", "scored")

        if method == "automated":
            handler = _AUTOMATED_HANDLERS.get(name)
            if handler is not None:
                scores[name] = handler(newsletter_text, dim, output_type=output_type)
                continue
            # Unknown automated dimension — warn and fall through to LLM scoring.
            # This prevents silent skipping of a dimension that was added to the
            # rubric but forgot to add a handler here.
            import structlog
            structlog.get_logger().warning(
                "bvcs.unknown_automated_dimension",
                brand=brand,
                dimension=name,
                message="falling back to LLM scoring",
            )

        # LLM-scored path (default, or fallback for unknown automated dims)
        prompt = dim.get("scoring_prompt", dim.get("description", ""))
        weight = int(dim.get("weight", 10))
        scores[name] = _score_dimension_llm(
            newsletter_text,
            name,
            prompt,
            weight,
            canonical_examples,
        )

    # Total score
    total = sum(int(d.score) for d in scores.values())

    # Check immediate fail
    immediate_fail = False
    banned_dim = scores.get("banned_phrase_check")
    if banned_dim and "IMMEDIATE FAIL" in banned_dim.notes:
        immediate_fail = True
        total = min(total, 60)

    passed = total >= rubric["pass_threshold"]

    # Build revision notes for failed dimensions
    revision_notes = ""
    if not passed:
        failed_dims = sorted(
            [(name, d) for name, d in scores.items() if d.score < d.max_score * 0.7],
            key=lambda x: x[1].score / x[1].max_score,
        )
        notes_parts = [revision_instructions.get("general", "").strip()]
        by_dim = revision_instructions.get("by_dimension", {})
        for name, d in failed_dims:
            instruction = by_dim.get(name, "")
            if instruction:
                notes_parts.append(f"\n{name.upper()} ({d.score}/{d.max_score}):\n{instruction.strip()}")
            else:
                notes_parts.append(f"\n{name.upper()} ({d.score}/{d.max_score}): {d.notes}")
        revision_notes = "\n".join(notes_parts)

    return BVCSResult(
        total_score=total,
        dimension_scores=scores,
        passed=passed,
        revision_notes=revision_notes,
        immediate_fail=immediate_fail,
    )
