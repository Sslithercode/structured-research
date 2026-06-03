---
name: structured-research
description: >
  Structured research skill using the structured-research MCP server. Use this skill
  whenever the user asks a research question, wants to investigate a topic, asks
  "what do we know about X", wants sources cited, or asks anything that benefits
  from searching multiple angles and synthesizing findings. This skill decomposes
  the question into sub-queries, runs parallel web searches that return
  reliability-scored claim graphs, combines all graphs into a unified evidence base,
  distills that evidence into a structured outline mapped back to the original
  sub-questions, then synthesizes a well-cited answer from the outline — not from
  raw claims. Trigger this skill for any non-trivial research question.
---

# Structured Research

You have access to six MCP tools: `get_research_config`, `structured_search`, `combine_graphs`, `search_graph`, `distill_graph`, and `get_theme`. Use them in order. Never synthesize directly from a raw claim graph — always distill first.

## Workflow

### Step 0 — Fetch config

Call `get_research_config` first. It returns the live config:
```json
{
  "research": { "min_queries": 2, "max_queries": 3, "max_followup_rounds": 1 },
  "pipeline": { "similarity_threshold": 0.75, "require_corroboration": false, "min_reliability_tier": "low", "max_claims_per_source": 20 },
  "search":   { "search_depth": "basic", "extract_top_n": 5 }
}
```

Values that govern your behaviour:
- `research.min_queries` / `research.max_queries` — how many sub-queries to run
- `research.max_followup_rounds` — how many gap-filling rounds you may run after distill
- `pipeline.require_corroboration` — if true, only claims backed by 2+ sources survive
- `pipeline.min_reliability_tier` — sources below this tier were filtered out
- `search.extract_top_n` — sources per query; lower = faster, less coverage

Do not hardcode any of these.

### Step 1 — Decompose the question

Break the user's question into between `min_queries` and `max_queries` focused sub-queries. These sub-queries are the skeleton the final answer will be organized around — not just search strings but the actual questions that need answering.

Each should target a distinct angle:
- Core facts / current state
- Causes, mechanisms, or context
- Implications, conflicts, or edge cases

Good sub-queries are specific and searchable. "nuclear fusion private investment 2025" is better than "nuclear fusion".

Hold onto the exact sub-query strings — you will need them for `distill_graph`.

### Step 2 — Run parallel searches

Call `structured_search` for each sub-query simultaneously. Each returns a summary:
```
{
  graph_id, query,
  total_claims, total_edges, conflicts,
  sources: [{id, publication, date, tier}],
  top_claims: [{id, text, source, corroborated_by}]
}
```

Collect all `graph_id` values.

### Step 3 — Evaluate gaps

Review the summaries. Ask:
- Are there important angles completely missing?
- Do top claims suggest a follow-up would unlock more depth?
- Are there conflicts that warrant a targeted search to resolve?

If yes, run follow-up searches — up to `max_followup_rounds` additional rounds. If summaries feel complete, skip this.

### Step 4 — Combine graphs

Call `combine_graphs` with all `graph_id` values collected so far. This merges sources, deduplicates corroborated claims, and surfaces cross-search conflicts.

The response is always a lean summary — the full graph is stored server-side:
```json
{ "graph_id": "a9f21c3b", "total_claims": 107, "total_sources": 15, "conflict_count": 19, "source_graph_ids": [...] }
```

Note the returned `graph_id` — this is your `combined_graph_id` for the next step.

If you need to drill into specific claims before distilling, use `search_graph(graph_id, keyword)` — it searches the stored graph server-side and returns only matching claims. Do not try to read the full graph into context.

### Step 5 — Distill

Call `distill_graph` with:
- `graph_ids` — the original search graph IDs from Step 2 and any follow-ups (not the combined graph ID)
- `combined_graph_id` — the ID returned by `combine_graphs`
- `original_question` — the user's original question verbatim
- `top_n` — omit to use the default (50); increase if the question is broad and you want more coverage

This returns a structured outline:
```
{
  summary: { original_question, total_claims, total_sources, top_n_used, sub_questions },
  sub_questions: [
    {
      query: "...",
      coverage: "strong" | "partial" | "none",
      claims: [{ text, claim_type, score, source, corroboration, conflicts }]
    }
  ],
  cross_cutting: [...],   // claims relevant to multiple sub-questions
  emergent: [             // relevant findings outside any sub-question
    { topic, relevance, claims: [...] }
  ],
  conflicts: [            // high-severity conflicts only (both sides high-tier)
    { claim_a, source_a, tier_a, claim_b, source_b, tier_b }
  ],
  gaps: [...]             // sub-questions with weak or no coverage
}
```

### Step 6 — Handle gaps from distill

Review `gaps` and `emergent` in the distill output.

- If `gaps` contains sub-questions with `coverage: "none"` and you have remaining `max_followup_rounds`, run targeted searches for those gaps, then re-run `combine_graphs` and `distill_graph` with the expanded set.
- `emergent` topics are findings that surfaced from the evidence but weren't explicitly searched — do not run additional searches for these. They are findings, not gaps.

### Step 7 — Synthesize from the outline

`distill_graph` returns a lean skeleton — sub-question names, coverage ratings, conflict count, gaps, emergent topic names. The full claims are stored server-side.

For each sub-question with `coverage: "strong"` or `"partial"`, call `get_theme(distill_id, name="<exact query string>")` to fetch that theme's full claims before writing that section. Do this one theme at a time as you synthesize.

For cross-cutting findings: `get_theme(distill_id, name="cross_cutting")`.
For emergent topics: `get_theme(distill_id, name="<exact topic name>")`.

Do not try to fetch all themes at once. Pull each theme as you write it.

**Structure your answer around the distill output:**
- One section per sub-question that has `coverage: "strong"` or `"partial"`
- A section for cross-cutting findings if `cross_cutting` is non-empty
- A section for emergent findings if `emergent` is non-empty — introduce these as "the research also surfaced..." to signal they weren't in the original scope
- A conflicts section if `conflicts` is non-empty — surface both sides explicitly

**Citation rules:**
- Use publication names, not internal IDs: "according to Reuters" not "source gs4"
- For corroborated claims: name the key sources or say "corroborated by N independent sources"
- For conflicted claims: always present both sides — "Reuters reports $100B while FT reports $98B"
- For predictions and opinions: flag them — "analysts predict...", "one view holds..."
- High-tier sources carry more weight — reflect this in how confidently you state things
- Cross-query corroborated claims (same fact found across independent searches) are the strongest evidence — treat them with highest confidence

**Coverage signals:**
- `coverage: "strong"` — write with confidence
- `coverage: "partial"` — write but note limited evidence
- `coverage: "none"` — if still present after gap-filling, say explicitly that this angle wasn't covered by available sources

**Never expose** internal IDs (gs0, g0_s1_c0_2, etc.) in your response.

## Example citation patterns

- "Global private fusion investment has exceeded $10 billion — a figure reported consistently across all high-reliability sources including the IAEA, Bloomberg, and the Clean Air Task Force."
- "There is genuine disagreement on the funding figure: Reuters reported $5 billion in early 2024, while more recent data from Bloomberg puts the total above $10 billion, likely reflecting rapid growth over that period."
- "The MIT Energy Initiative predicts fusion must cost below $4,000/kW to compete with renewables, though this is highly dependent on carbon policy constraints."
- "The research also surfaced concerns about grid integration that weren't part of the original scope — multiple high-tier sources flagged transmission infrastructure as a binding constraint on deployment timelines."
