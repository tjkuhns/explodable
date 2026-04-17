"""KB Retriever — retrieves findings for the content pipeline.

Input: topic keywords or root anxiety tags
Multi-query retrieval: generate 3 query variants, retrieve top-k for each, deduplicate
Decay-weighted scoring: score = 0.7 * semantic_similarity + 0.3 * exp(-0.693 * age_days / 14)
Filter: status = 'active' and confidence_score >= 0.45
Output: ranked list of Finding objects
"""

import math
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel, Field
from psycopg import Connection
from psycopg.rows import dict_row

from langchain_anthropic import ChatAnthropic

from src.kb.models import Finding
from src.kb.embeddings import generate_embedding


# ── Query expansion ──


class QueryVariants(BaseModel):
    """Three query variants for multi-query retrieval."""

    variant_1: str = Field(description="Rephrase the topic as a direct factual question")
    variant_2: str = Field(description="Rephrase the topic using domain-specific academic terminology")
    variant_3: str = Field(description="Rephrase the topic by connecting it to a different domain or root anxiety")


QUERY_EXPANSION_PROMPT = """You generate search query variants for a knowledge base retrieval system.

The knowledge base contains findings organized by root human anxieties:
- mortality, isolation, insignificance, meaninglessness, helplessness

Given a topic, produce three distinct query variants that will surface different but relevant findings:
1. A direct factual question about the topic
2. A rephrasing using domain-specific or academic terminology
3. A cross-domain connection — link the topic to a different field or root anxiety

Each variant should be a single sentence, optimized for semantic similarity search against 280-character claims."""


def generate_query_variants(topic: str) -> list[str]:
    """Generate 3 query variants from a topic for multi-query retrieval."""
    from src.shared.constants import ANTHROPIC_MODEL
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.4,
        max_tokens=500,
        max_retries=5,
    ).with_structured_output(QueryVariants)

    result = llm.invoke(
        [
            {"role": "system", "content": QUERY_EXPANSION_PROMPT},
            {"role": "user", "content": topic},
        ]
    )
    return [result.variant_1, result.variant_2, result.variant_3]


# ── Decay-weighted scoring ──


def _compute_decay_weighted_score(
    semantic_similarity: float, age_days: float
) -> float:
    """Compute decay-weighted score per spec formula.

    score = 0.7 * semantic_similarity + 0.3 * exp(-0.693 * age_days / 14)

    - Semantic similarity dominates (70% weight)
    - Recency decays with 14-day half-life (30% weight)
    - A finding loses half its recency bonus every 14 days
    """
    recency = math.exp(-0.693 * age_days / 14.0)
    return 0.7 * semantic_similarity + 0.3 * recency


def _age_in_days(created_at: datetime) -> float:
    """Calculate age in days from creation timestamp."""
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    delta = now - created_at
    return max(delta.total_seconds() / 86400.0, 0.0)


# ── Core retrieval ──


class ScoredFinding(BaseModel):
    """A finding with its retrieval score components."""

    finding: Finding
    semantic_similarity: float
    age_days: float
    recency_score: float
    combined_score: float
    query_variant: str = Field(description="Which query variant retrieved this finding")


