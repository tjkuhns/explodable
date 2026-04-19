---
name: ingest-research
description: Extract findings from a Deep Research markdown document, validate against the taxonomy, dedup, and write as proposed findings in the KB. Use when the user pastes research content or provides a file path to a research doc.
allowed-tools: Bash Read Write Edit
---

# Ingest a Deep Research document into the KB

You are running the chat-native research ingestion flow that replaced
the old `/api/research/upload` HTTP endpoint. The substantive pipeline
is unchanged — you're calling the same code directly via KBStore
instead of going through FastAPI.

## Inputs

The user will provide one of:
- A file path to a markdown document (e.g. `docs/New-Research.md`)
- Pasted research content inline in chat

If the input is ambiguous, ask for clarification once before proceeding.

## Flow

1. **Read the document** into memory via the Read tool (file path) or
   parse the pasted content. Limit: 500KB. Require valid UTF-8 markdown.

2. **Run the extraction prompt** from `config/research_extraction_prompt.txt`
   by constructing an Anthropic API call:
   ```python
   from anthropic import Anthropic
   prompt = open('config/research_extraction_prompt.txt').read().replace('{document_text}', doc_text)
   client = Anthropic(max_retries=5)
   resp = client.messages.create(
       model=os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514'),
       max_tokens=16384,
       messages=[{'role': 'user', 'content': prompt}],
   )
   ```
   Strip markdown code fences from `resp.content[0].text` before parsing.

3. **Parse JSON output.** On parse failure, try to salvage complete
   finding objects from truncated output (the pattern in
   `src/operator_ui/api/research.py:_salvage_truncated_json_array`
   from before the retirement — reimplement inline if needed).

4. **Validate each finding** against `src.kb.ingest_models.FindingInput`.
   This enforces the canonical taxonomy: root_anxieties from the 5-value
   set, primary_circuits from the 7-value Panksepp set, cultural_domains
   from the 25-value list, source_type from the enum. Collect validation
   errors per finding.

5. **Cosine duplicate check** via `src.kb.dedup.cosine_discovery_check`
   (threshold 0.85) for each valid finding. Flag duplicates but do NOT
   write them. Let the user decide later whether to override.

6. **Write non-duplicate valid findings** via `KBStore.create_finding`
   with `provenance=FindingProvenance.HUMAN`, `status=FindingStatus.PROPOSED`,
   `source_document=<filename>`. Capture the returned finding ID.

7. **Write manifestations** for each source in the finding's sources list
   via `KBStore.create_manifestation(data, finding_ids=[finding.id])`.

## Report format

After processing, show the user:

```
Extraction: {filename}
  Extracted: N raw findings
  Written as proposed: N  ← these need review
  Flagged as duplicates: N  ← compared against existing KB
  Validation errors: N
  Classifier skips: N

New finding IDs: [uuid, uuid, ...]

Quality summary:
  - Confidence range: X%–Y%
  - Disciplines covered: [...]
  - Anxiety distribution: [...]
  - Small-N or replication-caveat findings: [...]
```

Then ask: **"Review the proposed findings now (triggers `/review-findings`)
or defer?"**

## Critical rules

- DO NOT auto-approve. Every ingested finding goes to the HITL queue.
- DO NOT fabricate findings when the extraction returns empty. If the
  document has no citable empirical claims, report that honestly and
  ask whether to adjust the extraction prompt or discard the doc.
- DO NOT skip the taxonomy validation. Drift in `cultural_domains` or
  `academic_discipline` will cause retrieval degradation downstream.
- DO log every written finding's ID so the user can undo individual
  entries if something goes wrong.

## Failure modes

- **Extraction LLM returns malformed JSON:** try the salvage pattern,
  then fail loudly. Do not invent findings.
- **Document is empty or non-English:** fail with a clear error.
- **Duplicate check says "everything is a duplicate":** confirm the
  user didn't already upload this doc. Check `source_document` filter
  in an active-findings query.
- **KB write fails on one finding:** log the error, continue with the
  rest, report the failure in the summary.

## Why not go through the HTTP API

The `/api/research/upload` endpoint was retired 2026-04-14 as part of
collapsing the operator interface. The same code path is now invoked
directly via `KBStore` — same validation, same dedup, same write
semantics, zero HTTP round-trip. See `docs/RETIREMENT_PLAN.md` for the
operator model change.
