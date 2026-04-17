# Your remote Applied AI career has a real path

**The market has a name for you now: "agentic engineer" or "AI product engineer" — and 20+ specific companies are hiring that exact profile for $150K–$300K remote in April 2026.** The bigger news is that the AI eval/observability category has consolidated violently in the last 14 months (Humanloop → Anthropic, WhyLabs → Apple, W&B → CoreWeave, Langfuse → ClickHouse, TruEra → Snowflake), leaving a small set of well-funded independents — Braintrust, LangChain/LangSmith, Arize, Galileo, Patronus, HoneyHive, Comet, Fiddler — all aggressively hiring Forward Deployed / Solutions / Deployed Engineer roles where your LLM-judge calibration work is directly on-product. Anthropic's Mike Krieger publicly prioritizes "prototyping over weekends" and "craft" over credentials, and OpenAI's own interview guide says in writing they are "not credential-driven." At the same time, Andrej Karpathy's "vibe coding" has matured into the more respectable "agentic engineering," which Simon Willison, LangChain, and Replit's Amjad Masad have all explicitly endorsed as a hireable discipline. Your BA, your gaps, and your Ohio ZIP are not the blockers you think they are — the real blocker is that every applied engineering interview above Series B still includes a live coding screen, so your path goes through **non-SWE tracks** (Solutions Architect, Implementation Director, AI Strategist, Technical Writer, Evals consulting, DevRel) at a specific short list of companies, not through the front door of any Applied AI Engineer role.

The rest of this report is the operational version: named companies, live job URLs, salary bands pulled from the postings themselves, interview landmines to avoid, and the communities where the warm intros actually happen.

---

## 1. Company landscape: named targets with live job URLs

### AI evaluation & observability — your #1 category

This is the category where your LLM-judge calibration (ρ=0.841 against a 5-model panel) is *product-adjacent*, not just resume-interesting. Hiring managers here read the Hamel Husain / Shreya Shankar evals literature on a Saturday. **Consolidation warning:** Humanloop was acqui-hired by Anthropic (Aug 2025, platform sunset Sep 2025), WhyLabs went to Apple (Jan 2025), TruEra to Snowflake (May 2024), W&B to CoreWeave ($1.7B, May 2025), and Langfuse to ClickHouse in the Jan 2026 Series D. The remaining independents are the targets.

**Braintrust (braintrust.dev)** — $80M Series B Feb 17, 2026 (ICONIQ led, $800M post-money); customers include Notion, Stripe, Ramp, Vercel, Dropbox, Airtable. Hiring Forward Deployed Engineers, Solutions Engineers. Glassdoor interview difficulty 2.38/5, avg process 13 days — softest eval-tier interview bar. Founded by Ankur Goyal (ex-Figma/Impira). Careers: braintrust.dev → /careers. *Why you fit:* their entire product is what you already build yourself.

**LangChain / LangSmith** — $125M Series B Oct 20, 2025, $1.25B valuation (IVP, Sequoia, Benchmark); ~233 employees; used by 35% of Fortune 500. Open **Deployed Engineer** role (the exact title), multiple US cities, **$150K–$270K base**, JD explicitly says *"Nice to have: deployed AI agents in production, especially using LangChain, LangGraph"* — your actual stack. All 39 open roles: https://jobs.ashbyhq.com/langchain. **Contact:** Harrison Chase (CEO), Brace Sproul (head of Deployed Engineering) on LinkedIn. This is your single strongest fit in the category.

**Arize AI** — $70M Series C Feb 2025, >$135M total, ~200 employees, 150+ enterprise customers (Uber, Booking.com, Siemens). Remote-first with NYC/SF offices. Open roles: AI Solutions Engineers/Architects (including Singapore), UX Engineer for LLM Experimentation, AI Application Engineer. DevOps disclosed $100K–$185K. Arize makes both Arize AX (commercial) and Phoenix (OSS). Arize DevRel interview reported on Glassdoor uses a take-home *"Talk us through a campaign you think we should run"* — very unlike LeetCode. Careers: arize.com/careers.

**Galileo (rungalileo.io)** — $45M Series B Oct 2024 (Scale Venture Partners), $68M total, 6 Fortune 50 customers. Launched "Agentic Evaluations" Jan 2025 — directly your wheelhouse. SF-based. CEO Vikram Chatterji.

**Patronus AI** — $17M Series A May 2024 (Notable Capital, Lightspeed, Datadog); ~40 employees; NYC/SF. Recent product launches: Percival (agent debugging copilot, May 2025), Multimodal LLM-as-a-Judge (Mar 2025). 9 open roles per Glassdoor.

