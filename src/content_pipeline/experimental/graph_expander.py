"""Graph expansion via Personalized PageRank + MMR diversity reranking.

Given a set of already-selected finding IDs, traverses the KB relationship
graph to discover additional findings in different cultural domains that share
underlying anxiety architecture. Uses PPR seeded on the selection set to rank
by graph proximity, then applies Maximal Marginal Relevance to maximize domain
diversity in the expanded set.

Design decisions (grounded in docs/research/hybrid_reports/01_graphrag.md):

* PPR is "the current optimal solution for structure-based extraction" (LEGO-
  GraphRAG, VLDB 2025). Runs on an undirected version of the graph because
  "related to" is symmetric even when "supports" is directional.

* Edge weights by relationship type:
  - supports (1.0), extends (1.0): core traversal edges
  - reframes (0.8): related but different angle
  - qualifies (0.5): limits/nuances — less useful for expansion
  - subsumes (0.3): containment — lower discovery value
  - contradicts (0.0): excluded from expansion; routed to adversarial critic

* MMR diversity uses Jaccard distance on cultural_domains arrays — directly
  measures what we care about (domain spread) without needing embeddings.

* Max expansion: adds at most `max_expand` findings (default 5) on top of
  the existing selection. Keeps total context focused.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import igraph as ig
import psycopg
from dotenv import load_dotenv


EDGE_WEIGHTS: dict[str, float] = {
    "supports": 1.0,
    "extends": 1.0,
    "reframes": 0.8,
    "qualifies": 0.5,
    "subsumes": 0.3,
    "contradicts": 0.0,
}

DEFAULT_DAMPING = 0.85
DEFAULT_MAX_EXPAND = 5
DEFAULT_MMR_LAMBDA = 0.5  # balance between PPR relevance and domain diversity


@dataclass(frozen=True)
class ExpandedFinding:
    finding_id: str
    ppr_score: float
    mmr_score: float
    domains: list[str]
    source: str  # "selected" or "expanded"


def _get_db_url() -> str:
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    db_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    if "${POSTGRES_PASSWORD}" in db_url:
        db_url = db_url.replace("${POSTGRES_PASSWORD}", os.environ["POSTGRES_PASSWORD"])
    return db_url


class KBGraph:
    """In-memory graph of the KB findings and their relationships.

    Loaded once at startup, reused across pipeline calls. Rebuild when KB
    changes (CQRS Stage 4 will automate this).
    """

    def __init__(self) -> None:
        self.graph: ig.Graph | None = None
        self.uuid_to_vid: dict[str, int] = {}
        self.vid_to_uuid: dict[int, str] = {}
        self.finding_domains: dict[str, list[str]] = {}
        self.finding_anxieties: dict[str, list[str]] = {}
        self.contradictions: list[tuple[str, str, str]] = []
        self._loaded = False

    def load(self) -> None:
        db_url = _get_db_url()
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, COALESCE(cultural_domains, '{}')::text[],
                           root_anxieties::text[]
                    FROM findings WHERE status = 'active'
                    """
                )
                findings = cur.fetchall()

                cur.execute(
                    """
                    SELECT from_finding_id::text, to_finding_id::text,
                           relationship::text, confidence
                    FROM finding_relationships
                    """
                )
                edges = cur.fetchall()

        # Build igraph undirected graph with edge weights
        g = ig.Graph(directed=False)

        for i, (fid, domains, anxieties) in enumerate(findings):
            g.add_vertex(name=fid)
            self.uuid_to_vid[fid] = i
            self.vid_to_uuid[i] = fid
            self.finding_domains[fid] = list(domains or [])
            self.finding_anxieties[fid] = list(anxieties or [])

        active_ids = set(self.uuid_to_vid.keys())
        edge_list: list[tuple[int, int]] = []
        edge_weights: list[float] = []

        for from_id, to_id, rel_type, confidence in edges:
            if from_id not in active_ids or to_id not in active_ids:
                continue
            weight = EDGE_WEIGHTS.get(rel_type, 0.5)
            if weight == 0.0:
                self.contradictions.append((from_id, to_id, rel_type))
                continue
            edge_list.append((self.uuid_to_vid[from_id], self.uuid_to_vid[to_id]))
            edge_weights.append(weight * confidence)

        g.add_edges(edge_list)
        g.es["weight"] = edge_weights
        self.graph = g
        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def ppr(
        self, seed_ids: list[str], damping: float = DEFAULT_DAMPING
    ) -> dict[str, float]:
        """Run Personalized PageRank seeded on the given finding IDs.

        Returns {finding_id: ppr_score} for all findings in the graph.
        """
        if not self._loaded:
            self.load()
        assert self.graph is not None

        n = self.graph.vcount()
        reset = [0.0] * n
        for fid in seed_ids:
            vid = self.uuid_to_vid.get(fid)
            if vid is not None:
                reset[vid] = 1.0 / len(seed_ids)

        scores = self.graph.personalized_pagerank(
            damping=damping, reset=reset, weights="weight"
        )

        return {self.vid_to_uuid[i]: scores[i] for i in range(n)}

    def get_contradictions_for(self, finding_ids: list[str]) -> list[tuple[str, str]]:
        """Return (finding_id, contradicting_id) pairs for the given findings.

        These are routed to the adversarial critic, not to expansion.
        """
        id_set = set(finding_ids)
        results: list[tuple[str, str]] = []
        for from_id, to_id, _ in self.contradictions:
            if from_id in id_set and to_id not in id_set:
                results.append((from_id, to_id))
            elif to_id in id_set and from_id not in id_set:
                results.append((to_id, from_id))
        return results


