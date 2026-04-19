"""Adversarial critique stage for the hybrid cognitive pipeline.

Reads a draft + the full KB (CAG-style) and produces structured atomic
critique proposals. Uses a DIFFERENT model from the generator to prevent
reward hacking (Pan et al. 2024 finding: same-model critique-and-revise
systematically inflates self-evaluated quality while degrading human-judged
quality).

Design grounded in Report 3 (docs/research/hybrid_reports/03_adversarial_critique.md):

* 5-phase sequential critique: factual grounding → completeness audit →
  structural coherence → counterargument probe → originality flag
* Atomic proposals, not rewritten drafts — each suggestion is independent
  and implementable
* Completeness capped at 3 unused findings to prevent cramming
* Different model family for critic vs generator
* Revision gate: before/after judge scoring with Pareto filter (improve ≥1
  dimension, degrade none)

Supported critic backends (pluggable):
* Gemini Flash via Google AI Studio (free, satisfies different-model req)
* Claude Opus (paid, same family as Sonnet generator — less ideal per Pan
  et al. but still useful if Gemini unavailable)
* Any OpenAI model (if API key available)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


class CritiqueDimension(str, Enum):
    FACTUAL_GROUNDING = "factual_grounding"
    COMPLETENESS = "completeness"
    STRUCTURAL_COHERENCE = "structural_coherence"
    COUNTERARGUMENT = "counterargument"
    ORIGINALITY = "originality"


DIMENSION_PRIORITY = [
    CritiqueDimension.FACTUAL_GROUNDING,
    CritiqueDimension.COMPLETENESS,
    CritiqueDimension.STRUCTURAL_COHERENCE,
    CritiqueDimension.COUNTERARGUMENT,
    CritiqueDimension.ORIGINALITY,
]


@dataclass
class CritiqueProposal:
    dimension: CritiqueDimension
    severity: str  # "high", "medium", "low"
    location: str  # paragraph or section reference
    issue: str  # what's wrong
    suggestion: str  # specific fix
    finding_ids: list[int] = field(default_factory=list)  # [src:N] IDs to add, if any


@dataclass
class CritiqueResult:
    draft_path: str
    proposals: list[CritiqueProposal]
    summary: str
    critic_model: str
    raw_response: str = ""
    contradictions_checked: list[str] = field(default_factory=list)


CRITIQUE_SYSTEM_PROMPT = """You are an adversarial editor reviewing a long-form analytical essay produced by a behavioral-strategy consulting practice. Your job is to find weaknesses, not to praise. The essay was generated from a knowledge base of behavioral-science findings — the full knowledge base is provided below so you can identify what was left out, what was misused, and what contradicts the essay's claims.

You will critique the essay across 5 dimensions, in priority order. For each issue you find, produce an atomic proposal — a single, specific, implementable suggestion.

IMPORTANT CONSTRAINTS:
- You are a CRITIC, not a rewriter. Output structured proposals, never rewritten text.
- Each proposal targets ONE issue. Do not bundle multiple fixes.
- For completeness (dimension 2), identify AT MOST 3 unused findings that would genuinely strengthen the argument. Do not suggest findings just because they're tangentially related.
- Higher-priority dimensions override lower ones. Never suggest a completeness addition that would break structural coherence.
- If the essay is genuinely strong on a dimension, say so briefly and move on. Not every dimension needs proposals.

THE 5 DIMENSIONS (in priority order):

1. FACTUAL GROUNDING — For each major claim in the essay, verify it traces to a cited finding ([src:N]) in the knowledge base. Flag:
   - Claims with no citation that should have one
   - Citations where the quoted phrase doesn't match the finding's actual text
   - Claims that overstate or mischaracterize what the finding actually says

2. COMPLETENESS — Scan the full knowledge base for the 3 most important findings NOT used in the essay that would materially strengthen the argument. For each:
   - State which finding (by id) and why it matters
   - Identify where in the essay it would fit
   - Explain what it adds that isn't already covered

