# Building an LLM-as-judge rubric for consulting-quality analytical writing

The strongest evaluative frameworks converge on a single insight: **diagnostic credibility is signaled in the first 100 words and sustained through structural moves that are well-documented but rarely combined into a single rubric.** The Minto Pyramid Principle, expertise-signaling research, and B2B sharing data all point toward specific, testable criteria that can reliably distinguish writing that commands $8–25K engagements from writing that gets filed and forgotten.

## The consulting canon prescribes exact structural moves

Barbara Minto's Pyramid Principle — McKinsey's writing standard since the 1970s — mandates that **the governing thought appears in the first sentence**, every subsequent idea summarizes the ideas grouped below it, and no cluster exceeds 3–5 arguments. The introduction follows SCQA (Situation-Complication-Question-Answer), where the Situation contains only things the reader already agrees are true, and the Complication "must raise a question the reader is already anxious about." Resolution takes **60–70%** of the content. BCG adds "one message per paragraph" and requires action titles that are complete sentences passing a "so what?" test — readers should grasp the argument from headings alone.

No controlled experiment has directly tested pyramid-structured versus bottom-up business writing. The empirical support is indirect: cognitive load theory confirms working memory handles only ~4 chunks (supporting the 3–5 argument rule), and meta-analyses show structured text improves comprehension. Nielsen Norman Group research finds **79% of professionals scan rather than read**, validating answer-first architecture.

**Rubric items:** Does the opening sentence name the governing thought? Are supporting arguments clustered in groups of 3–5, with MECE logic? Does the complication name a tension the reader already feels?

## Diagnostic expertise is signaled through pattern-naming, not framework-citing

David C. Baker's "Drop and Give Me 20" test — can you list 20 domain-specific truths without preparation? — operationalizes the difference between genuine and performed expertise. Baker argues that going "really, really deep" on one narrow topic signals equivalent depth everywhere else. April Dunford's positioning framework adds that expert writing makes the reader the hero, opening with their situation rather than the writer's methodology, and sets up context so the conclusion "feels inevitable rather than argued-for."

Roger Martin's integrative thinking provides the sharpest diagnostic: expert writers **hold two opposing models in tension and synthesize a third way** rather than choosing sides. They introduce variables others hadn't considered salient, reveal feedback loops that invalidate linear explanations, and refuse false binaries.

Empirically, Ambady and Rosenthal's thin-slicing research (r = .39 across 38 studies) confirms that expertise judgments form within seconds and barely change with more exposure — making opening moves disproportionately important. Research on linguistic markers of credibility identifies the "Goldilocks zone" of specificity: enough concrete detail to signal insider knowledge without over-explaining.

**Rubric items:** Does the piece name a pattern visible only through concentrated domain exposure? Does it show the writer's thinking evolving (what they initially assumed versus what they found)? Does it introduce a variable that changes the entire analysis?

## The "forward-to-CEO" test has empirical predictors

Edelman-LinkedIn's 2024 B2B Thought Leadership study (n ≈ 3,500) found that **60% of decision-makers** influenced by thought leadership realized their organization was missing a significant opportunity, while **29%** realized they were more vulnerable to a threat than expected. Berger and Milkman's foundational 2012 study (1,333+ citations) established that sharing is driven by **physiological arousal level**, not emotional valence — awe, anger, and anxiety drive transmission; sadness suppresses it. The forwarding act serves social currency: the forwarder signals competence and vigilance to the CEO.

Content that gets forwarded combines a **specific named threat backed by credible data** with a contrarian framing that makes the forwarder look sophisticated for spotting it. Demand Gen Report data shows **77% of B2B buyers** expect content specific to their situation; generic insight doesn't travel through dark social channels.

**Rubric items:** Does the piece name a specific threat or missed opportunity the reader's organization faces? Would forwarding it make the sender look smart? Is the arousal level high enough to trigger action (awe or anxiety, not resignation)?

## Contrarian framing works only in the moderate-incongruity zone

Paul Graham's formula — usefulness = correctness × importance × novelty × strength — explains when "buyers decide with fear" lands as insight versus bumper sticker. Research on schema incongruity shows an **inverted U-shaped pattern**: moderate incongruity increases recall and positive attitude; extreme incongruity triggers rejection. Burgoon's Expectancy Violations Theory adds that high-credibility communicators get the benefit of the doubt when violating expectations, while low-credibility ones do not.

Critically, belief perseverance research shows that **counter-explanation is the only effective debiasing technique** — simple assertion ("buyers are irrational") fails. The claim needs a specific causal mechanism (defensive decision-making, career risk, status quo bias). Gartner's finding that **80% of B2B decisions are influenced by emotional factors** and that 40–60% of B2B tenders end in "no decision" provides the evidential backbone that makes "buyers decide with fear" defensible rather than gimmicky.

