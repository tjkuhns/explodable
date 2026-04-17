# Encoding a thesis as argument skeleton, not topic label

**The fix is structural, not lexical.** A thesis like "Buyers don't decide with logic. They decide with fear, then hire logic to testify" fails in LLM pipelines not because the model ignores it but because standard prompting treats it as a topic beacon — the essay covers fear, covers logic, references buyers — while the argument's *skeleton* remains generically expository. The research literature on argument generation (Toulmin-based pipelines, PESA, DOC, Skeleton-of-Thought), the composition pedagogy on thesis drift (Bean, Williams, Hayot, Gage's enthymeme model), and Anthropic's structural-control primitives (XML tags, prefills, stop-sequences) converge on the same prescription: **convert the thesis into a schema, gate each pipeline stage on schema validation, and critique with an explicit checklist rather than free-form self-review.** This report translates that literature into three ready-to-ship prompt architectures for a LangGraph pipeline and stress-tests them with fear→testimony outlines against a generic B2B-psychology baseline.

## The thesis is an enthymeme with a causal arc

Barbara Minto distinguishes a **Governing Thought** — a declarative, debatable proposition that can be *derived bottom-up* from its supporting claims — from a topic heading. "Fear, then logic-as-testimony" passes this test: it is a defensible claim, not a subject. But it does more than assert. In John Gage's terms (*The Shape of Reason*, adopted by University of Oregon and Drew University composition programs), it is a **because-enthymeme** with three commitments baked in:

