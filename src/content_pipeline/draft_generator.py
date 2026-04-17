"""Draft Generator — generates long-form content from outline + voice profile.

Supports two brands (The Boulder, Explodable) and two output types
(newsletter, brief). Loads voice profile YAML from config/ at runtime —
never hardcodes voice parameters.

Output types:
- newsletter: long-form essay + social variants (X post, X thread,
  LinkedIn, Substack Notes). Both brands.
- brief: Explodable-only diagnostic deliverable, 5-section structure,
  no social variants.

The Boulder and Explodable voice profiles have structurally different
YAML shapes (Boulder uses patterns.{opener,body,closer} + rules.{dos,donts};
Explodable uses patterns.newsletter + anti_patterns). Separate prompt
builders per brand handle each shape.

All outputs flow through the shared DraftResult model. Briefs leave the
social variant fields empty — the publisher node knows to skip them for
output_type='brief'.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import yaml
from pydantic import BaseModel, Field, field_validator

from anthropic import Anthropic
from langchain_anthropic import ChatAnthropic

from src.content_pipeline.outline import (
    BriefOutline,
    NewsletterOutline,
)
from src.content_pipeline.retriever import ScoredFinding
from src.shared.constants import ANTHROPIC_MODEL


# ── Feature flags ──
#
# USE_CITATIONS_API: LEGACY. Anthropic's Citations API is architecturally
# incompatible with voice-profile-driven prose generation — Claude honors
# the voice profile's "cite conversationally" rule over the Citations API's
# metadata instructions when the two compete. Disabled by default
# 2026-04-14 Session 4 after testing showed Citations API returned 0
# citations through the pipeline path despite working in isolation.
#
# See docs/CITATION_ARCHITECTURE.md for the full diagnosis. Kept as an
# opt-in flag for brief generation where formal citation might be
# appropriate, though the hybrid inline-marker path is now the default.
USE_CITATIONS_API = os.environ.get("USE_CITATIONS_API", "false").lower() in ("true", "1", "yes")

# USE_HYBRID_CITATIONS: when true (default), uses the hybrid inline-marker
# pattern — findings are passed as [src:N] labeled source blocks in the
# user prompt, Claude writes conversational prose with [src:N] markers
# inline, and a post-processor (src/content_pipeline/citation_processor.py)
# transforms markers into markdown footnotes with URL-linked source
# definitions at the publisher_stub_node stage.
#
# This preserves the voice profile AND produces verifiable hyperlinked
# sources the reader can click.
USE_HYBRID_CITATIONS = os.environ.get("USE_HYBRID_CITATIONS", "true").lower() in ("true", "1", "yes")


# ── Output model ──


class SocialVariants(BaseModel):
    """Social media variants generated from a newsletter."""

    x_post: str = Field(description="Single X/Twitter post (180-280 chars)")
    x_thread: list[str] = Field(description="X/Twitter thread (3-5 posts)")
    linkedin: str = Field(description="LinkedIn post")
    substack_notes: str = Field(description="Substack Notes post (50-150 words)")

    @field_validator("x_thread", mode="before")
    @classmethod
    def _coerce_thread(cls, v):
        # Claude occasionally returns x_thread as a JSON-stringified list
        # rather than a native list when generating structured output
        # outside the tool-use path. Parse it back into a list so the
        # pipeline doesn't error on a purely cosmetic type mismatch.
        if isinstance(v, str):
            import json
            stripped = v.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed]
                except json.JSONDecodeError:
                    pass
            # Fallback: treat the whole string as a single post
            return [stripped] if stripped else []
        return v


class Citation(BaseModel):
    """A single inline citation from the Citations API response.

    Maps a span of generated text back to a specific finding document.
    document_index corresponds to the finding's position in the selected
    findings list passed to the draft generator.
    """

    document_index: int
    document_title: str | None = None
    cited_text: str
    start_char_index: int | None = None
    end_char_index: int | None = None


class DraftResult(BaseModel):
    """All content outputs from a single draft generation run.

    For newsletters, all fields are populated. For briefs, only the
    newsletter field holds the brief text; social variant fields are
    empty strings because briefs are private deliverables, not multi-
    platform content.

    citations field populated when USE_CITATIONS_API is true (default).
    Empty list in the ChatAnthropic fallback path.
    """

    newsletter: str = Field(description="Full newsletter body in markdown, OR brief text for output_type='brief'")
    x_post: str = Field(default="", description="Single X/Twitter post")
    x_thread: list[str] = Field(default_factory=list, description="X/Twitter thread")
    linkedin: str = Field(default="", description="LinkedIn post")
    substack_notes: str = Field(default="", description="Substack Notes post")
    citations: list[Citation] = Field(
        default_factory=list,
        description="Inline citations from the Citations API, when enabled",
    )


# ── Voice profile loading ──

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def load_voice_profile(brand: str = "the_boulder") -> dict:
    """Load the voice profile YAML for the specified brand at runtime.

    Pattern: config/voice_profile_{brand}.yaml
    Fails loudly if missing — do not fall back to defaults.
    """
    path = _CONFIG_DIR / f"voice_profile_{brand}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Voice profile not found at {path} for brand '{brand}'. "
            "Pipeline cannot proceed without voice profile — do not fall back to defaults."
        )
    with open(path) as f:
        return yaml.safe_load(f)


# ── Newsletter prompt builders (per brand, distinct YAML shapes) ──


def _build_boulder_newsletter_prompt(profile: dict) -> str:
    """Construct the Boulder newsletter generation system prompt.

    Boulder voice profile uses the canonical schema defined in
    voice_profile_the_boulder.yaml: patterns.{opener,body,closer},
    rules.{dos,donts}, examples.{opener,body,closer}.
    """
    brand = profile["brand"]
    tone = profile["tone"]
    structure = profile["structure"]
    vocab = profile["vocabulary"]
    patterns = profile["patterns"]
    rules = profile["rules"]
    examples = profile["examples"]

    banned = "\n".join(f"  - {phrase}" for phrase in vocab["banned_phrases"])
    dos = "\n".join(f"  - {rule.strip()}" for rule in rules["dos"])
    donts = "\n".join(f"  - {rule.strip()}" for rule in rules["donts"])

    return f"""You are the writer for {brand['name']} — "{brand['tagline']}".
Audience: {brand['audience']}.

TONE:
- Formality ({tone['formality']}/5): {tone['formality_description'].strip()}
- Humor ({tone['humor']}/5): {tone['humor_description'].strip()}
- Earnestness ({tone['earnestness']}/5): {tone['earnestness_description'].strip()}

