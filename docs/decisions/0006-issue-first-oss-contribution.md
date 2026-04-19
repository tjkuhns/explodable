---
status: accepted
date: 2026-04-18
---
# ADR-0006: Issue-first (not cold PR) for contributing code judge to Braintrust autoevals

## Context

The evaluation harness methodology transferred cleanly to Python code quality scoring (`scripts/score_code.py`, `config/rubrics/python_code_quality.yaml`). Research (`docs/research/code_judge_report.md`) identified Braintrust's `autoevals` as the highest-leverage contribution target: the library ships LLM-as-judge scorers for factuality, humor, security, and other single-axis dimensions, but no scorer for subjective Python code quality. A standalone GitHub repo for the code judge would be saturated signal; a contribution to an established eval tool is a stronger portfolio artifact.

## Options considered

- **Standalone repo** — publish as its own project. Low friction, saturated category (dozens of "AI-judged code" repos on GitHub in 2026), no maintainer validation.
- **Cold PR** — build full PR (scorer class, tests, docs, benchmark) and submit unsolicited. Maximum ambiguity on whether it fits the library's architecture; likely to get declined for scope or fit reasons; weeks of work at risk.
- **Issue-first** — open a GitHub issue proposing the feature, including rubric design, two implementation options (six template scorers vs. one combined), and runnable references (rubric YAML, scorer script). Ask maintainers if it's welcome before building the PR.

## Decision

Issue-first. Opened `braintrustdata/autoevals#185` on 2026-04-18. Issue describes the gap (no subjective code quality scorer ships in the library), the 6-criterion rubric grounded in Clean Code / Ousterhout / PEP 8/257 / Google style guide, two implementation patterns that fit the library's existing `SpecFileClassifier` architecture, and links to working reference code in this repo.

## Consequences

Non-invasive contribution; maintainer signal is required before PR work begins. If accepted, the PR is scoped to the maintainers' architectural preference (fewer rebuilds). If silent, the issue remains a portfolio artifact documenting the proposal and the methodology transfer story. If declined, signal to try a different target (`inspect-ai`, `openevals`, or `langfuse`). Current status (2026-04-18): issue open, 0 engagement, <24 hours old — maintainer response window is days-to-weeks, not hours. The code judge itself is not calibrated against human reviewers — this is acknowledged explicitly in the issue.