3. STRUCTURAL COHERENCE — Evaluate the essay's argument flow:
   - Does each section build on the previous one?
   - Are there logical gaps between sections?
   - Does the conclusion advance the argument or just restate it?
   - Are there sections that feel like separate essays crammed together?

4. COUNTERARGUMENT — Identify the single strongest objection a skeptical reader would raise:
   - What's the most vulnerable claim?
   - What evidence would challenge it?
   - Is the essay's counterargument section (if any) addressing the RIGHT objection?

5. ORIGINALITY — Flag passages that read as generic consulting language or content-marketing platitudes rather than genuine analytical insight. Be specific about which sentences and why.

OUTPUT FORMAT — Return a JSON object with exactly this shape:

{
  "proposals": [
    {
      "dimension": "factual_grounding|completeness|structural_coherence|counterargument|originality",
      "severity": "high|medium|low",
      "location": "paragraph N or section title",
      "issue": "specific description of the problem",
      "suggestion": "specific, implementable fix",
      "finding_ids": [N]
    }
  ],
  "summary": "2-3 sentence overall assessment"
}

No prose before or after the JSON. No markdown code fence. Just the JSON object.
"""


REVISION_SYSTEM_PROMPT = """You are revising a long-form analytical essay based on specific editorial critique proposals. Each proposal targets one issue and suggests one fix. You have the original essay and any additional findings that were recommended by the critic.

CONSTRAINTS:
- Apply ONLY the approved proposals listed below. Do not make additional changes.
- Preserve the essay's voice, tone, and overall structure unless a proposal specifically asks for structural changes.
- When adding a new finding, integrate it naturally — do not just append a paragraph.
- Maintain the [src:N] "quoted phrase" citation format for any new citations.
- Keep the essay within 900-1500 words. If adding material, cut elsewhere to compensate.
- Output only the revised essay body as markdown, starting with the title as an H1.
"""


class CriticBackend(Protocol):
    def critique(self, draft: str, kb_context: str) -> str:
        """Send the draft + KB to the critic model, return raw JSON response."""
        ...


class AnthropicCritic:
    """Uses Claude (Opus or Sonnet) as the critic. Same model family as the
    generator — less ideal per Pan et al. but functional."""

    def __init__(self, model: str = "claude-opus-4-20250514"):
        from anthropic import Anthropic
        self.client = Anthropic()
        self.model = model

    def critique(self, draft: str, kb_context: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=3000,
            temperature=0.3,  # lower temp for analytical critique
            system=[
                {"type": "text", "text": CRITIQUE_SYSTEM_PROMPT + "\n\n" + kb_context,
                 "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": f"ESSAY TO CRITIQUE:\n\n{draft}"}],
        )
        return msg.content[0].text


class GeminiCritic:
    """Uses Gemini Flash via Google AI Studio (free tier). Different model
    family from the Anthropic generator — satisfies Pan et al. recommendation."""

    def __init__(self, model: str = "gemini-2.5-flash"):
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "pip install google-generativeai to use GeminiCritic"
            )
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_AI_API_KEY")
        if not api_key:
            raise ValueError("Set GEMINI_API_KEY or GOOGLE_AI_API_KEY in .env")
        genai.configure(api_key=api_key)
        self._genai_model = genai.GenerativeModel(model)
        self.model = model  # store name as string for serialization

    def critique(self, draft: str, kb_context: str) -> str:
        prompt = (
            CRITIQUE_SYSTEM_PROMPT + "\n\n" + kb_context
            + "\n\nESSAY TO CRITIQUE:\n\n" + draft
        )
        response = self._genai_model.generate_content(prompt)
        return response.text


class OpenAICritic:
    """Uses GPT-4o or GPT-4o-mini via OpenAI API."""

    def __init__(self, model: str = "gpt-4o-mini"):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("pip install openai to use OpenAICritic")
        self.client = OpenAI()
        self.model = model

    def critique(self, draft: str, kb_context: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.3,
            max_tokens=3000,
            messages=[
                {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT + "\n\n" + kb_context},
                {"role": "user", "content": f"ESSAY TO CRITIQUE:\n\n{draft}"},
            ],
        )
        return response.choices[0].message.content


def get_critic(backend: str = "auto") -> CriticBackend:
    """Get the best available critic backend.

    Priority: Gemini Flash (free + different model family) > OpenAI (paid +
    different family) > Anthropic Opus (paid + same family).
    """
    if backend == "gemini":
        return GeminiCritic()
    if backend == "openai":
        return OpenAICritic()
    if backend == "anthropic":
        return AnthropicCritic()

    # Auto-detect: try free options first
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_AI_API_KEY"):
        try:
            return GeminiCritic()
        except (ImportError, ValueError):
            pass
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return OpenAICritic()
        except ImportError:
            pass
    return AnthropicCritic()


def parse_critique(raw: str) -> tuple[list[CritiqueProposal], dict]:
    """Parse the critic's JSON response.

    Returns (proposals, raw_data) so callers can access the top-level
    `summary` field without re-parsing the JSON.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    data = json.loads(cleaned)
    proposals = []
    for p in data.get("proposals", []):
        proposals.append(
            CritiqueProposal(
                dimension=CritiqueDimension(p["dimension"]),
                severity=p.get("severity", "medium"),
                location=p.get("location", ""),
                issue=p["issue"],
                suggestion=p["suggestion"],
                finding_ids=p.get("finding_ids", []),
            )
        )
    return proposals, data


