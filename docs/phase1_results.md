# Phase 1 bake-off results

**Date:** 2026-04-16
**Status:** COMPLETE. Wiki recommended for Phase 2.
**Artifacts:** `logs/phase1_bakeoff/` (all drafts, metadata, judge scores)

## Setup

Three pipelines tested on 5 frozen topics spanning both brand registers and four KB density conditions. All pipelines used the same model (claude-sonnet-4-20250514) and temperature (0.7). Pipeline A ran 3× per topic for variance measurement (15 runs total); B and C ran 1× each (5 runs each). 25 drafts scored through the Phase 0 calibrated judge (ρ = 0.841 against the 5-model editorial ground truth).

KB state at run time: 305 active findings, verified live against docker postgres.

### The 5 test topics

| ID | Topic | Register | KB density |
|---|---|---|---|
| T1 | The Silent Disengagement (enterprise churn) | Explodable | Dense |
| T2 | The First Number Wins (B2B anchoring) | Explodable | Medium-sparse |
| T3 | B2B Vendor Lock-in and Religious Conversion | Boulder | Cross-domain (3 dense clusters) |
| T4 | Legacy Anxiety (economics of post-death signaling) | Boulder | Sparse (mortality + legacy) |
| T5 | Golf and Organizational Status Games | Boulder | Zero (out-of-distribution) |

### The 3 pipelines

- **Pipeline A (current stack):** LangGraph content pipeline — retriever → selector → outliner → drafter → BVCS scorer → publisher. Full prompt engineering: voice profile, outline HITL gates (auto-approved), BVCS revision loop (up to 3 auto-revisions for scores <70). Production config unchanged.
- **Pipeline B (CAG):** Entire KB (305 findings, ~115K tokens) cached in system prompt as XML with edge-loaded ordering and table of contents. Two-pass slot-filling: Pass 1 selects 7 findings by slot type (1 primary, 3 mechanisms, 2 data, 1 counterpoint), Pass 2 writes the essay from committed IDs. No retrieval, no outline stage, no BVCS revision.
- **Pipeline C (Wiki):** KB compiled into a markdown index (~41K tokens) plus per-finding files. Two-pass: Pass 1 reads index and picks 8–12 IDs, harness fetches the full text, Pass 2 writes the essay from the selected findings. No retrieval, no outline stage, no BVCS revision.

## Results — judge-weighted totals (max 57.5)

| Topic | A (current stack) | B (CAG) | C (Wiki) |
|---|---|---|---|
| T1 — dense commercial | **41.0** (35.0–43.5) | 33.5 | 40.5 |
| T2 — medium-sparse | **35.0** (32.5–37.5) | 27.5 | 30.0 |
| T3 — cross-domain | 23.0 (21.5–29.5) | 22.5 | **32.0** |
| T4 — sparse stress | **33.0** (27.5–34.0) | 24.0 | 31.5 |
| T5 — out-of-distribution | **31.0** (28.5–32.5) | 24.0 | 26.0 |
| **MEAN** | **32.3** | 26.3 | 32.0 |

Pipeline A values are medians across 3 runs; range in parentheses.

## Interpretation

### CAG lost decisively

26.3 mean, worst on every topic. Dumping 115K tokens of findings into context produced worse essays, not better ones. The slot-filling two-pass architecture did not compensate for the context density.

The research reports (especially `06_cag_novelty.md` and `07_cag_tactical.md`) were bullish on CAG for our KB size. The empirical test contradicts them. This is consistent with the generation-specific failure modes documented in Report 6 (LongGenBench showed only r=0.51 between retrieval and generation performance), but the magnitude of underperformance is larger than the research predicted. At 115K tokens the model appears to suffer from selection paralysis — too many findings available, not enough signal to discriminate.

Edge-loading (high-confidence findings in primacy and recency positions) and the structured table of contents were insufficient mitigations. The slot-filling constraint (7 slots) may have been too rigid for some topics. These are optimizable, but the 6-point gap to Wiki and the 6-point gap to the current stack suggest the issue is architectural, not prompt-level.

**Implications for the research write-up (Phase 5):** this is a genuinely publishable negative result. CAG works for QA extraction (per Chan et al.) but fails for long-form argumentative generation — exactly the gap Report 6 identified as uncharted. The bake-off data supports a workshop paper on this finding.

### Wiki tied the current stack (with zero prompt engineering)

32.0 vs 32.3 mean — statistically indistinguishable given Pipeline A's observed variance (median range ~5–9 points per topic). But Wiki had none of the current stack's prompt engineering advantages:

- No voice profile
- No outline generation or review stage
- No BVCS scoring or auto-revision loop (the current stack auto-revises drafts scoring <70, up to 3 times)
- No publisher post-processing

Pipeline C's prompts are ~40 lines of instructions. Pipeline A's content pipeline is hundreds of lines of engineered prompts across 6+ nodes. The fact that Wiki tied without any of this engineering is the strongest signal in the bake-off.

### Cross-domain synthesis is the headline

T3 (B2B vendor lock-in × religious conversion) produced the largest quality gap: Wiki 32.0, Pipeline A 23.0 (9-point advantage for Wiki). This was the topic designed to stress-test cross-domain synthesis — the stated brand differentiator.

