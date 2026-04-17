"""Content Selector — ranks and selects findings for a newsletter draft.

Input: retrieved findings (list of ScoredFinding from retriever)
Ranks by:
  - Novelty: time since last used in a draft (never-used findings score highest)
  - Narrative potential: relationship density in the KB (more connections = richer story)
  - Brand relevance: domain breadth and cross-domain connection potential
Output: selected findings for this draft, max 8
Must select at least one finding with cross-domain relationships (MVP criterion 2).
"""

from pathlib import Path

import yaml
from psycopg import Connection
from psycopg.rows import dict_row

from src.content_pipeline.retriever import ScoredFinding
from src.kb.models import Finding

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _load_voice_profile(brand: str) -> dict:
    """Load the voice profile YAML for a brand."""
    path = _CONFIG_DIR / f"voice_profile_{brand}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _count_relationships(conn: Connection, finding_id: str) -> int:
    """Count inbound + outbound relationships for a finding."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM finding_relationships
            WHERE from_finding_id = %s OR to_finding_id = %s
            """,
            (finding_id, finding_id),
        )
        return cur.fetchone()[0]


def _has_cross_domain_relationships(conn: Connection, finding: Finding) -> bool:
    """Check if a finding has relationships to findings in different academic disciplines."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT f.academic_discipline
            FROM finding_relationships fr
            JOIN findings f ON (
                (fr.to_finding_id = f.id AND fr.from_finding_id = %s)
                OR (fr.from_finding_id = f.id AND fr.to_finding_id = %s)
            )
            WHERE f.academic_discipline != %s
            """,
            (str(finding.id), str(finding.id), finding.academic_discipline),
        )
        return len(cur.fetchall()) > 0


def _has_multiple_root_anxieties(finding: Finding) -> bool:
    """Check if a finding spans multiple root anxieties (cross-domain signal)."""
    return len(finding.root_anxieties) > 1


def _novelty_score(conn: Connection, finding_id: str) -> float:
    """Score novelty based on how many times a finding has been used in drafts.

    Formula: score = exp(-usage_count * decay_factor)
    - Never used → 1.0
    - Used once → ~0.74 (with default decay 0.3)
    - Used twice → ~0.55
    - Used 5 times → ~0.22

    decay_factor configurable via NOVELTY_DECAY_FACTOR env var (default 0.3).
    """
    import math
    import os

    decay_factor = float(os.environ.get("NOVELTY_DECAY_FACTOR", "0.3"))

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM draft_usage WHERE finding_id = %s",
                (finding_id,),
            )
            usage_count = cur.fetchone()[0]
    except Exception:
        # Table may not exist yet — treat as fully novel
        return 1.0

    if usage_count == 0:
        return 1.0
    return math.exp(-usage_count * decay_factor)


def _narrative_potential_score(conn: Connection, finding_id: str) -> float:
    """Score narrative potential based on relationship density.

    More relationships = more connections to weave into a story.
    0 relationships = 0.3 (still usable as standalone)
    1-2 = 0.6
    3-5 = 0.8
    6+ = 1.0
    """
    count = _count_relationships(conn, finding_id)
    if count >= 6:
        return 1.0
    elif count >= 3:
        return 0.8
    elif count >= 1:
        return 0.6
    return 0.3


def _brand_relevance_score(finding: Finding, brand: str = "the_boulder") -> float:
    """Score brand relevance based on the brand's voice profile.

    Loads the voice profile to determine what the brand values:
    - Higher contrarianism → reward cross-domain connections
    - Higher earnestness → reward evidence density (confidence)
    - Higher formality → reward neurobiological grounding (circuits)
    - Explodable-style brands (urgency > 3) → reward buyer/business domains
    """
    profile = _load_voice_profile(brand)
    tone = profile.get("tone", {})

    score = 0.5  # baseline

    # Cross-domain potential scales with how much the brand values unexpected connections
    contrarianism = tone.get("contrarianism", 3.0)
    if len(finding.root_anxieties) > 1:
        score += 0.1 + (contrarianism / 5.0) * 0.2  # 0.18–0.30 range

    # Confidence scales with earnestness (brands that value rigor reward high-confidence findings)
    earnestness = tone.get("earnestness", 3.0)
    if finding.confidence_score >= 0.75:
        score += (earnestness / 5.0) * 0.15  # up to 0.15
    elif finding.confidence_score >= 0.60:
        score += (earnestness / 5.0) * 0.08

    # Circuits present = analytical depth, scaled by formality
    formality = tone.get("formality", 3.0)
    if finding.primary_circuits and len(finding.primary_circuits) > 0:
        score += (formality / 5.0) * 0.1

    # Urgency-driven brands reward buyer-facing domains
    urgency = tone.get("urgency", 2.0)
    if urgency >= 3.0:
        buyer_domains = {"buyer psychology", "healthcare buyer psychology",
                         "behavioral economics", "crm fiction and sales attribution",
                         "messaging and positioning psychology"}
        if finding.academic_discipline in buyer_domains:
            score += 0.1

    return min(score, 1.0)


