import httpx
import logging
from urllib.parse import urlparse
from backend import config
from backend.models import Source

log = logging.getLogger("research.fetch")


def _is_blocked(url: str) -> bool:
    blocked = config.blocked_domains()
    if not blocked:
        return False
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith(f".{d}") for d in blocked)

TAVILY_BASE = "https://api.tavily.com"


async def search(query: str) -> list[dict]:
    log.debug("Tavily search: %r", query)
    cfg = config.search_cfg()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{TAVILY_BASE}/search",
            json={
                "api_key": config.tavily_key(),
                "query": query,
                "search_depth": cfg["search_depth"],
                "max_results": cfg["extract_top_n"],
                "include_raw_content": False,
            },
        )
        r.raise_for_status()
        return r.json()["results"]  # [{url, title, snippet, published_date?}]


async def extract(urls: list[str]) -> list[dict]:
    log.debug("Tavily extract: %d URLs", len(urls))
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{TAVILY_BASE}/extract",
            json={
                "api_key": config.tavily_key(),
                "urls": urls,
            },
        )
        r.raise_for_status()
        return r.json()["results"]  # [{url, raw_content, ...}]


async def fetch_documents(query: str) -> tuple[list[Source], list[dict]]:
    results = await search(query)
    unblocked = [r for r in results if not _is_blocked(r["url"])]
    if len(unblocked) < len(results):
        log.info("Blocked %d result(s) by domain filter", len(results) - len(unblocked))
    results = unblocked
    urls = [r["url"] for r in results]
    extracted = await extract(urls)

    # index extracted by url for quick lookup
    extracted_map = {e["url"]: e for e in extracted}

    sources: list[Source] = []
    documents: list[dict] = []

    for i, result in enumerate(results):
        url = result["url"]
        tavily_score = float(result.get("score", 0.5))
        ext = extracted_map.get(url, {})
        markdown = ext.get("raw_content", result.get("content", ""))

        log.debug("Source s%d: %s [tavily_score=%.2f]", i, url, tavily_score)
        source = Source(
            source_id=f"s{i}",
            url=url,
            date=result.get("published_date"),
            reliability_score=tavily_score,   # preliminary — overwritten in Stage 2
            reliability_tier="medium",         # preliminary — overwritten in Stage 2
        )
        sources.append(source)
        documents.append({
            "source_id": f"s{i}",
            "url": url,
            "markdown": markdown,
            "title": result.get("title", ""),
            "tavily_score": tavily_score,
        })

    return sources, documents
