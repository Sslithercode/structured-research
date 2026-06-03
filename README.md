# Structured Research

A research harness that turns questions into reliability-scored claim graphs. Instead of returning raw text from the web, it extracts atomic claims from each source, corroborates them across sources, detects conflicts, and builds a structured evidence graph. Runs as both a FastAPI HTTP server and an MCP server — plug it directly into Claude as a custom connector or use it via the frontend UI.

## What it does

1. **Searches** the web via Tavily, fetches and chunks full article content
2. **Extracts atomic claims** from each chunk — classified as fact, prediction, opinion, or reported speech
3. **Scores source reliability** — weighted formula across source authority, author credibility, date relevance, and Tavily score
4. **Merges corroborated claims** — groups claims that assert the same fact across sources into a single canonical claim, preserving original phrasings
5. **Detects conflicts** — identifies pairs of claims that directly contradict each other
6. **Builds an edge graph** — `supports / contradicts / qualifies` edges between claims
7. **Combines graphs** — when multiple searches are run, deduplicates sources, remaps claims, and re-merges across the full evidence set
8. **Scores faithfulness** — verifies extracted claims against the source chunk they came from

The output is a structured `ClaimGraph` — not a summary, not raw text. Claude (or any consumer) gets a graph of what is established, what is contested, and where each fact came from.

---

## Setup

### Requirements