STRUCTURE:
- Sentence length: {structure['avg_sentence_length_words']} words avg, range {structure['sentence_length_range_words']}
  {structure['sentence_length_description'].strip()}
- Paragraph length: {structure['avg_paragraph_length_sentences']} sentences avg, range {structure['paragraph_length_range_sentences']}
  {structure['paragraph_length_description'].strip()}
- Reading level: Flesch-Kincaid grade {structure['reading_level_flesch_kincaid_grade']}, range {structure['reading_level_range']}
- Target length: {structure['target_newsletter_length_words']} words ({structure['newsletter_length_range_words'][0]}-{structure['newsletter_length_range_words'][1]})

STRUCTURAL PATTERNS:
- OPENER ("{patterns['opener']['name']}"): {patterns['opener']['description'].strip()}
- BODY ("{patterns['body']['name']}"): {patterns['body']['description'].strip()}
  Section arc: {' → '.join(patterns['body']['section_structure'])}
- CLOSER ("{patterns['closer']['name']}"): {patterns['closer']['description'].strip()}

VOCABULARY:
- Preferred terms: {', '.join(vocab['preferred_terms'])}
- Reference style: {vocab['reference_style'].strip()}

BANNED PHRASES (zero tolerance — never use any of these):
{banned}

BANNED PUNCTUATION: No exclamation marks. No emoji.

DO:
{dos}

DON'T:
{donts}

CANONICAL EXAMPLES — study these, match this voice:

OPENER EXAMPLE:
{examples['opener']['text'].strip()}

BODY EXAMPLE:
{examples['body']['text'].strip()}

CLOSER EXAMPLE:
{examples['closer']['text'].strip()}

Write the newsletter as continuous prose in markdown. Use section breaks (---) between major sections. No subheadings unless exceeding 2500 words. Every claim must trace to a finding provided. Do not invent facts."""


def _build_explodable_newsletter_prompt(profile: dict) -> str:
    """Construct the Explodable newsletter generation system prompt.

    Explodable voice profile uses the Explodable-specific schema:
    patterns.newsletter (not patterns.{opener,body,closer}), anti_patterns
    (not rules.{dos,donts}), examples.newsletter_opener (not examples.opener).

    Explicitly enforces the cross_contamination_rule: no Sisyphus, no Camus,
    no absurdist philosophy bleeding from Boulder into Explodable.
    """
    brand = profile["brand"]
    tone = profile["tone"]
    structure = profile["structure"]
    vocab = profile["vocabulary"]
    patterns = profile["patterns"]
    anti_patterns = profile.get("anti_patterns", {})
    examples = profile.get("examples", {})

    # Vocabulary — Explodable uses banned_words_absolute, not banned_phrases
    banned_words = vocab.get("banned_words_absolute", [])
    banned_str = "\n".join(f"  - {w}" for w in banned_words[:30])
    preferred = ", ".join(vocab.get("preferred_terms", []))
    icp_vocab = vocab.get("icp_vocabulary_to_use", {}).get("terms", [])
    icp_str = ", ".join(icp_vocab) if icp_vocab else ""

    # Newsletter-specific patterns
    newsletter = patterns.get("newsletter", {})
    opener_rule = newsletter.get("opener_rule", "First sentence names a specific finding.").strip()
    body_rule = newsletter.get("body_rule", "Each section = finding + evidence + implication.").strip()
    closer_rule = newsletter.get("closer_rule", "End on implication, not summary.").strip()
    length_guidance = newsletter.get("length", "600–1,200 words").strip()
    forwarding = newsletter.get("forwarding_artifact", {})
    forwarding_desc = forwarding.get("description", "").strip() if isinstance(forwarding, dict) else ""

    # Anti-patterns — the Explodable failure modes to avoid
    anti_str = ""
    for k, v in list(anti_patterns.items())[:5]:
        if isinstance(v, dict):
            desc = v.get("description", "").strip()
            anti_str += f"\n  - {k}: {desc[:200]}"

    # Canonical examples
    newsletter_opener_ex = examples.get("newsletter_opener", {}).get("text", "").strip()
    finding_formatted_ex = examples.get("finding_formatted", {}).get("text", "").strip()

    # Cross-contamination rule from brand_relationships
    cross_rule = (
        profile.get("brand_relationships", {})
        .get("the_boulder", {})
        .get("cross_contamination_rule", "")
        .strip()
    )

    return f"""You are the writer for {brand['name']} — "{brand['tagline']}".
Audience: {brand.get('audience_description', brand.get('audience', '')).strip()}

REGISTER:
Diagnostic, not persuasive. The posture is "here is what the research shows, here is what it means for your situation." Never pitch. Never sell. Diagnose. A doctor delivering test results.

TONE:
- Formality ({tone['formality']}/5): {tone['formality_description'].strip()}
- Humor ({tone['humor']}/5): {tone['humor_description'].strip()}
- Earnestness ({tone['earnestness']}/5): {tone['earnestness_description'].strip()}
- Urgency ({tone['urgency']}/5): {tone['urgency_description'].strip()}
- Contrarianism ({tone['contrarianism']}/5): {tone['contrarianism_description'].strip()}

STRUCTURE:
- Sentence length: {structure['avg_sentence_length_words']} words avg, range {structure['sentence_length_range_words']}
  {structure['sentence_length_description'].strip()}
- Paragraph length: {structure['avg_paragraph_length_sentences']} sentences avg
  {structure['paragraph_length_description'].strip()}
- Reading level: Flesch-Kincaid grade {structure['reading_level_flesch_kincaid_grade']}, range {structure['reading_level_range']}
- Skim architecture REQUIRED: {structure.get('skim_architecture', {}).get('description', 'First sentence of every paragraph must carry the full paragraph claim.').strip()}

NEWSLETTER STRUCTURAL RULES:
- OPENER: {opener_rule}
- BODY: {body_rule}
- CLOSER: {closer_rule}
- Target length: {length_guidance}

FORWARDING ARTIFACT (REQUIRED):
{forwarding_desc if forwarding_desc else 'Include one self-contained standalone paragraph that survives being forwarded without context. Format as a pull quote or bolded block.'}

VOCABULARY:
- Preferred terms: {preferred}
- ICP vocabulary (use their words): {icp_str}

BANNED WORDS (zero tolerance):
{banned_str}

BANNED PUNCTUATION: No exclamation marks. No emoji.