def _retrieve_for_query(
    conn: Connection,
    query: str,
    top_k: int = 10,
    min_confidence: float = 0.45,
) -> tuple[list[tuple[Finding, float]], list[float]]:
    """Retrieve top-k active findings for a single query by semantic similarity.

    Filters: status='active', confidence_score >= min_confidence, embedding IS NOT NULL.

    Returns (results, embedding) — the embedding is returned so callers can log it
    without regenerating.
    """
    embedding = generate_embedding(query)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT *, 1 - (embedding <=> %(emb)s::vector) AS similarity
            FROM findings
            WHERE status = 'active'
              AND confidence_score >= %(min_conf)s
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %(emb)s::vector
            LIMIT %(top_k)s
            """,
            {"emb": embedding, "min_conf": min_confidence, "top_k": top_k},
        )
        results = []
        for row in cur.fetchall():
            similarity = row.pop("similarity")
            results.append((Finding(**row), similarity))
        return results, embedding


# ── Relationship-graph expansion ──
#
# Semantic retrieval alone misses the structural moat the KB is built around:
# 480 typed relationships (supports, extends, qualifies, subsumes, reframes,
# contradicts) connect findings across domains that semantic similarity would
# never surface in the same query result. A finding about luxury consumption
# and a finding about political radicalization can share an 'extends' edge
# through their mutual connection to insignificance anxiety — structurally
# adjacent but lexically unrelated.
#
# This function takes the top semantic-retrieval results as seeds, walks out
# one hop via the finding_relationships table, and pulls the connected
# findings back as candidate results with relationship-type-weighted scores.

# Relationship type weights for graph expansion scoring.
# Higher weight = more valuable to surface. contradicts and reframes create
# the most interesting narrative tension; supports is the most redundant
# (a supporting edge means the neighbor says the same thing from a different
# angle, less surprising).
_RELATIONSHIP_WEIGHTS = {
    "contradicts": 1.00,
    "reframes": 0.90,
    "extends": 0.85,
    "qualifies": 0.80,
    "subsumes": 0.70,
    "supports": 0.50,
}


def _expand_via_relationships(
    conn: Connection,
    seed_findings: list[ScoredFinding],
    max_seeds: int = 5,
    max_neighbors: int = 6,
) -> list[ScoredFinding]:
    """Pull findings connected to seeds via typed relationships.

    Uses the top `max_seeds` semantic-retrieval results as seeds, walks one
    hop along finding_relationships edges, and returns up to `max_neighbors`
    neighbor findings scored by seed_score × relationship_weight × edge_confidence.

    Neighbors that were already in the semantic result set are filtered out
    by the caller (they'll keep their original semantic score). Only genuinely
    structurally-adjacent findings that semantic search missed come through.
    """
    if not seed_findings:
        return []

    seeds = seed_findings[:max_seeds]
    seed_ids = [str(sf.finding.id) for sf in seeds]
    seed_score_map = {str(sf.finding.id): sf.combined_score for sf in seeds}

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                fr.relationship::text AS relationship,
                fr.confidence AS rel_confidence,
                CASE
                    WHEN fr.from_finding_id = ANY(%(seed_ids)s::uuid[]) THEN fr.to_finding_id
                    ELSE fr.from_finding_id
                END AS neighbor_id,
                CASE
                    WHEN fr.from_finding_id = ANY(%(seed_ids)s::uuid[]) THEN fr.from_finding_id
                    ELSE fr.to_finding_id
                END AS seed_id,
                f.*
            FROM finding_relationships fr
            JOIN findings f ON (
                (fr.from_finding_id = ANY(%(seed_ids)s::uuid[]) AND f.id = fr.to_finding_id)
                OR (fr.to_finding_id = ANY(%(seed_ids)s::uuid[]) AND f.id = fr.from_finding_id)
            )
            WHERE f.status = 'active' AND f.embedding IS NOT NULL
            """,
            {"seed_ids": seed_ids},
        )
        rows = cur.fetchall()

    # Deduplicate neighbors — one finding may be reachable from multiple
    # seeds or via multiple edges. Keep the highest-scored edge per neighbor.
    best_by_neighbor: dict[str, dict] = {}
    for row in rows:
        neighbor_id = str(row["neighbor_id"])
        if neighbor_id in seed_ids:
            continue  # Skip seed-to-seed relationships — the seed is already in the result set.

        rel_type = row["relationship"]
        rel_weight = _RELATIONSHIP_WEIGHTS.get(rel_type, 0.5)
        rel_confidence = row["rel_confidence"] or 0.7
        seed_id = str(row["seed_id"])
        seed_score = seed_score_map.get(seed_id, 0.5)

        graph_score = seed_score * rel_weight * rel_confidence

        existing = best_by_neighbor.get(neighbor_id)
        if existing is None or graph_score > existing["graph_score"]:
            # Reconstruct the Finding from the joined row. The SELECT pulls
            # f.* plus fr.relationship/confidence/neighbor_id/seed_id, so we
            # need to strip the fr.* fields before building the Finding.
            finding_fields = {
                k: v for k, v in row.items()
                if k not in ("relationship", "rel_confidence", "neighbor_id", "seed_id")
            }
            try:
                neighbor_finding = Finding(**finding_fields)
            except Exception:
                continue  # Malformed row — skip rather than fail the whole expansion
            best_by_neighbor[neighbor_id] = {
                "finding": neighbor_finding,
                "graph_score": graph_score,
                "rel_type": rel_type,
                "seed_id": seed_id,
            }

    # Convert top-N neighbors to ScoredFinding objects. Graph-expanded findings
    # get combined_score = graph_score and semantic_similarity = 0.0 (they
    # weren't retrieved semantically). query_variant records how they surfaced.
    sorted_neighbors = sorted(
        best_by_neighbor.values(), key=lambda x: x["graph_score"], reverse=True
    )[:max_neighbors]

    results: list[ScoredFinding] = []
    for data in sorted_neighbors:
        finding = data["finding"]
        age = _age_in_days(finding.created_at)
        results.append(
            ScoredFinding(
                finding=finding,
                semantic_similarity=0.0,
                age_days=age,
                recency_score=math.exp(-0.693 * age / 14.0),
                combined_score=data["graph_score"],
                query_variant=f"graph:{data['rel_type']}",
            )
        )
    return results


