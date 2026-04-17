# Framing memo: per-stage knowledge-access routing

**Read first:** The working name "cognitive architecture selection" should be retired. The mechanism you built is partially precedented by **Modular RAG (Gao et al., Jul 2024)** and **Adaptive-RAG (Jeong et al., NAACL 2024)** — you must engage both directly. Your defensible novelty is narrower than "cognitive architecture selection" and sharper for it: **cognitive-task-type as the conditioning variable, in a multi-stage content-generation setting (not QA), with calibrated per-stage LLM-judge evaluation**. Everything below is built on that reframe.

---

## 1. Competitive landscape and the honest novelty claim

### The map

| # | Work (date) | What it does | Overlap |
|---|---|---|---|
| 1 | **Modular RAG / RAG Flow** — Gao et al. (arXiv 2407.21059, Jul 2024) | Formalizes RAG as swappable modules with routing/scheduling/fusion operators; explicitly includes KG, vector, full-text as interchangeable. | **HIGH — biggest threat.** This is the algebra your system is a policy over. |
| 2 | **Adaptive-RAG** — Jeong et al. (NAACL 2024, arXiv 2403.14403) | Trained classifier routes queries to {no-retrieval, single-step, multi-step}; now a LangGraph template. | **HIGH.** Routes retrieval strategy, but conditions on query complexity, not stage task-type. |
| 3 | **RouteRAG** — Guo et al. (arXiv 2512.09487, Dec 2025) | RL policy picks DPR vs HippoRAG-2 vs hybrid per reasoning turn in QA. | **HIGH.** Same axis (vector vs graph), but per-turn in QA, not per-stage in content generation. |
| 4 | **HetaRAG** — Yan et al. (arXiv 2509.21336, Sep 2025) | Parallel-launches Milvus + Neo4j + Elasticsearch + MySQL per query, fuses results. | **Partial.** Uses the same substrates but fuses always, never selects. |
| 5 | **CAG** — Chan et al. (arXiv 2412.15605, Dec 2024) | Preload corpus into extended context; skip retrieval. | **Low.** One of your four options, not a selection framework. |
| 6 | **Self-RAG** — Asai et al. (ICLR 2024) | Reflection tokens gate retrieve/critique per segment. | **Partial.** Gates retrieval on/off, not between architectures. |
| 7 | **RAGSmith** — Kartal et al. (arXiv, Nov 2025) | Genetic search over 9-stage RAG pipeline configurations per domain. | **Partial.** Stage decomposition is explicit; conditioning variable is domain-fit, not task type. |
| 8 | **HedraRAG** — Hu et al. (arXiv 2507.09138, SOSP'25) | Systems-level abstraction for heterogeneous multi-stage RAG workflows. | Partial — validates "stages with heterogeneous retrieval" as a named abstraction. |
| 9 | **RAG+** — (arXiv 2506.11555, 2025) | Adds an "application-aware" retrieval stage motivated by Bloom's taxonomy. | **Partial and important.** This is the only RAG paper I found that explicitly invokes a cognitive taxonomy. You should cite it and extend it. |
| 10 | **RouteLLM / Martian / Not Diamond / OpenRouter-Auto** | All route between **models**, holding retrieval fixed. | **None** on retrieval, but critical to name because everyone will assume you are doing this. |
| 11 | **LangGraph / LlamaIndex agentic workflows** | Per-node tool/retriever selection; ship Adaptive-RAG as a template. | Engineering substrate, not a claim. |

### The honest verdict

The mechanism — **picking different retrieval substrates at different points in a compound LLM workflow** — is precedented. Modular RAG already names "routers" as first-class operators. Adaptive-RAG already trains a classifier to pick retrieval strategy. Per-stage LLM-judge evaluation is now explicit industry advice (LightOn, Oct 2025: *"stage-wise metrics are mandatory"*). Do not claim any of this as novel.

What you actually have that is new:

1. **Cognitive-task-type as the conditioning variable.** Adaptive-RAG conditions on query complexity. RouteRAG conditions on an RL-learned turn policy. RAGSmith conditions on domain fit. No paper I could verify conditions on a taxonomy of stage task types (classification / discovery / synthesis / generation / critique) within a content-generation pipeline.
2. **Content generation, not QA.** Every precedent above benchmarks on HotpotQA / NQ / PopQA / 2Wiki. Long-form, multi-stage content generation is structurally underpopulated. Your +13 on cross-domain synthesis is not meaningful on HotpotQA; it *is* meaningful here.
3. **A calibrated judge, not a judge.** ρ = 0.841 against a 5-model editorial panel is publishable calibration. The vast majority of LLM-judge deployments never report correlation with humans.
4. **The negative CAG result.** You tested an obvious competitor for one of the five stages and it lost. That is a small ablation but a rare one in RAG literature, which has a strong positive-result bias.

### How to position against each threat

- **Against Modular RAG:** *"Modular RAG supplies the algebra; the selection policy is left unspecified. We contribute an empirically-calibrated selection policy keyed on stage task-type, with per-stage ablations justifying each choice. Modular RAG is our substrate, not our competitor."*
- **Against Adaptive-RAG / RouteRAG:** *"Prior routing conditions on query-side signals inside QA workflows. Cognitive-task-type routing conditions on stage-side signals inside compound content generation, where a single task legitimately traverses retrieval, synthesis, and critique stages with structurally different optimal backends. Query-conditional routing cannot express this."*
- **Against model routers (RouteLLM, Martian, Not Diamond):** *"They route between language models and hold the knowledge-access layer fixed. We route between knowledge-access architectures and hold the model roughly fixed. Orthogonal axes. The retrieval-architecture axis is the larger lever for long-form factual grounding."*

### One honesty flag

Your five-category task taxonomy (classification, discovery, synthesis, generation, critique) doesn't match any canonical cognitive-science taxonomy I could find. Self-RAG uses retrieve/generate/critique. RAG+ cites Bloom. If you don't ground your taxonomy in **something** — Bloom, Anderson & Krathwohl's revised Bloom, or at minimum a defensible engineering argument — reviewers will call it ad hoc. **Strongest move: cite Bloom's revised taxonomy (remember → understand → apply → analyze → evaluate → create) and show your five map onto it.**

---

## 2. Naming

### 2a. "Cognitive architecture selection" — direct verdict: retire it

Four reasons, ranked:

1. **Semantic mismatch.** "Cognitive architecture" in the classical sense (ACT-R, Soar, CLARION, LIDA, Sigma) denotes a whole-system blueprint of an agent's mind — memory, control, action, learning cycle. Your system swaps a retrieval backend per stage. These are different objects. A reviewer from the Laird / Anderson / Sun / Samsonovich orbit (BICA conference, AAAI ACS symposium) will flag this instantly.
2. **The term is already being reclaimed and contested.** Sumers, Yao, Narasimhan, Griffiths (2023, TMLR) published *"Cognitive Architectures for Language Agents"* (CoALA), which is the serious academic reclamation. Harrison Chase (LangChain, 2024) tried to reclaim it for product marketing and had to issue a public update after being called out. You will arrive into a live controversy, on the wrong side.
3. **SEO and discoverability collision.** Search for "cognitive architecture selection" today returns debates over which classical architecture fits which task. Practitioners looking for a retrieval router won't find you; cognitive scientists finding you will be annoyed.
4. **Factual precision.** Your system isn't selecting architectures of cognition. It's selecting **knowledge-access substrates**. Use language that names the actual thing.

### 2b. Five alternative names, ranked

The dominant pattern in durable AI naming is **descriptive-compound → short acronym**, optionally spiced with a **vivid metaphor** (RAG, CAG, MoE, CoT). The high-variance pattern is **provocative declaration** ("Attention Is All You Need," "Software 2.0"). The risky pattern is **terminological reclamation** ("agent," "cognitive architecture") — that's what you are currently on.

Ranked recommendations:

**1. Mixture-of-Retrievers (MoR) — strongest.** Direct parallel to MoE, which every ML reader parses in under a second. "Experts" → "retrievers." Task-conditional gating is already the mental model for MoE. The paper writes itself: *"MoR: task-conditional gating over heterogeneous knowledge-access backends."* Minor existing use of the term in a couple of small papers, but not locked. **Pros:** instant legibility, slot-based memorability, extensible (MoR-v2, sparse-MoR, etc.). **Con:** implies learned gating — if your gating is rule-based rather than learned, you'll need to be explicit, or you'll under-claim.

**2. Stage-Specialized Retrieval (SSR).** Pure descriptive compound. **Pros:** accurate, defensible, no collision. **Con:** forgettable; doesn't do the work of a metaphor.

**3. Task-Conditional RAG (TC-RAG).** Parasitic on RAG the way CAG was. **Pros:** piggybacks on a term everyone knows; communicates the key variable (task) clearly. **Cons:** makes you look like a footnote to RAG rather than a new lens; the acronym is awkward to say.

**4. The Monolith Tax (as rhetorical frame, not product name).** This is the *blog-post name*, not the paper name. It names the enemy (monolithic pipelines), it has stakes (a tax is money you didn't know you were losing), and it pairs with your $0.09 vs $0.30 proof point. Use this for the essay, use MoR for the paper.

**5. Pipeline-MoE / MoRE (Mixture of Retrieval Experts).** A portmanteau play. Honest about the lineage. MoRE is also phonetically nice. If MoR feels taken, this is the fallback.

**Do not use:** anything with "cognitive," "neuro-," "brain-," or "mind-." Attracts the wrong audience, invites the wrong scrutiny.

### 2c. Acronym check

- **TARA** (Task-Aware Retrieval Architecture) — pronounceable, memorable, but collides with dozens of products, a Google privacy tool, and common proper names. Skip.
- **CAR** (Cognitive Architecture Routing) — too generic; collides with literal cars; and retains the "cognitive" problem. Skip.
- **SAR** (Stage-Aware Retrieval) — clean and defensible, but "SAR" already means Synthetic Aperture Radar and Search-and-Rescue in technical contexts. Survivable but noisy.
- **MoR** (Mixture-of-Retrievers) — three letters, parallels MoE, clean Google result. **Winner.**
- **MoRE** (Mixture of Retrieval Experts) — slightly fuller, pronounceable as a word, good fallback.

**Recommendation: lead with MoR. Keep MoRE in the pocket.**

---

## 3. One-sentence pitches, by audience

**Researcher reviewing a paper submission.**
*"We formalize per-stage knowledge-access routing as a learned policy over {vector, graph, full-text, long-context-cache} conditioned on a cognitive-task taxonomy, extend Modular RAG with an empirically-calibrated selection policy (LLM-judge at ρ = 0.841 vs. a 5-model editorial panel), and report +2.1 mean across five task types and +13 on cross-domain synthesis over a monolithic RAG baseline — along with a negative result for Cache-Augmented Generation in stages where the literature predicted it should help."*

**YC partner, two minutes.**
*"Most AI pipelines in production are one model doing five jobs badly; we built the router that picks the right knowledge-access substrate for each pipeline stage and cut per-draft cost from thirty cents to nine cents while beating monolithic pipelines by thirteen points on the hardest task — in the window when enterprises are admitting that ninety-five percent of their GenAI pilots haven't paid back, and the CFO wants to know why."*

**CTO evaluating AI infrastructure.**
*"Your content pipeline is running one retrieval pattern across stages that need different ones; we route each stage to the substrate its task actually rewards — vector for discovery, graph for synthesis, full-text for grounding, cache for critique — with a calibrated per-stage judge so you can see exactly where quality comes from and where you're overpaying, and in our benchmarks that comes out to 3.3× lower cost at higher end-to-end quality."*

**Fractional CMO evaluating a consulting hire.**
*"Your content operation is paying three times what it needs to pay for drafts that are weaker than they could be, because nobody told you that different stages of content reward different AI setups; I find where the money is leaking, fix the stages that matter, and prove it with measurement rigorous enough that your board stops asking what AI is actually doing for you."*

**Anthropic partnerships manager.**
*"Extended context and prompt caching make long-context a first-class pipeline primitive, but nobody has published a principled policy for when to use it versus vector or graph retrieval per stage — we have, with calibrated per-stage evaluation, and the cleanest case for when Claude's 200K-plus context window is the right substrate rather than a wasteful default, which we'd like to co-publish as a reference pattern."*

---

## 4. "Why now" — five angles with citable evidence

The structure of the narrative: *the preconditions arrived in the Feb 2024 → late 2025 window, and the disillusionment arrived on top of them — so the architectural question that was premature in 2023 is now forced.*

**Enterprise AI has officially entered the trough.** MIT NANDA's *"The GenAI Divide: State of AI in Business 2025"* (Aug 2025) found 95% of enterprise GenAI pilots delivered no measurable P&L impact across 150 interviews, 350 employee surveys, and 300 public deployments (lead author Aditya Challapally; widely covered by Fortune Aug 18 2025 and HBR). Gartner's *Hype Cycle for AI 2025* (Aug 5 2025) placed GenAI in the Trough of Disillusionment and reported fewer than 30% of AI leaders say their CEOs are satisfied with AI ROI despite average $1.9M GenAI spend. S&P Global reported 42% pilot abandonment. **Quality: strong.** This is the single best why-now anchor.

**Agents look worse the closer you look.** τ-bench (Yao et al., arXiv 2406.12045) shows frontier agents at pass^8 < 25% on retail tasks — one-in-four odds of solving the same task eight times in a row. τ²-bench (Barres et al., arXiv 2506.07982, 2025) drops GPT-4.1 from 74% → 34% when control becomes dual-sided. SWE-bench Pro (Scale, Sept 2025) drops top models from the ~75% Verified numbers to ~23%. Gaia2 (HuggingFace/Meta, Sept 2025) has GPT-5-high at 42% pass@1. **Quality: strong.** Agents don't need more prompt engineering; they need architectural discipline.

**Tokens got 10–20× cheaper, and that flipped the constraint.** GPT-4 at launch (Mar 2023) was $30 / $60 per million tokens in/out; GPT-4o-mini (Jul 2024) shipped at $0.15 / $0.60; Gemini 3 Flash and Grok 4.1 are now in the $0.20–$0.50/M range (Feb 2026). Andrew Ng's *The Batch* (Aug 2024) clocked the blended price drop at ~79% per year. Price is no longer the constraint; **ROI pressure is**, as the Gartner and MIT numbers above confirm. **Quality: strong.**

**Evaluation stopped being amateur hour.** Zheng et al.'s *"Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena"* (NeurIPS 2023, arXiv 2306.05685) established >80% agreement with human preferences and is now cited 5,000+ times. Arize raised a $70M Series C in Feb 2025 (secondary-sourced; verify before citing). Langfuse, Braintrust, Ragas, and DeepEval are now enterprise defaults. Cleanlab's *AI Agents in Production 2025* survey found evaluation/observability was the #1 stated investment priority for 71% of teams with production agents. **Quality: strong on foundations, moderate on specific adoption milestones.**

**Long context became viable economically, not just technically.** Gemini 1.5 shipped 1M-token context Feb 15 2024, 2M tokens at I/O May 14 2024. Anthropic prompt caching went to public beta in Aug 2024 and broadly available Dec 17 2024, with Anthropic's official claim of *"up to 90% cost reduction and 85% latency reduction."* OpenAI prompt caching shipped at DevDay Oct 1 2024 with automatic 50%+ cached-input discounts. **Quality: strong, all primary-source vendor announcements.** This is why CAG is even on the table as a pipeline option in 2026 — and, critically, also why your **negative CAG result** lands: the field expected "just stuff it in context" to win; you measured, it didn't, everywhere.

**The composed narrative (one paragraph):** *CAG landed in Dec 2024 because million-token contexts and 90%-off cache reads made it possible. Modular RAG (Jul 2024), Adaptive-RAG (Mar 2024), HetaRAG (Sep 2025), and RouteRAG (Dec 2025) staked out the per-stage routing idea but left the selection policy unspecified. Meanwhile MIT, Gartner, and S&P independently reported that 42–95% of enterprise GenAI pilots weren't paying back, token prices fell 79% a year, and evaluation tooling finally got serious. The window for a principled, measured policy over which knowledge-access substrate to use for which stage of which task is exactly now.*

---

## 5. Proof-point mapping by audience

Your five proof points: **+13 on cross-domain synthesis**, **+2.1 mean across task types**, **judge at ρ = 0.841**, **CAG negative result**, **$0.09 vs $0.30/draft**.

| Audience | Resonates most | Missing / credibility gap | How to close |
|---|---|---|---|
| **Researcher** | ρ = 0.841 judge; CAG negative result; +13 on synthesis. | No public leaderboard benchmark (HotpotQA, MuSiQue, BEIR, or a named long-form gen benchmark). No ablations beyond CAG. No confidence intervals / significance tests across seeds. | Run against at least one standard long-form benchmark (e.g., ELI5, ASQA, or propose your own and release it). Report n, seeds, CIs. Publish the judge calibration dataset. |
| **YC partner** | $0.09 vs $0.30 (3.3× cheaper); +13 on synthesis. | **Revenue, users, retention. Domain count. A customer with a name.** YC wants a company, not a finding. | Reframe as the product layer: "a routing platform that plugs in front of existing RAG stacks." Show 2–3 named pilots, even unpaid. Weekly active pipelines or drafts generated per week. |
| **CTO** | $0.09 vs $0.30; ρ = 0.841 (serious measurement); per-stage visibility. | **Latency** numbers. **Failure modes** and what happens when routing guesses wrong. Vendor/substrate compatibility matrix. Security/PII posture per substrate. SLA / reproducibility story. | Add P50/P95/P99 latency per stage. Document the fallback when the judge disagrees with the route. Ship a compatibility table (works with Pinecone / Neo4j / Elastic / Claude / GPT / Gemini). |
| **Fractional CMO** | 3.3× cheaper; +13 on synthesis translated to business language. | **No business outcomes yet.** Content produced per week. Editor override rate. Time-to-first-acceptable-draft. Domain breadth (finance content ≠ medical content ≠ marketing copy). | Run one paid pilot in one vertical with editor-override rate before and after. The CMO cares about "my editors stopped rejecting AI drafts," not about ρ. |
| **Anthropic partnerships** | CAG negative result (this is gold — it shows when long-context *isn't* the right tool, which is a more sophisticated message than Anthropic's own marketing); ρ = 0.841. | **Claude-specific** numbers. Stage-level breakdown showing where Claude's 200K+ context wins vs. vector retrieval. Prompt-caching savings in dollars. | Run a Claude-on-every-stage ablation and report where each Claude model variant is specifically preferred by your router. This is the partnership pitch. |

**The pattern:** *what you have is plenty to publish a paper. It is thin to sell a company, and thinnest to sell consulting.* Pick the lane, then fill the lane's specific gap. Do not try to use the same proof-point stack across three lanes.

---

## 6. Analogies — five candidates, ranked

Evaluation criteria: instant comprehension, technical accuracy, memorability, non-cliché. User explicitly forbade "hammer for every job."

**1. The hospital admissions analogy — strongest.**
*"A hospital doesn't send every patient to the cardiologist. Chest pain goes to the cardiologist, a rash goes to dermatology, a broken wrist goes to ortho, and vague fatigue goes to the GP first. The triage nurse is the whole reason hospitals work at scale. Your AI pipeline has no triage nurse; it sends every task to whichever specialist was on shift when you built it."*
- Instant comprehension: very high. Everyone has been triaged.
- Accuracy: excellent. The triage nurse = your task-type gate. The specialists = your retrieval substrates. Synthesis ≠ discovery ≠ critique, exactly as cardiology ≠ dermatology.
- Memorable: "your AI pipeline has no triage nurse" is a line.
- Non-cliché: specialization-in-medicine is common, but the **triage** frame is sharper than the generic "different doctors" version and is the part that maps onto your gating policy.

**2. The restaurant line-cooks analogy — second strongest.**
*"A restaurant doesn't have one person making every dish. Garde manger plates the salad, the sauté station sears the fish, the grill holds the steak, pastry finishes the dessert. One person doing all of it is a home kitchen. You are running a home kitchen in production."*
- Comprehension: high.
- Accuracy: very good — each station has different tools and different heat profiles for different dishes, matching substrate-to-task.
- Memorable: "You are running a home kitchen in production" is usable verbatim.
- Non-cliché: knife-as-tool is cliché; **brigade-system stations** is fresh for an AI audience.

**3. The structural engineering analogy — strong for technical audiences.**
*"You don't build a bridge out of one material. Compression members are concrete or masonry; tension members are steel cable; the deck is rebar-reinforced concrete on steel girders. Nobody gets a PE license by saying 'steel is my favorite, I'll use it for everything.' Monolithic AI pipelines are that license application."*
- Comprehension: high for engineers, moderate for non-technical.
- Accuracy: excellent — different materials for different load types maps cleanly to different substrates for different retrieval-access loads.
- Memorable: the PE-license jab lands.
- Non-cliché: yes — "right tool for the job" is cliché, but the specific compression/tension distinction is not.

**4. Athletic training analogy.**
*"A marathoner and a sprinter do not share a training program. They share a species. Training a generalist model on a generalist pipeline and expecting it to win both stages is a category mistake."*
- Comprehension: high.
- Accuracy: decent — less precise than the hospital/kitchen analogies, and relies on model-specialization more than retrieval-substrate specialization.
- Memorable: yes.
- Non-cliché: moderately fresh.

**5. Manufacturing line analogy.**
*"A Toyota plant doesn't use one machine for stamping, welding, painting, and assembly. It uses four lines, each tuned, each measured, each swappable. The reason it ships a car every 55 seconds is that it stopped treating the line as a monolith 60 years ago. Your AI pipeline is still treating the line as a monolith."*
- Comprehension: moderate — requires the reader to have a mental model of a car plant.
- Accuracy: very good — the Toyota Production System is literally a per-stage optimization system.
- Memorable: moderate.
- Non-cliché: moderate; "factory line" is well-worn but "a car every 55 seconds" is vivid.

**Recommendation: lead with the hospital-triage analogy for general audiences (including YC, CMO, and blog posts) and the structural engineering analogy for CTO/researcher audiences. Keep the kitchen brigade as the fun one for the blog's middle section. Don't use more than two in any given piece.**

---

## 7. Blog strategy

### Title candidates, ranked

1. **"Your pipeline is one model doing five jobs badly."** — accuses the reader, states the thesis, no colon, no subtitle, under ten words. This is the one.
2. **"The Monolith Tax."** — three words, names the enemy, becomes a meme-able phrase. Strong #2. Use as a **section title** inside the post either way.
3. **"Don't stuff everything in context."** — parasitic on "Don't Do RAG" (the CAG paper's title) and directly backs your negative CAG result. Provocative; risks reading as derivative.
4. **"Stop picking one model."** — clean imperative, but "model" slightly miscues (you're picking retrievers, not models). Second-order risk.
5. **"Pipelines are not models."** — declarative, Karpathy-register, slightly abstract. Works as the subtitle or the first bolded sentence of the post.

**Winner: "Your pipeline is one model doing five jobs badly."** It does the Hamel Husain move (accuse the reader of the thing they already suspect about themselves) and it pairs naturally with every proof point you have.

### The hook (outline, not prose — 3 beats, ~60 words total)

- Open by accusing the reader directly: they picked one substrate for every stage because it was a deadline, not a decision; they've been paying 3.3× for this convenience.
- Name the hidden cost in one number: **$0.21/draft they didn't need to spend**, and **+13 points on cross-domain synthesis they left on the floor**.
- Tease the negative result: *"And we'll also tell you which fashionable option didn't save us, so you don't have to waste the quarter finding out."*

No "in this post we will." No background paragraph. No hedge.

### Narrative arc (section headers, in order)

1. **The Monolith Tax** — name the enemy. Why end-to-end evals hide per-stage waste.
2. **Five jobs, not one** — name the five cognitive-task types; claim each one rewards a different substrate; show the table.
3. **The hospital has a triage nurse** — single analogy section. Brief. One paragraph.
4. **The numbers** — +2.1 mean, +13 on synthesis, 3.3× cheaper. Include the Pareto chart.
5. **How I know the judge is real** — the calibration story. ρ = 0.841 against a 5-model editorial panel. Include the calibration plot.
6. **What didn't work: CAG** — the negative result. Dry, Camus-register. This is the voice-showcase section.
7. **What to do Monday morning** — three named prescriptions. Numbered. Accusing.

### The shareable artifact

**One diagram. Above the fold. Non-negotiable.** Two-panel: left panel shows a monolithic pipeline — one model, five sad arrows, one cost number ($0.30). Right panel shows five stages, each labeled with task type + substrate + per-stage judge score + per-stage cost, summing to $0.09. Ugly-and-legible beats pretty-and-confusing. This image is the tweet. Everything else is the argument.

### The moment the reader gets it

Section 4 or section 5, when they see the per-stage breakdown and realize **the +2.1 is small but the +13 on synthesis is large** — which means stages are not interchangeable, which means their monolithic pipeline has been averaging over a real signal, which means the end-to-end eval on their own product has been lying to them. You want the reader to close the tab and ask their team what their synthesis-stage score is. That's the conversion event.

### What to explicitly not do

- No "in this post we will explore." Start with the accusation.
- No jargon wall. "Vector retrieval," "graph traversal," and "cache-augmented generation" are fine; do not use "knowledge-access architecture" unless you define it in the same sentence. Karpathy reduces; don't reach.
- No academic voice ("we propose," "we present"). First-person, opinionated, slightly rude.
- No hedge on the main thesis. Put hedges in footnotes — especially the one about your taxonomy being informal.
- No 15,000-word encyclopedia. This is a 2,500–3,500-word essay. The encyclopedic version is the paper.
- No "Part 1 of 5." Single post. If you split it, nobody reads part 2.
- Do not host on Medium. Own the URL. `becausetom.com/monolith-tax` or equivalent.
- Do not call the thing "cognitive architecture selection" anywhere in the post. The post's vocabulary is **per-stage routing**, **the monolith tax**, and **Mixture-of-Retrievers** (introduce the term once, bolded, in section 2).

### Voice notes

You are allowed — expected — to be drier and more accusatory than the reference essays. Karpathy's move is *"it is better than you."* Anthropic's is *"the simplest solution usually wins."* Hamel's is *"you skipped the boring part."* The **Because Tom** move for this post is *"you already knew this and you did it anyway, and it cost you 21 cents a draft for a year."* Stay there. One joke per section. The negative-CAG section is where the Camus register should peak — resigned, specific, funny. Everywhere else, decline into confidence.

---

## Closing

The most important recommendation in this memo: **rename first, write second.** Your working name is the single highest-leverage change because it shifts the conversation from a collision you will lose (cognitive architectures) to a lineage you can extend (RAG → CAG → MoE → MoR). Once you ship under MoR or Stage-Specialized Retrieval, the paper has a clean spine, the pitch has a clean hook, the blog post has a shareable term, and the consulting offer has a concrete deliverable. The finding is genuinely good — narrower than "cognitive architecture selection" implies, but more defensible, more measurable, and more marketable for being narrow. The monolith tax is real; the case you have built against it is enough to publish and enough to sell, in one lane. Pick the lane.