ANTI-PATTERNS TO AVOID:{anti_str}

CROSS-BRAND CONTAMINATION RULE:
{cross_rule if cross_rule else 'This is Explodable, not The Boulder. No Sisyphus. No Camus. No absurdist observations about the human condition. Explodable diagnoses pipeline problems. The Boulder diagnoses civilization. Keep these separate.'}

CANONICAL EXAMPLES — study these, match this voice:

NEWSLETTER OPENER EXAMPLE:
{newsletter_opener_ex}

FINDING FORMAT EXAMPLE:
{finding_formatted_ex}

Write the newsletter as continuous prose in markdown. Every claim traces to a finding provided. Do not invent facts. Every finding is evidence — cite specifically. The newsletter must contain a forwarding artifact."""


def _build_explodable_brief_prompt(profile: dict) -> str:
    """Construct the Explodable Buyer Intelligence Brief prompt.

    Uses the 5-section diagnostic structure: Real Buying Decision, Anxiety
    Map, Buying Committee Dynamics, Messaging Gaps, Positioning Opportunity.
    Brief is a private deliverable for a specific client situation — not
    a newsletter, not a think piece.
    """
    brand = profile["brand"]
    tone = profile["tone"]
    structure = profile["structure"]
    vocab = profile["vocabulary"]
    anti_patterns = profile.get("anti_patterns", {})
    examples = profile.get("examples", {})

    banned_words = vocab.get("banned_words_absolute", [])
    banned_str = "\n".join(f"  - {w}" for w in banned_words[:20])
    preferred = ", ".join(vocab.get("preferred_terms", []))

    anti_str = ""
    for k, v in list(anti_patterns.items())[:5]:
        if isinstance(v, dict):
            desc = v.get("description", "").strip()
            anti_str += f"\n  - {k}: {desc[:180]}"

    finding_example = examples.get("finding_formatted", {}).get("text", "").strip()
    newsletter_opener_ex = examples.get("newsletter_opener", {}).get("text", "").strip()

    cross_rule = (
        profile.get("brand_relationships", {})
        .get("the_boulder", {})
        .get("cross_contamination_rule", "")
        .strip()
    )

    return f"""You are writing a Buyer Intelligence Brief for {brand['name']} — "{brand['tagline']}".
Audience: {brand.get('audience_description', brand.get('audience', '')).strip()}

REGISTER:
This is a diagnostic deliverable for a specific client situation, not a pitch. The posture is: here is what the research shows, here is what it means for your situation. Never persuade. Never sell. Diagnose.

TONE:
- Formality ({tone['formality']}/5): {tone['formality_description'].strip()}
- Humor ({tone['humor']}/5): {tone['humor_description'].strip()}
- Earnestness ({tone['earnestness']}/5): {tone['earnestness_description'].strip()}
- Urgency ({tone['urgency']}/5): {tone['urgency_description'].strip()}
- Contrarianism ({tone['contrarianism']}/5): {tone['contrarianism_description'].strip()}

STRUCTURE:
- Sentence length: {structure['avg_sentence_length_words']} words avg
  {structure['sentence_length_description'].strip()}
- Paragraph length: {structure['avg_paragraph_length_sentences']} sentences avg
  {structure['paragraph_length_description'].strip()}
- Skim architecture REQUIRED: first sentence of every paragraph must carry the full paragraph claim.

PREFERRED VOCABULARY: {preferred}

BANNED WORDS (zero tolerance):
{banned_str}

BANNED PUNCTUATION: No exclamation marks. No emoji.

ANTI-PATTERNS TO AVOID:{anti_str}

CROSS-BRAND CONTAMINATION RULE:
{cross_rule if cross_rule else 'This is Explodable, not The Boulder. No absurdist philosophy. Diagnose pipeline problems with evidence.'}

BRIEF STRUCTURE — write these five sections in order, each as a bold heading followed by prose:

## The Real Buying Decision
What fear calculation is actually driving this purchase. What a bad decision costs the buyer personally, not organizationally. Be specific about the psychological stakes. This section names the core emotional mechanism at play.

## The Anxiety Map
Root anxieties active in this purchase category, mapped to the KB findings provided. Rank by prevalence. Name each anxiety. Show the evidence — cite findings specifically.

## The Buying Committee Dynamics
Who is in the room. What each stakeholder is protecting. What triggers a stall. Be specific — not generic "champion" and "blocker" language. Use the ICP's vocabulary (deal, pipeline, buying committee, stall, etc.).

## The Messaging Gaps
Where current category messaging misfires against actual emotional drivers. Specific, citable failures. Name the pattern the client is probably doing wrong.

## The Positioning Opportunity
One concrete positioning angle specific enough to brief a copywriter. Not a tagline. A positioning thesis with evidence behind it. This is the "so what."

FINDING FORMAT EXAMPLE:
{finding_example}

VOICE REFERENCE:
{newsletter_opener_ex}

Write the full five-section brief in continuous prose. Every claim traces to a finding provided. Do not invent facts. Cite specifically — name the mechanism, name the study, name the effect size. The brief is evidence-backed diagnosis, not commentary."""


# ── Standalone post prompt builders (short-form, single-finding) ──


def _build_boulder_standalone_prompt(profile: dict) -> str:
    """Construct the Boulder standalone LinkedIn post prompt.

    Standalone posts are 300-500 word observations anchored to a single
    seed finding. They're not newsletter excerpts — they work as complete
    standalone pieces on LinkedIn, demonstrating voice without requiring
    a long-form anchor. Boulder register: absurdist-analytical, dark
    humor, cultural reference + reframe.
    """
    brand = profile["brand"]
    tone = profile["tone"]
    vocab = profile["vocabulary"]
    patterns = profile["patterns"]

    banned = "\n".join(f"  - {phrase}" for phrase in vocab["banned_phrases"][:15])

    opener_pattern = patterns["opener"]["description"].strip()
    body_pattern = patterns["body"]["description"].strip()
    closer_pattern = patterns["closer"]["description"].strip()

    return f"""You are writing a standalone LinkedIn post for {brand['name']} — "{brand['tagline']}".
Audience: {brand['audience']}.

This is NOT a newsletter excerpt. This is a complete standalone piece that demonstrates {brand['name']}'s voice on LinkedIn without requiring a long-form anchor. The reader sees this in their feed, with zero context. The first sentence decides whether they keep reading.

