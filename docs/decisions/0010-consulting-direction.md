---
status: retired
date: 2026-04-17
---
# ADR-0010: Consulting commercial direction — retired in favor of AI employment

## Context

The project's original commercial model was behavioral-strategy consulting for B2B SaaS mid-market: Decision Diagnostics ($8K–$15K fixed-scope engagements), Deep Analysis Projects ($15K–$25K), Advisory Retainers ($5K–$8K/month). Fractional CMOs at $30M–$100M ARR B2B SaaS clients were the content audience + referral channel; their end clients were the commercial buyers. Extensive GTM planning, pricing architecture, community access strategy (Pavilion CAF, Fractionals United), and runway math were built out.

## Options considered

- **Continue building the consulting practice** — 18–24 month runway to $250K–$450K annualized per research-validated solo-advisor case studies (Baker, Enns, Karten, Morgan, Stark). Patient ramp, compounding credibility asset, founder-legibility infrastructure.
- **Pivot fully to AI employment** — target Applied AI / Solutions / FDE / DevRel roles at AI-native companies. The engine becomes portfolio piece + content distribution surface. Shorter runway to income.
- **Hybrid** — pursue both simultaneously. Splits operator attention, dilutes both narratives, and makes consulting positioning harder to defend to employment interviewers.

## Decision

Retire the consulting direction. Full pivot to AI employment (target: Applied AI Engineer / AI Solutions Engineer / Forward Deployed Engineer / Developer Relations at AI-native mid-tier companies). Engine continues producing content, but output is now portfolio evidence and LinkedIn distribution surface, not consulting pipeline.

## Consequences

Consulting artifacts (Decision Diagnostic pricing, fractional-CMO ICP descriptions, Pavilion CAF / Fractionals United community access strategy, consulting footers, GTM notes, competitive landscape reports for the consulting market, CRM scaffolding) moved to `.internal/archive/` or deleted. Pricing is no longer published anywhere. The engine's content audience shifts from fractional CMOs (who used to refer end-client buyers) to LinkedIn readers who include hiring managers and business leaders simultaneously. Target company band shifts from "B2B SaaS $30M–$100M ARR" to AI-native mid-tier (Braintrust, LangChain, Comet, Abridge, Ambience, Decagon, Sierra, Intercom, Lorikeet, Supabase, Cursor, Weaviate, Baseten). Do not re-propose consulting pricing, Decision Diagnostic packaging, or fractional-CMO referral model unless a new ADR explicitly revisits this direction.
