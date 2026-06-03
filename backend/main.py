import asyncio
import json
import logging
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.routing import Mount
from mcp.server.sse import SseServerTransport

from backend.logging_config import setup_logging
from backend.models import ClaimGraph, ResearchResponse
from backend.pipeline.fetch import fetch_documents
from backend.pipeline.extract_claims import process_all_documents
from backend.pipeline.merge import merge_claims
from backend.pipeline.edges import build_edges
from backend.pipeline.combine import combine_graphs as run_combine
from backend import config, pending as pending_store, graph_store, broadcaster
from backend.mcp_server import server as mcp_server

setup_logging()
log = logging.getLogger("research.main")

app = FastAPI(title="Structured Research API")


@app.on_event("startup")
async def _startup():
    graph_store.load_from_disk()
    log.info("Graph store ready (%d graphs)", len(graph_store.list_all()))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_TIER_ORDER = {"high": 3, "medium": 2, "low": 1}



def _filter_by_tier(sources, claims, edges, min_tier: str):
    cutoff = _TIER_ORDER.get(min_tier, 1)
    allowed = {s.source_id for s in sources if _TIER_ORDER.get(s.reliability_tier, 1) >= cutoff}
    if len(allowed) == len(sources):
        return sources, claims, edges
    filtered_sources = [s for s in sources if s.source_id in allowed]
    filtered_claims = [c for c in claims if c.source_id in allowed]
    surviving = {c.claim_id for c in filtered_claims}
    filtered_edges = [e for e in edges if e.from_claim in surviving and e.to_claim in surviving]
    log.info("min_reliability_tier=%s: kept %d/%d sources, %d/%d claims",
             min_tier, len(filtered_sources), len(sources), len(filtered_claims), len(claims))
    return filtered_sources, filtered_claims, filtered_edges


async def _maybe_pause(
    request_id: str,
    stage: str,
    snapshot: dict,
    events: asyncio.Queue | None,
) -> bool:
    """If interruptible, register a pending stage and block until UI approves. Returns False if rejected."""
    if not config.pipeline_cfg().get("interruptible"):
        return True
    key = f"{request_id}:{stage}"
    entry = pending_store.PendingStage(request_id=request_id, stage=stage, snapshot=snapshot)
    pending_store.pending_stages[key] = entry
    if events:
        await events.put({"stage": "waiting", "pause_stage": stage, "request_id": request_id, "data": snapshot})
    log.info("Pipeline paused at stage=%s request_id=%s", stage, request_id)
    await entry.event.wait()
    del pending_store.pending_stages[key]
    if not entry.approved:
        log.info("Pipeline rejected at stage=%s request_id=%s", stage, request_id)
        return False
    return True


async def _run_pipeline(query: str, request_id: str, events: asyncio.Queue | None = None):
    async def emit(stage: str, data: dict):
        if events is not None:
            await events.put({"stage": stage, **data})

    await emit("start", {"message": "Pipeline started", "query": query, "request_id": request_id})

    log.info("[1/4] Fetching sources")
    await emit("fetch", {"message": "Fetching sources"})
    sources, documents = await fetch_documents(query)
    await emit("fetch_done", {
        "message": f"Fetched {len(sources)} sources",
        "sources": [{"id": s.source_id, "url": s.url, "date": s.date} for s in sources],
    })

    ok = await _maybe_pause(request_id, "fetch", {
        "sources": [{"id": s.source_id, "url": s.url} for s in sources]
    }, events)
    if not ok:
        raise RuntimeError("Pipeline cancelled at fetch stage")

    log.info("[2/4] Extracting claims from %d documents", len(documents))
    await emit("extract", {"message": f"Extracting claims from {len(documents)} documents"})
    sources, claims = await process_all_documents(documents, sources, query)
    await emit("extract_done", {
        "message": f"Extracted {len(claims)} claims",
        "count": len(claims),
        "sources": [
            {"id": s.source_id, "url": s.url, "reliability_tier": s.reliability_tier,
             "reliability_score": round(s.reliability_score, 2), "publication": s.publication,
             "authors": s.authors, "date": s.date}
            for s in sources
        ],
    })

    ok = await _maybe_pause(request_id, "extract", {
        "claims": [{"id": c.claim_id, "text": c.text, "source_id": c.source_id} for c in claims]
    }, events)
    if not ok:
        raise RuntimeError("Pipeline cancelled at extract stage")

    log.info("[3/4] Merging and clustering claims")
    await emit("merge", {"message": "Merging and clustering claims"})
    merged_claims, conflict_pairs = await merge_claims(claims)
    await emit("merge_done", {
        "message": f"Merged to {len(merged_claims)} claims, {len(conflict_pairs)} conflict pairs",
        "claim_count": len(merged_claims),
        "conflict_count": len(conflict_pairs),
    })

    ok = await _maybe_pause(request_id, "merge", {
        "claims": [{"id": c.claim_id, "text": c.text, "source_id": c.source_id,
                    "corroborated_by": c.corroborated_by} for c in merged_claims],
        "conflicts": [{"a": a, "b": b} for a, b in conflict_pairs],
    }, events)
    if not ok:
        raise RuntimeError("Pipeline cancelled at merge stage")

    log.info("[4/4] Classifying %d conflict edges", len(conflict_pairs))
    await emit("edges", {"message": f"Classifying {len(conflict_pairs)} conflict edges"})
    edges = await build_edges(merged_claims, conflict_pairs)
    await emit("edges_done", {"message": f"Built {len(edges)} edges", "count": len(edges)})

    min_tier = config.pipeline_cfg().get("min_reliability_tier", "low")
    sources, merged_claims, edges = _filter_by_tier(sources, merged_claims, edges, min_tier)

    await emit("done", {"message": "Pipeline complete"})
    return sources, merged_claims, edges


