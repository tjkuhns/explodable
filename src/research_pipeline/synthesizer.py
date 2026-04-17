"""DEPRECATED 2026-04-14 — see src/research_pipeline/DEPRECATED.md

Synthesizer agent. Dormant dependency of drift_monitor. Deduplicates and
detects conflicts across research results. No longer an active ingestion path.

Input: list of ResearchResult from parallel researcher agents
Dedup: SHA-256 exact → MinHash near-duplicate → pgvector cosine >0.90 semantic
Conflict detection: NLI check for contradictory claims
Output: SynthesisResult(proposed_findings, conflicts)

Reads structured data from researchers, never conversational summaries.
"""

import hashlib
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel, Field

from langchain_anthropic import ChatAnthropic
from datasketch import MinHash

from src.research_pipeline.researcher import ResearchResult, Source
from src.kb.models import RootAnxiety, PankseppCircuit
from src.kb.dedup import _text_to_minhash
from src.shared.constants import ANTHROPIC_MODEL


# ── Output models ──


class ProposedFinding(BaseModel):
    """A finding proposed for KB insertion, pending critic review and HITL approval."""

    claim: str = Field(default="", description="The core claim (target 280 chars)")
    elaboration: str = ""
    root_anxieties: list[str] = Field(
        default_factory=list,
        description="From: mortality, isolation, insignificance, meaninglessness, helplessness",
    )
    primary_circuits: list[str] | None = Field(
        default=None,
        description="From: SEEKING, RAGE, FEAR, LUST, CARE, PANIC_GRIEF, PLAY",
    )
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_basis: str = ""
    academic_discipline: str = ""
    sources: list[Source] = Field(default_factory=list)
    source_task_ids: list[str] = Field(
        default_factory=list,
        description="Which research tasks contributed to this finding",
    )
    kb_status: str = Field(
        default="new",
        description="'new' = no KB match, 'supporting' = supports existing, 'contradicting' = contradicts existing",
    )
    existing_finding_ids: list[str] = Field(
        default_factory=list,
        description="IDs of existing KB findings this relates to (if any)",
    )


class Conflict(BaseModel):
    """A detected contradiction between two claims."""

    claim_a: str
    claim_b: str
    task_id_a: str
    task_id_b: str
    conflict_type: str = Field(
        description="'direct_contradiction', 'scope_disagreement', 'evidence_conflict'"
    )
    explanation: str


class DedupMatch(BaseModel):
    """A duplicate detected during synthesis."""

    original_task_id: str
    duplicate_task_id: str
    match_type: str = Field(description="'exact', 'near_duplicate', 'semantic'")
    similarity: float | None = None


class SynthesisResult(BaseModel):
    """Structured output from the Synthesizer."""

    proposed_findings: list[ProposedFinding]
    conflicts: list[Conflict]
    dedup_matches: list[DedupMatch] = Field(default_factory=list)
    merge_notes: str = Field(
        default="",
        description="Explanation of how results were merged or deduplicated",
    )


# ── Internal dedup ──

from src.shared.constants import NUM_PERM, LSH_THRESHOLD as MINHASH_THRESHOLD


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_exact_duplicates(results: list[ResearchResult]) -> list[tuple[int, int]]:
    """Find exact claim duplicates via SHA-256."""
    hashes: dict[str, int] = {}
    dupes = []
    for i, r in enumerate(results):
        h = _sha256(r.claim)
        if h in hashes:
            dupes.append((hashes[h], i))
        else:
            hashes[h] = i
    return dupes


def _find_near_duplicates(results: list[ResearchResult]) -> list[tuple[int, int, float]]:
    """Find near-duplicate claims via MinHash Jaccard similarity."""
    minhashes = [_text_to_minhash(r.claim) for r in results]
    dupes = []
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            sim = minhashes[i].jaccard(minhashes[j])
            if sim >= MINHASH_THRESHOLD:
                dupes.append((i, j, sim))
    return dupes