TONE:
- Formality ({tone['formality']}/5): {tone['formality_description'].strip()}
- Humor ({tone['humor']}/5): {tone['humor_description'].strip()}
- Earnestness ({tone['earnestness']}/5): {tone['earnestness_description'].strip()}

STRUCTURE — 300-500 WORDS, 4-8 SHORT PARAGRAPHS:

OPENER (first sentence — everything):
{opener_pattern}
The first sentence must land before the LinkedIn "See more" fold (~210 characters). Lead with an uncomfortable claim, an unexpected juxtaposition, or a concrete cultural artifact that will be reframed. NEVER lead with the study citation, a question, or a scene-setting "In 2005 researchers discovered..." opener.

BODY (2-5 short paragraphs):
{body_pattern}
Take the single seed finding and develop ONE angle from it. Not three angles compressed — one angle developed. Show the mechanism beneath the surface observation. If the finding is about loss aversion in salespeople, the body is about what loss aversion looks like in a specific observable behavior, not a survey of loss aversion research.

CLOSER (last 1-2 sentences):
{closer_pattern}
End on an implication or lingering image, not a summary or a call to action. Never "what do you think?" or "thoughts?" or any engagement bait.

VOCABULARY:
Preferred terms: {', '.join(vocab['preferred_terms'][:10])}

BANNED PHRASES (zero tolerance):
{banned}

BANNED: Exclamation marks. Emoji. Hashtags. "Thoughts?" "Hot take:" "Unpopular opinion:" "Research shows" without naming the research. Academic citation format. "In this post" openers.

Reference style: {vocab['reference_style'].strip()}

You will receive ONE finding. Your job is to develop a complete, standalone 300-500 word LinkedIn post that works as a single piece of writing — not a newsletter excerpt, not a compressed summary, a finished short-form piece in {brand['name']}'s voice. Every claim traces to the finding or to the opener artifact. Do not invent facts."""


def _build_explodable_standalone_prompt(profile: dict) -> str:
    """Construct the Explodable standalone LinkedIn post prompt.

    Explodable register: diagnostic, direct, evidence-backed. No absurdism,
    no cultural artifacts. A standalone Explodable post observes one specific
    B2B buyer-psychology mechanism and reframes it for a reader who is
    probably a fractional CMO or revenue leader skimming on mobile.
    """
    brand = profile["brand"]
    tone = profile["tone"]
    vocab = profile.get("vocabulary", {})

    banned_words = vocab.get("banned_words_absolute", [])
    banned_str = "\n".join(f"  - {w}" for w in banned_words[:20])
    preferred = ", ".join(vocab.get("preferred_terms", [])[:12])
    icp_vocab = vocab.get("icp_vocabulary_to_use", {}).get("terms", [])
    icp_str = ", ".join(icp_vocab[:12]) if icp_vocab else ""

    cross_rule = (
        profile.get("brand_relationships", {})
        .get("the_boulder", {})
        .get("cross_contamination_rule", "")
        .strip()
    )

    return f"""You are writing a standalone LinkedIn post for {brand['name']} — "{brand['tagline']}".
Audience: {brand.get('audience_description', brand.get('audience', '')).strip()}

This is NOT a newsletter excerpt. This is a complete standalone diagnostic observation that works on its own in a LinkedIn feed. The ICP is skimming on mobile between meetings with 400 unread emails. The first sentence determines whether this becomes 399 or stays buried.

REGISTER:
Diagnostic, not persuasive. Here is what the research shows. Here is what it means for your situation. Never pitch. Never sell. A doctor delivering test results in 400 words.

TONE:
- Formality ({tone['formality']}/5): {tone['formality_description'].strip()}
- Humor ({tone['humor']}/5): {tone['humor_description'].strip()}
- Earnestness ({tone['earnestness']}/5): {tone['earnestness_description'].strip()}
- Urgency ({tone['urgency']}/5): {tone['urgency_description'].strip()}
- Contrarianism ({tone['contrarianism']}/5): {tone['contrarianism_description'].strip()}

STRUCTURE — 300-500 WORDS, 4-7 SHORT PARAGRAPHS:

OPENER (first sentence — everything):
Lead with the finding itself, stripped to its sharpest form. Make the ICP recognize their own situation in the first 10 words. Never lead with "A new study shows", "Research finds", "JOLT Effect research...", or any citation-first construction. Name the pattern, then prove it.

BODY (2-5 short paragraphs, each one claim → evidence → implication):
Each paragraph: claim, evidence, implication. First sentence of every paragraph must carry the paragraph's full claim (skim architecture — the ICP reads first sentences and decides whether to read the rest).

Take the single seed finding and develop ONE specific observable pattern from it. If the finding is about loss aversion in B2B committees, the body is about what that looks like in a stalled deal, not a survey of loss aversion research. Name the buyer behavior. Show the mechanism. Point at the specific moment in the deal cycle where it surfaces.

CLOSER (last 1-2 sentences):
End on the implication for the reader's specific pipeline reality — not a CTA, not a summary, not a question. "If this pattern holds in your category, the question isn't X. It's Y."

VOCABULARY:
Preferred: {preferred}
ICP vocabulary (use their words): {icp_str}

BANNED WORDS:
{banned_str}

BANNED: Exclamation marks. Emoji. Hashtags. "Hot take:" "Unpopular opinion:" Rhetorical questions as openers. Engagement bait. "What do you think?" "Thoughts?"

CROSS-BRAND CONTAMINATION RULE:
{cross_rule if cross_rule else 'This is Explodable, not The Boulder. No absurdist philosophical register. Diagnostic voice only.'}

You will receive ONE finding. Your job is to produce a complete, standalone 300-500 word LinkedIn post that diagnoses one specific B2B buyer-psychology pattern grounded in that finding. Every claim traces to the finding. Do not invent facts. Do not editorialize beyond what the evidence supports."""


# ── Social variants prompt builder ──


