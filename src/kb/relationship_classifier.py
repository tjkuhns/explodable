"""Relationship classification: find and classify relationships for newly-ingested findings.

For each new finding, retrieves the N nearest neighbors by cosine similarity and uses
an LLM classifier to determine the relationship type, confidence, and rationale.

Auto-commits relationships above the confidence floor; queues the rest for review.

Cost optimization (Phase 1):
- Prompt caching: the ~2000-token system prompt is identical on every call, so it's
  sent as a cached ephemeral block. Cache hits cost 10% of the normal rate, writes
  cost 125%. Break-even at the 2nd-3rd call. Default 5-minute TTL. Roughly 52%
  reduction in per-call cost with zero accuracy or coverage tradeoff.

Why no pre-filter on low-similarity cross-discipline pairs: empirically, 42 of
480 existing relationships (8.8%) came from pairs at similarity < 0.45 with
different academic disciplines. Sample inspection shows these are exactly the
"I wouldn't have thought of that" cross-domain links the anxiety-graph architecture
exists to surface (e.g., existential psych → social neuroscience, buyer psych →
evolutionary psych). Dropping them to save API calls is a value-destroying
optimization disguised as a cost optimization.
"""

import json
import os
from pathlib import Path
from uuid import UUID

from anthropic import Anthropic
from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from src.kb.crud import KBStore
from src.kb.models import FindingRelationshipCreate, RelationshipType


# Load system prompt from config (single source of truth)
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "relationship_classification_prompt.txt"

# Runtime configuration
AUTO_COMMIT_FLOOR = 0.70
QUEUE_FLOOR = 0.50
NEIGHBOR_COUNT = 20
SIMILARITY_FLOOR = 0.40
QUEUE_FILE = Path("/home/thoma/explodable/logs/relationship_review_queue.json")


class ClassificationResult(BaseModel):
    """LLM relationship classification output.

    All fields optional/nullable because the LLM may return `null` for
    a_element / b_element / direction_check when it decides to skip a pair
    without populating supporting context. Prior to 2026-04-14 these were
    non-Optional `str` fields, which caused Pydantic validation failures
    on ~13% of classification calls during the gambling batch approval
    (83 of 640 attempted). Making them nullable recovers those calls and
    lets the downstream caller handle the skip path explicitly.
    """

    relationship_type: str | None = None
    confidence: float | None = None
    rationale: str = ""
    a_element: str | None = None
    b_element: str | None = None
    direction_check: str | None = "correct"
    skip: bool = False


class NeighborPair(BaseModel):
    orphan_id: str
    neighbor_id: str
    similarity: float
    orphan_claim: str
    orphan_elaboration: str
    orphan_discipline: str
    orphan_anxieties: list[str]
    neighbor_claim: str
    neighbor_elaboration: str
    neighbor_discipline: str
    neighbor_anxieties: list[str]


def _load_prompt() -> str:
    with open(_PROMPT_PATH) as f:
        return f.read()


def _get_neighbors(conn: Connection, finding_id: UUID) -> list[NeighborPair]:
    """Retrieve nearest neighbors for a finding by cosine similarity."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT
                f2.id, f2.claim, f2.elaboration, f2.academic_discipline, f2.root_anxieties,
                1 - (f1.embedding <=> f2.embedding) AS similarity,
                f1.claim AS orphan_claim, f1.elaboration AS orphan_elaboration,
                f1.academic_discipline AS orphan_discipline, f1.root_anxieties AS orphan_anxieties
            FROM findings f1, findings f2
            WHERE f1.id = %s AND f2.id != f1.id
            AND f2.embedding IS NOT NULL AND f2.status = 'active'
            AND f1.embedding IS NOT NULL
            AND 1 - (f1.embedding <=> f2.embedding) > %s
            ORDER BY f1.embedding <=> f2.embedding
            LIMIT %s
        """, (str(finding_id), SIMILARITY_FLOOR, NEIGHBOR_COUNT))
        rows = cur.fetchall()

    return [
        NeighborPair(
            orphan_id=str(finding_id),
            neighbor_id=str(r["id"]),
            similarity=float(r["similarity"]),
            orphan_claim=r["orphan_claim"],
            orphan_elaboration=r["orphan_elaboration"][:500],
            orphan_discipline=r["orphan_discipline"],
            orphan_anxieties=r["orphan_anxieties"] if isinstance(r["orphan_anxieties"], list) else [],
            neighbor_claim=r["claim"],
            neighbor_elaboration=r["elaboration"][:500],
            neighbor_discipline=r["academic_discipline"],
            neighbor_anxieties=r["root_anxieties"] if isinstance(r["root_anxieties"], list) else [],
        )
        for r in rows
    ]


