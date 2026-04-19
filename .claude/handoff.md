## As of 2026-04-19

**Last commits (pushed):**
- `cb0c798` — Experimental pipeline: disclose the revision_gate_node integration gap
- `94e80ea` — Demo: split architecture into production vs experimental
- `8f6fe42` — Website/blog: fix architecture drift, retire consulting frame, add receipts
- `81f6de6` — Context continuity: ADRs + CLAUDE.md + selective .claude/ tracking

**What landed this session:**
- 10 MADR-lite ADRs in `docs/decisions/` indexed from `CLAUDE.md`
- `/adr` slash command + handoff template + selective `.claude/` tracking
- Website + blog + Streamlit demo all reconciled: production-vs-experimental architecture split, consulting frame retired with historical-context note, Receipts footer on the blog
- `revision_gate_node` integration gap honestly disclosed in docstring + `architecture.md` §5 + `experimental/README.md`

**Three-reviewer fresh-context portfolio review (all advanced):**
- Recruiter: top 5–10% for Applied AI / DevRel at evals-adjacent
- Applied AI hiring manager: 85th percentile, Mid-to-Senior band
- FDE / Solutions hiring manager: strong fit FDE + Solutions, stretch DevRel
- Full writeups in agent output logs if needed; synthesis was in-conversation only
- **Tier 1 role targets** (named by all three): Braintrust (Issue #185 is the cold intro), LangChain, evals-DevRel (Comet/LangFuse/Arize/W&B)

**In flight (from the plan):**
- **Phase 3** — write `.internal/brag.md` (gitignored SSOT for shipped artifacts): eval harness + ρ=0.841 calibration, Wiki/CAG/RAG bakeoff, N=50 replication, code judge methodology transfer, Braintrust #185, ADR system, 59-test CI suite. One entry per artifact, each with SHA + date + metric + outcome.
- **Phase 4** — resume v1 derived from brag doc. Use `.internal/personal/AI_Engineer_Resume_Research.md` + `resume_prompt.md` as inputs. Pragmatic Engineer / Will Larson structure. Write to `.internal/personal/resume_v1.md`.
- **Phase 5** — LinkedIn audit. **Needs Tom to paste current About + most recent Experience entry.** Can't be done without it.
- **Phase 6 (dropped)** — Tech Radar / public decisions page. Honestly re-rated as nice-to-have, not critical. ADRs already serve the role for anyone who clones.

**Open questions / blockers:**
- LinkedIn profile state unknown until Tom pastes.
- Whether the phased approach still holds or Tom wants to parallelize — default to sequential unless told otherwise.

**Interview prep items (not portfolio fixes — for Tom's own prep):**
- Defensible articulation of "built entirely through AI pair programming" — top 5 insights that were his (flat tool schema after Opus serialization bug, content-vs-execution axis split, post-hoc outlier disclosure, ADR discipline, experimental/production boundary), each with a concrete discovery story.
- FDE gap: no pair-debugging evidence in portfolio. Addressable with a postmortem-style blog post about a live debugging session (even if "customer" was Tom himself).

**Do NOT:**
- Re-propose consulting / GEO / SBIR / two-brand / Boulder / frontier labs (ADRs 0007–0010 covered this; re-proposing is a protocol violation).
- Edit the "Built entirely through AI pair programming" README claim to soften it. Reviewers said it's honest; the fix is interview rehearsal, not portfolio language.
- Wire up the revision_gate stub without also running a new N=50 benchmark to compare. Fixing the stub silently would invalidate the disclosed numbers.
- Touch the blog's calibration criterion verbatim ("fractional CMO forwarding to CEO as evidence of why to hire the firm") — historical context note now frames it; rewriting would invalidate the ρ=0.841 measurement.