def _build_social_prompt_boulder(profile: dict) -> str:
    """Social variants prompt for Boulder.

    Key discipline: social posts must work STANDALONE. They are not condensed
    newsletter openers. The newsletter's opener works because it's the first
    thing a reader sees in a long-form piece they already decided to read;
    social posts have to earn the stop-scrolling moment in the first sentence
    with no context. Lead with the uncomfortable claim or the reveal. Evidence
    and the specific artifact come second.
    """
    platforms = profile["platforms"]
    x = platforms["x_twitter"]
    li = platforms["linkedin"]
    sn = platforms["substack_notes"]

    return f"""Generate four social media variants from the newsletter. Same voice, but social-first hook architecture — not condensed newsletter openers.

THE CORE DISCIPLINE:
Newsletter openers assume the reader has already chosen to read. Social posts have to earn that choice in the first sentence. Lead with the uncomfortable claim or the unexpected reveal. The specific artifact, experiment, or stat comes SECOND as evidence. Never lead with setup — the reader has zero context and will keep scrolling.

Example of the wrong pattern (DO NOT DO THIS):
"Swedish researchers gave people the opposite photo they chose. 75% never noticed. B2B buyers do this too."
^ This is a compressed newsletter opener. It starts with setup, not stakes. A scrolling reader has no idea why they should care.

Example of the right pattern:
"Your buyers literally don't know what they chose. They'll confidently explain why they picked you — and the explanation is fiction. Swedish researchers proved this in a 2005 photo-swap study: 75% never noticed they got handed the opposite of what they'd chosen."
^ This leads with the uncomfortable claim (buyers don't know). The evidence arrives once the reader is already implicated.

X/TWITTER SINGLE POST ({x['length_characters'][0]}-{x['length_characters'][1]} chars):
One sentence — maybe two — that lands the sharpest claim from the piece with zero setup. Deadpan. No hashtags. No emoji. Should make someone stop scrolling because the first clause is uncomfortable or surprising. If the first six words are scene-setting ("Swedish researchers did...", "A new study shows...", "In 2005...") it's wrong — rewrite.

X/TWITTER THREAD (3-5 posts):
Post 1 must work as an X single post on its own — same hook discipline as above. Subsequent posts build but each one still stands alone. No "thread:" or "1/" announcements. No "here's why" transitions between posts — let each land.

LINKEDIN ({li['length_words'][0]}-{li['length_words'][1]} words):
{li['description'].strip()}
First sentence is everything — LinkedIn truncates at ~210 characters, so the hook must land before the "See more" fold. Lead with the claim, not the experiment. Slightly more scaffolding than X but the first line still has to earn the click-through to read more.
Format: {li['format']}

SUBSTACK NOTES ({sn['length_words'][0]}-{sn['length_words'][1]} words):
{sn['description'].strip()}
Behind-the-scenes register — the thought that sparked the piece, not the piece itself. More conversational than the newsletter. Still no setup-first opener.

RULES:
- Same core voice across all platforms — only compression and scaffolding change. Tone: {x.get('tone_delta', 'wry, deadpan')}
- Every post must be readable in isolation. No post can assume the reader has seen the newsletter.
- NEVER lead with "Swedish researchers...", "A new study finds...", "Research shows...", "In 2005..." or any variation. Lead with the claim or stakes. Evidence follows.
- No hashtags anywhere. No emoji. No exclamation marks.
- No "Read more at..." or link teasers. No "thoughts?" No engagement bait."""


def _build_social_prompt_explodable(profile: dict) -> str:
    """Social variants prompt for Explodable.

    Key discipline: social posts are standalone diagnostic artifacts. They are
    NOT condensed newsletter openers. Lead with the finding or the reframe —
    not the study, not the setup. The ICP is skimming on mobile between
    meetings; the first six words determine whether they stop or scroll.
    """
    patterns = profile.get("patterns", {})
    linkedin = patterns.get("linkedin", {})
    li_register = linkedin.get("register", "Same voice, compressed. Lead with finding.").strip()
    li_length = linkedin.get("length", "150-400 words")
    li_prohibited = linkedin.get("prohibited", "").strip()

    vocab = profile.get("vocabulary", {})
    banned_words = vocab.get("banned_words_absolute", [])
    banned_str = ", ".join(banned_words[:15])

    return f"""Generate four social media variants from the Explodable newsletter. Same diagnostic voice, but social-first hook architecture — not condensed newsletter openers.

THE CORE DISCIPLINE:
Newsletter openers assume the reader has decided to read. Social posts have to earn that decision in the first sentence. Lead with the finding itself, stripped to its sharpest form — not the study, not the setup, not the scene-setting. The ICP is skimming on mobile between meetings with 400 unread emails. The first six words decide whether this becomes 399 or stays buried.

Example of the wrong pattern (DO NOT DO THIS):
"JOLT Effect research analyzed 2.5 million sales calls. 56% of no-decision losses are actually buyer indecision. Your sales team is probably misdiagnosing the problem."
^ This is a compressed newsletter opener. The first clause is scene-setting. A skimmer stops at the citation and scrolls past.

Example of the right pattern:
"Your 'no decision' deals aren't about preferring the status quo. They're about buyers who are afraid to pick. That's 56% of your no-decision losses — and the fix is the opposite of what your sales playbook says."
^ Leads with the uncomfortable reframe. The ICP recognizes their own pipeline in the first sentence. The stat arrives to prove the point, not to set it up.

X/TWITTER SINGLE POST (180-280 chars):
One sentence — maybe two — that delivers the sharpest diagnostic claim with zero setup. Never a hot take. Never a question. Just the finding, reframed to make the reader recognize their own situation. If the first six words are a citation or "research shows" or "a new study" — wrong, rewrite.

X/TWITTER THREAD (3-5 posts):
Post 1 must work as an X single post on its own — leads with the finding, not the setup. Subsequent posts build evidence and implication but each still stands alone. No "thread:" announcements. Lead each post with a diagnostic observation, not a transition.

LINKEDIN ({li_length}):
{li_register}
{f'PROHIBITED: {li_prohibited}' if li_prohibited else ''}
First sentence is everything — LinkedIn truncates at ~210 characters. Lead with the finding or the reframe. Evidence in paragraph 2. One implication at the end.

SUBSTACK NOTES (50-150 words):
Behind-the-scenes diagnostic observation. The one thing that surfaced in research that wouldn't fit the main piece. More conversational than the newsletter but still diagnostic. Still no setup-first opener.

RULES:
- Same diagnostic voice across all platforms. No hot-take register. No rhetorical questions as openers.
- Every post must be readable in isolation. No post can assume the reader has seen the newsletter.
- NEVER lead with "JOLT Effect research...", "A new study finds...", "Research shows...", "Analysis of X conversations..." or any citation-first opener. Lead with the finding. Evidence follows.
- Never: {banned_str}
- No hashtags. No emoji. No exclamation marks.
- No "Read more at..." teasers. No "thoughts?" No engagement bait.
- Never absurdist/philosophical register. This is Explodable, not The Boulder."""


# ── Draft generation ──


