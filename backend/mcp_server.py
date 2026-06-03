import asyncio
import json
import logging
import uuid
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from backend.logging_config import setup_logging
from backend.pipeline.fetch import fetch_documents
from backend.pipeline.extract_claims import process_all_documents
from backend.pipeline.merge import merge_claims
from backend.pipeline.edges import build_edges
from backend.pipeline.combine import combine_graphs
from backend.pipeline.distill import distill_graph
from backend.models import ClaimGraph
from backend import config, pending as pending_store
from backend import graph_store, broadcaster

setup_logging()
log = logging.getLogger("research.mcp")

server = Server("structured-research")

# distill_id → full distill result dict
_distill_store: dict[str, dict] = {}



def _graph_summary(graph_id: str, query: str, graph: ClaimGraph) -> dict:
    """Compact summary returned to Claude after each search — not the full graph."""
    top_claims = sorted(graph.claims, key=lambda c: len(c.corroborated_by), reverse=True)[:5]
    return {
        "graph_id": graph_id,
        "query": query,
        "total_claims": len(graph.claims),
        "total_edges": len(graph.edges),
        "conflicts": sum(1 for e in graph.edges if e.type == "contradicts"),
        "sources": [
            {
                "id": s.source_id,
                "publication": s.publication or s.url,
                "date": s.date,
                "tier": s.reliability_tier,
            }
            for s in graph.sources
        ],
        "top_claims": [
            {
                "id": c.claim_id,
                "text": c.text,
                "source": c.source_id,
                "corroborated_by": c.corroborated_by,
            }
            for c in top_claims
        ],
    }


def _unified_graph_output(graph: ClaimGraph) -> dict:
    """Full graph returned after combine — this is what Claude synthesizes from."""
    source_map = {s.source_id: s for s in graph.sources}
    claim_map = {c.claim_id: c for c in graph.claims}

    def _source_dict(s) -> dict:
        return {
            "url": s.url,
            "publication": s.publication,
            "authors": s.authors,
            "date": s.date,
            "reliability": round(s.reliability_score, 2),
            "tier": s.reliability_tier,
        }

    def _serialize_claim(c) -> dict:
        primary_source = source_map.get(c.source_id)

        corroborated_by = []
        for sid in c.corroborated_by:
            src = source_map.get(sid)
            if src is None:
                continue
            entry = {"source": _source_dict(src)}
            original_text = c.original_texts.get(sid)
            if original_text:
                entry["original_text"] = original_text
            corroborated_by.append(entry)

        conflicts_with = []
        for cid in c.conflicts_with:
            other = claim_map.get(cid)
            if other is None:
                continue
            other_source = source_map.get(other.source_id)
            entry = {"text": other.text}
            if other_source:
                entry["source"] = _source_dict(other_source)
            conflicts_with.append(entry)

        return {
            "text": c.text,
            "claim_type": c.claim_type,
            "source": _source_dict(primary_source) if primary_source else {"source_id": c.source_id},
            "corroborated_by": corroborated_by,
            "conflicts_with": conflicts_with,
        }

    claims = {c.claim_id: _serialize_claim(c) for c in graph.claims}
    conflict_count = sum(1 for c in graph.claims if c.conflicts_with)
    return {
        "summary": {
            "total_claims": len(claims),
            "total_sources": len(graph.sources),
            "conflict_count": conflict_count,
        },
        "claims": claims,
    }


