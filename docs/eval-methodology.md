# How I built an eval harness that actually tracks editorial quality

Most LLM evaluation measures whether the model got the answer right. I needed to measure whether an AI-generated analytical essay was good enough for a fractional CMO to forward to their CEO. Those are different problems, and standard eval tools don't solve the second one.

This is the methodology I built, what it found, and where it broke.

## The problem: RAGAS doesn't measure coherence

I was building a content engine that produces long-form analytical essays (~1,000 words) from a structured knowledge base of behavioral-science findings. The engine worked — drafts scored 88/100 on voice compliance (BVCS). But some essays had sections that read like a second essay crammed in. A piece about B2B procurement fear would suddenly veer into identity theory for three paragraphs, then snap back. The voice was right. The argument wasn't.

Standard RAG evaluation metrics — RAGAS, ROUGE, BERTScore — wouldn't catch this. They measure retrieval relevance and surface-level text quality. They'd score a paragraph-shuffled draft the same as a coherent one. BVCS measures voice, not argument structure. I needed something that could tell me whether the essay held together as one argument.

## Building the judge

I designed a 10-criterion rubric grounded in published frameworks for analytical writing:

- **Minto Pyramid** — does the governing thought control every section?
- **BCG action-titles** — do headings work as standalone arguments?
- **Toulmin argument model** — does each section have claim, grounds, warrant, rebuttal?
- **Berger-Milkman sharing research** — would someone forward this?
- **David C. Baker expertise tests** — does this read like it comes from a specialist?

Each criterion is scored 1-5 by an LLM judge (Claude) using structured output. Three criteria are weighted 1.5x based on which dimensions the research literature says matter most for analytical writing that gets shared.

The judge uses a flat parallel-array schema instead of nested objects for the structured output. I discovered early that Opus serializes nested array fields with unescaped inner quotes — the same failure class that broke citation processing in an earlier pipeline version. Flat arrays work reliably.

## Calibrating against a 7-model panel

A judge is only useful if it tracks what humans would say. I didn't have a panel of human editors. So I built the next best thing: a panel of 7 independent LLMs, each ranking the same 12 drafts on the same criterion.

The criterion: "Would a fractional CMO be comfortable forwarding this piece to their CEO as evidence of why to hire the firm that produced it?"

The panel:
1. Claude Deep Research
2. Gemini 2.5 Pro
3. Grok 4
4. DeepSeek V3
5. Mistral Large
6. GPT-5
7. Qwen3

I batched all 12 drafts into a single ~44K token prompt and pasted it into each model's web UI. Total cost: $0. Each model returned a strict 1-12 ranking with one-sentence reasoning per draft.

## What the panel agreed on (and where it didn't)

Mean pairwise Spearman ρ across all 7 models: **0.544**. Not tight enough to use as-is. But the structure told a story:

Five models (Gemini, Grok, DeepSeek, Mistral, GPT-5) formed a tight cluster with internal mean pairwise ρ ≈ **0.83**. Two models were outliers:

- **Deep Research** (ρ = 0.261 vs others) was the only model that heavily penalized execution issues — leaked pipeline scaffolding, placeholder tokens, internal metadata in footnotes. It was applying a second axis the others collapsed.
- **Qwen** (ρ = 0.396 vs others) produced inconsistent rankings that didn't track any principled axis.

I dropped both outliers and used the 5-model tight cluster as the ground truth.

**The honesty note:** I chose to drop these models after seeing which ones disagreed, not before. A pre-registered protocol would have specified the drop criteria in advance. The ρ = 0.841 number I report below is real, but it's inflated by post-hoc outlier selection. I'd design this differently next time — specify the drop threshold before running the panel.

## Calibration result

The Claude Opus judge scored all 12 drafts against the 10-criterion rubric, and I computed Spearman ρ against the 5-model ground truth.

**ρ = 0.841.** Threshold was 0.7. Passed on first attempt.

