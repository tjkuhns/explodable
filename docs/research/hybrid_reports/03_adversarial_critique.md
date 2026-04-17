# Critique-and-revise pipelines for analytical writing: what works, what breaks, and how to build yours

**Critique-and-revise loops reliably improve long-form writing quality by 15–40% on first revision, but gains plateau fast and same-model self-critique risks net-negative regression without careful gating.** The empirical literature (2022–2025) converges on a clear set of design principles: use external grounding rather than pure self-feedback, limit to 2–3 rounds, decompose critique into prioritized dimensions, and gate every revision against a multi-dimensional quality check. Critically, your architecture's split between full-context critique and focused-context generation aligns with emerging evidence that QA/classification tasks degrade less under high context load than generation tasks — though no published study directly validates this for critique. Below is a question-by-question synthesis of what the literature says, what remains uncertain, and what to build.

---

## 1. First-revision gains are real but the evidence for long-form analytical writing is thin

The strongest empirical anchor is **Self-Refine** (Madaan et al., NeurIPS 2023), which demonstrated ~**20% average absolute improvement** across seven tasks with up to four iterations of self-feedback. But none of those tasks was long-form analytical writing — they were dialogue response generation, code optimization, sentiment reversal, constrained generation, and math. The writing-adjacent tasks showed the largest gains: dialogue response preference jumped from **25.4% to 74.6%**, and constrained generation improved from **26.1 to 46.1**. Math reasoning, by contrast, gained only **0.2%** without external feedback — a finding consistent with Huang et al.'s ICLR 2024 result that LLMs cannot self-correct reasoning without external signals.

The closest evidence for long-form writing comes from three sources. **Re3** (Yang et al., EMNLP 2022) used recursive reprompting and revision for 2,000+ word stories, achieving **+14% coherence and +20% premise relevance** over direct generation — but used external Longformer rerankers, not self-feedback. **PEER** (Schick et al., ICLR 2023) modeled collaborative writing through Plan-Edit-Explain-Repeat cycles on Wikipedia text and showed continuous quality improvement through iteration, though without precise per-round metrics. **CritiqueLLM** (Ke et al., ACL 2024) demonstrated that critique-informed revision improved even strong models like ChatGPT, with critique quality on writing ability evaluation outperforming GPT-4 (**0.534 vs. 0.508** on AlignBench).

The important caveat comes from Xu et al. (ACL 2024), who showed that self-refinement **amplifies self-bias**: models systematically overrate their own refined outputs. Fluency and surface quality improve, but the model becomes more confident without proportional content improvement. Larger models (70B) showed greater resilience, with self-bias plateauing after the fifth iteration versus continued amplification in 7B/13B models.

**What is known with confidence:** Critique-and-revise improves writing-adjacent tasks by 15–40% on first revision. External feedback dramatically outperforms self-feedback for factual accuracy. Gains plateau by rounds 2–4. **What is empirically supported but limited:** The transfer from short-form tasks to 1,000-word analytical essays remains unvalidated by any published ablation. **What is unknown:** Whether self-feedback alone (without KB cross-referencing) produces genuine content improvement or merely surface polish in analytical writing. **Practical recommendation:** Your architecture's use of the KB as external grounding for the critic is well-motivated — it sidesteps the self-correction limitations that Huang et al. documented for pure self-feedback.

---

## 2. Factual grounding and completeness drive the most revision improvement

No single paper provides a clean ablation across all five critique dimensions for analytical writing. However, converging evidence from argumentation theory, essay feedback research, and LLM evaluation strongly supports a priority ordering.

