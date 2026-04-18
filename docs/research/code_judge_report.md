# Build it, but not as a standalone repo

**TL;DR verdict: Build the judge — a real gap exists and the market is hot — but ship it as a calibration-focused blog post plus a merged PR to an existing eval framework (Promptfoo, DeepEval, Inspect AI, Braintrust autoevals, or Arize Phoenix), not yet another standalone GitHub project.** The methodology generalizes, the ρ = 0.841 number is genuinely strong by published benchmarks, and "evaluate AI-generated code" is a funded category as of Feb 2026. But a standalone repo is saturated signal; the same artifact delivered as an upstream contribution plus a Hamel-Husain-style writeup is 3–5× higher leverage for the target roles. The "I build through AI pair programming" framing is an asset at AI-native companies **if** you call it vibe engineering / agentic engineering — never vibe coding.

---

## Decision Point 1: the existence check

**Verdict: real gap, with informative adjacent work — no exact duplicate exists as of April 2026.**

Nothing ships as a reusable, calibrated, rubric-based LLM-as-judge for **subjective Python code quality** (readability, naming, architecture, documentation) with per-criterion numeric output. The pieces exist separately; nobody has packaged the integrated artifact.

**The nearest academic analogs are informative rather than duplicative.** CodeVisionary (ASE 2025, arXiv 2504.13472) is an agentic code-eval framework with multi-dimensional scoring including readability and best-practices, but it's benchmark-oriented and focused on code-generation quality holistically. Meta's "A Note on Code Quality Score" (arXiv 2508.02732, Aug 2025) is the closest industrial system — LLM scoring of PRs on modularity, readability, error handling, testability — but it's internal, no public code. TRACE (CMU, arXiv 2603.24586, 2026) is a meta-evaluation tool that extracts rubric items and measures LLM-judge-vs-developer alignment; its core finding — **LLM judges systematically misalign on code-quality dimensions** — is itself a validation that a carefully calibrated judge is worth building. Other prior work is narrower: ICE-Score (EACL 2024) covers only usefulness and correctness; CodeJudge (EMNLP 2024) is correctness-only; RACE (arXiv 2407.11470) uses static analysis rather than LLMs for its readability/maintainability axes. A recent systematic survey of LLM-as-judge for SE (arXiv 2510.24367, 2025) explicitly flags the gap in scalable judges for nuanced subjective aspects.

**Open-source frameworks all provide the primitives but none ship the artifact.** Promptfoo's `llm-rubric`, DeepEval's `GEval`/`DAGMetric`, Braintrust's autoevals, Prometheus-Eval's open-weights evaluator LMs, and Arize Phoenix/Weave/Opik/LangSmith/Ragas/Inspect AI all accept arbitrary rubrics, but **none ship a code-quality-specific preset**. The one OSS project that is directionally similar is CodeDog (github.com/codedog-ai/codedog), which does LLM-based PR review scoring on correctness/readability/maintainability, but it's informal and doesn't publish calibration numbers.

**Commercial tools do not overlap.** CodeRabbit, Greptile, Ellipsis, Graphite Diamond, Bito, and GitHub Copilot Code Review produce natural-language comments with severity labels, not calibrated per-criterion numeric vectors. SonarQube, Codacy, DeepSource, and Amazon CodeGuru are rule-based or ML-classifier-based with letter grades and severity tiers — not LLM rubrics. **PR-Agent/Qodo is the closest**, with a `review_effort [1–5]` label and internal self-reflection scores used as thresholds, but it's still coarse and single-dimensional. DeepSource markets "five-dimension PR report cards" which is directionally close but per-issue rather than calibrated holistic scoring. **What a calibrated rubric judge adds that none of these provide**: a stable orthogonal score vector enabling longitudinal tracking across PRs/authors/repos, ranking of LLM-generated code variants, calibration to team standards via anchor exemplars, and a trainable reward signal for RLHF/DPO — none of which comment-stream tools can produce.