@server.list_resources()
async def list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            uri=f"graph://{entry['graph_id']}",
            name=entry["query"],
            description=f"{entry['claims']} claims, {entry['sources']} sources",
            mimeType="application/json",
        )
        for entry in graph_store.list_all()
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    graph_id = uri.removeprefix("graph://")
    entry = graph_store.get(graph_id)
    if not entry:
        raise ValueError(f"Unknown graph resource: {uri}")
    graph = entry["graph"]
    output = _unified_graph_output(graph)
    output["graph_id"] = graph_id
    output["query"] = entry["query"]
    return json.dumps(output, indent=2)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="structured_search",
            description=(
                "Search the web for a single query and return a reliability-scored claim graph. "
                "Returns a graph_id and summary — not the full graph. "
                "Call this multiple times with different queries to research a topic from multiple angles. "
                "When done searching, call combine_graphs with all graph_ids to merge everything before synthesizing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The specific search query to research",
                    }
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_research_config",
            description=(
                "Returns the current research configuration. "
                "Call this first before starting any research task to get the correct values for "
                "min_queries, max_queries, and max_followup_rounds."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="distill_graph",
            description=(
                "Distill a combined claim graph into a structured outline mapped back to the original sub-questions. "
                "Run this after combine_graphs. Uses the original graph_ids to trace cross-query corroboration, "
                "scores claims by evidential strength, maps them to sub-questions via LLM, and surfaces high-severity "
                "conflicts and coverage gaps. Use the returned outline as the basis for synthesis — do not synthesize "
                "directly from the raw combined graph."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The original graph_ids passed to combine_graphs",
                    },
                    "combined_graph_id": {
                        "type": "string",
                        "description": "The graph_id returned by combine_graphs",
                    },
                    "original_question": {
                        "type": "string",
                        "description": "The original user question — used to identify emergent findings relevant to the question but outside any sub-question",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Max claims passed to the LLM mapping step (default 50)",
                        "default": 50,
                    },
                },
                "required": ["graph_ids", "combined_graph_id", "original_question"],
            },
        ),
        types.Tool(
            name="get_theme",
            description=(
                "Fetch the full claims for one section of a distilled graph. Call this after distill_graph "
                "to retrieve claims for a specific sub-question or emergent topic (by name), or cross-cutting findings. "
                "Use the exact query string from the skeleton for sub-questions, the exact topic name for emergent topics, "
                "or 'cross_cutting' to get cross-cutting claims."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "distill_id": {
                        "type": "string",
                        "description": "The distill_id returned by distill_graph",
                    },
                    "name": {
                        "type": "string",
                        "description": "Exact sub-question query string, emergent topic name, or 'cross_cutting'",
                    },
                },
                "required": ["distill_id", "name"],
            },
        ),
        types.Tool(
            name="search_graph",
            description=(
                "Search claims within a stored graph by keyword. Use this to drill into a specific "
                "graph (typically the combined graph) without loading the full content. "
                "Returns matching claims with their source, tier, and corroboration info."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_id": {
                        "type": "string",
                        "description": "The graph_id to search (from structured_search or combine_graphs)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Keyword or phrase to search for in claim text",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Max results to return (default 20)",
                        "default": 20,
                    },
                },
                "required": ["graph_id", "query"],
            },
        ),
        types.Tool(
            name="combine_graphs",
            description=(
                "Finalize one or more claim graphs from previous structured_search calls into a unified graph. "
                "With multiple graph_ids: deduplicates sources, merges corroborated claims, detects cross-search conflicts. "
                "With a single graph_id: returns the full graph immediately without re-processing. "
                "Always call this when done searching — use the returned graph as your evidence base for synthesis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of graph_ids from previous structured_search calls",
                    }
                },
                "required": ["graph_ids"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_research_config":
        rc = config._cfg.get("research", {})
        pc = config.pipeline_cfg()
        sc = config.search_cfg()
        return [types.TextContent(type="text", text=json.dumps({
            "research": {
                "min_queries": rc.get("min_queries", 2),
                "max_queries": rc.get("max_queries", 3),
                "max_followup_rounds": rc.get("max_followup_rounds", 1),
            },
            "pipeline": {
                "similarity_threshold": pc.get("similarity_threshold", 0.75),
                "require_corroboration": pc.get("require_corroboration", False),
                "min_reliability_tier": pc.get("min_reliability_tier", "low"),
                "max_claims_per_source": pc.get("max_claims_per_source", 20),
            },
            "search": {
                "search_depth": sc.get("search_depth", "basic"),
                "extract_top_n": sc.get("extract_top_n", 5),
            },
        }))]

    elif name == "structured_search":
        query = arguments["query"]
        log.info("structured_search: %r", query)

        sources, documents = await fetch_documents(query)
        sources, claims = await process_all_documents(documents, sources, query)
        merged_claims, conflict_pairs = await merge_claims(claims)
        edges = await build_edges(merged_claims, conflict_pairs)

        graph = ClaimGraph(sources=sources, claims=merged_claims, edges=edges)
        graph_id = str(uuid.uuid4())[:8]
        graph_store.save(graph_id, query, graph)

        log.info("Graph %s stored: %d claims, %d edges", graph_id, len(merged_claims), len(edges))

        summary = _graph_summary(graph_id, query, graph)

        # push to all connected frontend clients
        import asyncio as _asyncio
        _asyncio.create_task(broadcaster.publish({
            "type": "graph_added",
            "graph_id": graph_id,
            "query": query,
            "summary": summary,
        }))

        return [types.TextContent(type="text", text=json.dumps(summary, indent=2))]

    elif name == "distill_graph":
        graph_ids = arguments["graph_ids"]
        combined_graph_id = arguments["combined_graph_id"]
        original_question = arguments["original_question"]
        top_n = arguments.get("top_n", 50)
        log.info("distill_graph: combined=%s original=%s top_n=%d", combined_graph_id, graph_ids, top_n)
        result = await distill_graph(graph_ids, combined_graph_id, original_question, top_n=top_n)

        distill_id = str(uuid.uuid4())[:8]
        _distill_store[distill_id] = result

        skeleton = {
            "distill_id": distill_id,
            "summary": result["summary"],
            "sub_questions": [
                {"index": i, "query": sq["query"], "coverage": sq["coverage"], "claim_count": len(sq["claims"])}
                for i, sq in enumerate(result["sub_questions"])
            ],
            "cross_cutting_count": len(result["cross_cutting"]),
            "emergent": [{"topic": e["topic"], "relevance": e["relevance"], "claim_count": len(e["claims"])} for e in result["emergent"]],
            "conflicts": result["conflicts"],
            "gaps": result["gaps"],
        }
        return [types.TextContent(type="text", text=json.dumps(skeleton, indent=2))]

    elif name == "get_theme":
        distill_id = arguments["distill_id"]
        theme_name = arguments["name"]
        result = _distill_store.get(distill_id)
        if not result:
            return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown distill_id: {distill_id}"}))]

        if theme_name == "cross_cutting":
            return [types.TextContent(type="text", text=json.dumps({"cross_cutting": result["cross_cutting"]}, indent=2))]

        # match sub-question by query string
        for sq in result["sub_questions"]:
            if sq["query"] == theme_name:
                return [types.TextContent(type="text", text=json.dumps(sq, indent=2))]

        # match emergent topic by topic name
        for topic in result["emergent"]:
            if topic["topic"] == theme_name:
                return [types.TextContent(type="text", text=json.dumps(topic, indent=2))]

        available = (
            [sq["query"] for sq in result["sub_questions"]]
            + [e["topic"] for e in result["emergent"]]
            + ["cross_cutting"]
        )
        return [types.TextContent(type="text", text=json.dumps({
            "error": f"No theme matching {theme_name!r}",
            "available": available,
        }))]

    elif name == "combine_graphs":
        graph_ids = arguments["graph_ids"]
        log.info("combine_graphs: %s", graph_ids)

        missing = [gid for gid in graph_ids if not graph_store.get(gid)]
        if missing:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown graph_ids: {missing}"})
            )]

        if config.require_combine_approval():
            combine_id = str(uuid.uuid4())[:8]
            entry = pending_store.PendingCombine(graph_ids=graph_ids)
            pending_store.pending_combines[combine_id] = entry
            log.info("combine_graphs blocked — awaiting UI approval (combine_id=%s)", combine_id)
            await entry.event.wait()
            if not entry.approved:
                del pending_store.pending_combines[combine_id]
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": "Combine rejected by user"})
                )]
            del pending_store.pending_combines[combine_id]

        raw_graphs = [graph_store.get(gid)["graph"] for gid in graph_ids]
        if len(raw_graphs) == 1:
            unified = raw_graphs[0]
        else:
            unified = await combine_graphs(raw_graphs)

        combined_id = str(uuid.uuid4())[:8]
        combined_query = " + ".join(
            graph_store.get(gid)["query"] for gid in graph_ids
        )
        graph_store.save(combined_id, combined_query, unified)
        import asyncio as _asyncio
        _asyncio.create_task(broadcaster.publish({
            "type": "graph_combined",
            "graph_id": combined_id,
            "query": combined_query,
            "source_ids": graph_ids,
        }))

        log.info("Unified graph: %d sources, %d claims, %d edges",
                 len(unified.sources), len(unified.claims), len(unified.edges))
        conflict_count = sum(1 for c in unified.claims if c.conflicts_with)
        output = {
            "graph_id": combined_id,
            "total_claims": len(unified.claims),
            "total_sources": len(unified.sources),
            "conflict_count": conflict_count,
            "source_graph_ids": graph_ids,
        }
        return [types.TextContent(type="text", text=json.dumps(output, indent=2))]

    elif name == "search_graph":
        graph_id = arguments["graph_id"]
        query = arguments["query"].lower()
        top_n = arguments.get("top_n", 20)

        entry = graph_store.get(graph_id)
        if not entry:
            return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown graph_id: {graph_id}"}))]

        graph = entry["graph"]
        source_map = {s.source_id: s for s in graph.sources}

        matches = [
            c for c in graph.claims
            if query in c.text.lower()
        ]
        matches.sort(key=lambda c: len(c.corroborated_by), reverse=True)
        matches = matches[:top_n]

        results = []
        for c in matches:
            src = source_map.get(c.source_id)
            results.append({
                "claim_id": c.claim_id,
                "text": c.text,
                "claim_type": c.claim_type,
                "source": src.publication or src.url if src else c.source_id,
                "tier": src.reliability_tier if src else "unknown",
                "corroborations": len(c.corroborated_by),
                "conflicts": len(c.conflicts_with),
            })

        return [types.TextContent(type="text", text=json.dumps({
            "graph_id": graph_id,
            "query": query,
            "total_matches": len(results),
            "claims": results,
        }, indent=2))]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