def filter_proposals(
    proposals: list[CritiqueProposal],
    max_completeness: int = 3,
) -> list[CritiqueProposal]:
    """Apply priority filtering and completeness cap.

    Per Report 3: higher-priority dimensions override lower ones. Cap
    completeness suggestions at max_completeness to prevent cramming.
    """
    completeness_count = 0
    filtered: list[CritiqueProposal] = []
    # Sort by dimension priority
    priority_map = {d: i for i, d in enumerate(DIMENSION_PRIORITY)}
    proposals.sort(key=lambda p: priority_map.get(p.dimension, 99))

    for p in proposals:
        if p.dimension == CritiqueDimension.COMPLETENESS:
            if completeness_count >= max_completeness:
                continue
            completeness_count += 1
        filtered.append(p)
    return filtered


def critique_draft(
    draft_text: str,
    kb_xml: str,
    critic: CriticBackend | None = None,
    contradiction_findings: list[tuple[str, str]] | None = None,
) -> CritiqueResult:
    """Run the full adversarial critique on a draft.

    Args:
        draft_text: the essay to critique
        kb_xml: full KB as XML (CAG format) for the critic's context
        critic: the critic backend to use (auto-detected if None)
        contradiction_findings: list of (finding_id, contradicting_id) pairs
            from the graph expander, pre-identified for the critic's use
    """
    if critic is None:
        critic = get_critic()

    # Add contradiction context if available
    extra_context = ""
    if contradiction_findings:
        extra_context = (
            "\n\nNOTE: The following findings in the KB CONTRADICT findings "
            "used in this essay. Consider whether the essay addresses or "
            "ignores these contradictions:\n"
        )
        for from_id, contra_id in contradiction_findings:
            extra_context += f"  - Finding {from_id} is contradicted by finding {contra_id}\n"

    raw = critic.critique(draft_text, kb_xml + extra_context)

    proposals, data = parse_critique(raw)
    proposals = filter_proposals(proposals)
    summary = data.get("summary", "")

    return CritiqueResult(
        draft_path="",
        proposals=proposals,
        summary=summary,
        critic_model=getattr(critic, "model", "unknown"),
        raw_response=raw,
        contradictions_checked=[f"{a}->{b}" for a, b in (contradiction_findings or [])],
    )
