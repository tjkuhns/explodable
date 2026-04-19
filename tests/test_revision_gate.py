"""Unit tests for src/content_pipeline/revision_gate.py.

The gate's core contract: accept a revision only if at least one
criterion improves and none regress (beyond optional tolerance).
Tests mock `score_draft` so the Pareto logic is exercised directly
without hitting the Anthropic API.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import yaml

from src.content_pipeline.eval.judge import CriterionScore, DraftScore
from src.content_pipeline.experimental.revision_gate import evaluate_revision, revision_gate


def _score(scores: dict[str, int]) -> DraftScore:
    return DraftScore(
        draft_path="",
        draft_word_count=0,
        criterion_scores=[CriterionScore(cid, s, "") for cid, s in scores.items()],
        rubric_version="v1",
        rubric_path="",
    )


@pytest.fixture
def stub_rubric(tmp_path):
    rubric = {
        "criteria": [
            {"id": "a", "name": "A", "what_it_measures": "", "scale": {1: "", 3: "", 5: ""}},
            {"id": "b", "name": "B", "what_it_measures": "", "scale": {1: "", 3: "", 5: ""}},
            {"id": "c", "name": "C", "what_it_measures": "", "scale": {1: "", 3: "", 5: ""}},
        ],
    }
    path = tmp_path / "rubric.yaml"
    path.write_text(yaml.safe_dump(rubric))
    return path


class TestEvaluateRevision:
    def test_accepts_when_one_criterion_improves_none_regress(self, stub_rubric, tmp_path):
        orig = tmp_path / "orig.md"
        orig.write_text("original")
        rev = tmp_path / "rev.md"
        rev.write_text("revised")

        with patch("src.content_pipeline.experimental.revision_gate.score_draft") as mock_score:
            mock_score.side_effect = [
                _score({"a": 3, "b": 3, "c": 3}),
                _score({"a": 4, "b": 3, "c": 3}),
            ]
            decision = evaluate_revision(str(orig), str(rev), stub_rubric)

        assert decision.accepted is True
        assert "a" in decision.improved_criteria
        assert decision.regressed_criteria == []

    def test_rejects_when_no_criterion_improves(self, stub_rubric, tmp_path):
        orig = tmp_path / "orig.md"
        orig.write_text("original")
        rev = tmp_path / "rev.md"
        rev.write_text("revised")

        with patch("src.content_pipeline.experimental.revision_gate.score_draft") as mock_score:
            mock_score.side_effect = [
                _score({"a": 3, "b": 3, "c": 3}),
                _score({"a": 3, "b": 3, "c": 3}),
            ]
            decision = evaluate_revision(str(orig), str(rev), stub_rubric)

        assert decision.accepted is False
        assert decision.reason == "no criteria improved"

    def test_rejects_when_any_criterion_regresses(self, stub_rubric, tmp_path):
        orig = tmp_path / "orig.md"
        orig.write_text("original")
        rev = tmp_path / "rev.md"
        rev.write_text("revised")

        with patch("src.content_pipeline.experimental.revision_gate.score_draft") as mock_score:
            mock_score.side_effect = [
                _score({"a": 3, "b": 3, "c": 3}),
                _score({"a": 4, "b": 2, "c": 3}),  # a improves, b regresses
            ]
            decision = evaluate_revision(str(orig), str(rev), stub_rubric)

        assert decision.accepted is False
        assert "b" in decision.regressed_criteria
        assert "regression" in decision.reason

    def test_tolerance_allows_small_regression(self, stub_rubric, tmp_path):
        orig = tmp_path / "orig.md"
        orig.write_text("original")
        rev = tmp_path / "rev.md"
        rev.write_text("revised")

        with patch("src.content_pipeline.experimental.revision_gate.score_draft") as mock_score:
            mock_score.side_effect = [
                _score({"a": 4, "b": 4, "c": 4}),
                _score({"a": 5, "b": 3, "c": 4}),  # a +1, b -1
            ]
            # tolerance=1.0 absorbs the b regression
            decision = evaluate_revision(str(orig), str(rev), stub_rubric, tolerance=1.0)

        assert decision.accepted is True


class TestRevisionGate:
    def test_returns_revised_text_when_accepted(self, stub_rubric):
        with patch("src.content_pipeline.experimental.revision_gate.score_draft") as mock_score:
            mock_score.side_effect = [
                _score({"a": 3, "b": 3, "c": 3}),
                _score({"a": 4, "b": 3, "c": 3}),
            ]
            chosen, decision = revision_gate("original text", "revised text", stub_rubric)

        assert chosen == "revised text"
        assert decision.accepted is True

    def test_returns_original_text_when_rejected(self, stub_rubric):
        with patch("src.content_pipeline.experimental.revision_gate.score_draft") as mock_score:
            mock_score.side_effect = [
                _score({"a": 3, "b": 3, "c": 3}),
                _score({"a": 4, "b": 2, "c": 3}),
            ]
            chosen, decision = revision_gate("original text", "revised text", stub_rubric)

        assert chosen == "original text"
        assert decision.accepted is False

    def test_raises_on_empty_original(self):
        with pytest.raises(ValueError, match="original_draft is empty"):
            revision_gate("", "revised")

    def test_raises_on_empty_revised(self):
        with pytest.raises(ValueError, match="revised_draft is empty"):
            revision_gate("original", "")
