# Code quality evaluation harness — Deep Research prompt

**Instructions:** Run in a single Claude Deep Research chat. Save output as `docs/research/code_judge_report.md`.

---

I built an LLM-as-judge evaluation harness for analytical essay quality — a 10-criterion rubric with structured scoring, calibrated against a 7-model editorial panel at Spearman ρ = 0.841. Now I want to adapt the same methodology to evaluate Python code quality. Before I build anything, I need to know: has this already been done, is it actually useful, and where would it fit in the existing landscape?

## My existing methodology (for context)

- YAML-defined rubric with named criteria, 1-5 scoring per criterion, weighted criteria
- LLM judge using structured output (tool_use) to enforce per-criterion scores with reasoning
- Multi-model calibration panel to validate the judge against independent assessors
- Spearman ρ correlation as the calibration metric
- Deterministic (temperature=0) for stable rank ordering
- Veto rules (any criterion at 1/5 flags for review regardless of total score)

I want to apply this exact infrastructure to code evaluation — swap the rubric from "essay quality" to "code quality," keep the judge prompt structure, calibration methodology, and scoring mechanics.

## What I need to know

### 1. Does this already exist?

I found Microsoft's LLM-Rubric (ACL 2024) and "Rubric Is All You Need" (ACM ICER 2025). What else is out there? Specifically:

- Has anyone built a **rubric-based LLM-as-judge for code quality** (not just correctness/pass-fail, but subjective dimensions like readability, naming, architecture)?
- How does this differ from existing code review tools (CodeRabbit, SonarQube, Codacy, PR-Agent)? Those tools exist — what would a rubric-based LLM judge add that they don't?
- Is there an open-source implementation I should be building on top of rather than from scratch?
- Has anyone **calibrated** a code quality judge against human reviewers the way I calibrated the essay judge? What correlation numbers exist?

### 2. Is this actually useful?

- Do engineering teams actually want structured, per-criterion code quality scoring? Or is the standard (linters + human code review) sufficient for production use?
- What are the documented pain points with current code review that an LLM judge could address? Are there published surveys or studies?
- Would this be useful for **learning** — specifically, someone who builds through AI pair programming but wants to understand what good code looks like and where their AI-generated code falls short?
- Would this be useful for **AI-generated code evaluation** specifically? As more code is written by Copilot/Cursor/Claude Code, is there a growing need to evaluate the quality of AI-generated code beyond "does it run"?

### 3. What criteria belong in a code quality rubric?

Not generic "best practices" — I need criteria that:
- Are evaluable by an LLM (not things that require running the code)
- Cover subjective dimensions linters can't catch (readability, naming quality, architectural choices, documentation quality)
- Have some established grounding (published standards, style guides, research)
- Would produce a useful signal at 1-5 scale (not binary pass/fail)

What do senior engineers actually care about in code review that automated tools miss? What are the dimensions where human judgment diverges from linter output?

### 4. The free/local model question

- Can Gemini Flash (free tier) evaluate code quality reliably, or does it need a frontier model?
- Has anyone benchmarked local models (Llama, Qwen, CodeLlama, DeepSeek Coder) on structured code evaluation tasks? What's the quality floor for useful code review?
- Prometheus (open-source eval LLM) claims GPT-4-level evaluation — has anyone tested it specifically on code?

### 5. Where would this fit as a portfolio piece?

- If I build this as a standalone tool and open-source it, does it fill a real gap? Or is the space already saturated with code review tools?
- Would contributing to Microsoft's LLM-Rubric repo (extending it to code evaluation) be higher-leverage than a standalone project?
- For the specific roles I'm targeting (Applied AI Engineer, Solutions Engineer, DevRel at AI-native companies like LangChain, Braintrust, Arize), does a code quality judge demonstrate relevant skills? Or is it off-topic from their product areas?

### 6. The meta angle

I'm someone who builds through AI pair programming (Claude Code). I don't write Python from scratch — I architect systems and direct AI to implement. A code quality judge would:
(a) Help me learn what good code looks like by scoring real codebases
(b) Let me evaluate the code my AI pair produces
(c) Demonstrate that I care about code quality even though I don't write code traditionally

Is this framing credible to a hiring manager? Or does "I built a tool to evaluate code I can't write" read as a red flag?

I am NOT interested in: generic code quality advice, lists of linting tools, or "how to write clean code" tutorials. I need to understand whether a calibrated LLM-as-judge for code quality is a novel enough contribution to be worth building, and whether the specific framing (AI pair programmer evaluating AI-generated code) is an asset or a liability for Applied AI roles.
