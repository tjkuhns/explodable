# RAG coherence metrics don't measure what readers feel

**No standard RAG evaluation framework — RAGAS, ARES, or retrieval precision/recall — includes any metric for discourse coherence.** They measure whether claims are grounded in retrieved context (faithfulness), whether the right chunks were fetched (context precision/recall), and whether the answer addresses the question (relevancy). None captures whether the output reads as a coherent essay. For a behavioral-science B2B editorial workflow, this means standard benchmarks will not tell you if Pipeline B produces better *writing* than Pipeline A.

## What each metric actually computes under the hood

**RAGAS faithfulness** decomposes an answer into atomic claims, then checks each claim's entailment against retrieved context — pure fact-grounding, no discourse awareness. **RAGAS answer relevancy** generates synthetic questions from the answer and measures cosine similarity to the original query — topical alignment only. **Context precision and recall** evaluate whether the retriever surfaced the right chunks, using LLM-judged binary relevance. **ARES** fine-tunes a DeBERTa classifier on synthetic data for those same three dimensions (context relevance, faithfulness, answer relevance), then applies Prediction-Powered Inference for confidence intervals. None of these will change score if you shuffle every paragraph in the output.

**G-Eval** is the exception. It prompts GPT-4 with evaluation criteria (e.g., the DUC coherence definition: "should build from sentence to sentence to a coherent body of information"), auto-generates chain-of-thought evaluation steps, then probability-weights the score across token logits. It achieved **Spearman ρ = 0.582** with human coherence judgments on SummEval — the highest reported for any automated metric.

## The gap is empirically large and well-documented

The G-Eval paper provides the clearest evidence: **ROUGE-L correlates at ρ = 0.128 with human coherence ratings** — functionally random. BERTScore reaches only 0.284. ROUGE and BLEU produce *identical scores* for sentence-shuffled text versus the original, since n-gram counts are order-invariant. Reiter's structured review of 284 correlations across 34 papers concluded that BLEU "poorly correlates with human judgments for NLG" and recommended a minimum threshold of ρ ≥ 0.7 for a useful surrogate metric — a bar no current coherence metric clears.

Even G-Eval's 0.582 falls short, and it introduces **self-preference bias**: GPT-4 consistently rated GPT-3.5 summaries higher than human-written ones, even when human judges preferred the human versions. UniEval (ρ = 0.575) and BARTScore (ρ = 0.448) sit between the extremes but remain below Reiter's threshold.

## Approaches that get closer to reader experience

Three categories show promise. **LLM-as-judge with structured rubrics** (G-Eval style) delivers the best automated correlation and can be customized with editorial-specific criteria. **BooookScore's eight-type coherence error taxonomy** — entity omission, causal omission, discontinuity, salience errors, duplication, inconsistency, incorrect coreference, language errors — is the closest published framework to editorial quality assessment, achieving **78.2% precision** matching human annotators. **DiscoScore**, a BERT-based metric grounded in Centering Theory, outperforms BARTScore by over 10 Kendall points at system-level coherence evaluation and ships with open-source code.

For structural checks, adjacent-sentence embedding similarity (the modern version of LSA coherence) is trivial to implement but penalizes stylistic diversity. Entity grid models capture local coherence transitions at ~87–93% discrimination accuracy. RST parsing captures deep discourse structure but is computationally prohibitive for regression testing.

## What actually works for single-author B2B editorial regression testing

For **900–1,500 word behavioral-science essays with a subjective editorial standard**, published benchmarks will not help. Build a custom LLM-as-judge harness. The editorial voice is the evaluation criterion, and only a rubric reflecting *your* editor's standards can capture it.

### Recommended one-day evaluation protocol

**Morning — build the rubric (3 hours).** Have your editor rank 10 existing essays by coherence quality, then articulate *why* in 3–5 specific criteria (e.g., "argument builds across sections," "behavioral-science concepts are introduced before applied," "transitions signal logical relationships"). Translate these into a G-Eval-style prompt with a 1–5 scale per criterion.

**Midday — calibrate the judge (2 hours).** Run the LLM judge (GPT-4 or Claude) on those 10 editor-ranked essays. Compute Spearman rank correlation between LLM scores and editor rankings. Iterate on prompt wording until ρ ≥ 0.7. If you cannot reach 0.7, add BooookScore-style error annotation (flag discontinuities, causal omissions, salience errors) and score on error counts instead.

**Afternoon — wire the regression test (3 hours).** Generate 5 essays from Pipeline A and 5 from Pipeline B using held-out queries. Run the calibrated judge on all 10. Use a paired comparison: for each query, does the judge prefer B over A? A 4/5 or 5/5 preference rate with consistent criteria scores constitutes a meaningful signal. Store prompts, rubrics, and scores in version control. This becomes your Phase 4 regression gate — rerun on every pipeline change, flag any query where the new pipeline scores lower on any criterion.

**Skip RAGAS for coherence.** Use it only for faithfulness and retrieval quality. Your editorial coherence signal must come from the custom judge.