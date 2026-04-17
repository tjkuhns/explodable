# Auditing four B2B schema fields against established taxonomies

Two of your four enums are solid, one needs a modest fix, and one has a real structural problem. Here's the field-by-field verdict against the frameworks that serious practitioners and academics actually use.

## buyer_context mixes a segment axis with two outliers

The **SMB / mid-market / enterprise** spine is standard practice. Every major CRM (Salesforce, HubSpot), every ABM platform (Demandbase, 6sense), and every GTM community (Pavilion, Revenue Collective) uses company-size tiers as the primary segmentation axis — typically defined by employee count or revenue bands. Adding `solo_founder` at the bottom is a defensible B2B-native refinement that HubSpot's default lifecycle stages lack.

The problems are `committee` and `b2c`. **"Committee" is a buying dynamic, not a buyer segment.** Gartner's research shows buying groups of **5–16 stakeholders** across all company sizes; Forrester's 2024 survey puts the average at 13. Every mid-market and enterprise deal involves a committee, so it crosscuts the size axis rather than sitting alongside it. **"b2c" is a business model**, not a buyer context — flag it with a boolean or a separate disqualification field instead.

The deeper question is whether company size alone is sufficient. SaaS RevOps teams increasingly segment by **ACV band** (which determines sales motion: self-serve under $5K, inside sales $5–50K, field sales $50K+, strategic above $150K), and Forrester's B2B Revenue Waterfall redefines the unit of analysis as an opportunity + buying group, not a company. For a content knowledge base, though, company size is the right primary axis — ACV and sales motion are better captured as separate fields.

**Revised enum:** `solo_founder / smb / mid_market / enterprise / n/a` — drop `committee` and `b2c`.

## mechanism_type is a pragmatic hybrid with no academic parent

No dominant taxonomy of behavioral mechanisms exists. The field is **fundamentally fragmented** across incompatible organizing principles: Kahneman organizes by generative heuristic (anchoring, availability, representativeness), Cialdini by interpersonal influence principle (7 principles grouped into relationship-building, uncertainty-reduction, and action-motivation), and the MINDSPACE framework by intervention lever (9 categories: Messenger, Incentives, Norms, Defaults, Salience, Priming, Affect, Commitments, Ego). The closest academic taxonomy is Congdon, Kling & Mullainathan's three categories — imperfect optimization, bounded self-control, nonstandard preferences — but even that doesn't cover your economic-structural categories.

Your enum's real issue is **mixing levels of analysis**. `cognitive_bias` and `emotional_regulation` are individual psychology; `social_dynamic` and `identity_motivation` are social psychology; `structural_incentive` and `information_asymmetry` are microeconomics. This isn't wrong for applied content tagging — it's pragmatically useful — but you should know it's a bespoke schema, not borrowed rigor. One gap: you have **no coverage of defaults/status quo bias**, which appears in every practitioner framework (MINDSPACE, EAST, Nudge) and is arguably the single most powerful mechanism in B2B purchasing.

**Revised enum:** Keep as-is but acknowledge it's custom. Optionally rename `structural_incentive` → `choice_architecture` to bring it closer to behavioral science language and absorb defaults/framing.

## decision_stage is correctly abstracted — keep it

Your four stages map cleanly to the academic five-stage model (Kotler) with information search and evaluation of alternatives merged — a reasonable collapse since B2B content rarely distinguishes the two. You improve on HubSpot's three-stage buyer's journey (Awareness / Consideration / Decision) by including `post_purchase`, and you appropriately ignore Gartner's non-linear six buying jobs (Problem Identification, Solution Exploration, Requirements Building, Supplier Selection, Validation, Consensus Creation), whose concurrency model is important for sales execution but unnecessary for content tagging. MEDDIC, Challenger, and Miller Heiman are **seller-side methodologies** that describe what reps do, not what buyers experience — they're not comparable taxonomies.

**Verdict:** Keep as-is. Four stages is the right abstraction level.

## evidence_tier needs the most work

Every major evidence hierarchy — OCEBM, GRADE, the Cochrane/Campbell pyramid — places systematic reviews at top and expert opinion at bottom. Your enum aligns at the top (`meta_analysis` ≈ OCEBM Level 1) but has three problems below it.

**`peer_reviewed` is too broad.** It collapses OCEBM Levels 2–4 into one tier. A randomized controlled trial and a qualitative interview study are both peer-reviewed but occupy entirely different evidence levels. Split this into `experimental` (RCTs, controlled A/B tests) and `observational` (cohort, cross-sectional, qualitative).

**`theoretical` is a misnomer for the bottom tier.** Every major hierarchy uses "expert opinion," "mechanism-based reasoning," or "anecdotal" at the bottom. Prospect Theory is "theoretical" but backed by decades of experimental evidence — labeling theory as lowest-quality mischaracterizes foundational frameworks. Rename to `expert_opinion`.

**`industry_research` is a pragmatic B2B addition** with no medical equivalent. Gartner and Forrester reports are proprietary, non-peer-reviewed, and methodologically opaque. Placing them at tier 3 is defensible in a business context where they're often the best available evidence, though in scientific terms they sit closer to expert opinion. No Cochrane-equivalent exists for B2B marketing; the Campbell Collaboration covers social science but simply adopts medical-hierarchy methodology.

**Revised enum:** `meta_analysis / experimental / observational / industry_research / case_study / expert_opinion`