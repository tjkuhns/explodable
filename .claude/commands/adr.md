---
description: Draft a new Architecture Decision Record in docs/decisions/
---

You are drafting a new ADR in `docs/decisions/` using the MADR-lite format from `docs/decisions/TEMPLATE.md`.

**Process:**

1. Run `ls docs/decisions/` to find the highest-numbered ADR. The new file's number is that + 1, zero-padded to 4 digits (e.g., `0011`).
2. Ask the user for the short title (imperative kebab-case for the filename, human-readable for the heading). Skip if already given in $ARGUMENTS.
3. Draft the ADR body by interviewing the user for:
   - **Context** — what prompted this? Name the problem, not the solution.
   - **Options considered** — at least two real options, each with its key tradeoff. Pure strawmen don't count.
   - **Decision** — which option, and why.
   - **Consequences** — what this makes easier AND what it makes harder. Include follow-up cleanup work the decision creates.
4. If this ADR supersedes a prior one, add `supersedes: NNNN` to the frontmatter and mark the prior ADR's status as `superseded-by-NNNN` in a follow-up edit.
5. Write the file to `docs/decisions/NNNN-short-title.md`.
6. Update the Decisions index table in `CLAUDE.md` with the new row.
7. Do NOT commit automatically — leave that to the user.

**Status vocabulary:** `proposed` | `accepted` | `superseded-by-NNNN` | `rejected` | `retired`. Default to `accepted` unless the user indicates the decision is still under discussion.

**Date:** use today's date in `YYYY-MM-DD` format.

**Length target:** ~20–40 lines total. ADRs are load-bearing precisely because they're short enough to read before re-litigating. Resist padding.

**Tone:** declarative, past-tense for Context / Decision, imperative for Consequences. No hedging, no marketing voice.

$ARGUMENTS