**HoneyHive** — $7.4M total (Apr 2025, Insight Partners led), OpenTelemetry-based LLM observability. Small team, NYC. CEO Mohak Sharma. Early — equity matters more, but more risk.

**Comet ML (Opik)** — >$63M raised; remote-first (NYC/Tel Aviv); customers Uber, Netflix, Etsy. Open roles: **Developer Relations Lead – Opik at $220K–$280K base (West Coast)**, Senior Python Engineer, Product Design Team Lead. Opik is their fastest-growing OSS eval framework.

**Fiddler AI** — Series C, $65.6M total (Lightspeed, Insight, Lux); Palo Alto; focus on explainable AI for government/finance. Several remote US roles including Senior Solutions Engineer.

### AI infrastructure & developer tools

**Supabase** is your cleanest infra fit — born-remote with 180+ team in 35+ countries, pgvector is their flagship AI primitive (you already use it), and their interview style is async take-homes, not LeetCode. All roles at https://jobs.ashbyhq.com/supabase. Current open: Strategic Customer Solutions Architect (AMER) remote, GTM Engineer remote, DevRel Engineer. **Supabase pays globally flat** per Himalayas and their careers page — no Youngstown discount. $200M Series D April 2025 at $2B. LinkedIn: Paul Copplestone (CEO), Tyler Shukert (DevRel).

**Vercel** discloses salaries directly: **AI Engineer SF $192K–$288K** (vercel.com/careers/ai-engineer-5517523004), Product Engineer v0 $196K–$294K, Software Engineer AI SDK, and a Forward Deployed Engineer for v0 on Indeed. Remote-eligible outside commute radius. Several postings explicitly list *"Power user of AI coding tools"* as a requirement — you're the intended reader. Contacts: Guillermo Rauch (CEO), Jared Palmer (VP AI/v0), Lee Robinson (VP Product).

**Writer (writer.com)** — $200M Series C Nov 12, 2024 at $1.9B valuation; Palmyra models + **graph-based RAG + Agent Builder** (exact overlap with your knowledge-graph portfolio). **AI Engineer role disclosed at $152K–$315K remote US** (wellfound.com/company/writer-ai/jobs). LangChain listed as a requirement in their JD. Writer was founded by May Habib with linguistics/content DNA — Comm Studies is a cultural fit, not a liability.

**Glean** — $150M Series F Jun 2025 at $7.25B. Their product *is* an enterprise knowledge graph with evaluation frameworks. **Founding Forward Deployed Engineer role** at https://job-boards.greenhouse.io/gleanwork/jobs/4651991005 explicitly lists "evaluation frameworks, prompt engineering, agent development, deployment at scale." Median remote base $218K (Himalayas). ⚠️ Their core ML/SWE tracks are confirmed LeetCode Hard on Glassdoor — target the FDE, AI Deployment Strategist, and AI Success tracks exclusively.

**Dust (dust.tt)** — Sequoia-backed, "OS for AI agents," customers include Cursor and Clay. **Publicly anti-LeetCode** — their engineering hiring blog (dust.tt/blog/engineering-hiring-process-at-dust) states *"We don't do algorithm puzzles or whiteboard gymnastics. We work together on real problems that mirror what you'd actually build at Dust."* Uses pair-programming and full-day PoC. Downside: requires SF or Paris in-person; not remote. Founding US Solutions Engineer role live. Stanislas Polu (CTO, ex-OpenAI/Stripe) on LinkedIn.

**LlamaIndex** — $19M Series A Jun 2024; **Applied AI Solutions Architect – East Coast (Remote)** open at remoterocketship.com. Full-Stack Product Engineer role at llamaindex.ai/careers framed as "ship AI products fast, wear every hat." Jerry Liu (CEO), Laurie Voss (VP DevRel).

**Pinecone** has a Senior SWE Experience Platform role that *explicitly requires* "hands-on experience shipping with AI coding tools (Claude Code, Cursor, Copilot)" — the most literal match for your profile you will find. ⚠️ Calcalist (Oct 2025) reported Pinecone is exploring a sale to Oracle/IBM/MongoDB/Snowflake after losing Notion as a customer; revenue reportedly declined. Treat as high-variance.

**Weaviate** — fully remote globally per weaviate.io/company/careers. Customer Solution Engineer role open at jobs.ashbyhq.com/weaviate. Interview style: take-home Weaviate-related challenge + discussion. European-heavy team may cap US comp.

**Skip or deprioritize** for this profile: Modal Labs (Python/GPU-heavy systems role), Notion (anchor days Mon/Tue/Thu required — not remote), Replit core SWE (LeetCode-heavy), Numeric (in-person mandate), Brex (3 days/week office Feb 2026), Hippocratic AI (5 days/week Palo Alto), Chroma (too early for $150K+ with comfort), deepset/Haystack (Berlin-centric, EU comp bands).

