# Research Pipeline Benchmark Prompts
## Agent Drift Detection — Weekly Automated Comparison

These five prompts are run against the research pipeline every week. Outputs are scored against baseline. Deviation >15% on any dimension triggers an alert. Baseline is recorded on first successful run after MVP validation.

Each prompt is designed to test a specific capability the pipeline must maintain. Topics are stable (won't change week to week), outputs are predictable enough to score, and diverse enough to catch different failure modes.

---

## Prompt 1: Factual retrieval with citation
**Tests:** Source retrieval accuracy, citation formatting, confidence scoring

**Input:**
```
Research the documented psychological effects of social media use on adolescent loneliness. Focus on peer-reviewed studies published between 2018 and 2024. Return findings with full citations, confidence scores for each claim, and identification of any conflicting evidence in the literature.
```

**Expected output characteristics:**
- Minimum 3 distinct peer-reviewed sources cited with author, publication, year
- Each claim has an explicit confidence score (0.0–1.0)
- At least one instance of conflicting evidence identified and noted
- No claims made without supporting citation
- Sources are real and verifiable (not hallucinated)

**Scoring dimensions:**
- Citation completeness (0–25): Are sources fully cited and real?
- Confidence scoring (0–25): Is scoring present and calibrated to evidence strength?
- Conflict identification (0–25): Does output acknowledge contradictions in literature?
- Claim-source alignment (0–25): Does each claim trace to a cited source?

**Drift signal:** Hallucinated citations, missing confidence scores, claims without sources, failure to note conflicting studies.

---

## Prompt 2: Cross-domain connection
**Tests:** The core KB thesis — does the pipeline surface non-obvious connections across domains?

**Input:**
```
Research the psychological mechanism underlying both doomscrolling behavior and gambling addiction. What do these behaviors share at the neurobiological level? Connect your findings to any documented cultural or political phenomena that operate through the same mechanism.
```

**Expected output characteristics:**
- Identifies variable-ratio reinforcement as the shared mechanism (or equivalent framing)
- Connects to at least one non-digital cultural phenomenon (not just "other apps")
- References Panksepp's SEEKING circuit or equivalent neuroscience literature
- Makes the cross-domain connection explicit, not implied
- Root anxiety tagging: helplessness and/or meaninglessness should be present

**Scoring dimensions:**
- Mechanism identification (0–25): Core shared mechanism correctly identified?
- Cross-domain reach (0–25): Connection made to genuinely unrelated domain?
- Neuroscience grounding (0–25): Biological substrate referenced?
- Explicit connection (0–25): Is the cross-domain link stated clearly or buried?

**Drift signal:** Stays within one domain, misses the mechanism, produces surface-level comparison without structural insight.

---

## Prompt 3: Synthesis under conflicting evidence
**Tests:** How the pipeline handles contradiction — does it resolve, flag, or paper over?

**Input:**
```
Research the relationship between economic inequality and political polarization. There is significant debate in the literature about the causal direction and relative importance of economic versus cultural factors. Synthesize the conflicting evidence and return a confidence-scored assessment of what the current evidence actually supports.
```

**Expected output characteristics:**
- Explicitly acknowledges the causal debate (economic vs. cultural drivers)
- Cites evidence from both sides without false resolution
- Produces a confidence-scored synthesis that reflects genuine uncertainty
- Does not collapse nuance into a single confident claim
- Flags where evidence is thin or methodologically weak

**Scoring dimensions:**
- Conflict acknowledgment (0–25): Both sides of debate represented?
- False resolution avoidance (0–30): Does it resist picking a winner without evidence?
- Calibrated uncertainty (0–25): Does confidence scoring reflect genuine uncertainty?
- Methodological critique (0–20): Are source limitations noted?

**Drift signal:** False resolution, overconfident claims, ignoring one side of the debate, missing the methodological controversy.

---

## Prompt 4: Voice-agnostic research output
**Tests:** Does the research pipeline produce clean structured output that the content pipeline can work with — no voice bleed, no editorializing?

**Input:**
```
Research how the concept of "authenticity" has been commodified in marketing and consumer culture since 2010. Cover: academic critiques, documented brand strategies, consumer psychology research, and specific examples of authenticity claims in advertising. Return structured findings only — no interpretation of implications, no editorial framing.
```

**Expected output characteristics:**
- Output is structured findings, not narrative prose
- No first-person editorial voice
- No "this is important because" or implication framing
- Findings are discrete and separable (not woven into a single argument)
- Academic, brand strategy, consumer psychology, and specific examples all represented

**Scoring dimensions:**
- Structural cleanliness (0–30): Is output structured findings vs. narrative?
- Voice neutrality (0–30): No editorial framing or interpretation?
- Domain coverage (0–25): All four requested domains represented?
- Separability (0–15): Can individual findings be extracted independently?

**Drift signal:** Pipeline starts editorializing, produces narrative essays instead of structured findings, bleeds voice from content pipeline into research output.

---

## Prompt 5: Confidence calibration under thin evidence
**Tests:** Does the pipeline know what it doesn't know? This is the hardest failure mode to detect.

**Input:**
```
Research the documented psychological effects of using AI assistants as primary social companions. Focus specifically on longitudinal effects (12+ months of regular use). Return findings with explicit confidence scores and clear notation of where the evidence base is thin or absent.
```

**Expected output characteristics:**
- Acknowledges that longitudinal research on this specific topic is limited (it is)
- Does not fill evidence gaps with adjacent research presented as directly applicable
- Low confidence scores (below 0.5) on extrapolated claims
- Explicitly flags where claims are inferred vs. directly supported
- Does not produce false confidence through volume of output

**Scoring dimensions:**
- Evidence gap acknowledgment (0–35): Does it admit where research is thin?
- Confidence calibration (0–35): Are low-evidence claims scored low?
- Inference flagging (0–20): Are extrapolated claims marked as such?
- Volume-confidence resistance (0–10): Does length of output correlate with actual evidence strength?

**Drift signal:** Fills gaps with adjacent research without flagging, produces high-confidence claims on thin evidence, uses length to mask uncertainty.

---

## Scoring and Alert Logic

**Weekly process:**
1. Run all five prompts against the research pipeline
2. Score each dimension (automated where possible, human spot-check on Prompt 5)
3. Calculate total score per prompt (0–100) and overall score (average of five)
4. Compare to baseline
5. Alert if any single prompt deviates >15% from baseline OR overall score deviates >10%

**Baseline recording:** First clean run after MVP validation. Store as JSON with timestamp.

**Alert routing:** Log to operator interface landing page as priority item. Do not suppress — drift compounds.

**What drift usually looks like in practice:**
- Prompt 1 fails first: citation hallucination is the earliest sign of model degradation
- Prompt 5 fails second: confidence calibration degrades as the model becomes more "helpful"
- Prompt 3 fails third: nuance collapses into false resolution
- Prompts 2 and 4 are the last to fail and signal serious architectural problems

**What drift is NOT:**
- Week-to-week variation in which specific papers are cited (expected)
- Minor phrasing differences in how mechanisms are described (expected)
- Different examples used to illustrate the same concept (expected)
