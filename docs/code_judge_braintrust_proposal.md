# Draft GitHub Issue for braintrustdata/autoevals

**Title:** Feature proposal: Code Quality scorer (rubric-based, multi-criterion)

---

**The gap:** autoevals ships LLM-as-judge scorers for factuality, humor, security, translation, summarization, and closed Q&A. There's no scorer for **subjective code quality** — the dimensions linters can't assess (readability, naming clarity, architectural fit, documentation intent, error handling philosophy, testability).

As AI-generated code grows (Copilot, Cursor, Claude Code), evaluation beyond "does it pass tests" is becoming a real need. DORA 2025 found AI adoption correlates with higher throughput but lower software delivery stability — more code shipping faster with less quality assurance. A standardized rubric-based scorer for the subjective quality layer would complement what linters and test suites already cover.

**What I built (exploratory, not yet calibrated for code):**

I have a calibrated LLM-as-judge evaluation harness for analytical essay quality — a 10-criterion rubric calibrated against a 7-model editorial panel; after inter-rater analysis identified 2 outlier models, the judge achieves Spearman ρ = 0.841 against the remaining 5-model consensus ([full methodology writeup](https://github.com/tjkuhns/explodable/blob/main/docs/eval-methodology.md)). I adapted the harness methodology to a 6-criterion Python code quality rubric to test whether the approach transfers across domains. The harness architecture ported in an afternoon; **the code judge itself is not yet calibrated against human reviewers.** I'd propose calibrating against human reviewers as part of the PR scope — happy to discuss what calibration evidence would be sufficient for inclusion.

The 6 criteria, grounded in Clean Code (Martin), A Philosophy of Software Design (Ousterhout), PEP 8/257, and Google Python Style Guide:

1. **Naming clarity** (weighted 1.5×) — intent-revealing identifiers, consistent domain vocabulary
2. **Readability & structure** (weighted 1.5×) — abstraction consistency, control flow clarity
3. **Architectural fit** — module boundaries, coupling, single responsibility
4. **Documentation quality** — docstrings explain contracts, comments explain WHY
5. **Error handling** — explicit failure modes, no silent swallowing
6. **Testability** — dependency injection, pure function preference, observable side effects

Each criterion has anchor exemplars at 1/3/5 levels. Deliberately excludes what linters already catch (PEP 8 formatting, import order, line length). Includes veto rules for security red flags (`eval()`, bare `except:`, hardcoded credentials).

**Sanity check on my own codebase (not calibration — just checking the judge differentiates):**

| File | Score |
|---|---|
| eval/judge.py | 35.0/35.0 |
| adversarial_critic.py | 34.0/35.0 |
| graph_expander.py | 30.5/35.0 |
| thesis_outline.py | 30.5/35.0 |
| revision_gate.py | 26.5/35.0 |
| topic_router.py | 25.5/35.0 |

The per-criterion reasoning cited specific patterns in each file. This is directional, not validated — proper calibration against human reviewers would strengthen the signal.

**How it could fit autoevals:**

I see your template-based scorers use `SpecFileClassifier` with Mustache prompts and `choice_scores` mapping — that maps naturally to single-dimension evaluation. A multi-criterion code quality scorer doesn't fit that pattern directly. Two options:

- **Six separate template scorers** (`CodeNaming`, `CodeReadability`, `CodeArchitecture`, etc.) — each as a standard YAML template with 5 choices (A-E mapping to score values). Fits your existing `SpecFileClassifier` pattern, users compose as needed.
- **One combined custom scorer** (extending `ScorerWithPartial`) that returns a single 0-1 score with per-criterion breakdown in `metadata`. More useful for holistic assessment but more code to review.

Either way, I'd adapt to whatever pattern you prefer.

**Rubric YAML and exploratory implementation:** [python_code_quality.yaml](https://github.com/tjkuhns/explodable/blob/main/config/rubrics/python_code_quality.yaml) and [score_code.py](https://github.com/tjkuhns/explodable/blob/main/scripts/score_code.py)

Would this be welcome as a PR? Happy to discuss scope, criteria design, calibration approach, or architecture fit.