### Vertical AI — legal, finance, healthcare

The healthcare AI scribes are the **strongest vertical fit** for your B2B buyer psychology edge, because selling to hospital CIOs/CMIOs is exactly fear-driven executive decision-making, and two of the top players pay well on remote.

**Abridge** — ~$460M total raised, deployed at 100+ health systems, Levels.fyi median TC $240K, median base ~$204K. Remote-US roles actively posted: Implementation Director, Clinical Success Director, Revenue Enablement Lead, GenAI Software Engineer. Open roles: https://jobs.ashbyhq.com/abridge. *Their Linked Evidence product maps LLM outputs to ground truth — your eval calibration work is the exact capability they sell.* Shiv Rao (CEO) on LinkedIn.

**Ambience Healthcare** — $243M Series C Jul 2025 at $1.25B valuation (Oak HC/FT + a16z); Cleveland Clinic 5-year exclusive partnership. Careers page states *"Most roles remote-friendly — work from anywhere in the U.S."* — the cleanest remote policy of any vertical unicorn in the list. Recently hired Mike Valli as CRO (Feb 2026), signaling GTM expansion. careers.ambiencehealthcare.com.

**Hebbia** — $130M Series B at $700M val; 40% of largest asset managers use their Matrix product, $15T AUM managed. Their **AI Strategist** role (post-sales deployment at financial institutions) is the lightest coding bar + direct match for your B2B exec-psych reading. ⚠️ Their FDE role has confirmed "whole day coding onsite" on Glassdoor — target AI Strategist or Partnerships Solutions Engineer instead. NYC-primary but some remote. careers.hebbia.ai. George Sivulka (CEO).

**Harvey** — $11B valuation Mar 2026, $190M ARR, 1,000+ customers. ⚠️ **In-person NYC mandate on FDE role**; Glassdoor reports LeetCode Medium + systems design, only 26.7% positive interview experience, 3.03/5 difficulty. Levels.fyi median TC $336K. If you want the prestige/comp, the only realistic entry for your profile is Customer Success Manager or Legal Engineer — not FDE. CPO Kelly Butler authored their public hiring guide: harvey.ai/blog/landing-a-job-at-harvey.

**EvenUp** — $150M Series E Oct 2025 (Bessemer), $2B+ valuation, 2,000+ PI law firms, 10,000 cases/week. Hybrid SF/Toronto with flexible remote — more accommodating than Harvey. Legal B2B psych applies; SMB/mid-market lower coding bar. evenuplaw.com/careers.

**Rogo** — $75M Series C Jan 2026 (Sequoia), $165M total, 25,000+ pro users at Lazard, Jefferies, Nomura, Rothschild. NYC + London. Similar selling-to-MDs psychology fit as Hebbia; Solutions Engineer / AI Strategist roles are the path.

**Spellbook** — Toronto-based legal AI, ~140 employees, remote-friendly globally. Lightest coding bar in legal AI, Product/CSM/Legal Expert roles suit Comm Studies + domain fluency. jobs.ashbyhq.com/spellbook.legal. Worth adding to your short list specifically for remote accommodation.

**Skip:** Hippocratic AI (5 days/week Palo Alto), Numeric (in-person), Brex (hybrid mandate), Robin AI (Artificial Lawyer reported funding trouble Jan 2026), Nabla (Paris-heavy, less US remote than Abridge/Ambience).

### Model providers — applied roles only

**Anthropic** has a rich set of applied roles — but also a CodeSignal 90-minute assessment that even Solutions Architect candidates report as brutal. Current listings from job-boards.greenhouse.io/anthropic: **Forward Deployed Engineer, Applied AI at $200K–$300K** (multiple US cities, jobs/4985877008); **Applied AI Engineer (Startups) at $200K–$320K** (jobs.generalcatalyst.com/companies/anthropic/jobs/70950856); Solutions Architect (Applied AI, multiple verticals); Partner Solutions Architect $280K–$300K on ZipRecruiter. **No "Prompt Engineer" or "Developer Advocate" titles exist in current listings** — closest equivalents are the SA and Applied AI variants. Hybrid policy: "25% of time in one of our offices" is the stated minimum — only ~8% of the 454 open roles are fully remote (jobsbyculture.com/blog/anthropic-remote-work-policy-2026). Hybrid/25% is a blocker for Youngstown unless you relocate.