def _check_kb_duplicates(
    results: list[ResearchResult],
) -> dict[int, list[dict]]:
    """Check each result against existing KB findings via cosine similarity.

    Returns dict mapping result index to list of KB matches.
    Only runs if DB is available — gracefully skips otherwise.
    """
    kb_matches: dict[int, list[dict]] = {}
    try:
        from uuid import uuid4
        from src.kb.connection import get_connection
        from src.kb.dedup import cosine_discovery_check
        from src.kb.telemetry import log_query, compute_relationship_types_present

        session_id = uuid4()

        with get_connection() as conn:
            for i, r in enumerate(results):
                matches = cosine_discovery_check(conn, r.claim)
                matched_ids = [str(m.id) for m in matches] if matches else []
                if matches:
                    kb_matches[i] = [
                        {"id": str(m.id), "claim": m.claim, "confidence": m.confidence_score}
                        for m in matches
                    ]

                log_query(
                    conn,
                    query_text=r.claim,
                    pipeline_source="research_pipeline",
                    finding_ids_returned=matched_ids,
                    relationship_types_present=compute_relationship_types_present(conn, matched_ids),
                    session_id=session_id,
                )
    except Exception:
        # DB not available — skip KB dedup, will catch at KB write time
        pass
    return kb_matches


# ── NLI conflict detection ──

NLI_SYSTEM_PROMPT = """You are a natural language inference (NLI) specialist. Given two claims, determine if they contradict each other.

Respond with EXACTLY one of:
- ENTAILMENT: Claim B follows from or is consistent with Claim A
- CONTRADICTION: Claim B contradicts or is incompatible with Claim A
- NEUTRAL: Claims are about different things or don't directly relate

Then provide a one-sentence explanation.

Format your response exactly as:
LABEL: <label>
EXPLANATION: <one sentence>"""


def _check_conflicts_llm(results: list[ResearchResult]) -> list[Conflict]:
    """Detect contradictions between claims using NLI via Claude."""
    if len(results) < 2:
        return []

    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.0,
        max_tokens=500,
        max_retries=5,
    )

    conflicts = []
    # Check all pairs
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            response = llm.invoke(
                [
                    {"role": "system", "content": NLI_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Claim A (from {results[i].domain}): {results[i].claim}\n"
                            f"Claim B (from {results[j].domain}): {results[j].claim}"
                        ),
                    },
                ]
            )
            text = response.content
            if "CONTRADICTION" in text:
                explanation = ""
                for line in text.split("\n"):
                    if line.startswith("EXPLANATION:"):
                        explanation = line.replace("EXPLANATION:", "").strip()
                        break

                conflicts.append(
                    Conflict(
                        claim_a=results[i].claim,
                        claim_b=results[j].claim,
                        task_id_a=results[i].task_id,
                        task_id_b=results[j].task_id,
                        conflict_type="direct_contradiction",
                        explanation=explanation or "Claims are contradictory.",
                    )
                )

    return conflicts


# ── Anxiety/circuit classification ──

CLASSIFY_SYSTEM_PROMPT = """You classify research findings into the root anxiety framework.

Root anxieties (pick 1-2):
- mortality: Fear of death, non-existence, finitude
- isolation: Fear of being alone, disconnected, excluded
- insignificance: Fear that one's life/actions don't matter
- meaninglessness: Fear that existence has no purpose
- helplessness: Fear of lacking agency or control

Panksepp affective circuits (pick 0-3, only if clearly relevant):
- SEEKING: Exploration, curiosity, anticipation
- RAGE: Frustration, anger at constraints
- FEAR: Threat detection, anxiety
- LUST: Sexual desire, reproduction drive
- CARE: Nurturing, attachment
- PANIC_GRIEF: Separation distress, loss
- PLAY: Joy, social bonding, creativity"""


class AnxietyClassification(BaseModel):
    root_anxieties: list[str] = Field(default_factory=lambda: ["insignificance"])
    primary_circuits: list[str] | None = Field(default=None)
    rationale: str = ""