**The calibration number is strong, not mediocre.** Published human–human agreement on subjective code tasks sits at Spearman ρ ≈ 0.55–0.7 (Buse & Weimer, IEEE TSE 2010) and Krippendorff α ≈ 0.46–0.66 (Paixão et al., EMSE 2022; Turzo & Bosu, EMSE 2023). Published LLM–human SOTA correlations on code quality run ρ ≈ 0.75–0.85: **HuCoSC reports ρ = 0.853 with GPT-4-Turbo against human experts on CodeNet** (arXiv 2412.00314); CodeRPE reports ρ ≈ 0.82 for GPT-4 on code summarization. The generic G-Eval baseline is ρ ≈ 0.51 on SummEval. **ρ = 0.841 for the essay judge is in the top band of published LLM-as-judge correlations and exceeds typical human-human agreement on code** — if the code judge lands anywhere near there, it's publishable-grade signal for a portfolio post. Two honest caveats: Spearman against a *panel aggregate* is easier than against a single rater, so report Kendall τ and Krippendorff α alongside it; and cross-domain transfer from essays to code is non-trivial and the code judge may calibrate lower.

**Conclusion on DP1**: build on top of the adjacent prior work rather than cite around it. The natural positioning is "Microsoft LLM-Rubric methodology + Prometheus-2-style open rubric scoring, applied and calibrated on Python code quality, with a concrete rubric grounded in PEP 8 / Clean Code / Ousterhout, published with full reproducibility." That's a defensible artifact because the integrated form doesn't exist yet.

---

## Decision Point 5: portfolio fit and the framing question

**Verdict: the project fits the target roles but the packaging matters more than the project. The AI-pair-programmer framing is an asset at AI-native companies if phrased correctly; the biggest risk is shipping it as yet-another-standalone-eval-repo.**

**Rubric-based LLM eval with calibration is table-stakes competence, not the headline differentiator at these companies.** Across ~10 current (late-2025 / early-2026) JDs I pulled — LangChain Applied AI (jobs.ashbyhq.com/langchain/c75915ba), LangChain Professional Services AI Engineer, Braintrust Eval Engineer, Arize DevRel (job-boards.greenhouse.io/arizeai/jobs/5704428004), Arize Solutions Engineer, W&B Weave SWE, Galileo Forward Deployed Engineer, Patronus Forward Deployed SWE, Confident AI Founding DevAdvocate, Comet Opik DevRel Lead, LlamaIndex Senior DevRel — **only Braintrust's Eval Engineer role makes eval methodology the entire job**. Everywhere else, "evaluation framework design," "LLM-as-judge," and "deterministic evaluators" appear as one bullet among six to ten. LangChain comes closest to explicit methodology requirements ("Hands-on experience implementing evaluation and monitoring systems for agents or workflows... running rigorous evals"). The dominant eval domains called out are **agent eval, RAG eval, trajectory/tool-calling eval, and safety/red-teaming — in that order**. Code quality eval is not explicitly listed anywhere, which is both a gap and a signal that it's not yet validated as a priority.

**What actually differentiates hired candidates, ranked by signal strength**:

1. **Shipping production LLM/agent systems end-to-end** — most cited.
2. **Open-source contributions to the company's own or peer ecosystem.** Arize DevRel explicitly lists "running or contributing to open-source projects like Arize Phoenix." Confident AI requires "a green GitHub profile and is already active in open-source." Comet's Opik DevRel role ties KPIs directly to "GitHub stars, OSS adoption." LangChain Applied AI: "Contribute to the LangChain and LangGraph ecosystem."
3. **Public technical writing** (especially Hamel-Husain-style error-analysis + calibration posts).
4. **Customer-facing communication** (for FDE/SE roles).
5. **Eval methodology depth** — assumed if you pass #1, a credibility floor rather than a ceiling.