**OpenAI** is more transparent than the FDE-comp-rumors imply. Forward Deployed Engineer NYC posts **$162K–$280K base** plus equity (openai.com/careers/forward-deployed-engineer-(fde)-nyc-new-york-city/); FDE Life Sciences SF **$198K–$335K**. The "$350K–$550K mid-to-senior" figure you'll see cited is total comp including PPUs — Levels.fyi shows SWE median TC $555K and L6 up to $1.24M. The official OpenAI interview guide says in writing: *"We are not credential-driven… excited about people who are already experts in their fields as well as people who are not yet specialized but show high potential"* (openai.com/interview-guide/). Process: resume → intro → coding assessment on HackerRank/CoderPad + system design → 4–6 hours final interviews. Hybrid 3 days/week; rare US-remote roles in GTM/IT.

**Cohere, Mistral** — DevRel roles exist; less-signaled hiring volume vs Anthropic/OpenAI but lower interview rigor. Mistral is EU-heavy. Check their respective careers pages directly.

### AI consulting and small shops

A real emerging category: **Parlance Labs** (Hamel Husain + Shreya Shankar) runs Maven's canonical LLM evals course and does consulting directly — your eval harness portfolio is their job description. **AI Makerspace** (Greg Loughnane) runs bootcamps focused on "leveraging coding agents exactly the right amount." Invisible Agency posts AI QA Trainer roles at $6–$65/hr freelance as a low-barrier entry. Small AI implementation consultancies around Anthropic and OpenAI partner programs are multiplying — search *"Anthropic partner"* and *"OpenAI solutions partner"* directory listings.

---

## 2. Roles beyond the obvious — the middle layer has 12 titles

The most useful mental model from the research: the "middle layer between tool builders and tool users" is not one role, it is a **dozen titles with different interview bars**. For your specific profile, the ranking by fit and lowest LeetCode risk runs roughly:

**AI Technical Writer / Developer Educator (best fit, lowest barrier)** — docs-as-code, quickstart tutorials, sample apps for developer-facing AI products. Comm Studies BA is an asset not a liability. Typical $90K–$150K with cloud/devtools specialists going higher. Search Indeed "AI technical writer remote." Infisical's Documentation Lead and various "Developer Educator" postings explicitly list Claude Code as required tooling.

**AI Solutions Architect** — Glassdoor average $206K (range $164K–$264K nationally); California average $230K; Robert Half 2026 guide $142K–$196K. Rarely LeetCode-tested; most postings accept "equivalent experience." LangChain, Vercel, Arize all have these roles open; the Amsterdam/remote-EU LangChain SA is a particularly soft target.

**Implementation / Deployment Engineer** — Decagon and Deepgram's "FDE for Restaurants" explicitly list *"comfortable using AI coding tools to multiply output"* as a requirement (fwddeploy.com — aggregator specifically for this role family). Lowest LeetCode pressure of the FDE family; customer-facing comms are weighted heaviest.

**Forward Deployed Engineer (FDE)** — the hottest role of 2026 with reported 800% growth in listings. Palantir FDSE $135K–$200K base + RSUs (Levels.fyi median TC $207.5K up to $415K). LangChain's Deployed Engineer is the softest FDE interview in the category because the JD matches your stack verbatim. Anthropic, OpenAI, Harvey, Hebbia, Sierra, Decagon, Deepgram all have FDE tracks; interview rigor varies from practical (LangChain) to brutal (Anthropic CodeSignal, Harvey LC medium).

**Agent Engineer** — LangChain's October 2025 manifesto *"Agent Engineering: A New Discipline"* (blog.langchain.com/agent-engineering-a-new-discipline/) crystallized the title. Sierra uses the exact title at sierra.ai/blog/meet-the-ai-agent-engineer. Focused is hiring Lead Agent Engineer in Chicago at $175K–$250K (job-boards.greenhouse.io/focused/jobs/6541249003). Crucially, LangChain's framing explicitly says the discipline spans "software engineers AND PMs writing prompts" — it is the category that most explicitly accepts non-traditional code paths.

**AI Product Engineer** — Vercel's v0 Product Engineer at $196K–$294K (vercel.com/careers/product-engineer-v0-5466858004) is the archetype. This is *the* title for the vibe-coded-to-production career path.

**Technical Marketing Engineer (TME)** — Cloudflare's Product Marketing Engineer Intern (AI Automation) explicitly requires *"hands-on experience with AI coding environments (Claude Code, Windsurf, or OpenCode)."* NVIDIA TME AI Platform pays $136K–$253K but wants DL + Python/C++ (harder fit). The Cloudflare-style GTM-engineer variant is a bullseye.

**AI Educator / Curriculum Developer** — DeepLearning.AI, Maven, AI Makerspace all operate cohort-instructor models; pricing $500–$2,000/seat. Alumni Slacks are talent-dense. Path: build audience via public portfolio → get invited or launch a course.

