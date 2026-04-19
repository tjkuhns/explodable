"""Unit tests for src/content_pipeline/citation_processor.py.

Tests the hybrid inline-marker → markdown-footnote pipeline. Pure
functions (extract_markers, render_footnotes) tested directly;
DB-touching paths (resolve_sources, process_citations) use mocked
psycopg connections.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.content_pipeline.citation_processor import (
    ResolvedSource,
    extract_markers,
    process_citations,
    render_footnotes,
    resolve_sources,
)


# ── extract_markers ──


class TestExtractMarkers:
    def test_finds_single_marker_with_position(self):
        markers = extract_markers("Claim [src:0] evidence.")
        assert markers == [(6, 0)]

    def test_finds_multiple_markers_in_order(self):
        text = "First [src:2] second [src:0] third [src:5]"
        assert [m[1] for m in extract_markers(text)] == [2, 0, 5]

    def test_handles_multi_digit_marker_ids(self):
        assert extract_markers("Claim [src:123].") == [(6, 123)]

    def test_returns_empty_when_no_markers(self):
        assert extract_markers("Plain prose with no citations.") == []

    def test_ignores_malformed_markers(self):
        # None of these match the regex
        text = "[src] [src:] [src:abc] [source:0]"
        assert extract_markers(text) == []


# ── render_footnotes ──


def _resolved(marker_id: int, footnote_num: int, *, url: str | None = "https://example.com/paper", title: str = "Test Source") -> ResolvedSource:
    return ResolvedSource(
        marker_id=marker_id,
        finding_id=str(uuid4()),
        finding_claim="Test claim",
        finding_discipline="test discipline",
        finding_confidence=0.85,
        source_title=title,
        source_url=url,
        source_type="academic",
        source_date="2024-01-01T00:00:00",
        footnote_number=footnote_num,
    )


class TestRenderFootnotes:
    def test_replaces_src_markers_with_footnote_refs(self):
        annotated, _ = render_footnotes("Claim [src:0] evidence.", [_resolved(0, 1)])
        assert "[src:0]" not in annotated
        assert "[^1]" in annotated

    def test_builds_footnote_block_with_url(self):
        _, block = render_footnotes("Claim [src:0].", [_resolved(0, 1, url="https://arxiv.org/abs/1234")])
        assert "[^1]:" in block
        assert "https://arxiv.org/abs/1234" in block

    def test_footnote_block_omits_url_when_none(self):
        _, block = render_footnotes("Claim [src:0].", [_resolved(0, 1, url=None)])
        assert "[^1]:" in block
        assert "http" not in block

    def test_unresolved_marker_becomes_html_comment(self):
        # marker_id 99 has no resolved entry
        annotated, _ = render_footnotes("Claim [src:99].", [_resolved(0, 1)])
        assert "<!-- unresolved [src:99] -->" in annotated

    def test_deduplicates_repeated_markers_to_one_footnote(self):
        text = "Claim [src:0] and again [src:0] and once more [src:0]."
        annotated, _ = render_footnotes(text, [_resolved(0, 1)])
        # Three references to same footnote number
        assert annotated.count("[^1]") == 3


# ── resolve_sources ──


class TestResolveSources:
    def test_out_of_range_marker_is_flagged(self):
        sf = MagicMock()
        sf.finding.id = uuid4()

        resolved, report = resolve_sources(
            markers=[(0, 5)],  # marker_id=5 but only 1 finding
            selected_findings=[sf],
            conn=MagicMock(),
        )

        assert report.markers_unresolved == 1
        assert any("out of range" in w for w in report.warnings)

    def test_unique_sources_count_dedupes_repeated_marker_ids(self):
        sf = MagicMock()
        sf.finding.id = uuid4()
        sf.finding.claim = "Claim"
        sf.finding.academic_discipline = "test"
        sf.finding.confidence_score = 0.9

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("Title", "https://example.com", "academic", None)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        markers = [(0, 0), (20, 0), (40, 0)]  # same marker_id three times
        resolved, report = resolve_sources(markers, [sf], mock_conn)

        assert report.unique_sources_cited == 1
        assert len(resolved) == 1


# ── process_citations ──


class TestProcessCitations:
    def test_no_markers_returns_text_unchanged(self):
        text = "No citations here at all."
        annotated, block, report = process_citations(text, [], MagicMock())

        assert annotated == text
        assert block == ""
        assert report.markers_found == 0
        assert any("no [src:N] markers" in w for w in report.warnings)