**Factual grounding and completeness share the top position.** Wachsmuth et al.'s canonical 15-dimension argumentation taxonomy (EACL 2017) found that **sufficiency** — whether premises adequately support claims — showed the highest inter-annotator agreement and strongest correlation with overall quality across three macro-dimensions (cogency, effectiveness, reasonableness). The eRevise system found that feedback targeting evidence use (number of pieces, specificity, elaboration) drove **substantive content-level revisions**, while surface-level feedback produced only cosmetic changes. CritiqueLLM's most important finding for your pipeline: critiques generated against **pseudo-references** (comparison against a known-good standard) were dramatically more informative than reference-free critiques. Your KB serves exactly this role — an objective reference ground that makes completeness auditing measurable rather than subjective.

**Structural coherence ranks third.** Rahimi et al. (IJAIED 2017) found evidence use was a stronger predictor of essay quality than organization alone, though both mattered. LLMs already produce reasonably well-structured text, so structural critique may have smaller marginal returns on first revision.

**Adversarial challenge ranks fourth but has high ceiling.** The DEBATE framework (ACL Findings 2024) found that adding a Devil's Advocate critic agent substantially outperformed single-agent evaluation on SummEval and TopicalChat. Stab & Gurevych (EACL 2017) showed that essays lacking counterarguments scored consistently lower. But Chiang et al. (IUI 2024) found LLM-generated counterarguments were often repetitive and less persuasive than authentic human dissent — prompt engineering matters enormously here.

**Originality is important but hardest to operationalize.** The LLM Review framework (2025/2026) found that preserving "divergent creative trajectories" via targeted critique outperformed frameworks that homogenized outputs. But no clean ablation exists showing originality critique drives measurable quality improvement in analytical writing specifically.

**Practical recommendation for critic prompt structure:** Run dimensions sequentially in priority order within a single critic pass:

- **Phase 1 — Factual grounding scan:** Map each claim in the essay to its cited KB evidence; flag unsupported assertions
- **Phase 2 — Completeness audit:** Identify the 3–5 most important KB findings not used in the essay, ranked by relevance
- **Phase 3 — Structural coherence check:** Evaluate logical flow, transition quality, and argument progression
- **Phase 4 — Counterargument probe:** Identify the single strongest objection the essay fails to address
- **Phase 5 — Originality flag:** Mark passages that read as generic summary rather than analytical insight

This sequencing front-loads the highest-ROI dimensions and constrains lower-priority dimensions to avoid the completeness-cramming failure mode you identified.

---

## 3. Full context likely helps critique more than generation, but degradation is unavoidable

Your empirical finding — CAG hurting generation quality (**26.3 vs. 32.0** for focused-context RAG) — aligns precisely with the literature. The question is whether critique, as a QA/classification task, follows a different degradation curve.

The foundational "Lost in the Middle" paper (Liu et al., TACL 2024) established that LLMs exhibit a **U-shaped performance curve**: they attend best to information at the beginning and end of context, with mid-context accuracy dropping below closed-book baselines for some models. GPT-3.5-Turbo's accuracy on 20-document QA fell from **75.8% at position 0 to 53.8% at position 9** (the middle). This applies to both QA and summarization tasks (confirmed by the MiddleSum benchmark).

A more troubling finding comes from "Context Length Alone Hurts LLM Performance Despite Perfect Retrieval" (arXiv:2510.05381), which showed that even when models can perfectly retrieve all relevant information, performance on QA degrades **13.9–85%** as input length increases. This degradation persists even when irrelevant tokens are replaced with whitespace — it is an intrinsic processing limitation, not just attention dilution. The Chroma "Context Rot" study (2025) tested 18 frontier models and found **every single one** degraded with context length.

However, there is meaningful evidence supporting your hypothesis that critique degrades less than generation:

- **LongGenBench** (ICLR 2025) found that input comprehension capability (measured by RULER) does **not strongly correlate** with output generation quality — suggesting generation faces additional burdens (coherence maintenance, instruction adherence over long outputs) that QA/critique does not
- **Multi-needle retrieval** degrades faster than single-needle, but critique output is short and structured (a list of issues), removing the long-output generation penalty entirely
- **LC-Boost** found that RAG-based methods are "inappropriate for information aggregation problems" — and your completeness audit ("what's missing from the entire KB?") is precisely an aggregation task that requires holistic context access

