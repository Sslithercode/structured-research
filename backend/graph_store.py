"""
Shared graph store — used by both the MCP server and FastAPI routes.
Persists each graph as graphs/{graph_id}.json so exports work and
restarts don't lose everything.
"""
import json
import logging
from pathlib import Path

from backend.models import ClaimGraph

log = logging.getLogger("research.graph_store")

GRAPHS_DIR = Path(__file__).parent.parent / "graphs"
GRAPHS_DIR.mkdir(exist_ok=True)

# graph_id → {"query": str, "graph": ClaimGraph}
_store: dict[str, dict] = {}


def _meta_path(graph_id: str) -> Path:
    return GRAPHS_DIR / f"{graph_id}.json"


def save(graph_id: str, query: str, graph: ClaimGraph) -> None:
    _store[graph_id] = {"query": query, "graph": graph}
    data = {"graph_id": graph_id, "query": query, "graph": graph.model_dump()}
    _meta_path(graph_id).write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info("Graph %s saved (%d claims)", graph_id, len(graph.claims))


def get(graph_id: str) -> dict | None:
    return _store.get(graph_id)


def list_all() -> list[dict]:
    return [
        {"graph_id": gid, "query": v["query"],
         "sources": len(v["graph"].sources),
         "claims": len(v["graph"].claims)}
        for gid, v in _store.items()
    ]


def delete(graph_id: str) -> bool:
    if graph_id not in _store:
        return False
    del _store[graph_id]
    path = _meta_path(graph_id)
    if path.exists():
        path.unlink()
    log.info("Graph %s deleted", graph_id)
    return True


def load_from_disk() -> None:
    """Called once at startup to reload any persisted graphs."""
    count = 0
    for path in GRAPHS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            graph = ClaimGraph.model_validate(data["graph"])
            gid = data["graph_id"]
            query = data.get("query", path.stem)
            _store[gid] = {"query": query, "graph": graph}
            count += 1
        except Exception as e:
            log.warning("Failed to load graph from %s: %s", path, e)
    if count:
        log.info("Loaded %d graphs from disk", count)