def _format_findings_context(findings: list[ScoredFinding]) -> str:
    """Format findings as source context for the draft generator."""
    parts = []
    for i, sf in enumerate(findings):
        f = sf.finding
        anxieties = [a.value if hasattr(a, 'value') else str(a) for a in f.root_anxieties]
        parts.append(
            f"Finding {i}:\n"
            f"  Claim: {f.claim}\n"
            f"  Elaboration: {f.elaboration}\n"
            f"  Academic discipline: {f.academic_discipline}\n"
            f"  Root anxieties: {', '.join(anxieties)}\n"
            f"  Confidence: {f.confidence_score:.0%}"
        )
    return "\n\n".join(parts)


def _format_outline_for_draft(outline) -> str:
    """Format a NewsletterOutline or BriefOutline as text for the draft prompt."""
    if isinstance(outline, BriefOutline):
        text = (
            f"Title: {outline.title}\n"
            f"Client context: {outline.client_context}\n"
            f"Core diagnosis: {outline.core_diagnosis}\n"
        )
        for section in outline.sections:
            text += (
                f"\nSection {section.section_number} — {section.heading}:\n"
                f"  Purpose: {section.purpose}\n"
                f"  Arguments: {'; '.join(section.key_arguments)}\n"
                f"  Uses findings: {section.finding_indices}\n"
            )
        return text

    # NewsletterOutline
    text = (
        f"Title: {outline.title}\n"
        f"Thesis: {outline.thesis}\n"
        f"Opener concept: {outline.opener_concept}\n"
    )
    for section in outline.sections:
        text += (
            f"\nSection {section.section_number} — {section.heading}:\n"
            f"  Purpose: {section.purpose}\n"
            f"  Arguments: {'; '.join(section.key_arguments)}\n"
            f"  Uses findings: {section.finding_indices}\n"
        )
        if section.cross_domain_note:
            text += f"  Cross-domain: {section.cross_domain_note}\n"
    text += f"\nCloser concept: {outline.closer_concept}"
    return text


# ── Hybrid inline-marker citation helpers ──


def _findings_as_marked_sources(findings: list[ScoredFinding]) -> str:
    """Build a source block with [src:N] labels for the user prompt.

    Returns a formatted string ready to drop into the user message.
    Each finding gets a [src:N] label that Claude is instructed to
    reference with inline markers in the output prose.

    The post-processor (citation_processor.py) scans the finished
    draft for [src:N] markers and transforms them into markdown
    footnotes with URL hyperlinks at publish time.
    """
    parts = ["SOURCE FINDINGS — cite with inline [src:N] markers:\n"]
    for i, sf in enumerate(findings):
        f = sf.finding
        anxieties = [a.value if hasattr(a, 'value') else str(a) for a in f.root_anxieties]
        circuits = [c.value if hasattr(c, 'value') else str(c) for c in (f.primary_circuits or [])]

        parts.append(
            f"\n[src:{i}]  ({f.academic_discipline} · {int(f.confidence_score * 100)}% confidence)\n"
            f"  Claim: {f.claim}\n"
            f"  Elaboration: {f.elaboration}\n"
            f"  Root anxieties: {', '.join(anxieties)}"
            + (f"\n  Panksepp circuits: {', '.join(circuits)}" if circuits else "")
            + f"\n  Evidence basis: {f.confidence_basis}\n"
        )
    return "".join(parts)


def _invoke_draft_with_markers(
    system_prompt: str,
    findings_block: str,
    task_text: str,
    *,
    max_tokens: int = 6000,
    temperature: float = 0.7,
) -> str:
    """Generate a draft using the hybrid inline-marker pattern.

    Uses the raw Anthropic client to get 1-hour prompt caching on the
    voice profile system prompt. Returns the full draft text with
    `[src:N]` markers embedded — the caller (graph.publisher_stub_node)
    is responsible for post-processing markers into footnotes.
    """
    client = Anthropic(max_retries=5)

    # System prompt cached at 1h TTL — voice profiles rarely change
    # mid-session, and multi-draft sessions amortize the profile cost
    # at 10% of normal read rate after the first generation.
    system = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]

    user_content = f"{findings_block}\n\n{task_text}"

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )

    # Response content is plain text blocks — no citations metadata to
    # extract. The post-processor handles marker → footnote translation.
    text_parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    return "".join(text_parts)


# ── Legacy Citations API helpers (kept for opt-in use) ──


def _findings_as_documents(findings: list[ScoredFinding]) -> list[dict]:
    """Build Anthropic Citations API document blocks from selected findings.

    Each finding becomes a structured document block that Claude can cite
    inline. The document_index returned in citations corresponds to the
    position in this list. Title includes the first 80 chars of the claim
    so citation metadata is self-describing. Context carries discipline
    and confidence so Claude can prioritize grounding.
    """
    docs = []
    for i, sf in enumerate(findings):
        f = sf.finding
        anxieties = [a.value if hasattr(a, 'value') else str(a) for a in f.root_anxieties]
        circuits = [c.value if hasattr(c, 'value') else str(c) for c in (f.primary_circuits or [])]

        doc_text = (
            f"Claim: {f.claim}\n\n"
            f"Elaboration: {f.elaboration}\n\n"
            f"Academic discipline: {f.academic_discipline}\n"
            f"Root anxieties: {', '.join(anxieties)}\n"
            f"Confidence: {f.confidence_score:.0%}\n"
            f"Confidence basis: {f.confidence_basis}"
        )

        context_parts = [f"Finding index {i}"]
        context_parts.append(f"Academic discipline: {f.academic_discipline}")
        if anxieties:
            context_parts.append(f"Anxieties: {', '.join(anxieties)}")
        if circuits:
            context_parts.append(f"Panksepp circuits: {', '.join(circuits)}")
        context_parts.append(f"Confidence: {f.confidence_score:.0%}")

        docs.append({
            "type": "document",
            "source": {
                "type": "content",
                "content": [{"type": "text", "text": doc_text}],
            },
            "title": f"Finding {i}: {f.claim[:80]}",
            "context": " · ".join(context_parts),
            "citations": {"enabled": True},
        })
    return docs


