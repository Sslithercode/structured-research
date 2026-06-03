# Structured Research

A research agent harness which turns questions into reliability-scored claim graphs, then synthesizes cited answers. Runs as both a FastAPI HTTP server and an MCP server so it works directly inside Claude Code.

## What it does

1. **Searches** the web across multiple angles in parallel
2. **Extracts claims** from each source, chunks and embeds them
3. **Merges** corroborated claims across sources, detects conflicts
4. **Builds a graph** — nodes are claims, edges are `supports / contradicts / qualifies`
5. **Scores reliability** of each source (tier: high / medium / low)
6. **Combines** multiple search graphs into a unified evidence base
7. **Synthesizes** a cited answer through the Claude skill

---

## Setup

### Requirements

- Python 3.11+
- Node.js 18+
- An [OpenRouter](https://openrouter.ai) API key (for LLM calls)
- A [Tavily](https://tavily.com) API key (for web search)

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

Create a `.env` file in the root:

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

**Backend** (HTTP + MCP over SSE):
```bash
python -m backend.server
```

**Frontend** (in a separate terminal):
```bash
cd frontend
npm run dev
```

Frontend runs at `http://localhost:5173`, backend at `http://localhost:8000`.

---

## Using with Claude Code (MCP)

Add to your Claude Code MCP config:

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

Then install the skill from the `skill/` folder into your Claude skills directory. Once installed, Claude will automatically use the structured research workflow when you ask research questions.

---

## Configuration (`config.json`)

### `models`

| Field | Default | Description |
|---|---|---|
| `main` | `deepseek/deepseek-v4-pro` | Primary model for extraction, merging, edge classification |
| `cheap` | `deepseek/deepseek-v4-flash` | Faster model for lighter tasks |
| `embeddings` | `sentence-transformers/all-mpnet-base-v2` | Embedding model for claim clustering |

Models are referenced via OpenRouter. Any OpenRouter model ID works here.

### `search`

| Field | Default | Description |
|---|---|---|
| `provider` | `tavily` | Search provider (only `tavily` supported currently) |
| `search_depth` | `basic` | Tavily search depth: `basic` or `advanced` |
| `extract_top_n` | `5` | Number of sources to fetch per query |

### `pipeline`

| Field | Default | Description |
|---|---|---|
| `chunk_size` | `400` | Token size for document chunks before claim extraction |
| `chunk_overlap` | `50` | Overlap between chunks to avoid cutting claims |
| `similarity_threshold` | `0.75` | Cosine similarity threshold for clustering claims. Lower = more aggressive merging. Try `0.65` if you're seeing few conflicts |
| `faithfulness_check` | `true` | Whether to verify extracted claims against source text |
| `require_corroboration` | `false` | If true, drops any claim not supported by at least 2 sources |
| `min_reliability_tier` | `low` | Filter out sources below this tier: `low`, `medium`, or `high` |
| `max_claims_per_source` | `20` | Cap on claims extracted per source document |
| `interruptible` | `false` | If true, pipeline pauses at each stage for UI approval before continuing |
| `require_combine_approval` | `false` | If true, `combine_graphs` MCP call blocks until approved in the UI |

### `research`

Controls the Claude skill behaviour:

| Field | Default | Description |
|---|---|---|
| `min_queries` | `2` | Minimum sub-queries to decompose a research question into |
| `max_queries` | `3` | Maximum sub-queries per research task |
| `max_followup_rounds` | `1` | How many gap-filling search rounds the skill can run after reviewing initial summaries |

### `sources`

| Field | Default | Description |
|---|---|---|
| `trusted` | `[]` | Domain list that gets a reliability boost (e.g. `["nature.com", "arxiv.org"]`) |
| `untrusted` | `[]` | Domain list that gets a reliability penalty |
| `blocked_domains` | `[]` | Domains excluded from search results entirely |
| `blocked_authors` | `[]` | Author names excluded from results (case-insensitive) |

---

## Architecture

```
structured-research/
├── backend/
│   ├── main.py              # FastAPI app — HTTP endpoints + MCP over SSE
│   ├── server.py            # Entry point — runs HTTP + MCP stdio together
│   ├── mcp_server.py        # MCP tool definitions (structured_search, combine_graphs)
│   ├── models.py            # Pydantic models: Source, Claim, Edge, ClaimGraph
│   ├── graph_store.py       # In-memory + disk persistence for graphs
│   ├── broadcaster.py       # SSE pub/sub for frontend live updates
│   ├── pending.py           # Interruptible pipeline state
│   ├── llm.py               # OpenRouter LLM + embedding client
│   ├── config.py            # Config loader
│   └── pipeline/
│       ├── fetch.py         # Web search + document fetching
│       ├── extract_claims.py# Chunk → LLM → structured claims
│       ├── reliability.py   # Source reliability scoring
│       ├── merge.py         # Embedding cluster → LLM merge/conflict detection
│       ├── edges.py         # LLM edge classification (supports/contradicts/qualifies)
│       ├── match.py         # Faithfulness scoring (claim vs source chunk)
│       └── combine.py       # Cross-graph dedup, remap, re-merge
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── store.ts         # Zustand state
│       ├── api.ts           # HTTP client
│       ├── types.ts
│       └── components/
│           ├── GraphWorkspace.tsx
│           ├── ClaimList.tsx
│           ├── SourceList.tsx
│           ├── EdgeList.tsx
│           ├── ConflictPanel.tsx
│           ├── ClaimEditor.tsx
│           ├── PipelineLog.tsx
│           ├── SessionList.tsx
│           └── ConfigPanel.tsx
├── skill/
│   └── SKILL.md             # Claude Code skill for automated research workflow
└── config.json
```

## HTTP API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/research` | Run full pipeline, return graph |
| `POST` | `/research/stream` | Same but SSE stream of pipeline events |
| `POST` | `/combine` | Combine multiple ClaimGraph objects |
| `GET` | `/graphs` | List all stored graphs |
| `GET` | `/graphs/{id}` | Fetch a specific graph |
| `GET` | `/events` | SSE stream of global graph events |
| `POST` | `/approve-stage/{id}/{stage}` | Approve/reject an interruptible pipeline stage |
| `GET` | `/pending-stages` | List stages waiting for approval |
| `POST` | `/approve-combine/{id}` | Approve/reject a pending combine |
| `GET` | `/health` | Health check |

## MCP Tools

| Tool | Description |
|---|---|
| `structured_search` | Run a single search query, returns graph_id + summary |
| `combine_graphs` | Merge one or more graphs into a unified dict-indexed evidence base |

---

## License

BUSL
