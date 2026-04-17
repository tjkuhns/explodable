"""Deduplication checks — mandatory order: SHA-256 → MinHash LSH → cosine similarity.

All three must run before any new finding is written. Short-circuit on first match.

Two cosine thresholds serve different purposes:
- COSINE_DEDUP_THRESHOLD (0.90): Used at write time to reject semantic duplicates.
- COSINE_DISCOVERY_THRESHOLD (0.85): Used at retrieval/presentation time to surface related findings.
"""

from uuid import UUID

from datasketch import MinHash, MinHashLSH
from psycopg import Connection
from psycopg.rows import dict_row

from src.kb.embeddings import generate_embedding
from src.kb.models import Finding
from src.shared.constants import NUM_PERM, LSH_THRESHOLD, COSINE_DEDUP_THRESHOLD, COSINE_DISCOVERY_THRESHOLD


# MinHash LSH index — rebuilt on startup, updated on each insert
_lsh: MinHashLSH | None = None
_minhashes: dict[str, MinHash] = {}


def _text_to_minhash(text: str) -> MinHash:
    """Create a MinHash from text using word-level shingles."""
    m = MinHash(num_perm=NUM_PERM)
    words = text.lower().split()
    for i in range(len(words) - 2):
        shingle = " ".join(words[i : i + 3])
        m.update(shingle.encode("utf-8"))
    return m


def init_lsh(conn: Connection) -> None:
    """Initialize the MinHash LSH index from existing findings."""
    global _lsh, _minhashes
    _lsh = MinHashLSH(threshold=LSH_THRESHOLD, num_perm=NUM_PERM)
    _minhashes = {}

    with conn.cursor() as cur:
        cur.execute("SELECT id, claim FROM findings")
        for row in cur.fetchall():
            finding_id = str(row[0])
            claim = row[1]
            m = _text_to_minhash(claim)
            _lsh.insert(finding_id, m)
            _minhashes[finding_id] = m


def _ensure_lsh(conn: Connection) -> MinHashLSH:
    global _lsh
    if _lsh is None:
        init_lsh(conn)
    return _lsh


def register_in_lsh(finding_id: UUID, claim: str) -> None:
    """Register a newly written finding in the LSH index."""
    if _lsh is None:
        return
    key = str(finding_id)
    if key not in _minhashes:
        m = _text_to_minhash(claim)
        _lsh.insert(key, m)
        _minhashes[key] = m


def check_sha256_duplicate(conn: Connection, claim: str) -> Finding | None:
    """Step 1: Check for exact duplicate via SHA-256 hash (generated column in DB)."""
    import hashlib

    claim_hash = hashlib.sha256(claim.encode("utf-8")).hexdigest()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM findings WHERE claim_hash = %s", (claim_hash,))
        row = cur.fetchone()
        if row:
            return Finding(**row)
    return None


def check_minhash_duplicate(
    conn: Connection, claim: str
) -> list[Finding]:
    """Step 2: Check for near-duplicate via MinHash LSH."""
    lsh = _ensure_lsh(conn)
    m = _text_to_minhash(claim)
    candidate_ids = lsh.query(m)
    if not candidate_ids:
        return []

    results = []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM findings WHERE id = ANY(%s)",
            ([UUID(fid) for fid in candidate_ids],),
        )
        for row in cur.fetchall():
            results.append(Finding(**row))
    return results


def cosine_dedup_check(
    conn: Connection,
    claim: str,
    threshold: float = COSINE_DEDUP_THRESHOLD,
    limit: int = 5,
    embedding: list[float] | None = None,
) -> list[Finding]:
    """Check for semantic duplicates via pgvector cosine similarity at WRITE time.

    Uses the strict 0.90 threshold. Called before any new finding is created.
    Findings above this threshold are rejected as duplicates.

    If ``embedding`` is provided, it is used directly instead of calling the
    embedding API — this avoids a redundant API call when the caller already
    has the vector.
    """
    if embedding is None:
        embedding = generate_embedding(claim)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT *, 1 - (embedding <=> %s::vector) AS similarity
            FROM findings
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (embedding, embedding, limit),
        )
        results = []
        for row in cur.fetchall():
            similarity = row.pop("similarity")
            if similarity >= threshold:
                results.append(Finding(**row))
        return results


def cosine_discovery_check(
    conn: Connection,
    claim: str,
    threshold: float = COSINE_DISCOVERY_THRESHOLD,
    limit: int = 5,
) -> list[Finding]:
    """Find semantically related findings via pgvector cosine similarity at RETRIEVAL time.

    Uses the looser 0.85 threshold. For surfacing related findings in the UI,
    synthesizer KB checks, and discovery workflows — NOT for dedup gating.
    """
    embedding = generate_embedding(claim)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT *, 1 - (embedding <=> %s::vector) AS similarity
            FROM findings
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (embedding, embedding, limit),
        )
        results = []
        for row in cur.fetchall():
            similarity = row.pop("similarity")
            if similarity >= threshold:
                results.append(Finding(**row))
        return results


def check_duplicate_finding(
    conn: Connection,
    claim: str,
    embedding: list[float] | None = None,
) -> tuple[str | None, Finding | list[Finding] | None]:
    """Run the full three-stage dedup check. Short-circuits on first match.

    Uses the strict COSINE_DEDUP_THRESHOLD (0.90) for the semantic check.

    If ``embedding`` is provided, it is forwarded to the cosine check to avoid
    a redundant embedding API call.

    Returns:
        (match_type, matches) where match_type is 'exact', 'near', 'semantic', or None.
    """
    # Step 1: SHA-256 exact match
    exact = check_sha256_duplicate(conn, claim)
    if exact:
        return ("exact", exact)

    # Step 2: MinHash near-duplicate
    near = check_minhash_duplicate(conn, claim)
    if near:
        return ("near", near)

    # Step 3: Cosine similarity (strict dedup threshold)
    semantic = cosine_dedup_check(conn, claim, embedding=embedding)
    if semantic:
        return ("semantic", semantic)

    return (None, None)


