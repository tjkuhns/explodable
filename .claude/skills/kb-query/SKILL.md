---
name: kb-query
description: Natural-language query against the KB with graph expansion. Returns findings ranked by semantic similarity, decay weighting, and graph-expansion scoring. Use when the user asks what the KB contains about a topic, wants to explore connections, or needs context for a content generation run.
allowed-tools: Bash Read
---

# Query the Explodable KB

You are running the chat-native KB browser that replaced `KBBrowserPage.jsx`.
This uses the same retriever the content pipeline uses — multi-query
expansion + decay-weighted scoring + graph expansion via typed relationship
edges — so the user sees exactly what the pipeline would see for a given
topic.

## Inputs

The user provides:
- A natural-language topic or question
- Optional: `min_confidence` (default 0.45), `top_k` (default 10),
  `root_anxiety_filter` (one of the 5 anxieties)

## Flow

1. **Call the retriever directly** via Python:
   ```python
   from src.kb.connection import get_connection
   from src.content_pipeline.retriever import retrieve_findings

   with get_connection() as conn:
       results = retrieve_findings(
           conn,
           topic=<user's topic>,
           top_k=10,
           min_confidence=0.45,
           root_anxiety_filter=None,  # or specific anxiety
           brand=None,
           enable_graph_expansion=True,
       )
   ```
   This generates 3 query variants via LLM, runs semantic search per
   variant, decay-weights by age, walks the relationship graph one hop
   from the top 5 semantic seeds, and returns a ranked list.

2. **Display results** in two groups:

   **Semantic matches** (sorted by combined_score descending):
   ```
   [N] {finding.id} · {discipline} · {confidence}%
       similarity={semantic_similarity:.2f} · age={age_days:.0f}d · combined={combined_score:.3f}
       anxieties: {root_anxieties}
       CLAIM: {claim}
       from query variant: "{query_variant}"
   ```

   **Graph-expanded neighbors** (findings surfaced via typed relationships):
   ```
   [G1] {finding.id} · {discipline} · {confidence}%
        via {relationship_type} edge · graph_score={combined_score:.3f}
        CLAIM: {claim}
   ```

   Cross-domain findings (multiple root anxieties or graph-expanded via
   a contradicts/reframes edge) should be flagged with a `⊕` marker
   next to the entry so the user can spot the non-obvious connections.

3. **Summarize the retrieval shape:**
   - N semantic matches, M graph-expanded neighbors
   - Disciplines covered
   - Anxiety distribution across results
   - Any contradicts/reframes edges found (these are the most
     narratively interesting)

4. **Offer follow-ups:**
   - Drill into a specific finding (full elaboration, sources, neighbors)
   - Query a variant topic
   - Use these findings for a content generation run (`/generate-content`)
   - See the full relationship neighborhood of a specific finding

## When the user asks "what does the KB know about X"

Same flow, but emphasize the synthesis:
- Lead with a 2–3 sentence summary of what the findings collectively say
- Then show the individual findings as evidence
- Flag any contradictions or tensions in the returned set

## When the user wants to see structural connections

If they ask "how do these connect" or "what connects X and Y":
- Pull relationships via direct DB query:
  ```sql
  SELECT fr.relationship, fr.rationale, fr.confidence,
         f1.claim as from_claim, f2.claim as to_claim
  FROM finding_relationships fr
  JOIN findings f1 ON f1.id = fr.from_finding_id
  JOIN findings f2 ON f2.id = fr.to_finding_id
  WHERE f1.id = ANY(%s) OR f2.id = ANY(%s)
  ```
- Show the edges with rationales. Graph-viz as HTML file is a
  post-launch enhancement — for now, text rendering is fine.

## Performance notes

- Retrieval generates 3 LLM query-variant calls + 3 embedding calls + 3
  pgvector searches + relationship graph walk. Total: 4–8 seconds typical.
- Caches are warm after the first call in a session.
- `enable_graph_expansion=False` skips the graph walk — useful for
  benchmarking or when the user only wants pure semantic results.

## Critical rules

- **DO NOT make up findings.** If the retriever returns nothing
  (min_confidence too high, topic too generic, KB doesn't cover it),
  say so honestly. Suggest lowering min_confidence or rephrasing.
- **DO show the scores.** The user needs to see whether a match is
  strong (>0.75 combined) or speculative (<0.55). Don't hide the
  epistemic structure.
- **DO flag cross-domain hits.** The anxiety-indexed architecture
  exists to surface non-obvious connections. If a query for B2B
  buying psychology returns a finding about gambling addiction via
  a shared anxiety node, that's the KB working as designed — highlight it.
- **DO NOT run the full content pipeline as a side effect.** Queries
  are read-only. Generation is a separate skill.

## Why not the old UI

`KBBrowserPage.jsx` was the biggest and most useful part of the
retired frontend — it had a working Cytoscape graph view, filterable
list, cluster view. The structural browsing affordance is genuinely
lost in the retirement, which is why an on-demand HTML graph viz is
listed as a post-launch enhancement in `docs/RETIREMENT_PLAN.md`.
Until then, this skill handles targeted queries well; pure structural
browsing is degraded.