# ── Request models ────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str

class CombineRequest(BaseModel):
    graphs: list[dict]  # list of ClaimGraph.model_dump() — client sends edited graphs

class ApprovalRequest(BaseModel):
    approved: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/research", response_model=ResearchResponse)
async def research(req: QueryRequest):
    request_id = str(uuid.uuid4())[:8]
    log.info("Query received: %r (request_id=%s)", req.query, request_id)
    try:
        sources, merged_claims, edges = await _run_pipeline(req.query, request_id)
        graph = ClaimGraph(sources=sources, claims=merged_claims, edges=edges)
        return ResearchResponse(query=req.query, graph=graph, response="", sentence_scores=[])
    except Exception as e:
        log.exception("Pipeline failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/research/stream")
async def research_stream(req: QueryRequest):
    request_id = str(uuid.uuid4())[:8]
    log.info("Streaming query: %r (request_id=%s)", req.query, request_id)
    events: asyncio.Queue = asyncio.Queue()

    async def run():
        try:
            sources, merged_claims, edges = await _run_pipeline(req.query, request_id, events)
            graph = ClaimGraph(sources=sources, claims=merged_claims, edges=edges)
            result = ResearchResponse(query=req.query, graph=graph, response="", sentence_scores=[])
            await events.put({"stage": "result", "data": result.model_dump()})
        except Exception as e:
            log.exception("Streaming pipeline failed: %s", e)
            await events.put({"stage": "error", "message": str(e)})
        finally:
            await events.put(None)

    asyncio.create_task(run())

    async def event_generator():
        while True:
            item = await events.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/combine")
async def combine(req: CombineRequest):
    """Takes edited graphs from the UI and runs combine on them."""
    try:
        graphs = [ClaimGraph.model_validate(g) for g in req.graphs]
        unified = await run_combine(graphs)
        return unified.model_dump()
    except Exception as e:
        log.exception("Combine failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/approve-stage/{request_id}/{stage}")
async def approve_stage(request_id: str, stage: str, req: ApprovalRequest):
    key = f"{request_id}:{stage}"
    entry = pending_store.pending_stages.get(key)
    if not entry:
        raise HTTPException(status_code=404, detail="No pending stage found")
    entry.approved = req.approved
    entry.event.set()
    return {"ok": True}


@app.get("/pending-stages")
async def list_pending_stages():
    return [
        {"request_id": e.request_id, "stage": e.stage, "snapshot": e.snapshot}
        for e in pending_store.pending_stages.values()
    ]


@app.post("/approve-combine/{combine_id}")
async def approve_combine(combine_id: str, req: ApprovalRequest):
    entry = pending_store.pending_combines.get(combine_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No pending combine found")
    entry.approved = req.approved
    entry.event.set()
    return {"ok": True}


@app.get("/pending-combines")
async def list_pending_combines():
    return [
        {"combine_id": cid, "graph_ids": e.graph_ids}
        for cid, e in pending_store.pending_combines.items()
    ]


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Global event stream (SSE push to all frontend clients) ────────────────────

@app.get("/events")
async def events():
    q = broadcaster.subscribe()

    async def generate():
        # send current graph list immediately on connect so UI can hydrate
        snapshot = {"type": "snapshot", "graphs": graph_store.list_all()}
        yield f"data: {json.dumps(snapshot)}\n\n"
        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            broadcaster.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Graph REST endpoints ───────────────────────────────────────────────────────

@app.get("/graphs")
async def list_graphs():
    return graph_store.list_all()


@app.get("/graphs/{graph_id}")
async def get_graph(graph_id: str):
    entry = graph_store.get(graph_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Graph not found")
    return {"graph_id": graph_id, "query": entry["query"], "graph": entry["graph"].model_dump()}


@app.delete("/graphs/{graph_id}")
async def delete_graph(graph_id: str):
    deleted = graph_store.delete(graph_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Graph not found")
    await broadcaster.publish({"type": "graph_deleted", "graph_id": graph_id})
    return {"ok": True}


# ── MCP over SSE ──────────────────────────────────────────────────────────────
_sse = SseServerTransport("/mcp/messages")

@app.get("/mcp/sse")
async def mcp_sse(request: Request):
    async with _sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())

app.router.routes.append(Mount("/mcp/messages", app=_sse.handle_post_message))
