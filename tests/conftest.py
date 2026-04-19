"""Shared pytest fixtures for the unit test suite."""

from __future__ import annotations

import pytest
import yaml


@pytest.fixture
def minimal_rubric() -> dict:
    """A minimal 3-criterion rubric for testing judge + gate logic.

    Uses the same shape as config/rubrics/analytical_essay.yaml but
    compressed to three criteria so tests are readable.
    """
    return {
        "version": "test-v1",
        "criteria": [
            {
                "id": "clarity",
                "name": "Clarity",
                "what_it_measures": "Is the writing clear?",
                "scale": {1: "Incomprehensible", 3: "Adequate", 5: "Crystal clear"},
                "weight": 1.5,
            },
            {
                "id": "rigor",
                "name": "Rigor",
                "what_it_measures": "Is the reasoning sound?",
                "scale": {1: "Sloppy", 3: "Adequate", 5: "Airtight"},
            },
            {
                "id": "evidence",
                "name": "Evidence",
                "what_it_measures": "Are claims backed?",
                "scale": {1: "Unsupported", 3: "Some support", 5: "Fully grounded"},
            },
        ],
        "scoring_guidance": {
            "weighted_criteria": {"clarity": 1.5},
        },
    }


@pytest.fixture
def rubric_yaml_file(tmp_path, minimal_rubric):
    """Write `minimal_rubric` to a temp yaml file and return the path."""
    path = tmp_path / "test_rubric.yaml"
    path.write_text(yaml.safe_dump(minimal_rubric))
    return path
