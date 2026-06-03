import asyncio
import logging
from typing import Optional
from pydantic import BaseModel
from backend import llm
from backend.models import Source, Claim
from backend import config
from backend.pipeline.reliability import score_reliability

log = logging.getLogger("research.extract_claims")


class MetadataResponse(BaseModel):
    title: Optional[str] = None
    publication: Optional[str] = None
    authors: list[str] = []
    date: Optional[str] = None


class ClaimItem(BaseModel):
    text: str
    claim_type: str = "fact"  # fact | prediction | opinion | reported_speech


class ClaimsResponse(BaseModel):
    claims: list[ClaimItem]


def _chunk(text: str, max_chunks: int = 10) -> list[str]:
    cfg = config.pipeline_cfg()
    size = cfg["chunk_size"]
    overlap = cfg["chunk_overlap"]
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i: i + size]))
        i += size - overlap
    chunks = [c for c in chunks if len(c.strip()) > 60]
    if len(chunks) <= max_chunks:
        return chunks
    step = len(chunks) / max_chunks
    return [chunks[int(j * step)] for j in range(max_chunks)]


METADATA_PROMPT = """Extract metadata from this article.

Rules:
- authors: real human names only, no institutions. Empty list if none found.
- publication: journal or outlet name (not parent company)
- date: publication date as YYYY-MM-DD, null if not found
- Look carefully — authors often appear after the title or in bylines

Article text:
{text}"""

CLAIMS_PROMPT = """Extract atomic claims from this text that directly answer the query.

Query: {query}

Rules:
- Maximum 5 claims
- Each claim must be a single, self-contained statement
- Write each claim in plain declarative form — no attribution phrases ("According to X", "The article states", "X reports that")
- NEVER include meta-claims about the article itself (e.g. "This article discusses...", "The text covers...", "No information is provided about...")
- NEVER include claims about what a source does or does not confirm — only extract the underlying facts
- Only include claims directly relevant to the query
- Be specific: include numbers, dates, names where present
- Skip boilerplate, ads, navigation text, methodology, and tangential facts
- If the text contains no facts relevant to the query, return an empty list
- For each claim, also classify its claim_type as one of:
  - fact: an established, verifiable fact or measurement
  - prediction: a forecast or projection about the future
  - opinion: a viewpoint, recommendation, or evaluative judgment
  - reported_speech: something a named person or organization stated

Text:
{text}"""


async def _extract_doc_metadata(doc: dict, source: Source) -> Source:
    result: MetadataResponse = await llm.chat_structured(
        [{"role": "user", "content": METADATA_PROMPT.format(text=doc["markdown"])}],
        response_model=MetadataResponse,
    )
    source.publication = result.publication or source.publication
    source.authors = result.authors or []
    if result.date and not source.date:
        source.date = result.date
    return source


async def _extract_chunk_claims(chunk: str, chunk_id: str, source_id: str, query: str) -> list[Claim]:
    try:
        result: ClaimsResponse = await llm.chat_structured(
            [{"role": "user", "content": CLAIMS_PROMPT.format(query=query, text=chunk)}],
            response_model=ClaimsResponse,
        )
        return [
            Claim(
                claim_id=f"{source_id}_{chunk_id}_{i}",
                text=item.text,
                source_id=source_id,
                chunk_text=chunk,
                chunk_id=chunk_id,
                claim_type=item.claim_type,
            )
            for i, item in enumerate(result.claims)
        ]
    except Exception as e:
        log.warning("Claim extraction failed for %s/%s: %s", source_id, chunk_id, e)
        return []


async def process_document(doc: dict, source: Source, query: str) -> tuple[Source, list[Claim]]:
    log.info("Processing doc %s: %s", doc["source_id"], doc["url"])
    source = await _extract_doc_metadata(doc, source)
    log.debug("Metadata — publication: %r, authors: %r, date: %r", source.publication, source.authors, source.date)

    blocked = config.blocked_authors()
    if blocked and any(a.lower() in blocked for a in source.authors):
        log.info("Doc %s skipped — author in blocked list", doc["source_id"])
        return source, []

    score, tier, reasoning = await score_reliability(
        query=query,
        url=source.url,
        publication=source.publication,
        authors=source.authors,
        date=source.date,
        tavily_score=doc.get("tavily_score", 0.5),
        content_preview=doc["markdown"],
    )
    source.reliability_score = score
    source.reliability_tier = tier
    source.reliability_reasoning = reasoning
    log.info("Doc %s reliability — %.2f (%s)", doc["source_id"], score, tier)

    chunks = _chunk(doc["markdown"])
    log.debug("Chunked into %d chunks", len(chunks))

    results = await asyncio.gather(*[
        _extract_chunk_claims(chunk, f"c{i}", doc["source_id"], query)
        for i, chunk in enumerate(chunks)
    ])
    claims = [c for chunk_claims in results for c in chunk_claims]
    max_claims = config.pipeline_cfg().get("max_claims_per_source")
    if max_claims and len(claims) > max_claims:
        claims = claims[:max_claims]
        log.debug("Doc %s — capped to %d claims", doc["source_id"], max_claims)
    log.info("Doc %s — extracted %d claims", doc["source_id"], len(claims))
    return source, claims


async def process_all_documents(
    documents: list[dict], sources: list[Source], query: str
) -> tuple[list[Source], list[Claim]]:
    source_map = {s.source_id: s for s in sources}
    results = await asyncio.gather(*[
        process_document(doc, source_map[doc["source_id"]], query)
        for doc in documents
    ])
    return [r[0] for r in results], [c for r in results for c in r[1]]
