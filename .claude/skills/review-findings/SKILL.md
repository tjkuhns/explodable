---
name: review-findings
description: Review all proposed findings in the KB — display in bulk, take approve/reject/edit decisions, fire relationship classification on approve. Use when the user wants to work through the HITL queue of newly-ingested findings or when load-state surfaces pending findings.
allowed-tools: Bash Read Edit
---

# Review HITL findings queue

You are running the chat-native HITL gate 1 review flow that replaced
the `ResearchReviewPage.jsx` React UI. Same substantive pipeline —
you call `KBStore` directly and `classify_and_commit` fires on approve
just like it did from the old endpoint.

## Flow

1. **Query proposed findings** via `KBStore.list_findings(status=FindingStatus.PROPOSED)`.
   Group by `source_document` so multiple upload batches are visually
   distinct.

2. **Display the batch** in compact form, one finding per entry:
   ```
   [N] {uuid}
       {academic_discipline} · {confidence}% · {anxieties}
       circuits: {circuits} (if present)
       domains: {cultural_domains} (if present)
       era: {era}
       CLAIM: {claim}
       ELAB: {elaboration, truncated to 400 chars}
       BASIS: {confidence_basis, truncated to 200 chars}
   ```
   Sort by confidence descending so strongest findings show first.

3. **Summarize quality.** Read all findings in the batch and give the
   user a 4–6 bullet summary covering:
   - Confidence distribution
   - Disciplines represented
   - Anxiety distribution
   - Cross-domain reach (findings spanning 2+ anxieties or disciplines)
   - Any small-N or replication-caveat flags you notice
   - Any findings that look structurally important for the Explodable
     thesis (fear → testimony framing) or the Boulder thesis (anxiety
     architecture of abstract systems)

4. **Ask for a decision.** Offer three modes:
   - **Bulk approve all:** fires the approval pipeline on every finding,
     relationship classification runs on each, report cumulative stats
   - **Bulk with exceptions:** user specifies "approve all except N, M"
     or "reject N, approve rest"
   - **One-by-one:** walk through the list individually

   My recommendation is always bulk-with-exceptions unless the batch
   looks weak (mixed confidence, taxonomy drift, or small batches
   < 10 findings).

5. **Execute decisions.** For each approved finding:
   ```python
   result = store.approve_finding(finding.id)
   rel_stats = classify_and_commit(conn, finding.id)
   ```
   Log per-finding results (committed/queued/skipped/fk_errors counts).

6. **For bulk batches of 20+ findings**, run the approvals in a
   background task so the chat doesn't block for 20+ minutes. Use
   `run_in_background=true` on the Bash call and surface progress
   via a log file.

## Report format

After the batch completes:

```
BATCH COMPLETE in {duration}s
  Findings approved: N
  Findings rejected: N
  Relationships committed: N
  Relationships queued for review: N (in logs/relationship_review_queue.json)
  Classification skipped: N
  Errors: N

KB state delta:
  Active findings: X → Y (+Z)
  Total relationships: A → B (+C)
  New contradictions: N

New relationship breakdown: supports/extends/qualifies/subsumes/reframes/contradicts
```

Then flag for the user:
- Any findings that triggered new `contradicts` edges (interesting — worth a look)
- Any findings where the classifier produced 0 committed edges (isolated
  nodes that may indicate a cross-domain gap)
- Any items queued for manual review in `logs/relationship_review_queue.json`

## Edge cases

- **Queue is empty:** tell the user "no proposed findings pending" and
  suggest `/load-state` if they're looking for work.
- **Classifier Pydantic bug recurs:** the 2026-04-14 fix made
  `a_element`, `b_element`, `direction_check` optional. If you see
  validation errors on those fields, something has regressed — flag
  it, don't swallow silently.
- **Batch includes findings with the SAME claim_hash as existing
  active findings:** this shouldn't happen (dedup runs on write) but
  if it does, the approve call will fail — log and continue.
- **Relationship classifier fires 20 LLM calls per approved finding:**
  at 32 findings that's ~640 calls taking ~28 minutes. For large
  batches, use the background task pattern and poll the log file.

## Why not go through the HTTP API

`/api/findings/pending` and `/api/findings/{id}/approve` were retired
2026-04-14. KBStore is the single source of truth now and chat drives
it directly. Same code, fewer layers.