For comparison, G-Eval (the most cited LLM-as-judge framework) reports ρ = 0.514 on SummEval. Most published LLM-as-judge work sits between 0.5 and 0.8. Our harness is at the upper end — though direct comparison is tricky because we're measuring different things on different data.

I later recalibrated on Claude Sonnet (8x cheaper per scoring call). Sonnet achieved **ρ = 0.782** against the same ground truth. Above the 0.7 threshold. This became the production judge for ongoing scoring.

## What the evaluation found when I used it

The harness exists to measure pipeline changes. Here's what it measured:

**Thesis-as-structural-schema vs standard prompting:** I encoded the brand thesis ("Buyers don't decide with logic. They decide with fear, then hire logic to testify") as a structural constraint in the outline stage — each section must instantiate the fear→testimony mechanism through three stages (fear-commit, logic-recruit, testimony-deploy), with Toulmin-complete micro-arguments per section and a derivation check verifying the thesis is derivable bottom-up from the section claims.

Result at N=50: **+8 points** for thesis-constrained outlines (38.2 mean) vs standard outlines (30.4 mean). This was the largest measured effect in the entire system — bigger than any retrieval architecture change.

**Three retrieval architectures bake-off:** I tested the current vector retrieval pipeline, Cache-Augmented Generation (full KB in context), and wiki-style index scanning on 5 topics scored by the calibrated judge.

- Vector retrieval (current stack): 32.6 mean
- CAG (full context, 115K tokens): 26.3 mean
- Wiki index scan: 32.0 mean

CAG lost on every topic. Every published CAG evaluation is on QA tasks — this appears to be the first measured result on a long-form generation task, and it's negative.

**Cross-domain synthesis:** Wiki index scanning scored +13 points over vector retrieval on a topic requiring synthesis across unrelated fields (B2B vendor lock-in × religious conversion psychology). The retriever's multi-query expansion clusters within one domain; the wiki index scan naturally reads across all categories.

## What I'd do differently

**Human validation.** The entire calibration is LLMs judging LLM output. Adding even 10-20 human rankings on a subset would break the circularity and make the methodology much more defensible.

**Pre-register the outlier criteria.** Dropping Deep Research and Qwen after seeing they disagreed is methodologically compromised. Next time: specify the agreement threshold and drop criteria before running the panel.

**Larger N for architecture comparisons.** The +13 cross-domain result came from N=5 topics. At N=50, cross-domain scored 32.2 with a wide confidence interval (27.7-36.7). The improvement is real but noisier than one run suggested.

**Separate content quality from execution polish.** Deep Research was the only panel member that penalized leaked pipeline scaffolding. The calibrated judge doesn't reliably catch execution issues (placeholder tokens, exposed metadata). I built a separate deterministic gate for that — a grep-based pre-flight checker that catches specific patterns. Two axes, two tools.

## The harness in practice

The eval harness is now a standard part of the pipeline. Every draft gets scored. Every architecture change gets measured against the 50-topic test set. The harness doesn't tell me if an essay is good — it tells me if a change made things better or worse, reliably enough to make engineering decisions on.

The rubric, the judge implementation, and the calibration data are all in the repo. The rubric is at `config/rubrics/analytical_essay.yaml`. The judge is at `src/content_pipeline/eval/judge.py`. The calibration result is documented in `docs/phase0_calibration_result.md`.

If you're building an eval harness for your own content pipeline, the three things that mattered most:

1. **Calibrate against multiple models, not one.** A single judge has systematic biases you can't see. Five independent rankings surface the biases through disagreement.
2. **Separate the axes.** Content quality and execution polish are orthogonal. Don't try to measure both with one rubric.
3. **Report honestly when the numbers don't hold.** The +13 cross-domain result was real at N=5. At N=50, it's +9 with wide variance. Both numbers are in the repo. The honest version is more useful than the impressive version.