**Evals Lead / Quality Engineer for AI** — full-time roles at Glean ($200K–$300K), Netflix L4/L5 LLM Evaluation (USA remote via explore.jobs.netflix.net), Scale AI Tech Lead LLM Evals all require Python/Go + distributed systems — **low fit for full-time**. *But* the consulting/training side (Parlance Labs pattern, Invisible Agency trainer) is a strong fit — the Pragmatic Engineer recently wrote that evals is a domain-expert-driven practice, not a pure code role (newsletter.pragmaticengineer.com/p/evals).

**AI Research Engineer (non-PhD variant)** — Anthropic's Research Engineer Tokens posts $315K–$340K. Still gated on strong Python + some ML background. Low fit.

**Prompt Engineer** — mostly dead as a standalone title in 2026. Standalone postings dropped ~30% 2024→2026 while prompt-eng-as-skill-inside-other-roles grew 3× (PE Collective). Technext called it a "mirage / bridge job" in Feb 2026. Alive as a skill, not a career.

**Customer / Sales Engineer with AI focus** — every AI company has them; lighter coding bar than FDE; often $150K–$220K base + commission. Good soft landing if your B2B psychology work lands with a sales org.

---

## 3. Non-traditional backgrounds in 2026 hiring

**Companies that explicitly hire on portfolio/craft over credentials, with sources:**

- **OpenAI's own interview guide** states: *"We are not credential-driven — rather, we want to understand your unique background and what you can contribute… excited about people who are already experts in their fields as well as people who are not yet specialized but show high potential"* (openai.com/interview-guide/).
- **Anthropic's Mike Krieger** on Silicon Valley Girl podcast (via finalroundai.com blog): *"I really look for the folks that on the weekends or in their spare time are prototyping ideas, they came up with something they're bringing that even to the interview process."* He's said Anthropic has "tended less to hire the like kind of fresh college grads" and prefers people "defined more about the problems they want to solve… than a very specific 'I know JavaScript.'" On Tomer Cohen's Building One podcast (Dec 2025) he framed the job around "the craft of product-making in this new era of AI." Anthropic's own careers page for non-technical roles: *"clarity, judgment, and a genuine interest in the mission… interviews are conversational."*
- **Anthropic's origin story is itself a credential-light signal**: Dario Amodei got his first ML job at Baidu with a biology/physics background after Greg Diamos vouched for his code ("anyone who can write this has got to be an amazingly good programmer"). The Anthropic founding team comes from physics, neuroscience, and philosophy, not exclusively CS.
- **Replit's Amjad Masad** (Feb 2026, x.com/amasad/status/2031926365868736940): *"Replit CEO says company aims to increase hiring in new grads who are vibe coding and 'agentmaxxing.'"* On VentureBeat: *"The population of professional developers who studied computer science and trained as developers will shrink over time. The population of vibe coders who can solve problems with software and agents will grow tremendously."*
- **Dust's engineering hiring blog** (dust.tt/blog/engineering-hiring-process-at-dust): *"We don't do algorithm puzzles or whiteboard gymnastics. We work together on real problems that mirror what you'd actually build at Dust."*
- **Swyx's canonical essay** "The Rise of the AI Engineer" (latent.space/p/ai-engineer, June 2023 and still the reference): *"There are ~5000 LLM researchers in the world, but ~50m software engineers. Supply constraints dictate that an 'in-between' class of AI Engineers will rise to meet demand."* Swyx now works on evals at Cognition — the identity is a legitimate career.
- **Sierra's** APX early-career program (sierra.ai/early-career-program) recruits non-traditional builders directly.
- Job postings explicitly requiring AI pair-programming fluency in 2026: Cloudflare PME Intern (Claude Code / Windsurf / OpenCode required), Deepgram FDE (*"Every team member at Deepgram is expected to actively use and experiment with advanced AI tools"*), Acadia Applied AI & Automation Engineer (Claude Code/Cursor/Copilot proficiency required) — aggregated at aitmpl.com/jobs and indeed.com/q-claude-code-l-remote-jobs.html.

**Companies that will eat you alive on traditional interviews** (per Glassdoor/Taro): Google, Meta, Stripe, most Anthropic engineering tracks (CodeSignal 90-min), Harvey FDE (LC medium), Hebbia FDE (full day onsite coding), Ramp core engineering, Numeric, Glean core SWE/ML (LC Hard, problem 317). For each, target their Solutions/Success/Implementation/Writing tracks instead of engineering tracks — the moat is thinner on the non-SWE side of the same company.

