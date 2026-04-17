"""Evaluation harness for content pipeline outputs.

LLM-as-judge scoring against a published analytical-writing rubric, plus
calibration tools for measuring rank correlation with editor rankings.
See docs/research/phase0_reports/03_coherence_metrics.md for the motivation
(RAG metrics don't measure discourse coherence; only LLM-as-judge with
structured rubrics clears the bar for long-form analytical writing).
"""