def _classify_anxieties(claim: str, elaboration: str, academic_discipline: str) -> AnxietyClassification:
    """Classify a finding's root anxieties and circuits."""
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.1,
        max_tokens=500,
        max_retries=5,
    ).with_structured_output(AnxietyClassification)

    return llm.invoke(
        [
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Claim: {claim}\n"
                    f"Elaboration: {elaboration[:500]}\n"
                    f"Academic discipline: {academic_discipline}"
                ),
            },
        ]
    )


# ── Main synthesizer ──


def synthesize(results: list[ResearchResult]) -> SynthesisResult:
    """Synthesize multiple research results into proposed findings.

    Runs the full dedup pipeline and conflict detection.
    Reads structured data only — never conversational summaries.
    """
    if not results:
        return SynthesisResult(proposed_findings=[], conflicts=[])

    dedup_matches: list[DedupMatch] = []
    excluded_indices: set[int] = set()

    # Step 1: SHA-256 exact dedup
    exact_dupes = _find_exact_duplicates(results)
    for orig_idx, dupe_idx in exact_dupes:
        dedup_matches.append(
            DedupMatch(
                original_task_id=results[orig_idx].task_id,
                duplicate_task_id=results[dupe_idx].task_id,
                match_type="exact",
            )
        )
        excluded_indices.add(dupe_idx)

    # Step 2: MinHash near-duplicate dedup
    near_dupes = _find_near_duplicates(results)
    for orig_idx, dupe_idx, sim in near_dupes:
        if dupe_idx not in excluded_indices:
            dedup_matches.append(
                DedupMatch(
                    original_task_id=results[orig_idx].task_id,
                    duplicate_task_id=results[dupe_idx].task_id,
                    match_type="near_duplicate",
                    similarity=sim,
                )
            )
            # Keep the higher-confidence result
            if results[dupe_idx].confidence_score > results[orig_idx].confidence_score:
                excluded_indices.add(orig_idx)
            else:
                excluded_indices.add(dupe_idx)

    # Step 3: Check remaining results against KB
    remaining = [r for i, r in enumerate(results) if i not in excluded_indices]
    remaining_indices = [i for i in range(len(results)) if i not in excluded_indices]
    kb_matches = _check_kb_duplicates(remaining)

    # Step 4: NLI conflict detection on remaining results
    conflicts = _check_conflicts_llm(remaining)

    # Step 5: Build proposed findings with anxiety classification
    proposed_findings: list[ProposedFinding] = []
    for local_idx, r in enumerate(remaining):
        global_idx = remaining_indices[local_idx]

        # Classify anxieties and circuits
        classification = _classify_anxieties(r.claim, r.elaboration, r.domain)  # r.domain stays — ResearchResult field

        # Determine KB status
        kb_status = "new"
        existing_ids: list[str] = []
        if local_idx in kb_matches:
            existing_ids = [m["id"] for m in kb_matches[local_idx]]
            # Check if any KB match contradicts — simplified: if KB match exists,
            # mark as supporting (contradiction detection is done separately)
            kb_status = "supporting"

        proposed_findings.append(
            ProposedFinding(
                claim=r.claim,
                elaboration=r.elaboration,
                root_anxieties=classification.root_anxieties,
                primary_circuits=classification.primary_circuits,
                confidence_score=r.confidence_score,
                confidence_basis=r.confidence_basis,
                academic_discipline=r.domain,
                sources=r.sources,
                source_task_ids=[r.task_id],
                kb_status=kb_status,
                existing_finding_ids=existing_ids,
            )
        )

    merge_notes = ""
    if dedup_matches:
        merge_notes = (
            f"Removed {len(dedup_matches)} duplicate(s): "
            + ", ".join(
                f"{d.duplicate_task_id} ({d.match_type})" for d in dedup_matches
            )
        )

    return SynthesisResult(
        proposed_findings=proposed_findings,
        conflicts=conflicts,
        dedup_matches=dedup_matches,
        merge_notes=merge_notes,
    )
