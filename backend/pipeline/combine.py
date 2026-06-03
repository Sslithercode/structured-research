import logging
from backend.models import ClaimGraph, Source, Claim, Edge
from backend.pipeline.merge import merge_claims
from backend.pipeline.edges import build_edges
from backend.pipeline.match import score_claim_chunks

log = logging.getLogger("research.combine")


def _deduplicate_sources(graphs: list[ClaimGraph]) -> tuple[list[Source], dict[str, str]]:
    """
    Merge sources across graphs, deduplicating by URL.
    Returns (deduped_sources, old_source_id → new_source_id map).
    """
    seen_urls: dict[str, str] = {}   # url → new source_id
    sources: list[Source] = []
    remap: dict[str, str] = {}       # old "s0", "s1" → new global id

    counter = 0
    for gi, graph in enumerate(graphs):
        for source in graph.sources:
            old_id = f"g{gi}_{source.source_id}"
            if source.url in seen_urls:
                remap[old_id] = seen_urls[source.url]
            else:
                new_id = f"gs{counter}"
                counter += 1
                seen_urls[source.url] = new_id
                remap[old_id] = new_id
                updated = source.model_copy()
                updated.source_id = new_id
                sources.append(updated)

    return sources, remap


def _remap_claims(graphs: list[ClaimGraph], source_remap: dict[str, str]) -> list[Claim]:
    """
    Collect all claims across graphs, rewrite source_ids and claim_ids
    to use the new global source IDs.
    """
    claims: list[Claim] = []
    for gi, graph in enumerate(graphs):
        for claim in graph.claims:
            old_source_key = f"g{gi}_{claim.source_id}"
            new_source_id = source_remap.get(old_source_key, claim.source_id)
            updated = claim.model_copy()
            updated.claim_id = f"g{gi}_{claim.claim_id}"
            updated.source_id = new_source_id
            # remap original_texts keys from local source IDs to global source IDs
            updated.original_texts = {
                source_remap.get(f"g{gi}_{old_sid}", old_sid): text
                for old_sid, text in claim.original_texts.items()
            }
            # reset merge state — will be recomputed
            updated.corroborated_by = []
            updated.conflicts_with = []
            claims.append(updated)
    return claims


async def combine_graphs(graphs: list[ClaimGraph]) -> ClaimGraph:
    log.info("Combining %d graphs: %d total claims across %d sources",
             len(graphs),
             sum(len(g.claims) for g in graphs),
             sum(len(g.sources) for g in graphs))

    sources, source_remap = _deduplicate_sources(graphs)
    log.info("After source dedup: %d unique sources", len(sources))

    all_claims = _remap_claims(graphs, source_remap)
    log.info("Remapped %d claims for cross-graph merge", len(all_claims))

    merged_claims, conflict_pairs = await merge_claims(all_claims)
    log.info("Cross-graph merge: %d → %d claims, %d conflict pairs",
             len(all_claims), len(merged_claims), len(conflict_pairs))

    edges = await build_edges(merged_claims, conflict_pairs)
    log.info("Cross-graph edges: %d", len(edges))

    merged_claims = await score_claim_chunks(merged_claims)

    return ClaimGraph(sources=sources, claims=merged_claims, edges=edges)