def _invoke_draft_with_citations(
    system_prompt: str,
    documents: list[dict],
    user_text: str,
    *,
    max_tokens: int = 6000,
    temperature: float = 0.7,
) -> tuple[str, list[Citation]]:
    """Call the Anthropic API with Citations enabled + 1h system prompt cache.

    Returns (full_draft_text, list of Citation objects). System prompt is
    cached at 1-hour TTL so multi-draft sessions amortize the voice profile
    prompt cost — the profile typically adds 2000–3000 tokens that would
    otherwise be paid fresh on every generation.
    """
    client = Anthropic(max_retries=5)

    # System prompt cached at 1-hour TTL. Voice profiles rarely change
    # mid-session; caching at 1h means back-to-back generations in a
    # session pay the voice profile input tokens at 10% of normal rate.
    system = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]

    # User message: documents block (findings) + task text
    user_content = documents + [{"type": "text", "text": user_text}]

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )

    # Extract text + citations from response content blocks.
    # The Citations API returns content as a list of blocks, where text
    # blocks may carry a `citations` field with 1+ citations pointing
    # back at document_index + character ranges in the cited document.
    text_parts = []
    citations: list[Citation] = []
    for block in response.content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_parts.append(block.text)
            block_citations = getattr(block, "citations", None) or []
            for c in block_citations:
                citations.append(
                    Citation(
                        document_index=getattr(c, "document_index", -1),
                        document_title=getattr(c, "document_title", None),
                        cited_text=getattr(c, "cited_text", "")[:500],
                        start_char_index=getattr(c, "start_char_index", None),
                        end_char_index=getattr(c, "end_char_index", None),
                    )
                )

    return "".join(text_parts), citations


def _build_single_finding_document(finding: ScoredFinding) -> list[dict]:
    """Build a single-document list for standalone post generation.

    Standalone posts develop ONE seed finding — the single-document form
    still lets Claude cite specific cited_text spans from the finding.
    """
    return _findings_as_documents([finding])


# ── Draft generation ──


def generate_standalone_draft(
    finding: ScoredFinding,
    brand: str = "the_boulder",
    revision_notes: str | None = None,
) -> DraftResult:
    """Generate a standalone short-form LinkedIn post from a single seed finding.

    Standalone posts are 300-500 word single-finding observations that work
    as complete pieces on their own — no outline, no newsletter anchor, no
    social variants. The post IS the social content. Operator picks the
    topic, the selector picks the seed finding, this generates the post,
    BVCS scores it, HITL reviews it, publisher writes to ~/explodable/posts/.

    Args:
        finding: The single seed ScoredFinding the post develops.
        brand: 'the_boulder' or 'explodable' — routes to the correct prompt.
        revision_notes: Optional BVCS feedback for revision passes.

    Returns:
        DraftResult with the standalone post text in the `newsletter` field
        and all social variant fields empty (the post IS the social artifact).
    """
    profile = load_voice_profile(brand)

    if brand == "the_boulder":
        system_prompt = _build_boulder_standalone_prompt(profile)
    elif brand == "explodable":
        system_prompt = _build_explodable_standalone_prompt(profile)
    else:
        raise ValueError(f"Unknown brand for standalone post: {brand}")

    task_text = (
        "Write a complete standalone 300-500 word LinkedIn post that develops ONE "
        "sharp observation from the seed source [src:0] provided above. "
        "The post must work on its own in a LinkedIn feed — no newsletter context, "
        "no 'part of a series' framing. Target 400 words. Lead with the claim, "
        "not the citation.\n\n"
        "INLINE CITATION MARKERS (mandatory):\n"
        "- When you draw a claim, statistic, study name, effect size, or specific "
        "finding from the seed source, drop an inline marker `[src:0]` immediately "
        "after that sentence.\n"
        "- The marker must appear right after the cited sentence, not at the end "
        "of a paragraph or as a footnote.\n"
        "- You should have at least 2 markers in the final post.\n"
        "- Write in your normal conversational reference style (voice profile rules "
        "apply). The `[src:0]` markers are a SEPARATE mechanism — they will be "
        "post-processed into markdown footnotes after you finish writing. Do not "
        "let them interfere with your voice.\n"
        "- Do not invent new marker IDs. Only `[src:0]` is valid for standalone posts."
    )
    if revision_notes:
        task_text = (
            f"REVISION — the previous draft failed voice compliance. "
            f"Address these specific issues:\n{revision_notes}\n\n"
            + task_text
        )

    if USE_HYBRID_CITATIONS:
        findings_block = _findings_as_marked_sources([finding])
        post_text = _invoke_draft_with_markers(
            system_prompt=system_prompt,
            findings_block=findings_block,
            task_text=task_text,
            max_tokens=2000,
            temperature=0.7,
        )
        return DraftResult(
            newsletter=post_text,
            x_post="",
            x_thread=[],
            linkedin="",
            substack_notes="",
            citations=[],  # hybrid path uses inline markers, not API citations
        )

    if USE_CITATIONS_API:
        documents = _build_single_finding_document(finding)
        post_text, citations = _invoke_draft_with_citations(
            system_prompt=system_prompt,
            documents=documents,
            user_text=task_text,
            max_tokens=2000,
            temperature=0.7,
        )
        return DraftResult(
            newsletter=post_text,
            x_post="",
            x_thread=[],
            linkedin="",
            substack_notes="",
            citations=citations,
        )

    # Fallback: ChatAnthropic path (pre-2026-04-14)
    f = finding.finding
    anxieties = [a.value if hasattr(a, 'value') else str(a) for a in f.root_anxieties]
    finding_context = (
        f"SEED FINDING:\n"
        f"  Claim: {f.claim}\n"
        f"  Elaboration: {f.elaboration}\n"
        f"  Academic discipline: {f.academic_discipline}\n"
        f"  Root anxieties: {', '.join(anxieties)}\n"
        f"  Confidence: {f.confidence_score:.0%}"
    )
    user_content = f"{finding_context}\n\n{task_text}"

    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.7,
        max_tokens=2000,
        max_retries=5,
    )

    response = llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    )
    post_text = response.content

    return DraftResult(
        newsletter=post_text,
        x_post="",
        x_thread=[],
        linkedin="",
        substack_notes="",
        citations=[],
    )