def _classify_pair(client: Anthropic, system_prompt: str, pair: NeighborPair) -> ClassificationResult | None:
    """Classify a single orphan-neighbor pair via the LLM.

    Uses prompt caching on the system prompt (ephemeral, 5-minute TTL). Cache
    hits cost 10% of normal input rate; the first call in a cache window
    pays a 25% write premium, so caching breaks even at ~2-3 calls and
    compounds from there.
    """
    user_msg = (
        f"Finding A:\n"
        f"Claim: {pair.orphan_claim}\n"
        f"Elaboration: {pair.orphan_elaboration}\n"
        f"Academic discipline: {pair.orphan_discipline}\n"
        f"Root anxieties: {pair.orphan_anxieties}\n\n"
        f"Finding B:\n"
        f"Claim: {pair.neighbor_claim}\n"
        f"Elaboration: {pair.neighbor_elaboration}\n"
        f"Academic discipline: {pair.neighbor_discipline}\n"
        f"Root anxieties: {pair.neighbor_anxieties}"
    )

    try:
        resp = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=1024,
            # System prompt sent as a content block with cache_control so
            # Anthropic caches it across subsequent calls in the same
            # 5-minute window. On cache hit, the ~2000-token system prompt
            # costs ~10% of the normal input rate.
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text.strip()
        # Strip any markdown code fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        # Empty or non-JSON response → treat as skip, not error. The LLM
        # sometimes returns empty output when it's confused about a pair;
        # we don't want that to blow up as a validation exception.
        if not text:
            return ClassificationResult(skip=True, rationale="empty LLM response")

        data = json.loads(text)
        return ClassificationResult(**data)
    except json.JSONDecodeError as e:
        import structlog
        structlog.get_logger().warning(
            "relationship_classification.json_parse_failed",
            error=str(e),
            pair=pair.neighbor_id,
            preview=text[:200] if 'text' in dir() else None,
        )
        return ClassificationResult(skip=True, rationale=f"JSON parse failed: {e}")
    except Exception as e:
        import structlog
        structlog.get_logger().warning("relationship_classification.failed", error=str(e), pair=pair.neighbor_id)
        return None


def _validate_finding_ids(conn: Connection, from_id: str, to_id: str) -> bool:
    """Verify both finding IDs exist before attempting insert."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM findings WHERE id = ANY(%s::uuid[])",
            ([from_id, to_id],),
        )
        return cur.fetchone()[0] == 2


def _append_to_queue(items: list[dict]) -> None:
    """Append below-threshold results to the review queue file."""
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE) as f:
            existing = json.load(f)
    existing.extend(items)
    with open(QUEUE_FILE, "w") as f:
        json.dump(existing, f, indent=2)


def classify_and_commit(
    conn: Connection,
    finding_id: UUID,
    *,
    auto_commit_floor: float = AUTO_COMMIT_FLOOR,
    queue_floor: float = QUEUE_FLOOR,
) -> dict:
    """Classify relationships for a newly-ingested finding against its nearest neighbors.

    Returns:
        dict with counts: {committed, queued, skipped, fk_errors}
    """
    import structlog
    log = structlog.get_logger()

    neighbors = _get_neighbors(conn, finding_id)
    if not neighbors:
        log.info("relationship_classification.no_neighbors", finding_id=str(finding_id))
        return {"committed": 0, "queued": 0, "skipped": 0, "fk_errors": 0}

    system_prompt = _load_prompt()
    # max_retries=5: relationship classification fires up to 20 LLM calls per
    # approved finding (one per nearest neighbor), so 529 tolerance matters a
    # lot. Exponential backoff: 1s, 2s, 4s, 8s, 16s.
    client = Anthropic(max_retries=5)
    store = KBStore(conn)

    committed = 0
    queued_items: list[dict] = []
    skipped = 0
    fk_errors = 0

    for pair in neighbors:
        result = _classify_pair(client, system_prompt, pair)
        if result is None:
            skipped += 1
            continue

        if result.skip or result.relationship_type is None:
            skipped += 1
            continue

        if result.confidence is None or result.confidence < queue_floor:
            skipped += 1
            continue

        # FK validation before attempting insert
        if not _validate_finding_ids(conn, pair.orphan_id, pair.neighbor_id):
            fk_errors += 1
            log.warning("relationship_classification.fk_invalid",
                        from_id=pair.orphan_id, to_id=pair.neighbor_id)
            continue

        # Determine actual from/to based on direction check
        if result.direction_check == "reversed":
            from_id = UUID(pair.neighbor_id)
            to_id = UUID(pair.orphan_id)
        else:
            from_id = UUID(pair.orphan_id)
            to_id = UUID(pair.neighbor_id)

        if result.confidence >= auto_commit_floor:
            try:
                store.create_relationship(FindingRelationshipCreate(
                    from_finding_id=from_id,
                    to_finding_id=to_id,
                    relationship=RelationshipType(result.relationship_type),
                    rationale=result.rationale,
                    confidence=result.confidence,
                ))
                conn.commit()
                committed += 1
            except Exception as e:
                conn.rollback()
                if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                    pass  # Already exists
                else:
                    log.warning("relationship_classification.commit_failed", error=str(e))
                    skipped += 1
        else:
            queued_items.append({
                "orphan_id": str(from_id),
                "neighbor_id": str(to_id),
                "relationship_type": result.relationship_type,
                "confidence": result.confidence,
                "rationale": result.rationale,
                "a_element": result.a_element,
                "b_element": result.b_element,
                "direction_check": result.direction_check,
            })

    if queued_items:
        _append_to_queue(queued_items)

    log.info(
        "relationship_classification.complete",
        finding_id=str(finding_id),
        committed=committed,
        queued=len(queued_items),
        skipped=skipped,
        fk_errors=fk_errors,
    )

    return {
        "committed": committed,
        "queued": len(queued_items),
        "skipped": skipped,
        "fk_errors": fk_errors,
    }
