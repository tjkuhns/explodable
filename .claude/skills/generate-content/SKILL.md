---
name: generate-content
description: Trigger a content pipeline run (newsletter, brief, or standalone post) via the FastAPI + Celery backend, poll state, display HITL gates inline, accept operator decisions, and return the final draft path. Use when the user wants to generate a Boulder or Explodable piece.
allowed-tools: Bash Read Edit
---

# Generate content via the pipeline

You are running the chat-native content pipeline flow that replaced
`ContentGeneratorPage.jsx` + `BriefGeneratorPage.jsx` + `PipelineReviewPanel.jsx`.
The pipeline itself is unchanged — you call the FastAPI endpoints
(`/api/generate/content`, `/api/pipeline/state/{id}`, `/api/pipeline/resume/{id}`)
and surface HITL gates as inline review moments in chat.

## Required inputs

- **topic** (required, min 10 chars): natural language description of
  what to write about. Specific > generic. "decision fatigue in procurement"
  beats "buyer psychology."
- **brand** (required): `the_boulder` or `explodable`
- **output_type** (optional, default `newsletter`): `newsletter`, `brief`,
  or `standalone_post`
- **client_context** (required only if `output_type=brief`, min 20 chars):
  the specific client situation the brief addresses

If any required input is missing, ask the user before proceeding.

## Flow

### Phase 1: Trigger

```bash
curl -s -X POST http://localhost:8000/api/generate/content \
  -H "Content-Type: application/json" \
  -d '{"topic": "...", "brand": "...", "output_type": "...", "client_context": "..."}'
```

Extract `task_id` and `thread_id` from the response. If the API returns
a validation error, show it and stop.

### Phase 2: Poll to first HITL gate (outline or standalone skip)

```bash
curl -s http://localhost:8000/api/pipeline/state/{thread_id}
```

Poll every 5 seconds until `status` becomes one of:
- `awaiting_outline_review` (newsletters, briefs) — proceed to Phase 3
- `awaiting_draft_review` (standalone posts skip outline gate) — jump to Phase 5
- `error` — show the error and stop
- `complete` — unexpected; show state and stop

Give the user a one-line progress update every 2–3 polls ("kb_retriever
done, now in outline_generator") so they know it's alive, but don't
spam.

### Phase 3: Outline review

Display the outline inline:

**For newsletters:**
```
HITL Gate 2 · Outline Review
{title}
{brand} · {output_type} · ~{estimated_word_count} words · {N} findings

Thesis: {thesis}
Opener concept: {opener_concept}
Closer concept: {closer_concept}

Sections ({N}):
  [1] {heading}
      Purpose: {purpose}
      Arguments: {key_arguments joined}
      Findings: [{finding_indices}]
      Cross-domain: {cross_domain_note if present}
  [2] ...

Source findings ({N}):
  [0] {discipline} · {confidence}% · {claim}
  [1] ...
```

**For briefs:**
Same shape but with `client_context`, `core_diagnosis`, and the 5 rigid
brief sections (Real Buying Decision, Anxiety Map, Buying Committee
Dynamics, Messaging Gaps, Positioning Opportunity).

Then ask: **"Approve, edit (which fields?), or reject?"**

### Phase 4: Resume with outline decision

```bash
curl -s -X POST http://localhost:8000/api/pipeline/resume/{thread_id} \
  -H "Content-Type: application/json" \
  -d '{"action": "approve"}'
```

For edits, include the changed fields (`title`, `thesis`,
`core_diagnosis`, `notes`). For rejection, include a reason.

Poll again until `status=awaiting_draft_review` or `error`.

### Phase 5: Draft review — CRITICAL DISCIPLINE

The draft is written to disk by the publisher_stub_node when the user
approves the draft review. Before approval, the draft text lives in the
pipeline checkpoint state — access via `draft.newsletter` on the state
response.

**Delayed BVCS disclosure is mandatory.** The old UI used an 85%-scroll
trigger to reveal the BVCS score after the operator read the draft. In
chat, the discipline is:

1. Tell the user: **"Draft is ready. It's in the pipeline checkpoint —
   saving it to `drafts/latest_unreviewed.md` so you can read it in your
   editor. Read it aloud, then come back and give me YOUR read of it.
   I'll withhold the BVCS score until you've formed your own impression."**

2. Write the draft text to `drafts/latest_unreviewed.md` via the Write
   tool so the user can open it in their editor. Include frontmatter
   with title, brand, output_type, word_count (but NOT BVCS score).

3. **Wait for the user's read.** Do not summarize the draft. Do not
   quote the best lines. Do not give your own assessment. Wait.

4. When the user shares their read, THEN reveal:
   - BVCS total score + pass/fail
   - Per-dimension breakdown
   - Revision notes if any
   - Your own assessment (brief — don't overshadow the user's read)

5. Ask for decision: **approve, edit (operator provides revised
   text), or reject.**

### Phase 6: Resume with draft decision

```bash
curl -s -X POST http://localhost:8000/api/pipeline/resume/{thread_id} \
  -H "Content-Type: application/json" \
  -d '{"action": "approve"}'
```

For edits, pass `newsletter_edits` with the full revised text.

Poll until `status=complete`. Extract `published_path` from the final
state and report it to the user.

### Phase 7: Report

```
Pipeline complete.
  Brand: {brand}
  Output: {output_type}
  Title: {title}
  Word count: {word_count}
  BVCS: {total_score}/100 ({PASS|FAIL})
  Revisions: {revision_count}
  Published: {published_path}
  Citations: {N citations from N findings}
```

Show the user the published path and ask if they want to open it for
a final read.

## Critical rules

- **NEVER reveal BVCS score before the user shares their read.** The
  anchoring effect is real. This is the single discipline that the UI
  enforced via scroll tracking; in chat it's on us.
- **NEVER editorialize on the draft before the user reads it.** No
  "this one's strong" or "the opener works." Wait.
- **DO write the draft to disk immediately** so the user has something
  to open in their editor. Don't make them scroll through chat.
- **DO check for `citations` on the draft response** — if Citations API
  is active (USE_CITATIONS_API=true, default), the draft.citations field
  will be populated with document_index + cited_text spans. Show the
  user the citation count in Phase 7 as a quality signal.

## Failure modes

- **Pipeline stalls at `starting` for > 60 seconds:** Celery worker
  probably isn't running or doesn't have the task registered. Check
  `pgrep -f "celery.*worker"` and the worker log at
  `logs/celery-content.log`.
- **Outline generator returns empty or errors:** usually means
  retrieval returned too few findings. Check the state response for
  `selected_findings` count. Minimum viable is 3.
- **BVCS revision loop exhausts 3 attempts:** the pipeline proceeds
  to HITL anyway with `bvcs_passed=False`. Flag this clearly in
  Phase 5 — you still wait for the user's read before revealing the
  score, but when you reveal, emphasize the revision count.
- **Draft HITL gate `interrupt()` raises:** this is a pipeline-internal
  bug. Show the error and stop. Don't retry.

## Why not the old UI

`ContentGeneratorPage.jsx` + `BriefGeneratorPage.jsx` + the
`PipelineReviewPanel` were retired 2026-04-14. The same endpoints are
still live — the UI just doesn't exist anymore. This skill reproduces
the operator experience in chat with the same decision points at the
same gates, plus the filesystem-based draft review discipline that the
old UI approximated via scroll tracking.