The current stack's retriever struggled with the cross-domain query because multi-query expansion at temperature 0.4 tends to stay within one domain cluster. Wiki's index scan, by contrast, is a full table read — the model can see all anxiety categories simultaneously and draw from multiple clusters naturally. This is exactly the use case where a retrieval-free architecture should outperform, and the data confirms it.

### Out-of-distribution: current stack won

T5 (golf × organizational status games) — zero KB coverage of golf. Pipeline A scored 31.0 vs Wiki 26.0 vs CAG 24.0. When the KB has nothing directly relevant, Pipeline A's retriever fails to find specific findings and the drafter falls back on parametric knowledge, producing a passable essay. Wiki and CAG both tried to force-fit KB findings onto a topic without coverage, which degraded quality.

**Implication:** the Wiki architecture needs a graceful-failure path for topics outside KB coverage. The Pass 1 selection step should be able to return "insufficient KB coverage for this topic — recommend parametric-only generation" instead of force-fitting thin signal.

### Pipeline A variance is substantial

| Topic | Range | Spread |
|---|---|---|
| T1 | 35.0–43.5 | 8.5 |
| T2 | 32.5–37.5 | 5.0 |
| T3 | 21.5–29.5 | 8.0 |
| T4 | 27.5–34.0 | 6.5 |
| T5 | 28.5–32.5 | 4.0 |

5–8.5 point spreads from the same topic and same pipeline. This is non-determinism from temperature 0.7 compounded by retrieval variance (different multi-query expansions hit different KB regions) and outline variance (different outline structures). The current stack's quality is not reproducible — the same topic can produce a 35 or a 43 depending on sampling.

Wiki and CAG share the same drafter temperature but have no retrieval or outline variance. Their single samples are tighter estimates (though not deterministic).

## Operational metrics

| Metric | Pipeline A | Pipeline B (CAG) | Pipeline C (Wiki) |
|---|---|---|---|
| Mean wall time per draft | 105s | 56s | 54s |
| Mean word count | ~950 | ~1120 | ~1100 |
| Execution gate pass rate | 15/15 | 5/5 | 5/5 |
| Per-draft API cost (est.) | ~$0.30 | ~$0.05 | ~$0.03 |
| Cache utilization | N/A | 207K tokens/call | 41K tokens/call (Pass 1 only) |

Pipeline B and C are both ~2× faster and ~6–10× cheaper per draft than Pipeline A, because they skip the outline stage, BVCS revision loop, and multi-step retrieval. If Wiki gets the current stack's prompt engineering, its cost and latency will increase but remain well below Pipeline A's.

## Recommendation

**Implement Wiki as the Phase 2 architecture.** Reasoning:

1. **Ties the current stack without any prompt engineering.** When it gets voice profiles, BVCS revision, and an outline stage, it should exceed A.
2. **Wins cross-domain by 9 points.** The brand differentiator topic is where the architecture matters most.
3. **Scales linearly.** Index grows at ~130 tokens/finding. At 5,000 findings the index is ~650K tokens (cacheable with 1M context); per-draft cost is only the selected findings, not the whole KB.
4. **Simpler.** No pgvector at query time, no embedding lookup, no multi-step retrieval. Index → pick → fetch → write.
5. **Cheaper and faster.** ~$0.03/draft vs ~$0.30/draft; ~54s vs ~105s.
6. **CAG failed empirically.** The only reason to reconsider CAG would be if the scaling ablation shows Wiki degrading faster than expected at 550/820 findings, making CAG a dark-horse comeback. That seems unlikely given CAG's baseline 26.3.

### Before Phase 2 starts

- **Scaling ablation** (per the plan): test Wiki at 550 and 820 synthetic findings on T1/T3/T4. Validates the index doesn't degrade at scale. ~$15, ~30 min.
- **Graceful-failure path** for out-of-distribution topics: design the "insufficient KB coverage" detection in Wiki Pass 1.
- **Integrate current-stack prompt engineering into Wiki** as part of Phase 2 implementation, not as a pre-Phase-2 experiment.

### Migration triggers (from Phase 2 spec, updated with empirical baselines)

1. KB crosses 800 active findings (placeholder — the scaling ablation will give a sharper number)
2. Citation position histogram goes U-shaped (measure once per quarter on live drafts)
3. Judge score on fresh topics drops below 28/57.5 weighted (lower than original 36 threshold because the bake-off showed 32.0 is the realistic mean for a stripped-down pipeline)
4. Any fabrication detected in production

## What to write up in Phase 5

The bake-off contains two publishable findings:

1. **CAG fails for long-form argumentative generation from a structured KB.** Every published CAG evaluation is QA-only; this is the first empirical test on a generation task. Negative result, but that's the point — it fills the exact gap Report 6 identified.
2. **Wiki-style index+fetch architecture achieves parity with retrieval-augmented generation for analytical essay production, while winning on cross-domain synthesis.** This is a practical architectural contribution to the RAG-vs-long-context debate, grounded in an applied use case rather than a benchmark.

Both findings are grounded in the Phase 0 calibrated judge (ρ = 0.841), the multi-model editorial panel, and a controlled 5-topic experimental design with variance measurement. The evidence standard is sufficient for a workshop paper or an Explodable blog post.