- Python 3.11+
- Node.js 18+
- An [OpenRouter](https://openrouter.ai) API key
- A [Tavily](https://tavily.com) API key

### 1. Clone and install backend

```bash
git clone https://github.com/yourname/structured-research
cd structured-research

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Set up environment

```env
OPENROUTER_API_KEY=sk-or-...
TAVILY_API_KEY=tvly-...
```

### 3. Install frontend

```bash
cd frontend
npm install
cd ..
```

### 4. Run

```bash
# Backend (HTTP + MCP over SSE):
python -m backend.server

# Frontend (separate terminal):
cd frontend
npm run dev
```

Frontend: `http://localhost:5173` — Backend: `http://localhost:8000`

---

## Using with Claude (MCP)

### Claude Code

Add to your MCP config:

```json
{
  "mcpServers": {
    "structured-research": {
      "command": "python",
      "args": ["-m", "backend.server"],
      "cwd": "/path/to/structured-research"
    }
  }
}
```

Install the skill from `skill/` into your Claude skills directory. Claude will automatically decompose research questions into sub-queries, run structured searches, combine the graphs, and synthesize a cited answer.

### Claude.ai (remote connector)

Run the server somewhere publicly accessible, then go to **Settings → Integrations → Add custom integration** and paste:

```
https://your-host/mcp/sse
```

Claude auto-discovers the three MCP tools from there.

---

## Frontend

The frontend is a real-time research workspace:

- **Sessions** — each search is a session; run multiple in parallel
- **Claim filtering** — filter by claim type, source reliability tier, conflicts, corroboration, or free-text search
- **Claim editing** — edit, delete, or add claims before combining
- **Original phrasings** — for corroborated claims, expand to see what each source originally said before the canonical rewrite
- **Conflict panel** — dedicated view of all contradicting claim pairs with their sources
- **Combine** — select multiple sessions, combine into a unified graph with cross-search dedup and re-merge
- **Pipeline log** — live stream of each pipeline stage, with optional pause/approve at each stage
- **Export / Delete** — export any graph as JSON, delete sessions (also removes from disk)

---

## Configuration (`config.json`)

### `models`

| Field | Default | Description |
|---|---|---|
| `main` | `deepseek/deepseek-v4-pro` | Primary model — extraction, merging, edge classification |
| `cheap` | `deepseek/deepseek-v4-flash` | Lighter model for faster tasks |
| `embeddings` | `sentence-transformers/all-mpnet-base-v2` | Embedding model for claim clustering |

Any OpenRouter model ID works.

### `search`

| Field | Default | Description |
|---|---|---|
| `search_depth` | `basic` | Tavily depth: `basic` or `advanced` |
| `extract_top_n` | `5` | Sources fetched per query |

### `pipeline`

| Field | Default | Description |
|---|---|---|
| `chunk_size` | `400` | Word size per document chunk |
| `chunk_overlap` | `50` | Overlap between chunks |
| `similarity_threshold` | `0.75` | Cosine similarity threshold for claim clustering |
| `faithfulness_check` | `true` | Verify claims against source chunk |
| `require_corroboration` | `false` | Drop claims not supported by 2+ sources |
| `min_reliability_tier` | `low` | Filter sources below this tier |
| `max_claims_per_source` | `20` | Cap on claims per source |
| `interruptible` | `false` | Pause at each stage for UI approval |
| `require_combine_approval` | `false` | Block `combine_graphs` until approved in UI |

### `research`

Controls the Claude skill:

| Field | Default | Description |
|---|---|---|
| `min_queries` | `2` | Minimum sub-queries per research question |
| `max_queries` | `3` | Maximum sub-queries |
| `max_followup_rounds` | `1` | Gap-filling rounds after initial search |

### `sources`

| Field | Default | Description |
|---|---|---|
| `trusted` | `[]` | Domains that get a reliability boost |
| `untrusted` | `[]` | Domains that get a reliability penalty |
| `blocked_domains` | `[]` | Domains excluded entirely |
| `blocked_authors` | `[]` | Author names excluded (case-insensitive) |

---

## Architecture

```
structured-research/
├── backend/
│   ├── main.py              # FastAPI app — HTTP endpoints + MCP over SSE
│   ├── server.py            # Entry point — runs HTTP + MCP stdio together
│   ├── mcp_server.py        # MCP tools: structured_search, combine_graphs, get_research_config
│   ├── models.py            # Pydantic models: Source, Claim, Edge, ClaimGraph
│   ├── graph_store.py       # In-memory + disk persistence for graphs
│   ├── broadcaster.py       # SSE pub/sub for frontend live updates
│   ├── pending.py           # Interruptible pipeline state
│   ├── llm.py               # OpenRouter LLM + embedding client
│   ├── config.py            # Config loader
│   └── pipeline/
│       ├── fetch.py         # Tavily search + document fetching
│       ├── extract_claims.py# Chunk → LLM → structured claims + metadata
│       ├── reliability.py   # Source reliability scoring
│       ├── merge.py         # Corroboration grouping + conflict detection
│       ├── edges.py         # Edge classification
│       ├── match.py         # Faithfulness scoring
│       └── combine.py       # Cross-graph dedup, remap, re-merge
├── frontend/
│   └── src/
│       ├── store.ts         # Zustand state + all mutations
│       ├── api.ts           # HTTP client
│       ├── types.ts         # TypeScript types
│       └── components/
│           ├── GraphWorkspace.tsx   # Main workspace with tab navigation
│           ├── ClaimList.tsx        # Claims tab with filtering + search
│           ├── SourceList.tsx       # Sources tab with reliability display
│           ├── EdgeList.tsx         # Edges tab
│           ├── ConflictPanel.tsx    # Conflicts tab
│           ├── ClaimEditor.tsx      # Inline claim editing
│           ├── PipelineLog.tsx      # Live pipeline event stream
│           ├── SessionList.tsx      # Session sidebar with combine controls
│           └── ConfigPanel.tsx      # Runtime config editor
├── skill/
│   └── SKILL.md             # Claude Code skill for automated research
└── config.json
```

## HTTP API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/research` | Run full pipeline, return graph |
| `POST` | `/research/stream` | SSE stream of pipeline events + result |
| `POST` | `/combine` | Combine multiple ClaimGraph objects |
| `GET` | `/graphs` | List all stored graphs |
| `GET` | `/graphs/{id}` | Fetch a specific graph |
| `DELETE` | `/graphs/{id}` | Delete a graph from memory and disk |
| `GET` | `/events` | SSE stream of global graph events |
| `POST` | `/approve-stage/{id}/{stage}` | Approve/reject an interruptible pipeline stage |
| `GET` | `/pending-stages` | List stages waiting for approval |
| `POST` | `/approve-combine/{id}` | Approve/reject a pending combine |
| `GET` | `/health` | Health check |

## MCP Tools

| Tool | Description |
|---|---|
| `get_research_config` | Returns current min/max queries and pipeline settings — call first |
| `structured_search` | Run a single search query, returns graph_id + summary |
| `combine_graphs` | Merge one or more graphs into a unified evidence base |

---

## License

BUSL
