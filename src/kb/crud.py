"""CRUD operations for all five KB entity types."""

from datetime import datetime
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from src.kb.connection import get_connection
from src.kb.embeddings import generate_embedding
from src.kb.dedup import check_duplicate_finding, register_in_lsh
from src.kb.models import (
    Finding,
    FindingCreate,
    FindingUpdate,
    FindingStatus,
    Manifestation,
    ManifestationCreate,
    FindingRelationship,
    FindingRelationshipCreate,
    ContradictionRecord,
    ContradictionRecordCreate,
    ContradictionResolution,
    RootAnxietyNode,
    AnxietyCircuitAffinity,
)


class KBStore:
    """Knowledge base storage — CRUD for all five entity types."""

    def __init__(self, conn: Connection):
        self.conn = conn

    # ── Root Anxiety Nodes (read-only — seeded by schema) ──

    def list_root_anxieties(self) -> list[RootAnxietyNode]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM root_anxiety_nodes ORDER BY anxiety")
            return [RootAnxietyNode(**row) for row in cur.fetchall()]

    def get_root_anxiety(self, anxiety: str) -> RootAnxietyNode | None:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM root_anxiety_nodes WHERE anxiety = %s", (anxiety,)
            )
            row = cur.fetchone()
            return RootAnxietyNode(**row) if row else None

    def list_circuit_affinities(
        self, anxiety: str | None = None
    ) -> list[AnxietyCircuitAffinity]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            if anxiety:
                cur.execute(
                    "SELECT * FROM anxiety_circuit_affinities WHERE anxiety = %s",
                    (anxiety,),
                )
            else:
                cur.execute("SELECT * FROM anxiety_circuit_affinities")
            return [AnxietyCircuitAffinity(**row) for row in cur.fetchall()]

    # ── Findings ──

    def create_finding(
        self, data: FindingCreate, skip_dedup: bool = False
    ) -> Finding:
        """Create a new finding with embedding and dedup checks.

        Dedup order (per spec): SHA-256 → MinHash → cosine >0.90.
        Raises ValueError if duplicate found (unless skip_dedup=True).
        """
        # Generate embedding if not provided
        if data.embedding is None:
            data.embedding = generate_embedding(data.claim)

        # Run dedup checks (pass pre-computed embedding to avoid redundant API call)
        if not skip_dedup:
            match_type, matches = check_duplicate_finding(
                self.conn, data.claim, embedding=data.embedding
            )
            if match_type == "exact":
                raise ValueError(
                    f"Exact duplicate found (SHA-256 match): {matches.id}"
                )
            if match_type in ("near", "semantic"):
                match_list = matches if isinstance(matches, list) else [matches]
                ids = [str(m.id) for m in match_list]
                raise ValueError(
                    f"Duplicate found ({match_type} match): {', '.join(ids)}"
                )

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO findings (
                    claim, elaboration, root_anxieties, primary_circuits,
                    confidence_score, confidence_basis, provenance,
                    academic_discipline, cultural_domains, era, source_document,
                    status, embedding
                ) VALUES (
                    %(claim)s, %(elaboration)s, %(root_anxieties)s, %(primary_circuits)s,
                    %(confidence_score)s, %(confidence_basis)s, %(provenance)s,
                    %(academic_discipline)s, %(cultural_domains)s, %(era)s,
                    %(source_document)s, %(status)s, %(embedding)s
                )
                RETURNING *
                """,
                {
                    "claim": data.claim,
                    "elaboration": data.elaboration,
                    "root_anxieties": [a.value for a in data.root_anxieties],
                    "primary_circuits": (
                        [c.value for c in data.primary_circuits]
                        if data.primary_circuits
                        else None
                    ),
                    "confidence_score": data.confidence_score,
                    "confidence_basis": data.confidence_basis,
                    "provenance": data.provenance.value,
                    "academic_discipline": data.academic_discipline,
                    "cultural_domains": data.cultural_domains,
                    "era": data.era,
                    "source_document": data.source_document,
                    "status": data.status.value,
                    "embedding": data.embedding,
                },
            )
            row = cur.fetchone()
            self.conn.commit()

        finding = Finding(**row)
        register_in_lsh(finding.id, finding.claim)
        return finding

    def get_finding(self, finding_id: UUID) -> Finding | None:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM findings WHERE id = %s", (finding_id,))
            row = cur.fetchone()
            return Finding(**row) if row else None

    def list_findings(
        self,
        status: FindingStatus | None = None,
        academic_discipline: str | None = None,
        root_anxiety: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Finding]:
        conditions = []
        params: dict = {"limit": limit, "offset": offset}

        if status:
            conditions.append("status = %(status)s")
            params["status"] = status.value
        if academic_discipline:
            conditions.append("academic_discipline = %(academic_discipline)s")
            params["academic_discipline"] = academic_discipline
        if root_anxiety:
            conditions.append("%(root_anxiety)s = ANY(root_anxieties)")
            params["root_anxiety"] = root_anxiety

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT * FROM findings {where}
                ORDER BY updated_at DESC
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                params,
            )
            return [Finding(**row) for row in cur.fetchall()]

    def update_finding(self, finding_id: UUID, data: FindingUpdate) -> Finding | None:
        updates = data.model_dump(exclude_none=True)
        if not updates:
            return self.get_finding(finding_id)

        # Re-generate embedding if claim changed
        if "claim" in updates and "embedding" not in updates:
            updates["embedding"] = generate_embedding(updates["claim"])

        # Convert enums to values for DB
        if "root_anxieties" in updates:
            updates["root_anxieties"] = [a.value for a in updates["root_anxieties"]]
        if "primary_circuits" in updates:
            updates["primary_circuits"] = [c.value for c in updates["primary_circuits"]]
        if "status" in updates:
            updates["status"] = updates["status"].value

        set_clauses = [f"{key} = %({key})s" for key in updates]
        updates["id"] = finding_id

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                UPDATE findings SET {', '.join(set_clauses)}
                WHERE id = %(id)s
                RETURNING *
                """,
                updates,
            )
            row = cur.fetchone()
            self.conn.commit()
            return Finding(**row) if row else None

    def approve_finding(self, finding_id: UUID) -> Finding | None:
        """Approve a proposed finding — sets status to active and records approval time."""
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE findings
                SET status = 'active', approved_at = NOW()
                WHERE id = %s AND status = 'proposed'
                RETURNING *
                """,
                (finding_id,),
            )
            row = cur.fetchone()
            self.conn.commit()
            return Finding(**row) if row else None

    def reject_finding(self, finding_id: UUID) -> Finding | None:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE findings SET status = 'rejected'
                WHERE id = %s AND status = 'proposed'
                RETURNING *
                """,
                (finding_id,),
            )
            row = cur.fetchone()
            self.conn.commit()
            return Finding(**row) if row else None

    # ── Manifestations ──

    def create_manifestation(
        self, data: ManifestationCreate, finding_ids: list[UUID] | None = None
    ) -> Manifestation:
        import hashlib
        import structlog
        from psycopg.errors import UniqueViolation

        if data.embedding is None:
            data.embedding = generate_embedding(data.description)

        try:
            with self.conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO manifestations (
                        description, academic_discipline, era, source, source_type,
                        source_url, source_date, embedding
                    ) VALUES (
                        %(description)s, %(academic_discipline)s, %(era)s, %(source)s, %(source_type)s,
                        %(source_url)s, %(source_date)s, %(embedding)s
                    )
                    RETURNING *
                    """,
                    {
                        "description": data.description,
                        "academic_discipline": data.academic_discipline,
                        "era": data.era,
                        "source": data.source,
                        "source_type": data.source_type.value,
                        "source_url": data.source_url,
                        "source_date": data.source_date,
                        "embedding": data.embedding,
                    },
                )
                row = cur.fetchone()

                # Link to findings if provided
                if finding_ids:
                    for fid in finding_ids:
                        cur.execute(
                            """
                            INSERT INTO finding_manifestations (finding_id, manifestation_id)
                            VALUES (%s, %s) ON CONFLICT DO NOTHING
                            """,
                            (fid, row["id"]),
                        )

                self.conn.commit()
            return Manifestation(**row)

        except UniqueViolation:
            self.conn.rollback()
            # Duplicate description — look up existing manifestation by hash
            desc_hash = hashlib.sha256(data.description.encode("utf-8")).hexdigest()
            structlog.get_logger().debug(
                "manifestation.dedup_collision",
                description_hash=desc_hash,
                source=data.source[:80],
            )
            with self.conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM manifestations WHERE description_hash = %s",
                    (desc_hash,),
                )
                row = cur.fetchone()

                # Still link the existing manifestation to the new finding(s)
                if finding_ids and row:
                    for fid in finding_ids:
                        cur.execute(
                            """
                            INSERT INTO finding_manifestations (finding_id, manifestation_id)
                            VALUES (%s, %s) ON CONFLICT DO NOTHING
                            """,
                            (fid, row["id"]),
                        )
                    self.conn.commit()

            return Manifestation(**row)

    def get_manifestation(self, manifestation_id: UUID) -> Manifestation | None:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM manifestations WHERE id = %s", (manifestation_id,)
            )
            row = cur.fetchone()
            return Manifestation(**row) if row else None

    def list_manifestations_for_finding(
        self, finding_id: UUID
    ) -> list[Manifestation]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT m.* FROM manifestations m
                JOIN finding_manifestations fm ON fm.manifestation_id = m.id
                WHERE fm.finding_id = %s
                ORDER BY m.created_at DESC
                """,
                (finding_id,),
            )
            return [Manifestation(**row) for row in cur.fetchall()]

    def link_finding_manifestation(
        self, finding_id: UUID, manifestation_id: UUID
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO finding_manifestations (finding_id, manifestation_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (finding_id, manifestation_id),
            )
            self.conn.commit()

    # ── Finding Relationships ──

    def create_relationship(
        self, data: FindingRelationshipCreate
    ) -> FindingRelationship:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO finding_relationships (
                    from_finding_id, to_finding_id, relationship, rationale, confidence
                ) VALUES (
                    %(from_finding_id)s, %(to_finding_id)s, %(relationship)s,
                    %(rationale)s, %(confidence)s
                )
                RETURNING *
                """,
                {
                    "from_finding_id": data.from_finding_id,
                    "to_finding_id": data.to_finding_id,
                    "relationship": data.relationship.value,
                    "rationale": data.rationale,
                    "confidence": data.confidence,
                },
            )
            row = cur.fetchone()
            self.conn.commit()
        return FindingRelationship(**row)

    def list_relationships_for_finding(
        self, finding_id: UUID, direction: str = "both"
    ) -> list[FindingRelationship]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            if direction == "outbound":
                cur.execute(
                    "SELECT * FROM finding_relationships WHERE from_finding_id = %s",
                    (finding_id,),
                )
            elif direction == "inbound":
                cur.execute(
                    "SELECT * FROM finding_relationships WHERE to_finding_id = %s",
                    (finding_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM finding_relationships
                    WHERE from_finding_id = %s OR to_finding_id = %s
                    """,
                    (finding_id, finding_id),
                )
            return [FindingRelationship(**row) for row in cur.fetchall()]

    # ── Contradiction Records ──

    def create_contradiction(
        self, data: ContradictionRecordCreate
    ) -> ContradictionRecord:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO contradiction_records (
                    finding_a_id, finding_b_id, description,
                    resolution, resolution_notes, merged_finding_id
                ) VALUES (
                    %(finding_a_id)s, %(finding_b_id)s, %(description)s,
                    %(resolution)s, %(resolution_notes)s, %(merged_finding_id)s
                )
                RETURNING *
                """,
                {
                    "finding_a_id": data.finding_a_id,
                    "finding_b_id": data.finding_b_id,
                    "description": data.description,
                    "resolution": data.resolution.value,
                    "resolution_notes": data.resolution_notes,
                    "merged_finding_id": data.merged_finding_id,
                },
            )
            row = cur.fetchone()
            self.conn.commit()
        return ContradictionRecord(**row)

    def resolve_contradiction(
        self,
        contradiction_id: UUID,
        resolution: ContradictionResolution,
        resolution_notes: str,
        merged_finding_id: UUID | None = None,
    ) -> ContradictionRecord | None:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE contradiction_records
                SET resolution = %(resolution)s,
                    resolution_notes = %(resolution_notes)s,
                    merged_finding_id = %(merged_finding_id)s,
                    resolved_at = NOW()
                WHERE id = %(id)s
                RETURNING *
                """,
                {
                    "id": contradiction_id,
                    "resolution": resolution.value,
                    "resolution_notes": resolution_notes,
                    "merged_finding_id": merged_finding_id,
                },
            )
            row = cur.fetchone()
            self.conn.commit()
            return ContradictionRecord(**row) if row else None

    def list_unresolved_contradictions(self) -> list[ContradictionRecord]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM contradiction_records
                WHERE resolution = 'unresolved'
                ORDER BY created_at DESC
                """
            )
            return [ContradictionRecord(**row) for row in cur.fetchall()]

    # ── Semantic Search ──

    def semantic_search(
        self,
        query: str,
        limit: int = 10,
        status_filter: FindingStatus | None = FindingStatus.ACTIVE,
        min_confidence: float = 0.45,
        pipeline_source: str = "manual",
        session_id: str | None = None,
    ) -> list[tuple[Finding, float]]:
        """Search findings by semantic similarity. Returns (finding, similarity_score) pairs."""
        import time
        from src.kb.telemetry import log_query, compute_relationship_types_present

        t0 = time.perf_counter()
        embedding = generate_embedding(query)
        conditions = ["embedding IS NOT NULL"]
        params: dict = {
            "embedding": embedding,
            "limit": limit,
        }

        if status_filter:
            conditions.append("status = %(status)s")
            params["status"] = status_filter.value
        if min_confidence > 0:
            conditions.append("confidence_score >= %(min_confidence)s")
            params["min_confidence"] = min_confidence

        where = "WHERE " + " AND ".join(conditions)

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT *, 1 - (embedding <=> %(embedding)s::vector) AS similarity
                FROM findings {where}
                ORDER BY embedding <=> %(embedding)s::vector
                LIMIT %(limit)s
                """,
                params,
            )
            results = []
            for row in cur.fetchall():
                similarity = row.pop("similarity")
                results.append((Finding(**row), similarity))

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        result_ids = [str(f.id) for f, _ in results]
        log_query(
            self.conn,
            query_text=query,
            query_embedding=embedding,
            pipeline_source=pipeline_source,
            finding_ids_returned=result_ids,
            similarity_scores=[s for _, s in results],
            relationship_types_present=compute_relationship_types_present(self.conn, result_ids),
            status_filter=status_filter.value if status_filter else None,
            min_confidence=min_confidence if min_confidence > 0 else None,
            session_id=session_id,
            duration_ms=elapsed_ms,
        )
        return results

    # ── Graph Data ──

    def get_graph_data(
        self, root_anxiety: str | None = None
    ) -> dict:
        """Get findings and relationships as graph nodes and edges for Cytoscape.js."""
        findings = self.list_findings(
            status=FindingStatus.ACTIVE,
            root_anxiety=root_anxiety,
            limit=500,
        )
        finding_ids = [f.id for f in findings]

        edges = []
        if finding_ids:
            with self.conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM finding_relationships
                    WHERE from_finding_id = ANY(%s) OR to_finding_id = ANY(%s)
                    """,
                    (finding_ids, finding_ids),
                )
                edges = [FindingRelationship(**row) for row in cur.fetchall()]

        return {"findings": findings, "relationships": edges}