**Is "vibe coding" legitimate in 2026?** The answer is nuanced and favorable to your specific practice. Karpathy's original tweet (Feb 2, 2025, x.com/karpathy/status/1886192184808149383) defined it as *"fully give in to the vibes, embrace exponentials, and forget that the code even exists… I 'Accept All' always, I don't read the diffs."* His one-year retrospective (Feb 4, 2026) proposed renaming it to **"agentic engineering"** — programming via LLM agents *with oversight and scrutiny*. Simon Willison separately coined **"vibe engineering"** (simonwillison.net/2025/Oct/7/vibe-engineering/) as the professional version: *"I won't commit any code to my repository if I couldn't explain exactly what it does to somebody else."* Critical takes exist — a Dec 2025 University of Michigan paper titled *"Professional Software Developers Don't Vibe, They Control"* and CIO.com's "Vibe Coding Crisis" article argue for dual-track architecture where vibe-coded prototypes must be rewritten for production. The consensus emerging in 2026 is: **blind vibe coding = prototype toy; supervised agentic engineering with evals + review = hireable discipline.** Your profile (directs Claude Code, builds LLM-judge evals, validates against independent models, can explain system behavior) is the legitimate version, not the dismissed one — frame it that way.

---

## 4. DevRel deep dive — a real path, with caveats

**Actively hiring AI DevRel as of April 2026** includes Anthropic (Developer Relations Lead founding role **$365K–$435K base**, Developer Relations MCP, Developer Relations Engineer NYC), OpenAI (**Developer Advocate $172K–$275K base**, senior variant $220K–$345K), Hugging Face (Data/Infra Advocate Engineer US/EMEA remote, Cloud ML DevRel US remote), Mistral (Senior/Staff AI Developer Advocate via Lever), Vercel (DX Engineer docs team), Replit (Developer Advocate multi-language, remote-first), LangChain (Education Engineer for 1M+ dev community, Senior Technical Support Engineer at Austin), Comet (DevRel Lead – Opik $220K–$280K base West Coast), and Arize. Hugging Face Glassdoor shows Developer Advocate total comp $111K–$167K (25th-75th) — notably lower than frontier labs.

**Typical AI DevRel interview process** (pulled from Glassdoor, Exponent, candidate blog posts): recruiter screen → hiring manager conversation → take-home assignment (campaign exercise at Arize; 60–90 min CodeSignal at Anthropic) → candidate-chosen technical presentation → technical interview (Python-heavy at Anthropic, system design like *"design system enabling a GPT to handle multi-question threads"*) → behavioral/values round (AI safety and ethics weighted heavily at Anthropic) → team matching (2–4 weeks Anthropic-specific) → references + offer. **Total 4 weeks to 3+ months.** Anthropic is reported as rigorous with no feedback given to rejected candidates. AI use in interview solutions is strictly prohibited unless specified.

**Salary reality**: Levels.fyi Developer Advocate median $152K all-industries; Common Room 2023 State of DevRel median base $175K / total comp $200K with cloud infra highest at $218K median. Anthropic DevRel Lead $365K–$435K base is the current market ceiling; OpenAI DA $172K–$345K mid-to-senior; Comet DevRel Lead $220K–$280K West Coast. **DevRel runs 10–15% below equivalent engineering at the same company and stage** — the Anthropic DevRel Lead comp is below their median SWE TC of $575K.

**Career path vs trap?** Both, depending on which door you take. The canonical successful transition: Logan Kilpatrick at Apple ML engineer → OpenAI DevRel Head (Nov 2022–Mar 2024) → Google AI Studio/Gemini API Product Lead — DevRel → PM is the most-traveled upward path. Swyx: DevRel → founded Latent Space + AI Engineer conferences → now at Cognition on eval standards for coding agents. Harrison Chase at LangChain and Simon Willison both came through technical-writing-heavy paths. The trap mode: DevRel → Head of DevRel → VP DX at a company that doesn't grow → stuck at $220K while peers compound. The research-engineer-skeptics view DevRel dismissively; senior engineers often don't. For your profile, DevRel is genuinely a career path **only if you treat it as a 2–3 year springboard** into Product, Product Marketing, or Founder, not a destination.

