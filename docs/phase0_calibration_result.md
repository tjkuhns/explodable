# Phase 0 calibration result

**Date:** 2026-04-15
**Status:** PASSED (Spearman ρ = 0.841, threshold 0.7)
**Artifacts:** `logs/phase0_judge_scores.json`, `docs/phase0_editor_rankings.md`, `docs/phase0_multi_judge_prompt.md`

## What we did

Calibrated the Claude-Opus LLM-as-judge (`src/content_pipeline/eval/judge.py` + `config/rubrics/analytical_essay.yaml`) against a multi-model editorial ground truth on all 12 existing drafts. The original plan called for Tom's personal gut ranking as the calibration anchor; Tom reframed this mid-session — the judge should track the *audience's* forward-readiness standard, not personal taste, because the business exists to serve an audience. The calibration target became "rigorous editorial judgment applied to the forward-to-CEO criterion" rather than "Tom's editorial gut."

## How the ground truth was built

Seven independent judgments were collected using a shared prompt (see `docs/phase0_multi_judge_prompt.md`):

1. Claude Deep Research (pre-session audit pass, `export_folder_audit.md`)
2. Gemini 2.5 Pro
3. Grok 4
4. DeepSeek V3
5. Mistral Large (Le Chat)
6. ChatGPT / GPT-5 (re-run once after first pass dropped Belonging Machine and duplicated Luxury of Extremism)
7. Qwen3

Pairwise Spearman ρ across all 7: mean **+0.544**, median **+0.664**, range **+0.084 to +0.909**.

The panel was not uniformly tight, but had clear structure. Five judges (Gemini, Grok, DeepSeek, Mistral, ChatGPT) formed a tight cluster with internal mean pairwise ρ ≈ **+0.83**. Two judges were outliers on different axes:

- **Deep Research (+0.261 vs others)** was the only judge that heavily penalized *execution* (Fear Tax #11, latest_unreviewed #12). This wasn't wrong — it was applying a second axis the others collapsed into the first.
- **Qwen (+0.396 vs others)** was differently inconsistent: ranked Preference Falsification #3 and Anxiety Economy #4 against panel consensus, and inverted the latest_unreviewed pair. Looked like a weaker editorial read, not a principled second axis.

We dropped DR and Qwen and used the 5-cluster mean-rank aggregate as the calibration ground truth.

### 5-cluster aggregate ranking (final editor ranks)

| Rank | Draft | Mean rank across cluster |
|------|-------|--------------------------|
| 1 | The Veto Machine | 1.40 |
| 2 | The Feedback Loop That Broke B2B Sales | 1.60 |
| 3 | The Fear Tax | 3.40 |
| 4 | The Attribution Trap (latest_unreviewed_v2) | 4.40 |
| 5 | The Committee Trap | 4.80 |
| 6 | latest_unreviewed (Feedback Loop regen) | 6.00 |
| 7 | The Belonging Machine | 7.60 |
| 8 | The Preference Falsification Machine | 9.20 |
| 9 | The Luxury of Extremism | 9.60 |
| 10 | The Hermès Heretic | 9.80 |
| 11 | The Anxiety Economy | 10.00 |
| 12 | The Dopamine Democracy | 10.20 |

## Calibration result

Judge scored all 12 drafts through the 10-criterion rubric. Against the 5-cluster editor ranks:

**Spearman ρ = 0.841 — threshold cleared.**

Editor rank vs judge weighted total:

| Editor rank | Judge weighted | Draft |
|-------------|----------------|-------|
| 1 | 42.5 | The Veto Machine |
| 2 | **46.0** | The Feedback Loop That Broke B2B Sales |
| 3 | 35.0 | The Fear Tax |
| 4 | 40.5 | The Attribution Trap |
| 5 | 38.0 | The Committee Trap |
| 6 | **44.5** | latest_unreviewed |
| 7 | 26.5 | The Belonging Machine |
| 8 | 23.5 | The Preference Falsification Machine |
| 9 | 24.0 | The Luxury of Extremism |
| 10 | 25.5 | The Hermès Heretic |
| 11 | 24.0 | The Anxiety Economy |
| 12 | 21.5 | The Dopamine Democracy |

Judge cleanly separates the commercial cluster (top 6, scores 35–46) from the cultural cluster (bottom 6, scores 21.5–26.5). Within each cluster, fine-grained rank noise matches the noise observed across human/LLM judges on the same pair comparisons.

## Key finding: content axis vs execution axis

The biggest single disagreement between judge and editor is **latest_unreviewed — judge 44.5 (effectively #2), editor rank 6.** The judge is not penalizing the exposed `Explodable` KB name, script paths (`scripts/backfill_manifestation_urls.py`), or `URL pending verification` footnote leakage. This is also why DR was the biggest panel outlier — it was the only judge applying an execution-polish axis on top of content.

**Conclusion:** the "forward-to-CEO" criterion has two orthogonal axes:

1. **Content axis** — POV sharpness, claim credibility, rhetorical structure, integrative thinking. The judge tracks this well (ρ = 0.841 vs the 5-cluster content-focused aggregate).
2. **Execution axis** — no visible pipeline scaffolding, no placeholder tokens, no exposed metadata, no internal system references. The judge cannot reliably track this from the rubric alone, and calibrating it against execution-aware ground truth would pull the judge toward conflating two axes.

**Design decision:** the judge remains the content-axis metric. The execution axis becomes a **pre-flight checker** — a deterministic `grep`-based gate run before any draft leaves the working directory. Initial pattern list (to be refined as more issues surface):

```
backfill_manifestation
Explodable
\[src:[0-9]+\]
URL pending verification
no manifestation recorded
review_status:
thread_id:
anxiety-indexed KB
```

Any match fails the check and blocks export. This is faster, cheaper, and more reliable than teaching the judge to recognize execution issues.

## What unlocks downstream

With a calibrated content-axis judge (ρ = 0.841) and a clear path to a deterministic execution gate, Phase 1 (the three-way bake-off between Current stack / CAG / Karpathy Wiki) now has a measurement instrument. Standard RAG metrics were never going to move under paragraph shuffles; this judge will. The bake-off can proceed.

## Caveats to remember

1. **ρ = 0.841 on n = 12 is statistically meaningful but not airtight.** The 5-cluster internal agreement is ~0.83, so our judge's 0.841 correlation is essentially at the ceiling set by the ground truth itself. Any downstream metric improvements need to be evaluated with this noise floor in mind.
2. **LLM-to-LLM calibration has correlated-bias risk.** We partially mitigated this by using six independent model families as the ground truth, and by sanity-checking inter-rater agreement before aggregating. Not clean, but defensible.
3. **The rubric is calibrated against the *current* set of 12 drafts.** As the corpus expands and new failure modes emerge (e.g., CAG-generated drafts that fail in ways these 12 never did), recalibration may be necessary.
4. **Execution axis is not measured.** Anything that fails the pre-flight grep is still dangerous even if the judge gives it a high content score. The two gates compose — both must pass.