def generate_draft(
    outline,
    findings: list[ScoredFinding],
    revision_notes: str | None = None,
    brand: str = "the_boulder",
    output_type: str = "newsletter",
) -> DraftResult:
    """Generate long-form content from outline + findings.

    Dispatches on (brand, output_type) to the correct prompt builder:
    - (the_boulder, newsletter) → Boulder newsletter + social variants
    - (explodable, newsletter)  → Explodable newsletter + social variants
    - (explodable, brief)       → Explodable brief, no social variants
    - (*, standalone_post)      → routed via generate_standalone_draft instead
    - (the_boulder, brief)      → not supported, raises ValueError

    Args:
        outline: NewsletterOutline or BriefOutline depending on output_type.
        findings: Selected findings used in the outline.
        revision_notes: Optional BVCS feedback for revision passes.
        brand: 'the_boulder' or 'explodable'.
        output_type: 'newsletter' or 'brief'.

    Returns:
        DraftResult. For briefs, social variant fields are empty strings.
    """
    if output_type == "standalone_post":
        # Standalone posts are generated directly from a single seed finding
        # without an outline. This branch exists so callers that dispatch on
        # output_type through generate_draft() still get the right behavior,
        # though the direct path is to call generate_standalone_draft().
        if not findings:
            raise ValueError("generate_draft for standalone_post requires at least one finding")
        return generate_standalone_draft(findings[0], brand=brand, revision_notes=revision_notes)

    if output_type == "brief" and brand != "explodable":
        raise ValueError(
            f"Briefs are Explodable-only. Got brand='{brand}', output_type='brief'. "
            "The Boulder does not produce briefs — it produces opinionated cultural analysis."
        )

    profile = load_voice_profile(brand)

    # Select the newsletter/brief prompt builder
    if output_type == "brief":
        system_prompt = _build_explodable_brief_prompt(profile)
    elif brand == "the_boulder":
        system_prompt = _build_boulder_newsletter_prompt(profile)
    elif brand == "explodable":
        system_prompt = _build_explodable_newsletter_prompt(profile)
    else:
        raise ValueError(f"Unknown brand: {brand}")

    outline_text = _format_outline_for_draft(outline)
    target_words = getattr(outline, "estimated_word_count", None) or 1800

    min_citations = max(4, len(findings) // 2)
    valid_markers = ", ".join(f"[src:{i}]" for i in range(len(findings)))

    task_text = (
        f"You have {len(findings)} source findings available, labeled [src:0] through [src:{len(findings) - 1}]. "
        f"Write the {'brief' if output_type == 'brief' else 'newsletter'} using those findings "
        f"and following this outline:\n\n"
        f"OUTLINE:\n{outline_text}\n\n"
        f"Write the full {'brief' if output_type == 'brief' else 'newsletter'} now. "
        f"Target {target_words} words.\n\n"
        f"INLINE CITATION MARKERS (mandatory):\n"
        f"- When you draw a claim, statistic, study name, effect size, or specific "
        f"finding from a source, drop an inline marker `[src:N]` immediately "
        f"after that sentence. Use the marker that matches the source you're drawing from.\n"
        f"- The marker must appear right after the cited sentence (or claim), NOT at "
        f"the end of a paragraph as a batch citation.\n"
        f"- You should reference at least {min_citations} distinct sources across the whole piece.\n"
        f"- Every quantitative claim (percentage, sample size, effect size) and every "
        f"named study (JOLT Effect, Dixon & McKenna, Corporate Visions, etc.) MUST "
        f"carry a marker pointing at the source it came from.\n"
        f"- Valid marker IDs: {valid_markers}. Do not invent new IDs.\n"
        f"- Write in your normal conversational reference style (voice profile rules "
        f"apply — 'a 2019 Stanford study,' not '(Smith, 2019)'). The `[src:N]` markers "
        f"are a SEPARATE mechanism that runs alongside your prose. A post-processor "
        f"will transform each marker into a markdown footnote with the source URL "
        f"after you finish writing. Do not let the markers interfere with your voice "
        f"or try to integrate them into sentence structure — they are tags."
    )
    if revision_notes:
        task_text = (
            f"REVISION — the previous draft failed voice compliance. "
            f"Address these specific issues:\n{revision_notes}\n\n"
            + task_text
        )

    citations: list[Citation] = []

    if USE_HYBRID_CITATIONS:
        findings_block = _findings_as_marked_sources(findings)
        main_text = _invoke_draft_with_markers(
            system_prompt=system_prompt,
            findings_block=findings_block,
            task_text=task_text,
            max_tokens=6000,
            temperature=0.7,
        )
    elif USE_CITATIONS_API:
        documents = _findings_as_documents(findings)
        main_text, citations = _invoke_draft_with_citations(
            system_prompt=system_prompt,
            documents=documents,
            user_text=task_text,
            max_tokens=6000,
            temperature=0.7,
        )
    else:
        # Fallback: ChatAnthropic prompt-based path (pre-2026-04-14).
        # max_retries=5 tolerates Anthropic 529 Overloaded + 429 rate limit
        # with exponential backoff (1s, 2s, 4s, 8s, 16s).
        findings_context = _format_findings_context(findings)
        user_content = (
            f"Write the {'brief' if output_type == 'brief' else 'newsletter'} using this outline and these findings.\n\n"
            f"OUTLINE:\n{outline_text}\n\n"
            f"SOURCE FINDINGS:\n{findings_context}\n\n"
            f"Write the full {'brief' if output_type == 'brief' else 'newsletter'} now. Target {target_words} words."
        )
        if revision_notes:
            user_content = (
                f"REVISION — the previous draft failed voice compliance. "
                f"Address these specific issues:\n{revision_notes}\n\n"
                + user_content
            )
        llm = ChatAnthropic(
            model=ANTHROPIC_MODEL,
            temperature=0.7,
            max_tokens=6000,
            max_retries=5,
        )
        main_response = llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
        main_text = main_response.content

    # Briefs: no social variants. Return with empty variant fields.
    if output_type == "brief":
        return DraftResult(
            newsletter=main_text,  # 'newsletter' field holds brief text too
            x_post="",
            x_thread=[],
            linkedin="",
            substack_notes="",
            citations=citations,
        )

    # Step 2 (newsletter only): Generate social variants
    if brand == "the_boulder":
        social_prompt = _build_social_prompt_boulder(profile)
    else:
        social_prompt = _build_social_prompt_explodable(profile)

    social_llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.6,
        max_tokens=4000,
        max_retries=5,
    ).with_structured_output(SocialVariants)

    social = social_llm.invoke(
        [
            {"role": "system", "content": social_prompt},
            {
                "role": "user",
                "content": (
                    f"Here is the newsletter to create social variants from:\n\n"
                    f"---\n{main_text}\n---\n\n"
                    f"Generate all four social variants now."
                ),
            },
        ]
    )

    return DraftResult(
        newsletter=main_text,
        x_post=social.x_post,
        x_thread=social.x_thread,
        linkedin=social.linkedin,
        substack_notes=social.substack_notes,
        citations=citations,
    )