def retrieve_findings(
    conn: Connection,
    topic: str,
    top_k: int = 10,
    min_confidence: float = 0.45,
    root_anxiety_filter: str | None = None,
    brand: str | None = None,
    enable_graph_expansion: bool = True,
) -> list[ScoredFinding]:
    """Retrieve findings using multi-query semantic expansion + graph expansion.

    1. Generate 3 query variants from the topic
    2. Retrieve top-k findings for each variant via semantic similarity
    3. Deduplicate by finding ID (keep highest similarity)
    4. Apply decay-weighted scoring
    5. Expand via finding_relationships graph — pull in neighbors of the top
       semantic results via typed edges, weighted by relationship type
    6. Optionally filter by root anxiety tag
    7. Return ranked by combined score

    Args:
        conn: Database connection.
        topic: Topic keywords or description.
        top_k: Number of findings to return per query variant.
        min_confidence: Minimum confidence score filter.
        root_anxiety_filter: Optional root anxiety to filter by.
        brand: Brand name for telemetry logging.
        enable_graph_expansion: If True (default), augment semantic results
            with findings reachable via relationship edges. Set False to
            disable for benchmarks or to compare semantic-only performance.

    Returns:
        Ranked list of ScoredFinding objects.
    """
    from uuid import uuid4
    import time
    from src.kb.telemetry import log_query, compute_relationship_types_present

    # Step 1: Generate query variants
    variants = generate_query_variants(topic)

    # Session groups all three query variants
    session_id = uuid4()

    # Step 2: Retrieve for each variant
    all_results: dict[str, tuple[Finding, float, str]] = {}  # id -> (finding, best_sim, variant)

    for variant in variants:
        t0 = time.perf_counter()
        hits, variant_embedding = _retrieve_for_query(
            conn, variant, top_k=top_k, min_confidence=min_confidence
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        variant_finding_ids = [str(f.id) for f, _ in hits]
        variant_scores = [sim for _, sim in hits]

        log_query(
            conn,
            query_text=variant,
            query_embedding=variant_embedding,
            pipeline_source="content_pipeline",
            finding_ids_returned=variant_finding_ids,
            similarity_scores=variant_scores,
            relationship_types_present=compute_relationship_types_present(conn, variant_finding_ids),
            min_confidence=min_confidence,
            status_filter="active",
            root_anxiety_filter=[root_anxiety_filter] if root_anxiety_filter else None,
            session_id=session_id,
            brand=brand,
            duration_ms=elapsed_ms,
        )

        for finding, similarity in hits:
            fid = str(finding.id)
            if fid not in all_results or similarity > all_results[fid][1]:
                all_results[fid] = (finding, similarity, variant)

    # Step 3: Apply root anxiety filter if provided
    if root_anxiety_filter:
        all_results = {
            fid: (f, sim, var)
            for fid, (f, sim, var) in all_results.items()
            if any(a.value == root_anxiety_filter for a in f.root_anxieties)
        }

    # Step 4: Compute decay-weighted scores for semantic results
    scored: list[ScoredFinding] = []
    for fid, (finding, similarity, variant) in all_results.items():
        age = _age_in_days(finding.created_at)
        recency = math.exp(-0.693 * age / 14.0)
        combined = _compute_decay_weighted_score(similarity, age)

        scored.append(
            ScoredFinding(
                finding=finding,
                semantic_similarity=similarity,
                age_days=age,
                recency_score=recency,
                combined_score=combined,
                query_variant=variant,
            )
        )

    # Step 4.5: Sort semantic results before using them as graph seeds
    scored.sort(key=lambda s: s.combined_score, reverse=True)

    # Step 5: Graph expansion — walk finding_relationships from the top seeds
    # and add neighbors that weren't already retrieved semantically. This is
    # the cross-domain retrieval moat: findings that share a structural edge
    # but not lexical similarity now surface together.
    if enable_graph_expansion and scored:
        try:
            graph_neighbors = _expand_via_relationships(
                conn, seed_findings=scored, max_seeds=5, max_neighbors=6
            )
        except Exception as e:
            import structlog
            structlog.get_logger().warning(
                "retriever.graph_expansion_failed",
                error=str(e),
                note="falling back to semantic-only results",
            )
            graph_neighbors = []

        existing_ids = {str(sf.finding.id) for sf in scored}
        for neighbor in graph_neighbors:
            nid = str(neighbor.finding.id)
            if nid not in existing_ids:
                # Apply root anxiety filter to graph neighbors too
                if root_anxiety_filter:
                    if not any(a.value == root_anxiety_filter for a in neighbor.finding.root_anxieties):
                        continue
                scored.append(neighbor)
                existing_ids.add(nid)

    # Step 6: Sort by combined score descending (may have changed after graph merge)
    scored.sort(key=lambda s: s.combined_score, reverse=True)

    return scored