def select_findings(
    conn: Connection,
    scored_findings: list[ScoredFinding],
    max_findings: int = 8,
    brand: str = "the_boulder",
    output_type: str = "newsletter",
) -> list[ScoredFinding]:
    """Select and rank findings for a content draft.

    Ranking formula combines:
    - Retrieval score (from retriever, includes semantic similarity + recency)
    - Novelty (has this finding been used before?)
    - Narrative potential (relationship density)
    - Brand relevance (loaded from voice profile for the active brand)

    For output_type='newsletter' or 'brief': returns up to max_findings
    findings, guaranteeing at least one cross-domain finding if any exist.

    For output_type='standalone_post': returns a single seed finding,
    heavily biased toward cross-domain + high-confidence + novel findings.
    Standalone posts anchor to one sharp finding and develop it in 300-500
    words — picking the right seed is the whole game.

    Args:
        conn: Database connection.
        scored_findings: Output from retrieve_findings().
        max_findings: Maximum findings to select (default 8 per spec).
        brand: Brand name (loads voice profile from config/).
        output_type: 'newsletter', 'brief', or 'standalone_post'.

    Returns:
        Selected and re-ranked list of ScoredFinding objects.
    """
    if not scored_findings:
        return []

    # Score each finding on all dimensions
    ranked: list[tuple[ScoredFinding, float, bool]] = []
    for sf in scored_findings:
        fid = str(sf.finding.id)

        novelty = _novelty_score(conn, fid)
        narrative = _narrative_potential_score(conn, fid)
        brand_score = _brand_relevance_score(sf.finding, brand=brand)

        if output_type == "standalone_post":
            # Standalone posts need ONE sharp finding that can carry a
            # 300-500 word observation on its own. Heavily weight novelty
            # (don't keep posting about the same finding), narrative
            # potential (relationship-rich findings produce interesting
            # short-form), and brand relevance. Retrieval score matters
            # less because we only need the finding to be on-topic, not
            # optimally ranked.
            selection_score = (
                0.2 * sf.combined_score
                + 0.3 * novelty
                + 0.25 * narrative
                + 0.25 * brand_score
            )
        else:
            # Newsletter / brief: standard ranking
            selection_score = (
                0.4 * sf.combined_score
                + 0.2 * novelty
                + 0.2 * narrative
                + 0.2 * brand_score
            )

        # Check cross-domain potential
        is_cross_domain = (
            _has_cross_domain_relationships(conn, sf.finding)
            or _has_multiple_root_anxieties(sf.finding)
        )

        ranked.append((sf, selection_score, is_cross_domain))

    # Sort by selection score
    ranked.sort(key=lambda x: x[1], reverse=True)

    # Standalone post: just return the top cross-domain finding.
    # If no cross-domain exists (unusual at 273-finding KB scale),
    # return the top-scored finding.
    if output_type == "standalone_post":
        cross_domain_top = [(sf, score) for sf, score, is_cross in ranked if is_cross]
        if cross_domain_top:
            return [cross_domain_top[0][0]]
        return [ranked[0][0]] if ranked else []

    # Newsletter / brief: select top N, ensuring at least one cross-domain
    selected: list[ScoredFinding] = []
    has_cross_domain = False

    for sf, score, is_cross in ranked:
        if len(selected) >= max_findings:
            break
        selected.append(sf)
        if is_cross:
            has_cross_domain = True

    # If no cross-domain finding was selected, find the best one and swap it in
    if not has_cross_domain:
        cross_domain_candidates = [
            (sf, score) for sf, score, is_cross in ranked if is_cross
        ]
        if cross_domain_candidates:
            best_cross = cross_domain_candidates[0][0]
            if selected:
                # Replace the lowest-scored selected finding
                selected[-1] = best_cross
            else:
                selected.append(best_cross)

    return selected