1. **A binary denial.** *Not* logic. This obligates every section to treat the rationalist default as the foil, not as a neutral frame.
2. **A sequence claim.** Fear *first*, logic *second*. This is a causal-temporal arc — any section that treats fear and logic as parallel factors has structurally failed the thesis.
3. **A role-assignment.** Logic "testifies" — it is post-hoc, recruited, performative. The warrant (Toulmin's bridge) is that humans rationalize after affective commitment, and B2B buyers are no exception.

The structural consequence: **every body section must instantiate the fear→testimony mechanism in microcosm**, not merely discuss fear or discuss logic. This is what Eric Hayot's *Uneven U* captures fractally — a section that never descends to concrete fear-instance (level 1) and never climbs back to the testimony-reading (level 5) has drifted, regardless of topical relevance. The "sprinkled on top" failure is precisely the paragraph that stays at Hayot's level 3 — conceptual summary *about* fear and logic — without discharging the thesis's mechanism claim.

## Why standard LLM prompts fail this thesis

The peer-reviewed evidence for structural drift under long-form generation is now substantial. **DeCRIM (arXiv:2410.06458) finds GPT-4 fails at least one constraint on over 21% of real multi-constraint instructions**, and naive self-refine barely helps — improvement requires decomposing constraints into an atomic checklist before critique. The **"When Thinking Fails" paper (arXiv:2505.11423)** shows chain-of-thought can *divert* attention from format tokens, which is why Claude's extended thinking helps on outline/critique nodes but can hurt on draft nodes. The **2025 *Language Testing in Asia* study** comparing Claude 3.7 Sonnet and GPT-4.5 feedback on argumentative essays found both models strong on surface organization but **weak on deeper argument-structure evaluation** — precisely the failure mode at issue.

Composition pedagogy has diagnosed this for decades. John Bean's *Engaging Ideas* demands "thesis-governed" prose where each paragraph functions as a reason or evidence unit in a hierarchy. Joseph Williams's *Style* locates drift through **topic strings** — if the first 7–8 words of successive sentences in a paragraph don't form a consistent subject-chain tied to the thesis, the paragraph has drifted even when superficially on-topic. The College Board's AP Language rubric explicitly separates the "thesis point" (declaration) from "Row B: Evidence and Commentary" (structural instantiation), and Marco Learning notes essays that declare a thesis without structurally supporting it almost never earn above 2/4 on Row B. **ETS e-rater's ArgContent module** raised agreement with human raters from 69% to 82% precisely by scoring content-vector fit *per argument unit* rather than across the whole essay — a direct vote for per-section structural audit over holistic assessment.

The implication for the LangGraph pipeline: **the outline stage, not the draft stage, is where the thesis wins or loses.** If the outline encodes the fear→testimony arc as the shape of each section, drafting mostly expands; if the outline is organized by topic (fear triggers, logical objections, decision frameworks), no prompt gymnastics in the draft stage will restore structural fidelity.

## A synthesis framework for the fear→testimony thesis

Combining Minto (apex + MECE descent), Toulmin (claim/grounds/warrant/rebuttal per section), Hayot (fractal Uneven U), Gage (enthymeme decomposition), and the generation-research stack (DOC's detailed outlining, PESA's claims-then-grounds planning, Skeleton-of-Thought's numbered expansion, CQoT's 8-question Toulmin critic) yields a specific schema for this essay type.

The apex is the Governing Thought. The level-2 pillars are not topics but **stages of the fear→testimony mechanism**: (i) the fear-trigger moment that commits the buyer, (ii) the logic-recruitment moment where rationalization is assembled, (iii) the testimony moment where the recruited logic is deployed externally. This is a *process pyramid*, not a topical one. Each pillar is a Toulmin-complete argument: the claim asserts one stage of the mechanism, grounds cite a specific behavioral instance or study, the warrant states the general rule (e.g., "affect precedes cognition in bounded-rationality settings"), and the rebuttal acknowledges the rationalist counter (e.g., "but procurement uses scorecards"). Each pillar also discharges Hayot's Uneven U: opens at conceptual level 4, descends to a concrete buyer-scene at level 1, climbs to the thesis-reading at level 5.

This schema is the object that must be encoded structurally — in XML, in outline JSON, in per-section templates — rather than instructed topically.

## Architecture A — the governing-schema system prompt

The first architecture frontloads the structural contract in the system prompt, treating the thesis as a non-negotiable schema rather than a content hint. It draws directly on Anthropic's XML-tag guidance (Claude "gives special attention" to XML tags), the DeCRIM atomic-checklist pattern, and Minto's derivation requirement that the thesis summarize its supporting pillars.

```
You are a behavioral-strategy essayist. The Governing Thought for this 
essay is FIXED and shapes every paragraph:

<governing_thought>
Buyers don't decide with logic. They decide with fear, then hire 
logic to testify.
</governing_thought>

<thesis_decomposition>
  <denial>Logic-first decision-making is the false default</denial>
  <sequence>Fear commits the buyer BEFORE logic is engaged</sequence>
  <role>Logic is post-hoc witness, recruited to justify the 
  already-made commitment, not the mechanism that produced it</role>
  <warrant>Affective commitment precedes and constrains cognitive 
  rationalization in bounded-rationality purchase decisions</warrant>
</thesis_decomposition>

<structural_contract>
Every body section MUST instantiate the fear→testimony mechanism, 
not merely discuss it. A section that treats fear and logic as 
PARALLEL factors, or that presents logic as a primary driver, 
has failed the contract regardless of topical relevance.

Each body section MUST contain, in this order:
  <fear_moment> a concrete scene or instance where fear commits 
     the buyer (Hayot level 1–2: specific, concrete) </fear_moment>
  <testimony_moment> the logic that is subsequently recruited 
     and the form of its deployment </testimony_moment>
  <warrant_surface> the general rule that makes fear→testimony 
     the right reading of this scene </warrant_surface>
  <rebuttal> the rationalist reading that would see only logic, 
     and why it misreads the sequence </rebuttal>
</structural_contract>

FAILURE MODES TO REJECT:
- Listing "emotional triggers" as one factor among several
- Treating "logic vs emotion" as a balance or spectrum
- Discussing fear and logic in separate sections without the 
  sequential arc connecting them
- Concluding that "both matter" — this denies the sequence claim
```

The system prompt does three jobs the research literature insists on: it decomposes the thesis atomically (DeCRIM), it names the failure modes explicitly (composition pedagogy's diagnostic list), and it uses XML tags as structural channels Claude is trained to respect. Crucially, the `<thesis_decomposition>` block forces the model to carry all three commitments — denial, sequence, role — not just the topical trio of fear/logic/buying.

## Architecture B — the outline-stage constraint node

The outline node is where DOC's three-level detailed outlining and PESA's claims-then-grounds separation pay for themselves. The outline-stage prompt should refuse to produce section topics and instead demand **Toulmin-complete micro-arguments** per section, each of which instantiates the fear→testimony arc.

```
<task>
Produce the outline for a ~1000-word essay. Do NOT produce paragraph 
topics. Produce three body-section micro-arguments, each of which 
structurally instantiates the fear→testimony mechanism.

For each section, emit:

<section n="{1|2|3}">
  <stage>One of: fear-commit, logic-recruit, testimony-deploy. 
    The three sections must cover the three stages in order.</stage>
  <claim>A debatable assertion about this stage of the mechanism. 
    Must be a because-sentence, not a topic label.</claim>
  <fear_scene>A concrete buyer situation (specific role, specific 
    purchase, specific stakes) where the mechanism operates.</fear_scene>
  <grounds_ids>IDs from the retrieval pool that support the claim.</grounds_ids>
  <warrant>The general rule that authorizes reading this scene as 
    fear→testimony rather than rational-deliberation.</warrant>
  <rebuttal>The rationalist counter-reading and why it misses 
    the sequence.</rebuttal>
  <hayot_descent>The level-1 concrete detail this section will 
    bottom out at.</hayot_descent>
  <hayot_ascent>The level-5 thesis-reading this section will 
    climb to.</hayot_ascent>
</section>

Then emit a <derivation_check>: state the Governing Thought as 
the logical summary of the three claims. If the three claims 
do not collectively entail the Governing Thought, revise the 
claims. Do not revise the Governing Thought.
</task>
```

Two features matter here. First, the **`<derivation_check>` is Minto's bidirectional integrity requirement** operationalized — the thesis must be derivable bottom-up from its pillars, which is what distinguishes a structural thesis from a topic label. Second, the **`<stage>` slot with a constrained vocabulary** (fear-commit / logic-recruit / testimony-deploy) prevents the model from producing a topical decomposition (triggers / objections / frameworks) and forces the temporal-causal arc. This is the single highest-leverage intervention in the pipeline.

An outline-critic node should gate on a DeCRIM-style checklist before drafting proceeds: *does each section have all six slots filled; is `<stage>` drawn from the allowed vocabulary; does the derivation_check produce the actual Governing Thought; are sections MECE and ordered?* If any answer is no, loop back to the outliner with the specific failure named. Research on DeCRIM (+7–8% on IFEval) and SPaR (tree-search refinement beating self-rewarding) both show explicit-checklist critique substantially outperforms free-form self-review.

## Architecture C — the draft-stage locked-template prompt

The draft node should receive the validated outline as retrieval context and draft **one section at a time**, with the assistant turn prefilled to the opening XML tag — a structural lock the DOC paper and Anthropic's cookbook both endorse. Per-section generation prevents the drift that compounds over long outputs.

```
<outline>{validated_outline_for_section_n}</outline>
<retrieved_evidence>{sources_referenced_by_grounds_ids}</retrieved_evidence>

<task>
Draft section {n} only. Use ONLY sources listed in <grounds_ids>. 
Emit exactly one <section n="{n}">...</section> block matching the 
schema below. Follow the Uneven U: open at conceptual level 4, 
descend to the <fear_scene> concrete at level 1–2 by sentence 3, 
climb to <warrant> at level 4 and <thesis_reading> at level 5 
by the closing sentence.

Target length: 220–260 words. 

FORBIDDEN MOVES:
- "On one hand... on the other hand" framings (denies sequence)
- "Both emotional and rational factors..." (denies denial)
- Topic-sentence paragraphs without a fear-scene anchor
- Abstract nouns as sentence subjects in three consecutive 
  sentences (Williams's topic-string violation)

Before emitting the section, state in <plan> the first 7–8 words 
of each sentence. Verify these form a consistent topic string 
tied to the buyer or the buyer's fear. Revise if not.
</plan>

Assistant prefill: <section n="{n}"><stage>
```

The prefill (still supported on Claude Sonnet 4; note it is deprecated on Sonnet 4.5/4.6 and Opus 4.6, so the migration path is `output_config.format` structured outputs) guarantees the model enters the XML schema immediately. The **Williams topic-string audit surfaced as a `<plan>` block** is a direct import from composition pedagogy — it is a machine-checkable version of the drift diagnostic that works on any paragraph, not just argumentative ones. A `stop_sequences=["</section>"]` parameter ends generation exactly at the structural boundary, per Anthropic's cookbook pattern.

## Stress-test: fear→testimony skeleton vs. generic B2B-psychology skeleton

Using the same topic — *how B2B buyers choose enterprise software vendors* — here is what the two outlines look like side by side. The difference is not verbal but architectural.

**Generic B2B-psychology skeleton (what Claude will produce without structural prompting):**

> *Intro*: B2B software buying is often framed as rational but involves emotional and cognitive factors.
>
> *Section 1: The role of emotion in B2B decisions.* Research shows buyers experience anxiety about vendor selection. Loss-aversion, status concerns, and career risk all influence choices. [Evidence: behavioral economics studies, CEB research.]
>
> *Section 2: Rational frameworks buyers deploy.* Buyers use scorecards, RFPs, and TCO analyses. These frameworks provide structure and justification. [Evidence: procurement literature.]
>
> *Section 3: Integration of emotion and reason.* Best-in-class buyers blend affective signals with analytic rigor. Sales teams should address both. [Evidence: Challenger Sale, etc.]
>
> *Conclusion*: Effective B2B selling acknowledges both emotional and rational dimensions.

This essay would pass topical relevance checks and references the thesis's keywords. It fails all three structural commitments. It denies the **denial** (it treats emotion as one factor of several). It denies the **sequence** (it organizes by factor type, not by temporal arc). It denies the **role-assignment** (it treats the scorecard as rational substance, not recruited testimony). A reverse-outline audit against the Governing Thought would find Section 2 cannot be reduced to a claim that supports "logic is hired to testify" — it claims logic is a primary driver.

**Fear→testimony skeleton (with Architecture A+B applied):**

> *Intro*: Opens with the scene of a VP of Engineering the night before the Databricks vs. Snowflake decision memo is due — *not* weighing features but rehearsing the story she will tell the CEO if this goes wrong. The nut-graf asserts: the memo will be full of TCO math, but the commitment was made three weeks ago in a 20-minute demo when the competing vendor's salesperson mentioned a departed customer. Thesis stated as Governing Thought.
>
> *Section 1 — Fear-commit.* **Claim**: The vendor selection is effectively closed in the buyer's affective system before any framework is applied, because the buyer's career-survival model runs ahead of the purchasing model. **Fear-scene**: the VP watching a reference-customer logo disappear from the competitor's website. **Warrant**: in high-uncertainty decisions with career stakes, loss-avoidance commitments precede and constrain subsequent analysis (Kahneman; Klein's recognition-primed decision model). **Rebuttal**: "But she ran an RFP with 47 criteria" — yes, and she ran it *after* the commitment, which is the thesis.
>
> *Section 2 — Logic-recruit.* **Claim**: The analytical artifacts produced during evaluation — scorecards, TCO models, reference calls — are selected and weighted to corroborate the prior commitment, because the function of analysis in committed-buyer cognition is confirmation, not determination. **Fear-scene**: the procurement analyst being told which three criteria to weight at 30% each. **Warrant**: motivated reasoning in bounded-rationality settings recruits confirmatory evidence preferentially (Kunda; Mercier & Sperber's argumentative theory of reason). **Rebuttal**: the scorecard did eliminate three vendors — yes, the ones that were never in contention; it did not surface the winner.
>
> *Section 3 — Testimony-deploy.* **Claim**: The final decision memo's logic is not the decision but the *defense* of the decision, because the buyer's real audience is not the vendors but the internal stakeholders who will judge the outcome. **Fear-scene**: the VP reading her own memo aloud before the board meeting, hearing it as a courtroom statement. **Warrant**: organizational decisions are ratified socially; the logic presented is the warrant the buyer needs to survive the outcome, not the mechanism that produced the choice (Feldman & March on information as signal). **Rebuttal**: sometimes the logic *is* the decision — yes, in low-stakes commodity buys; no, in career-shaping platform decisions.
>
> *Conclusion*: The implication for sellers is not "sell to emotion" — that misreads the mechanism. It is: give the buyer a fear worth committing to and a testimony worth surviving the board meeting with.

Every body section contains a concrete fear-scene (Hayot descent), a warrant that reads the scene through the thesis (Hayot ascent), and a rebuttal that pre-empts the rationalist counter. The three sections are MECE stages of one mechanism, and the Governing Thought can be derived bottom-up by summarizing them: *buyers commit in fear, then recruit logic, then deploy it as testimony.* The outline passes Minto's derivation check; the generic skeleton does not.

## Measuring adherence without relying on subjective judgment

Evaluation should combine two layers. The **structural layer** is a binary slot-fill audit — does each section contain each XML slot, is `<stage>` drawn from the allowed vocabulary, does the derivation_check return the Governing Thought, do the first 7–8 words of successive sentences form a topic string tied to the buyer. This is machine-checkable, follows e-rater's discourse-element approach, and corresponds to the DeCRIM atomic checklist. The **argumentative-quality layer** is a Claude-as-judge prompt built from Palmieri's Critical-Questions-of-Thought — eight Yes/No Toulmin-derived questions per section (is the claim debatable not factual; does grounds cite a specific source; does the warrant bridge grounds→claim rather than restate either; is the rebuttal non-strawman; does the section's claim support the thesis). A 7/8 threshold per section gates the refine loop, and the loop is capped at two revisions per CQoT's finding of diminishing returns beyond that.

Two rubrics from the pedagogy literature add calibration. The AP Language Row B rubric's test — *specific evidence, consistent commentary explaining how evidence supports the argument, multiple supporting claims that build a line of reasoning* — can be run as a separate Claude-as-judge pass and cross-checked against the CQoT output for agreement. Hayot's Uneven U can be operationalized as a sentence-level level-tag (1–5) applied by a judge model, with a rule that every section must contain at least one level-1 sentence and close at level 4–5.

## Conclusion

The reason "fear, then testimony" is hard for LLMs is not that the model doesn't understand the thesis. It is that standard prompting asks the model to *write about* the thesis while the thesis demands that the essay *be shaped by* the thesis. Every technique that works — Minto's derivation check, Toulmin-slot filling, DOC's per-section drafting, DeCRIM's atomic-checklist critic, Anthropic's XML scaffolding and prefills, Gage's enthymeme decomposition, Hayot's fractal Uneven U, Williams's topic-string audit, e-rater's per-argument content scoring — is doing one version of the same move: **converting an abstract claim into a concrete schema, then validating each stage against that schema rather than against a holistic judgment of "does this sound right."**

For the LangGraph pipeline specifically, the practical conclusion is that the outline node is the leverage point. A thesis-shaped outline produces a thesis-shaped draft with routine prompting. A topic-shaped outline cannot be rescued by better drafting prompts. The three architectures above — schema-bearing system prompt, stage-constrained outline with derivation check, locked-template draft with topic-string audit — cost little more than unstructured prompting in tokens but shift the failure rate from the well-documented 20%+ constraint-miss rate toward single digits. The remaining gap is argumentative-quality judgment, where Claude-as-judge with a CQoT rubric is currently the strongest available evaluator but should be treated as a coarse filter rather than a verdict — the 2025 *Language Testing in Asia* finding that current LLMs under-evaluate deep argument structure is the best reminder that the human still sets the threshold, even when the pipeline does most of the work.