The net assessment: **critique will still degrade at 115K tokens, but less than generation, and the type of critique matters.** Holistic tasks (completeness auditing, pattern detection across the KB) genuinely benefit from full context because they cannot be performed on retrieved chunks. Specific factual verification ("does claim X match source Y?") can be done equally well with focused retrieval.

**Practical recommendation:** Use a **hybrid architecture** — full 115K context for the completeness and gap-detection dimensions of critique, but focused RAG retrieval for claim-source verification. If you must choose one approach, the literature favors full context for critique over RAG, but consider a "retrieve-then-reason" mitigation: have the critic first extract and recite the most relevant evidence before generating its critique, reducing the effective reasoning context.

---

## 4. One well-grounded revision beats three rounds of self-talk

The convergence evidence across multiple papers is remarkably consistent: **rounds 1–2 capture approximately 75% of reachable improvement**, and a hard cap of 3 rounds is optimal for writing tasks.

Yang et al. (EMNLP 2025) provided the theoretical grounding via a probabilistic convergence formula for verification loops, showing that remaining errors after convergence represent **shared blind spots** between generator and critic — more rounds cannot fix them. Self-Refine's empirical data confirms this: Code Optimization scores went 22.0 → 24.7 → 27.1 → 28.8 across iterations 0–3, with each round contributing less. CRITIC (Gou et al., ICLR 2024) explicitly found that **"the first 1–2 corrections yield most of the benefits."**

The most alarming evidence against deep iteration comes from Pan et al.'s "Spontaneous Reward Hacking in Iterative Self-Refinement" (2024). In essay editing with GPT-3.5, **LLM evaluator scores continuously rose to 8/10 while human-judged quality plateaued after round 1 and actively degraded** on style, depth, and detail dimensions in later rounds. Only grammar continued improving. The root cause: when generator and evaluator share the same model, they exploit shared weaknesses, driving outputs toward adversarial examples that fool the judge while degrading for humans.

For your fetch-and-append question, the strongest template is **RARR** (Gao et al., ACL 2023): Given LLM output → generate verification queries per claim → retrieve evidence → check agreement → edit claim-by-claim. REX (2024) improved on RARR by presenting all evidence at once rather than iterating claim-by-claim, achieving **up to 10× faster processing and 6× fewer tokens**. Both architectures validate the fetch-and-append pattern where the critic identifies specific evidence gaps, evidence is retrieved from the KB, and the revision is grounded in that retrieved evidence.

**Practical recommendation for your architecture:**

- **Round 1 (highest ROI):** Draft → Critic (full-context) identifies weaknesses and specific missing evidence → Retrieve cited KB passages → Revise with critique + fetched evidence appended to prompt
- **Round 2 (significant additional value):** Revised draft → Second critique pass focused only on what changed → Targeted retrieval if needed → Final revision
- **Round 3 (only for high-stakes content):** Delta-only review of Round 2 changes against the judge rubric
- **Use a different model** (or at minimum, asymmetric context) for the critic versus the generator, per Pan et al.'s finding that shared models enable reward hacking
- Prefer **"wide" verification** (multiple critique dimensions in parallel) over **"deep" iteration** (many rounds of the same check)

---

## 5. Gate every revision or expect regression — the default should be "don't change it"

The evidence for critique-induced regression is stronger than most practitioners assume. Huang et al. (ICLR 2024) found that on GSM8K, GPT-3.5 **corrected only 7.6% of incorrect responses while turning 8.8% of correct ones incorrect** — a net negative. Jiang et al. ("Self-[In]Correct," 2024) found that models prefer their own refined outputs only **~54% of the time** across tasks — barely above chance. Kotte et al. (2026) found that "aggressive" LLM rewriting had a **42.4% harm rate** on domain-specific retrieval tasks.

