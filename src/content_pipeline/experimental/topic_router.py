"""Topic router: classifies incoming essay topics and routes to the optimal
retrieval modality.

Classifies on three dimensions:
1. Domain coverage — which anxiety clusters and cultural domains does this
   topic touch?
2. Cross-domain flag — does the topic require synthesis across ≥2 distinct
   domain clusters?
3. Density estimate — dense (many relevant findings), sparse (few), or
   out-of-distribution (none)?

Routing rules derived from Phase 1 empirical results:
- Cross-domain → wiki selector (Pipeline C +9 on T3)
- Single-domain dense → vector retrieval within cluster (Pipeline A best on T1/T2)
- Sparse → graph traversal from nearest findings (PPR discovers related)
- Out-of-distribution → parametric-only generation (graceful degradation)

The classifier backend is pluggable: TextSearchClassifier (free, no API) or
LLMClassifier (CAG-based, requires API credits) or EmbeddingClassifier (cheap,
requires embedding API call). All produce the same TopicClassification output.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

import psycopg


class RetrievalRoute(str, Enum):
    WIKI_SELECTOR = "wiki_selector"
    VECTOR_RETRIEVER = "vector_retriever"
    GRAPH_WALKER = "graph_walker"
    PARAMETRIC_ONLY = "parametric_only"


@dataclass
class TopicClassification:
    topic: str
    matched_anxieties: list[str]
    matched_domains: list[str]
    n_domain_clusters: int
    is_cross_domain: bool
    density: str  # "dense", "medium", "sparse", "ood"
    n_matched_findings: int
    route: RetrievalRoute
    classifier_type: str
    confidence: float = 1.0


# Routing thresholds (tunable, derived from Phase 1 observations).
# Density buckets: 0 findings = ood, 1..MEDIUM-1 = sparse,
# MEDIUM..DENSE-1 = medium, DENSE+ = dense.
CROSS_DOMAIN_MIN_CLUSTERS = 2
DENSE_THRESHOLD = 15
MEDIUM_THRESHOLD = 5


def _route_from_classification(
    is_cross_domain: bool, density: str
) -> RetrievalRoute:
    if density == "ood":
        return RetrievalRoute.PARAMETRIC_ONLY
    if is_cross_domain:
        return RetrievalRoute.WIKI_SELECTOR
    if density == "sparse":
        return RetrievalRoute.GRAPH_WALKER
    return RetrievalRoute.VECTOR_RETRIEVER


def _get_db_url() -> str:
    """Build a psycopg-compatible database URL from environment variables.

    Expects DATABASE_URL and optionally POSTGRES_PASSWORD in os.environ.
    Caller is responsible for loading .env before importing this module.
    """
    from dotenv import load_dotenv
    load_dotenv()
    db_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    if "${POSTGRES_PASSWORD}" in db_url:
        db_url = db_url.replace("${POSTGRES_PASSWORD}", os.environ["POSTGRES_PASSWORD"])
    return db_url


class TopicClassifier(ABC):
    @abstractmethod
    def classify(self, topic: str) -> TopicClassification:
        ...


class DomainSignalClassifier(TopicClassifier):
    """Free, zero-API classifier that matches topic text against domain/anxiety
    taxonomy signals rather than finding text.

    Two-stage approach:
    1. Match topic keywords against a manually-curated keyword → domain mapping
       (24 cultural domains + 5 anxiety categories) to identify which parts of
       the KB taxonomy the topic touches.
    2. Count findings under the matched (anxiety, domain) combinations to estimate
       density.

    This avoids the over-matching problem of full-text search against finding
    claims (where every finding shares behavioral-science vocabulary). The domain
    taxonomy is the discriminating signal, not individual word frequency.

    Intended as the bootstrap classifier — swap for LLMClassifier when API
    credits are available.
    """

    # Topic keywords → cultural domain mapping. Each domain has 5-15 signal
    # words that would appear in a topic about that domain. These are topic
    # vocabulary, not finding vocabulary.
    DOMAIN_SIGNALS: dict[str, list[str]] = {
        "competitive systems": [
            "b2b", "saas", "enterprise", "vendor", "procurement", "sales",
            "buyer", "deal", "churn", "renewal", "pipeline", "crm", "quota",
            "competition", "market", "pricing", "customer", "retention",
        ],
        "wealth": [
            "luxury", "wealth", "money", "price", "economic", "financial",
            "consumption", "spending", "affluence", "class", "income",
        ],
        "tribalism": [
            "tribe", "tribal", "group", "belonging", "identity", "community",
            "partisan", "loyalty", "faction", "cult", "movement",
        ],
        "technology": [
            "algorithm", "platform", "digital", "software", "tech", "ai",
            "automation", "data", "machine", "online",
        ],
        "religion": [
            "religion", "religious", "faith", "conversion", "church", "cult",
            "sacred", "worship", "belief", "spiritual", "salvation",
        ],
        "achievement culture": [
            "status", "achievement", "success", "meritocracy", "ambition",
            "performance", "career", "promotion", "rank", "hierarchy",
        ],
        "philosophy": [
            "existential", "meaning", "absurd", "nihilism", "philosophy",
            "ethics", "moral", "virtue",
        ],
        "addiction": [
            "addiction", "gambling", "dopamine", "compulsive", "habit",
            "withdrawal", "dependence", "slot",
        ],
        "social media": [
            "social media", "twitter", "facebook", "instagram", "algorithm",
            "engagement", "viral", "influencer", "feed",
        ],
        "medicine": [
            "medical", "clinical", "patient", "physician", "healthcare",
            "hospital", "diagnosis", "treatment",
        ],
        "ideology": [
            "ideology", "political", "liberal", "conservative", "partisan",
            "polarization", "propaganda",
        ],
        "fame": [
            "fame", "celebrity", "reputation", "visibility", "recognition",
            "spotlight",
        ],
        "friendship": [
            "friendship", "trust", "peer", "referral", "relationship",
            "social bond", "loneliness",
        ],
        "science": [
            "neuroscience", "neuroimaging", "fmri", "cortisol",
            "dopamine receptor", "amygdala",
        ],
        "authoritarianism": [
            "authoritarian", "obedience", "compliance", "conformity",
            "control", "power",
        ],
        "legacy": [
            "legacy", "death", "mortality", "monument", "memorial",
            "generativity", "posterity", "endow",
        ],
        "rebellion": [
            "rebellion", "dissent", "resistance", "protest", "counter",
            "subversion",
        ],
        "romantic love": [
            "romantic", "love", "attachment", "heartbreak", "rejection",
            "partner",
        ],
        "nationalism": [
            "nation", "patriot", "flag", "country", "sovereignty",
        ],
        "conspiracy theories": [
            "conspiracy", "paranoia", "distrust", "cover-up",
        ],
        "political movements": [
            "movement", "activism", "revolution", "protest", "rally",
        ],
        "narrative art": [
            "story", "narrative", "fiction", "novel", "film",
        ],
        "heroism": [
            "hero", "sacrifice", "courage", "martyr", "valor",
        ],
    }

    ANXIETY_SIGNALS: dict[str, list[str]] = {
        "helplessness": [
            "helpless", "powerless", "control", "uncertain", "overwhelm",
            "inability", "stuck", "trapped", "paralysis", "indecision",
        ],
        "insignificance": [
            "status", "insignificant", "irrelevant", "overlooked", "invisible",
            "comparison", "inadequacy", "recognition",
        ],
        "isolation": [
            "isolation", "lonely", "excluded", "ostracism", "disconnect",
            "abandon", "rejection", "belonging",
        ],
        "meaninglessness": [
            "meaning", "purpose", "absurd", "nihilism", "existential",
            "emptiness", "void",
        ],
        "mortality": [
            "death", "mortality", "dying", "legacy", "finite", "memorial",
            "endurance", "outlast", "afterlife",
        ],
    }

    @staticmethod
    def _word_boundary_match(signal: str, text: str) -> bool:
        """Match signal against text using word boundaries to avoid substring
        false positives (e.g. 'engagement' matching 'disengagement')."""
        return bool(re.search(r"\b" + re.escape(signal) + r"\b", text))

    def classify(self, topic: str) -> TopicClassification:
        """Classify a topic by matching against domain/anxiety signal keywords.

        Two-stage approach:
        1. Match topic text against curated keyword→domain and keyword→anxiety
           mappings using word-boundary regex (avoids substring false positives).
           Requires ≥2 signal hits per domain to count as a real match.
        2. Count findings in the matched (domain × anxiety) intersection to
           estimate density.

        Args:
            topic: the essay topic or prompt text to classify.

        Returns:
            TopicClassification with matched domains/anxieties, density
            estimate, cross-domain flag, and the recommended RetrievalRoute.
        """
        topic_lower = topic.lower()

        # Match domains — require word-boundary matches
        matched_domains: dict[str, int] = {}
        for domain, signals in self.DOMAIN_SIGNALS.items():
            hits = sum(1 for s in signals if self._word_boundary_match(s, topic_lower))
            if hits >= 2:  # require ≥2 signal hits to count as a real domain match
                matched_domains[domain] = hits

        # Match anxieties — require word-boundary matches
        matched_anxieties: dict[str, int] = {}
        for anxiety, signals in self.ANXIETY_SIGNALS.items():
            hits = sum(1 for s in signals if self._word_boundary_match(s, topic_lower))
            if hits > 0:
                matched_anxieties[anxiety] = hits

        if not matched_domains and not matched_anxieties:
            return TopicClassification(
                topic=topic,
                matched_anxieties=[],
                matched_domains=[],
                n_domain_clusters=0,
                is_cross_domain=False,
                density="ood",
                n_matched_findings=0,
                route=RetrievalRoute.PARAMETRIC_ONLY,
                classifier_type="domain_signal",
                confidence=0.7,
            )

        # Count findings using the tightest match: findings that sit in the
        # INTERSECTION of all matched domains + anxieties, not the union.
        # This gives true topic-specific density rather than inflated union counts.
        domain_list = list(matched_domains.keys())
        anxiety_list = list(matched_anxieties.keys())

        db_url = _get_db_url()
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                if domain_list and anxiety_list:
                    # Intersection: finding must match at least one matched domain
                    # AND at least one matched anxiety
                    cur.execute(
                        """
                        SELECT count(*) FROM findings
                        WHERE status = 'active'
                        AND cultural_domains && %s
                        AND root_anxieties::text[] && %s
                        """,
                        [domain_list, anxiety_list],
                    )
                elif domain_list:
                    # Primary domain only (highest signal hits)
                    primary = max(domain_list, key=lambda d: matched_domains[d])
                    cur.execute(
                        """
                        SELECT count(*) FROM findings
                        WHERE status = 'active' AND %s = ANY(cultural_domains)
                        """,
                        [primary],
                    )
                else:
                    cur.execute(
                        """
                        SELECT count(*) FROM findings
                        WHERE status = 'active' AND root_anxieties::text[] && %s
                        """,
                        [anxiety_list],
                    )
                n_matched = cur.fetchone()[0]

        n_clusters = len(matched_domains)
        is_cross_domain = n_clusters >= CROSS_DOMAIN_MIN_CLUSTERS

        if n_matched == 0:
            density = "ood"
        elif n_matched < MEDIUM_THRESHOLD:
            density = "sparse"
        elif n_matched < DENSE_THRESHOLD:
            density = "medium"
        else:
            density = "dense"

        route = _route_from_classification(is_cross_domain, density)

        return TopicClassification(
            topic=topic,
            matched_anxieties=sorted(matched_anxieties.keys()),
            matched_domains=sorted(matched_domains.keys()),
            n_domain_clusters=n_clusters,
            is_cross_domain=is_cross_domain,
            density=density,
            n_matched_findings=n_matched,
            route=route,
            classifier_type="domain_signal",
            confidence=0.7,
        )


def get_default_classifier() -> TopicClassifier:
    return DomainSignalClassifier()