**This inverts the default build plan.** A merged PR to Promptfoo (adding a code-quality rubric assertion), to DeepEval (adding a code-quality `GEval` or `DAGMetric` preset), to Inspect AI (adding a code scorer), to Braintrust's autoevals, or to Arize Phoenix, is strictly higher-signal than the same code in a personal repo. It proves you can read production eval code, it gives the maintainer company a direct reference channel, and it demonstrates the community fluency that is 40%+ of these roles. A PR that adds a novel scorer plus a judge-calibration utility plus a reference rubric is 3–5× more credible than a standalone GitHub project with the same content. **The best version of this artifact is: a PR + an upstream-merged reference rubric + a blog post on calibration methodology with reproducible code.**

**The "AI pair programmer who evaluates AI-generated code" framing is on-trend and credible — with vocabulary discipline.** As of 2026, Simon Willison's **"vibe engineering"** (simonwillison.net/2025/Oct/7/vibe-engineering/) and Karpathy's pivot to **"agentic engineering"** have formally distinguished disciplined AI-augmented workflows from vibe coding. Anthropic has publicly stated the majority of their internal code is Claude-written and that senior engineers have shifted to architecture and review roles. Thomas Dohmke (ex-GitHub CEO) raised a **$60M seed at a $300M valuation in Feb 2026 for Entire** — a tool that *explicitly captures and evaluates AI agent output per push*. That round is direct market validation of the user's project thesis. Swyx's "AI Engineer" taxonomy includes exactly this profile. **The framing matches the native dialect at Anthropic, LangChain, Braintrust, Arize, Cursor, Cognition, and peers.** Hiring-manager sentiment on Hacker News and elsewhere remains hostile to anyone signaling "vibe coding for production" — so never use that phrase. Lead with the evaluator's architecture (rubric design, panel composition, calibration protocol, veto logic) and have a deep-technical backup answer ready for "walk me through the hardest bug you personally debugged."

**The market demand signal is unambiguously hot.** DORA 2025 shows AI adoption positively correlates with throughput but **negatively with software delivery stability**; the 2026 update shows PR review time +441%, incidents per PR +242.7%, PR size +51.3%, with 31% of PRs merging with no review. GitClear's 2025 research (211M changed lines across major repos) reports code clones 4× higher and copy/paste now exceeding moved-code for the first time. Sonar's 2025 analysis: "AI-generated code creates technical debt faster than it can be refactored." **CodeRabbit's Dec 2025 study of 470 OSS PRs found AI co-authored PRs had 1.7× more major issues** (correctness 1.75×, maintainability 1.64×, security 1.57×). Veracode's Oct 2025 GenAI Code Security Report: 45% of AI-generated code introduces OWASP Top 10 vulnerabilities. Qodo's State of AI Code Quality 2025: only 3.8% of developers sit in the "high trust, low hallucination" quadrant. **Treat these vendor numbers with appropriate skepticism — GitClear, Sonar, Qodo all sell quality tooling — but DORA, METR, and the arXiv studies point the same direction with less alarming magnitudes.** The category is early and funded; no dominant tool has won.

**The portfolio saturation risk is real but solvable.** Every bootcamp grad has a RAGAS-scored chatbot on GitHub. Code quality eval is less saturated than RAG eval precisely because it's harder and the industry hasn't validated it yet — which cuts both ways. The defensible version of the project is the one that out-rigors 95% of eval portfolios on methodology: calibration protocol, inter-judge disagreement analysis, ablations on rubric weights, failure-mode taxonomy.

---

## Criteria design for a Python code quality rubric

This section applies because DP1 and DP5 both come back positive. Brief by design.

**Scope constraint: evaluable without execution, in the 1–5 ordinal band, with established literature grounding.** Drop anything a linter already catches reliably (PEP 8 whitespace, import order, line length — leave those to Ruff/Black/Pylint and cite that separation of concerns in the blog post).

A defensible 6-criterion starting rubric:

| Criterion | What it measures | Primary grounding |
|---|---|---|
| **Naming clarity** | Intent-revealing identifiers; consistent domain vocabulary; scope-appropriate length | Clean Code ch. 2; Ousterhout *A Philosophy of Software Design* ch. 14; PEP 8 §Naming |
| **Readability & structure** | Flow, whitespace meaning, consistent abstraction level within functions, control-flow clarity | Buse & Weimer 2010 readability features; PEP 8; Clean Code ch. 3 |
| **Architectural fit** | Function/class granularity, coupling, single-responsibility adherence, module boundaries | Ousterhout ch. 4–6 (deep modules, complexity); Clean Architecture; SOLID |
| **Documentation quality** | Docstring completeness & accuracy, comment-to-code ratio where needed, explains *why* not *what* | PEP 257; Google Python Style Guide §3.8; Ousterhout ch. 12–16 |
| **Error handling & edge cases** | Explicit failure modes, appropriate exception granularity, input validation, no silent swallowing | Google Python Style Guide §2.4; Python's EAFP idiom; Clean Code ch. 7 |
| **Testability & API design** | Dependency injection friendliness, pure-function preference, observable side effects, interface minimalism | Ousterhout ch. 7; Hitchhiker's Guide to Python §Structuring |

Two bullet notes on implementation:

- **Anchor exemplars per criterion per score level** (1, 3, 5 minimum) in the YAML itself. Buse & Weimer's methodology and the Prometheus-2 paper both show anchor-grounded rubrics dominate bare Likert prompts for inter-rater reliability.
- **Veto rules deserve thought for code specifically** — things like "contains hardcoded secrets," "uses `eval` on untrusted input," or "silently swallows `BaseException`" should collapse the overall score regardless of other criteria, mirroring how human senior reviewers actually reason.

Skip correctness, efficiency, and security as first-class rubric items unless you execute the code — the RACE benchmark and COMPASS have shown these need runtime signals. Frame the judge as **"subjective quality, complementary to test suites and linters,"** which is both honest and differentiates from the existing tool landscape.

---

## Final recommendation

Build it, but repackage the plan:

1. **Do not ship as a standalone repo.** Write the rubric-based code quality judge as a PR to one of: Promptfoo (new `code-rubric` assertion type), DeepEval (`CodeQualityMetric` or `DAGMetric` preset), Inspect AI (new scorer), Braintrust autoevals, or Arize Phoenix. Pick the one whose maintainer company is highest on your target list — **Braintrust autoevals is the single highest-leverage target** given Braintrust publicly emphasizes calibration as core methodology and has an Eval Engineer role where this work directly maps.

2. **Write the calibration methodology blog post as the primary artifact.** Lead with the cross-domain generalization story (essays → code, same harness, new rubric), publish the Spearman ρ plus Kendall τ plus Krippendorff α, show the ablations, show the disagreement failure modes. Cite Microsoft LLM-Rubric, Prometheus-2, CodeVisionary, Meta's Code Quality Score, and TRACE as the context. Target quality: Hamel Husain's eval posts.

3. **Frame the narrative as "vibe engineering" or "agentic engineering."** Not vibe coding. The story is: "I architect, I calibrate the evaluator, I direct the implementation, I validate the output against a multi-model panel and human labels." That is the native dialect at AI-native companies in 2026 — and the target companies' own founders (Dohmke, Anthropic leadership) have publicly endorsed this mode.

4. **Don't oversell code quality as the product.** The portfolio signal is the **methodology transfer** — you built a calibrated judge in one domain (essays, ρ = 0.841) and showed the harness generalizes to another (Python code) with rigorous calibration. That narrative beats "here's another AI code reviewer" by a wide margin, because the first is about your skill and the second is about a saturated product category.

5. **Two things to skip.** Don't try to turn this into an arXiv preprint — the bar there is higher than "useful and defensible" and TRACE/CodeVisionary are already in that lane. Don't build a SaaS around it — Dohmke already raised $60M for that market and you cannot out-execute him with a portfolio project.

The honest read: the underlying methodology is strong, the gap is real, the market is hot, the framing is defensible. **The risk isn't that it's a bad idea — the risk is that you ship it the default way (standalone repo, generic README) and it gets lost in the saturation**. Ship it as an upstream contribution plus a rigorous calibration post, and it becomes a credible differentiator for Applied AI / Solutions / DevRel roles at exactly the companies you're targeting.