**Rubric items:** Does the contrarian claim provide a specific causal mechanism? Does it fall in the moderate-incongruity zone — surprising but resolvable through self-recognition? Is the strength of the claim calibrated to the strength of its evidence?

## Published rubrics cluster around seven recurring dimensions

The Harvard Kennedy School policy memo rubric evaluates problem definition, evidence-based analysis, options analysis, counterargument handling, and actionable recommendations. MIT Sloan's 9-dimension professional writing rubric scores strategy/purpose, audience calibration, structure, evidence quality, coherence, and clarity on a 4-level scale. The Pulitzer Prize for Explanatory Reporting requires "mastery of subject, lucid writing, and evidence-based illumination of significant complexity." Towson University's business writing rubric specifically scores whether **headings can stand alone as headlines** and whether introductions "could stand alone and give a clear bottom line." Across all rubrics, the universal dimensions are: conclusion-first structure, evidence quality, audience awareness, analytical depth, and logical coherence.

**Rubric items:** Can the argument be reconstructed from headings alone? Does every claim have specific supporting evidence? Does the piece pass the HKS "counterargument" test — does it address the strongest objection?

---

## Draft LLM-as-judge rubric: 10 criteria for consulting-quality analytical essays

| # | Criterion | 1 (Fail) | 3 (Competent) | 5 (Commanding) |
|---|-----------|-----------|---------------|-----------------|
| 1 | **Governing thought in the opening sentence** | Opens with background, context-setting, or throat-clearing; the main claim appears late or never | Main argument appears in the first paragraph but is preceded by setup | First sentence names a specific, falsifiable claim that frames the entire piece |
| 2 | **Complication names a tension the reader already feels** | Complication is generic ("companies face challenges") or absent | Complication identifies a real problem but doesn't connect to the reader's lived anxiety | Complication articulates a specific fear, frustration, or contradiction the reader recognizes but hasn't named |
| 3 | **Pattern-naming from concentrated domain exposure** | Observations are available to any generalist; no insider signal | Some domain-specific observations, but framed as common knowledge | Names a repeating syndrome, archetype, or configuration that only someone with deep, narrow exposure would recognize |
| 4 | **Integrative thinking: holds opposing models in tension** | Binary framing (X is good / Y is bad) or single-perspective analysis | Acknowledges complexity but defaults to one side | Identifies two models that seem mutually exclusive, then synthesizes a resolution that contains elements of both |
| 5 | **Evidence specificity (the Goldilocks zone)** | Generic appeals ("studies show," "best practice," "many companies") | Some specific data points or examples, but not consistently deployed | Named cases, specific numbers, precise mechanisms — enough detail to signal insider knowledge without over-explaining |
| 6 | **Contrarian claim with causal mechanism** | Assertion without evidence ("buyers are irrational") or no contrarian element at all | Contrarian framing present but supported only by anecdote or appeals to authority | Contrarian claim backed by specific causal mechanism (e.g., defensive decision-making, loss aversion) and calibrated to evidence strength |
| 7 | **Forward-to-CEO arousal: names a specific threat or missed opportunity** | No urgency; reads as informational overview | Implies risk or opportunity but doesn't name it specifically enough to trigger action | Names a specific, quantifiable threat or missed opportunity that would make a CMO forward it with "thought you should see this" |
| 8 | **Headings function as standalone argument** | Topic-label headings ("Background," "Analysis," "Conclusion") | Headings hint at content but don't convey the argument | Reading only headings reconstructs the core argument; each heading is a complete, specific assertion in sentence case |
| 9 | **Counterargument handling (the strongest objection)** | No acknowledgment of alternative views or limitations | Mentions a potential objection but dismisses it quickly | Anticipates the reader's strongest objection, steelmans it, and addresses it with evidence — increasing rather than undermining credibility |
| 10 | **Conclusion advances beyond summary** | Restates what was already said; no new synthesis | Summarizes key points with modest reframing | Delivers a novel implication, actionable next step, or reframing that couldn't have been stated at the outset — the argument has *moved* |

**Scoring guidance:** Essays scoring 40+ (average 4+) across all criteria should correlate with editorial rankings in the top quartile. The three highest-signal criteria for predicting engagement at the $8–25K level are **#1** (governing thought), **#3** (pattern-naming), and **#7** (forward-to-CEO arousal) — these should receive 1.5× weighting in calibration against editorial rankings. A score of 1 on any criterion should be treated as a potential veto regardless of total score.