**DevRel portfolio vs engineering portfolio** — a DevRel portfolio is conference talks (AI Engineer Summit, AI Engineer World's Fair), blog posts with distribution (Substack, latent.space, company blogs), YouTube/Twitch demo streams, open-source contributions, Twitter/X presence with substantive technical threads, community-building moves (Discord participation, meet-up organization), and runnable sample apps. Engineering portfolio is GitHub repos with traffic, production systems with real users, benchmarks, and shipped features. **For you specifically, a hybrid portfolio leveraging both sides** — your knowledge-graph content engine as a running demo, a write-up of your ρ=0.841 eval calibration methodology as a blog post, and a conference talk proposal titled something like *"How I shipped a 305-node behavioral-science knowledge graph and calibrated LLM judges in 2 weeks with Claude Code"* — maps cleanly into the DevRel discovery flow. This is the single highest-leverage project you could publish in the next 30 days.

---

## 5. Geographic and compensation reality from Ohio

**Flat-pay AI companies (advantage for Youngstown)**: **Anthropic does not appear to apply geographic pay adjustments for US roles** per JobsByCulture's March 2026 analysis; posted ranges are national. **OpenAI** publishes single US ranges. **Supabase** pays globally flat per their careers page and Himalayas coverage — same money anywhere. **Hugging Face** is remote-first global; ranges typically national-US. **LangChain** is small enough to be role-based rather than metro-tiered. **These are your top targets** for not taking a haircut.

**Location-adjusted AI companies (you will eat a 15–35% cut in Ohio)**: GitLab's published formula is `SF benchmark × Location Factor × Level Factor × Compa × Contract × FX`, with Youngstown mapping to a Location Factor around 0.55–0.65 vs SF 1.0 (handbook.gitlab.com/handbook/total-rewards/compensation/compensation-calculator/). Buffer uses `SF 50% benchmark × COL multiplier × role multiplier × experience factor` (buffer.com/resources/salary-formula/). Stripe uses US-tiered zones with Ohio in Tier 3 at roughly 10–15% off SF. Coinbase zones similarly. Vercel and Replit pay national averages slightly below SF. PostHog publishes a transparent location factor calculator.

**Truly remote-first vs remote-tolerated** (April 2026 state):
- Remote-first and flourishing: **Hugging Face, Supabase, GitLab, PostHog, Grafana Labs, Weaviate, and smaller YC AI labs**.
- Remote-tolerated with SF gravity: **Anthropic (~8% of roles fully remote), OpenAI (few US-remote), Vercel, Replit (increasingly SF-centric since 2024), LangChain (multi-hub), Baseten, Together, Modal**.
- Remote dealbreakers: **Notion, Harvey, Hippocratic AI, Numeric, Brex (hybrid Feb 2026)**.

**The 2024–2026 RTO trend is real and harmful to remote candidates:** 83% of Fortune 500 have some RTO by 2025; fully-remote share of postings fell from 21% in 2023 to 7% in 2024 (founderreports.com). Amazon went 5 days/week Jan 2025; Google tightened to 3 days and some AI staff to 5. Counter-trend: smaller AI-native startups are using remote + flat pay as a talent-arbitrage weapon against FAANG, which works in your favor if you target them specifically.

**Equity math — honest version.** Most pre-Series-C startup equity is worth zero. The Holloway Guide's cited Susa data shows >50% of VC-backed startups fail, 1-in-8 return 5–30x, and only 1-in-20 return 30x+. Reasonable stage-by-stage equity expectation:

| Stage | Senior eng base | Grant size | Practical EV |
|---|---|---|---|
| Seed | $130K–$180K | 0.5%–1.5% | Close to $0 unadjusted; high-variance |
| Series A | $150K–$210K | 0.25%–0.75% (median 0.6% Carta) | Car money in a good exit, zero in the median |
| Series B | $170K–$240K | 0.1%–0.4% (median 0.4%) | House money in a $1B+ exit, rare |
| Series C | $190K–$290K | 0.05%–0.2% | **Actually meaningful** — dilution higher but exit probability much higher |
| Public / late-stage private | $250K–$500K+ | Liquid RSUs/PPUs | Real money (Anthropic 30–50% of TC is equity) |

**The sweet spot for a risk-adjusted hire is Series C or later with a clear IPO path** — grants are smaller percentages but exit probability is 50%+ vs <10% at seed. Gergely Orosz's equity guide (blog.pragmaticengineer.com/equity-for-software-engineers/) repeatedly warns that option strike prices + 409A + exercise cost make options practically worthless unless the company exits big; double-trigger RSUs common at unicorns are materially better. OpenAI's PPUs are their own specific instrument with liquidity rules — read the fine print. Practical rule: value any startup offer at `base + (50% of on-paper equity × probability you actually believe)`. For seed/A, that's base + near zero.

---

## 6. Gaps, communities, and where the warm intros actually happen

**Emerging role types that fit your profile and aren't widely advertised:**

1. **"Evals consulting" as a solo practice** — Parlance Labs (Hamel Husain + Shreya Shankar) essentially invented this category; the demand exceeds their capacity. A portfolio of documented LLM-judge calibration methodology can become a consulting practice in 90 days.
2. **Maven cohort-leader** — $500–$2,000/seat, small class sizes, alumni Slacks are talent-dense, hiring managers often teach/lurk. Eugene Yan, Jason Liu, Hamel Husain all made this the foundation of a high-leverage career.
3. **AI Product Engineer at Vercel v0 / Cursor / Replit** — explicitly a vibe-coded-to-production career path; 5+ years full-stack experience often still required but tool-assisted output is explicitly accepted.
4. **"Founding X Engineer" roles at post-acqui-hire companies** — ClickHouse's Langfuse team, Anthropic's former Humanloop team, Snowflake's former TruEra team, CoreWeave's W&B team all have fresh org-building happening with less-rigid hiring conventions.
5. **Anthropic-partner and OpenAI-partner implementation consultancies** — a growing set of 10–50-person shops implementing Claude/GPT for enterprises. Search partner directories directly.

**Communities where non-traditional AI hiring actually happens:**

The single highest-leverage moves are joining the **Latent Space Discord** (invite via latent.space/p/community; 200K+ newsletter subs, 10M views, hosts LLM Paper Club Wednesdays 12pm PT), attending the **AI Engineer World's Fair 2026 in person June 29–July 2 at SF Marriott Marquis + Moscone** ($450–$1,800 tickets, 300+ speakers, 6,000+ attendees — one intro recoups the cost), and joining the **MLOps Community Slack** (go.mlops.community/slack, ~21,000 members, veteran ML engineers recruit directly, less hype than LangChain's crowd). LangChain and LlamaIndex Discords are decent but more support-oriented. **Hamel Husain's Applied LLMs Slack** (via his Maven course) has the highest hiring-manager density per capita of any community I found. Eugene Yan's newsletter readership is a warm audience for content-first careers. Newsletters that drive hiring with varying signal quality: Ben's Bites (100K+ subs, curated job board), TLDR AI (broad awareness, minimal direct hiring), Interconnects by Nathan Lambert (research-adjacent, networking-based), Import AI by Jack Clark at Anthropic (thought-leadership, context-building for interviews). Reddit r/LocalLLaMA (688K members) is an informal DM-based hiring channel with huge open-source credibility upside if you post projects. The fwddeploy.com aggregator is the dedicated job board for Forward Deployed roles specifically. The ai.engineer jobs board is the official AI Engineer community board.

