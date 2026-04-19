"""Unit tests for src/content_pipeline/topic_router.py.

Covers the pure routing logic and word-boundary matching helper. The
`DomainSignalClassifier.classify()` method hits the DB, so it's covered
at the integration level elsewhere — these unit tests stay pure.
"""

from __future__ import annotations

from src.content_pipeline.experimental.topic_router import (
    DomainSignalClassifier,
    RetrievalRoute,
    _route_from_classification,
)


# ── Routing rules derived from Phase 1 empirical results ──


class TestRouteFromClassification:
    def test_ood_routes_to_parametric_only(self):
        assert _route_from_classification(False, "ood") == RetrievalRoute.PARAMETRIC_ONLY
        # Cross-domain + ood should still route to parametric (nothing in KB)
        assert _route_from_classification(True, "ood") == RetrievalRoute.PARAMETRIC_ONLY

    def test_cross_domain_routes_to_wiki_selector(self):
        assert _route_from_classification(True, "dense") == RetrievalRoute.WIKI_SELECTOR
        assert _route_from_classification(True, "medium") == RetrievalRoute.WIKI_SELECTOR
        assert _route_from_classification(True, "sparse") == RetrievalRoute.WIKI_SELECTOR

    def test_sparse_single_domain_routes_to_graph_walker(self):
        assert _route_from_classification(False, "sparse") == RetrievalRoute.GRAPH_WALKER

    def test_dense_single_domain_routes_to_vector_retriever(self):
        assert _route_from_classification(False, "dense") == RetrievalRoute.VECTOR_RETRIEVER

    def test_medium_single_domain_routes_to_vector_retriever(self):
        assert _route_from_classification(False, "medium") == RetrievalRoute.VECTOR_RETRIEVER


# ── Word-boundary matching (no substring false positives) ──


class TestWordBoundaryMatch:
    """The classifier uses word-boundary regex to avoid matching 'engagement'
    as a substring of 'disengagement' or similar."""

    def test_matches_whole_word(self):
        assert DomainSignalClassifier._word_boundary_match("sales", "b2b sales cycle") is True

    def test_does_not_match_substring(self):
        assert DomainSignalClassifier._word_boundary_match("engagement", "disengagement") is False
        assert DomainSignalClassifier._word_boundary_match("sale", "wholesale") is False

    def test_matches_at_string_boundaries(self):
        assert DomainSignalClassifier._word_boundary_match("sales", "sales") is True
        assert DomainSignalClassifier._word_boundary_match("sales", "sales cycle") is True
        assert DomainSignalClassifier._word_boundary_match("sales", "enterprise sales") is True

    def test_handles_punctuation_as_boundary(self):
        assert DomainSignalClassifier._word_boundary_match("sales", "sales.") is True
        assert DomainSignalClassifier._word_boundary_match("sales", "(sales)") is True


# ── Signal dictionaries are well-formed ──


class TestSignalDictionaries:
    """Sanity checks on the curated keyword mappings. These don't test
    classification output, just that the tables are consistent with the
    constraints the classifier expects."""

    def test_every_domain_has_at_least_two_signals(self):
        # The classifier requires >=2 signal hits per domain to count as
        # a real match, so singleton domains would never trigger.
        for domain, signals in DomainSignalClassifier.DOMAIN_SIGNALS.items():
            assert len(signals) >= 2, f"Domain '{domain}' has fewer than 2 signals"

    def test_every_anxiety_has_signals(self):
        for anxiety, signals in DomainSignalClassifier.ANXIETY_SIGNALS.items():
            assert len(signals) > 0, f"Anxiety '{anxiety}' has no signals"

    def test_all_five_root_anxieties_present(self):
        expected = {"helplessness", "insignificance", "isolation", "meaninglessness", "mortality"}
        assert set(DomainSignalClassifier.ANXIETY_SIGNALS.keys()) == expected