def _jaccard_distance(a: list[str], b: list[str]) -> float:
    """Jaccard distance between two domain lists. 1.0 = no overlap, 0.0 = identical."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    union = sa | sb
    if not union:
        return 0.0
    return 1.0 - len(sa & sb) / len(union)


def _mmr_select(
    candidates: list[tuple[str, float]],
    selected_domains: list[list[str]],
    all_domains: dict[str, list[str]],
    max_k: int,
    lam: float = DEFAULT_MMR_LAMBDA,
) -> list[tuple[str, float]]:
    """Maximal Marginal Relevance selection for domain diversity.

    Greedily picks candidates that balance PPR relevance (high is good) with
    domain diversity from the already-selected set (high distance is good).
    """
    chosen: list[tuple[str, float]] = []
    remaining = list(candidates)
    current_domains = list(selected_domains)

    for _ in range(min(max_k, len(remaining))):
        best_score = -1.0
        best_idx = -1
        for i, (fid, ppr_score) in enumerate(remaining):
            cand_domains = all_domains.get(fid, [])
            # Max diversity from any already-selected finding's domains
            max_diversity = max(
                (_jaccard_distance(cand_domains, sd) for sd in current_domains),
                default=1.0,
            )
            mmr = lam * ppr_score + (1 - lam) * max_diversity
            if mmr > best_score:
                best_score = mmr
                best_idx = i
        if best_idx < 0:
            break
        fid, ppr = remaining.pop(best_idx)
        chosen.append((fid, best_score))
        current_domains.append(all_domains.get(fid, []))

    return chosen


def expand(
    kb_graph: KBGraph,
    selected_ids: list[str],
    max_expand: int = DEFAULT_MAX_EXPAND,
    damping: float = DEFAULT_DAMPING,
    mmr_lambda: float = DEFAULT_MMR_LAMBDA,
) -> list[ExpandedFinding]:
    """Expand a set of selected findings via PPR + MMR diversity.

    Returns the full set: original selections (source="selected") plus
    expansion additions (source="expanded"), ordered by: selected first
    (original order preserved), then expanded (by MMR score descending).
    """
    if not kb_graph.is_loaded:
        kb_graph.load()

    # Run PPR seeded on the selected findings
    ppr_scores = kb_graph.ppr(selected_ids, damping=damping)

    # Candidates: all findings NOT already selected, with non-zero PPR score
    selected_set = set(selected_ids)
    candidates = [
        (fid, score)
        for fid, score in ppr_scores.items()
        if fid not in selected_set and score > 0
    ]
    candidates.sort(key=lambda x: -x[1])
    # Take top 3x max_expand as MMR candidate pool
    candidates = candidates[: max_expand * 3]

    # Gather domains for the already-selected findings
    selected_domains = [kb_graph.finding_domains.get(fid, []) for fid in selected_ids]

    # MMR selection for diversity
    expanded = _mmr_select(
        candidates, selected_domains, kb_graph.finding_domains, max_expand, mmr_lambda
    )

    # Build the result
    results: list[ExpandedFinding] = []
    for fid in selected_ids:
        results.append(
            ExpandedFinding(
                finding_id=fid,
                ppr_score=ppr_scores.get(fid, 0.0),
                mmr_score=0.0,
                domains=kb_graph.finding_domains.get(fid, []),
                source="selected",
            )
        )
    for fid, mmr_score in expanded:
        results.append(
            ExpandedFinding(
                finding_id=fid,
                ppr_score=ppr_scores.get(fid, 0.0),
                mmr_score=mmr_score,
                domains=kb_graph.finding_domains.get(fid, []),
                source="expanded",
            )
        )

    return results