**Is "vibe coding" / AI-native building recognized as a legitimate skill in 2026?** Yes, but the label has shifted. The word "vibe coding" now has negative connotations (Simon Willison, Andrew Ng, a16z's Andrew Chen all pushed back on the blind-trust version; the CIO.com "Vibe Coding Crisis" piece argues for dual-track architecture where vibe-coded prototypes don't touch production). The legitimate version is called **agentic engineering** (Karpathy, Feb 2026 retrospective) or **vibe engineering** (Willison, Oct 2025) — directing AI under oversight with evals, tests, and review. Your portfolio is the legitimate version: calibrated judge panel, controlled architecture comparisons with confidence intervals, thesis-constrained outline system with measurable quality improvement. **Frame your work as "agentic engineering with calibrated evaluation," not "vibe coding."** The distinction is the entire difference between being hireable at $250K and being dismissed as a dilettante.

## The operational plan hidden in this report

The shape of the right 90-day campaign is: publish two artifacts (a technical write-up of your ρ=0.841 eval calibration methodology; a runnable demo of your knowledge-graph content engine with a public eval harness). Join Latent Space Discord and MLOps Community Slack this week. Apply to **eight specific roles** where your profile is maximally legible — **LangChain Deployed Engineer, Supabase Solutions Architect AMER, Writer AI Engineer remote, Abridge Implementation Director, Ambience Healthcare Implementation, Hebbia AI Strategist, Comet DevRel Lead Opik, and LlamaIndex Applied AI Solutions Architect East Coast** — via Ashby/Greenhouse direct links rather than LinkedIn, and in parallel message one person on LinkedIn at each company (Brace Sproul at LangChain, Tyler Shukert at Supabase, Shiv Rao at Abridge, Mike Valli at Ambience, Stanislas Polu at Dust) with a link to one artifact. Buy the AI Engineer World's Fair ticket. Skip Anthropic's CodeSignal and Harvey's FDE; target Anthropic's Solutions Architect (Creatives) and Harvey's Customer Success or Legal Engineer paths only if the in-person tradeoff is acceptable. The $150K floor is easily clearable at Series B+ AI companies paying flat — your limiting factor is not your Python ability or your LeetCode gap, it's whether you publicly package the proof of your actual capability in the next 30 days.