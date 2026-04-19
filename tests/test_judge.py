"""Unit tests for src/content_pipeline/eval/judge.py.

Covers the portable surface: score dataclasses, rubric loading, tool
schema construction (the flat-parallel-array design note), prompt
building, rank correlation math, and calibration. No API calls.
"""

from __future__ import annotations

import pytest

from src.content_pipeline.eval.judge import (
    CriterionScore,
    DraftScore,
    build_judge_prompt,
    build_judge_tool_schema,
    calibrate,
    load_rubric,
    rubric_weights,
    spearman_rank_correlation,
)


# ── CriterionScore ──


class TestCriterionScore:
    def test_score_of_1_is_veto(self):
        assert CriterionScore("c", 1, "").is_veto() is True

    def test_score_above_1_is_not_veto(self):
        assert CriterionScore("c", 2, "").is_veto() is False

    def test_score_of_5_is_not_veto(self):
        assert CriterionScore("c", 5, "").is_veto() is False


# ── DraftScore ──


@pytest.fixture
def sample_draft_score() -> DraftScore:
    return DraftScore(
        draft_path="drafts/test.md",
        draft_word_count=1000,
        criterion_scores=[
            CriterionScore("clarity", 4, ""),
            CriterionScore("rigor", 3, ""),
            CriterionScore("evidence", 1, "weak"),
        ],
        rubric_version="v1",
        rubric_path="rubric.yaml",
    )


class TestDraftScore:
    def test_total_unweighted_sums_raw_scores(self, sample_draft_score):
        assert sample_draft_score.total_unweighted() == 8

    def test_total_weighted_applies_multipliers(self, sample_draft_score):
        weights = {"clarity": 1.5}  # rigor and evidence default to 1.0
        assert sample_draft_score.total_weighted(weights) == 4 * 1.5 + 3 + 1

    def test_total_weighted_defaults_missing_criterion_to_1(self, sample_draft_score):
        assert sample_draft_score.total_weighted({}) == 8

    def test_vetoed_criteria_lists_only_score_1(self, sample_draft_score):
        assert sample_draft_score.vetoed_criteria() == ["evidence"]

    def test_to_dict_round_trip(self, sample_draft_score):
        d = sample_draft_score.to_dict()
        assert d["draft_path"] == "drafts/test.md"
        assert d["total_unweighted"] == 8
        assert d["vetoed_criteria"] == ["evidence"]
        assert len(d["criterion_scores"]) == 3


# ── Rubric loading ──


class TestLoadRubric:
    def test_loads_valid_rubric(self, rubric_yaml_file):
        rubric = load_rubric(rubric_yaml_file)
        assert len(rubric["criteria"]) == 3

    def test_raises_on_missing_criteria_key(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("version: v1\n")
        with pytest.raises(ValueError, match="missing 'criteria' key"):
            load_rubric(bad)


class TestRubricWeights:
    def test_extracts_weights_from_scoring_guidance(self, minimal_rubric):
        assert rubric_weights(minimal_rubric) == {"clarity": 1.5}

    def test_returns_empty_when_no_guidance(self):
        assert rubric_weights({"criteria": []}) == {}


# ── Tool schema (the flat-parallel-array design note) ──


class TestBuildJudgeToolSchema:
    """The design note at judge.py:191-204 says flat primitive arrays
    avoid Opus's nested-object serialization bug. Verify shape."""

    def test_schema_uses_flat_keys_not_nested_arrays(self, minimal_rubric):
        schema = build_judge_tool_schema(minimal_rubric)
        props = schema["input_schema"]["properties"]
        assert "clarity__score" in props
        assert "clarity__reasoning" in props
        # No nested array-of-objects for criteria
        assert not any(
            p.get("type") == "array" and p.get("items", {}).get("type") == "object"
            for p in props.values()
        )

    def test_score_fields_are_bounded_integers(self, minimal_rubric):
        schema = build_judge_tool_schema(minimal_rubric)
        score_field = schema["input_schema"]["properties"]["clarity__score"]
        assert score_field["type"] == "integer"
        assert score_field["minimum"] == 1
        assert score_field["maximum"] == 5

    def test_all_criterion_fields_are_required(self, minimal_rubric):
        schema = build_judge_tool_schema(minimal_rubric)
        required = set(schema["input_schema"]["required"])
        for cid in ("clarity", "rigor", "evidence"):
            assert f"{cid}__score" in required
            assert f"{cid}__reasoning" in required


# ── Prompt builder ──


class TestBuildJudgePrompt:
    def test_user_prompt_contains_draft_text(self, minimal_rubric):
        _, user = build_judge_prompt("My draft essay.", minimal_rubric)
        assert "My draft essay." in user

    def test_user_prompt_lists_every_criterion(self, minimal_rubric):
        _, user = build_judge_prompt("draft", minimal_rubric)
        for c in minimal_rubric["criteria"]:
            assert c["id"] in user
            assert c["name"] in user


# ── Spearman rank correlation ──


class TestSpearmanRankCorrelation:
    def test_perfect_correlation(self):
        assert spearman_rank_correlation([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == pytest.approx(1.0)

    def test_perfect_anticorrelation(self):
        assert spearman_rank_correlation([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_zero_variance_returns_zero(self):
        assert spearman_rank_correlation([1, 2, 3], [7, 7, 7]) == 0.0

    def test_raises_on_unequal_lengths(self):
        with pytest.raises(ValueError, match="equal length"):
            spearman_rank_correlation([1, 2], [1, 2, 3])

    def test_raises_on_fewer_than_two_items(self):
        with pytest.raises(ValueError, match="at least 2"):
            spearman_rank_correlation([1], [1])

    def test_handles_tied_ranks(self):
        # Tied ranks should still yield ρ = 1 when the orderings agree
        assert spearman_rank_correlation([1, 2, 2, 3], [10, 20, 20, 30]) == pytest.approx(1.0)


# ── calibrate ──


class TestCalibrate:
    def _score_for(self, cid: str, value: int) -> DraftScore:
        return DraftScore(
            draft_path="",
            draft_word_count=0,
            criterion_scores=[CriterionScore(cid, value, "")],
            rubric_version="v1",
            rubric_path="",
        )

    def test_passes_when_rankings_agree(self, minimal_rubric):
        editor_rankings = {"d1": 1, "d2": 2, "d3": 3}
        judge_scores = {
            "d1": self._score_for("clarity", 5),
            "d2": self._score_for("clarity", 4),
            "d3": self._score_for("clarity", 3),
        }
        result = calibrate(editor_rankings, judge_scores, minimal_rubric)
        assert result["n"] == 3
        assert result["spearman_rho"] == pytest.approx(1.0)
        assert result["passes_calibration"] is True

    def test_fails_when_rho_below_threshold(self, minimal_rubric):
        # Judge reverses the editor ordering: ρ = -1, below 0.7 threshold
        editor_rankings = {"d1": 1, "d2": 2, "d3": 3}
        judge_scores = {
            "d1": self._score_for("clarity", 3),
            "d2": self._score_for("clarity", 4),
            "d3": self._score_for("clarity", 5),
        }
        result = calibrate(editor_rankings, judge_scores, minimal_rubric)
        assert result["passes_calibration"] is False

    def test_raises_when_fewer_than_three_shared_drafts(self, minimal_rubric):
        with pytest.raises(ValueError, match="at least 3 drafts"):
            calibrate({"d1": 1, "d2": 2}, {}, minimal_rubric)
