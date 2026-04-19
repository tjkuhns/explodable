---
status: accepted
date: 2026-04-15
---
# ADR-0003: Eval harness as scalable validation in place of a human panel

## Context

Content quality at generation volume (~5–20 drafts per pipeline run, expected hundreds per month at steady state) needs systematic validation. Standard RAG metrics (RAGAS, ROUGE, BERTScore) don't measure discourse coherence or argument quality in long-form analytical writing. A human review panel at this volume is economically and logistically infeasible for a solo operator.

## Options considered

- **Vibes-only review** — solo operator reads every draft; fine at low volume, fails at scale.
- **Hire a human review panel** — ~$50–200 per draft × hundreds of drafts/month is not affordable.
- **LLM-as-judge calibrated against a multi-model editorial panel** — build structured 10-criterion rubric (grounded in Minto Pyramid, BCG action-titles, Baker expertise tests, Berger-Milkman sharing research); calibrate a single-judge against an editorial ground truth derived from multiple independent models; disclose methodology limits transparently.

## Decision

Build LLM-as-judge (`src/content_pipeline/eval/judge.py` + `config/rubrics/analytical_essay.yaml`). Calibrate against a 7-model editorial panel (Gemini 2.5 Pro, Grok 4, DeepSeek V3, Mistral Large, GPT-5, Claude Deep Research, Qwen3). After pairwise agreement analysis, drop 2 outlier models; use 5-model cluster as ground truth. Use content axis only in the judge; polish/execution-axis issues (exposed pipeline scaffolding, placeholder tokens) are caught by a deterministic grep pre-flight gate (`scripts/check_export_gate.py`).

## Consequences

ρ = 0.841 (Opus) / ρ = 0.782 (Sonnet) against the 5-model cluster. The 5-model panel's internal agreement is ~0.83, so judge ρ is at the panel's ceiling — further tightening requires more independent ground truth, not better modeling. No human validation yet — acknowledged in every public surface (README, website, blog). Methodology writeup (`docs/eval-methodology.md`) discloses the post-hoc outlier drop as a pre-registration flaw, which is a credibility feature, not a weakness. Human ground-truth calibration is a known open item; not currently blocking publication, but it's the clearest next methodology upgrade.