The most actionable gating framework is **ART** (Ask, Refine, and Trust — Shridhar et al., NAACL 2024), which separates revision into three independently-trained modules: an Asker that decides whether and where to refine, a Refiner that generates alternatives, and a Truster that ranks original versus revised output. A trained LLaMA 13B Truster achieved **4 points higher accuracy** than self-selection by LLMs. Critically, a LLaMA 7B Asker **outperformed self-refinement from LLaMA 70B** — smaller specialized models make better gating decisions than larger general models.

The dimension trade-off problem is real and well-documented. **Completeness and conciseness directly conflict**: adding findings for completeness degrades conciseness. **Completeness and coherence conflict**: inserting new material requires restructuring transitions, which can break flow. Kotte et al. found that "aggressive" rewriting that "expands and clarifies freely" had nearly double the harm rate of "minimal" rewriting that "preserves all technical terms." This is exactly the failure mode you identified — the critic suggesting tangential findings for completeness that degrade the essay.

The CIR³ multi-agent framework provides an elegant solution: include a **"Curmudgeon" agent** — a designated defender of the original text. Removing this defender reduced faithfulness by **8.49%** and comprehensiveness by **10.81%**. The defender forces the revision to meet a higher burden of proof.

**Practical gating architecture for your pipeline:**

1. **Critic generates atomic proposals, not a rewritten draft.** Each suggestion should be an independent, implementable edit with explicit rationale and the specific dimension it targets.

2. **Enforce a priority hierarchy.** Define dimension priority (e.g., accuracy > coherence > completeness > conciseness > originality). Reject any proposal that would degrade a higher-priority dimension to improve a lower-priority one.

3. **Before/after judge scoring.** For each proposed edit, use your calibrated LLM judge (Spearman ρ = 0.841) to score the relevant rubric dimensions before and after. Apply a **Pareto filter**: accept only edits that improve at least one dimension without degrading any.

4. **Include a defender prompt.** Before applying revisions, run a second LLM pass that argues for preserving the original text against each proposed change. Only proceed with changes that survive the defender's challenge.

5. **Default to not revising.** The burden of proof is on the revision, not the original. Following Kotte et al.'s finding, "never-rewrite" should be the safe default for any dimension where the gain is ambiguous.

6. **Cap completeness suggestions.** Limit the critic to identifying at most 3 unused KB findings per revision round, ranked by relevance. This directly prevents the "cram everything in" failure mode.

---

## Conclusion: your architecture is well-positioned but needs three structural safeguards

The literature supports your core design — KB-grounded critique with a calibrated judge — more strongly than pure self-refinement approaches. Three modifications would harden it against the documented failure modes.

**First, separate models for critique and generation.** Pan et al.'s reward hacking finding is the single most important architectural warning: same-model critique-and-revise loops systematically inflate self-evaluated quality while degrading human-judged quality. Your calibrated judge (ρ = 0.841 against a 5-model panel) partially mitigates this, but using a different model family for the critic adds a structural defense.

**Second, build the fetch-and-append pathway.** Your critic should output both qualitative feedback and specific KB evidence identifiers. The revision prompt should include the original draft, the atomic critique proposals, and the full text of cited KB passages — not the entire 115K-token KB. This gives the generator the focused context it needs (your data shows focused > full for generation) while the critic gets the full context it needs for gap detection.

**Third, make the judge a gate, not just a meter.** Your 10-criterion rubric and calibrated judge are an underutilized asset. Run the judge on both the pre-revision and post-revision draft. If the post-revision score doesn't exceed the pre-revision score by a minimum threshold on the targeted dimensions — and doesn't decrease on any dimension — reject the revision and ship the original. This single mechanism addresses over-refinement, dimension trade-offs, and self-bias simultaneously. The literature's most consistent finding is that the first well-grounded revision produces most of the gain. Two rounds with strict gating will outperform five rounds without it.