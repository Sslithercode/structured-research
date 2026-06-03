import json
import logging
from pydantic import BaseModel
from backend import llm, graph_store
from backend.models import Claim, Source

log = logging.getLogger("research.distill")

TIER_WEIGHT = {"high": 3, "medium": 2, "low": 1}


# ── Pydantic models for LLM structured output ────────────────────────────────

class MappedClaim(BaseModel):
    claim_id: str
    sub_question: str        # verbatim sub-question this answers, or "emerged" if none
    cross_cutting: bool      # true if genuinely spans multiple sub-questions


class EmergentTopic(BaseModel):
    topic: str               # short label
    claim_ids: list[str]     # which claims belong here
    relevance: str           # one sentence on why this is relevant to the original question


class DistillMapping(BaseModel):
    mappings: list[MappedClaim]
    emergent_topics: list[EmergentTopic]   # relevant findings outside any sub-question
    gaps: list[str]                        # sub-questions with weak or no coverage


# ── Deterministic scoring ─────────────────────────────────────────────────────

def _build_source_origin(graph_ids: list[str]) -> dict[str, str]:
    """Returns {source_url: original_graph_id} by walking each subgraph's sources."""
    url_to_graph: dict[str, str] = {}
    for gid in graph_ids:
        entry = graph_store.get(gid)
        if not entry:
            continue
        for source in entry["graph"].sources:
            if source.url not in url_to_graph:
                url_to_graph[source.url] = gid
    return url_to_graph


def _score_claim(
    claim: Claim,
    source_map: dict[str, Source],
    url_to_graph: dict[str, str],
    claim_origin_graph: str,
) -> tuple[float, bool]:
    """
    Returns (score, cross_query).
    Score: primary tier weight + corroboration tier weights, 1.5x bonus for cross-query.
    """
    primary = source_map.get(claim.source_id)
    primary_weight = TIER_WEIGHT.get(primary.reliability_tier, 1) if primary else 1
    score = float(primary_weight)

    cross_query = False
    for sid in claim.corroborated_by:
        src = source_map.get(sid)
        if not src:
            continue
        score += TIER_WEIGHT.get(src.reliability_tier, 1)
        corr_graph = url_to_graph.get(src.url)
        if corr_graph and corr_graph != claim_origin_graph:
            cross_query = True

    if cross_query:
        score *= 1.5

    return score, cross_query


def _conflict_severity(
    claim: Claim,
    claim_map: dict[str, Claim],
    source_map: dict[str, Source],
) -> str:
    """high if both sides high-tier, low if either side low-tier, medium otherwise."""
    primary = source_map.get(claim.source_id)
    primary_tier = primary.reliability_tier if primary else "low"

    max_conflict_tier = "low"
    for cid in claim.conflicts_with:
        if not isinstance(cid, str):
            continue
        other = claim_map.get(cid)
        if not other:
            continue
        other_src = source_map.get(other.source_id)
        if other_src:
            t = other_src.reliability_tier
            if TIER_WEIGHT.get(t, 1) > TIER_WEIGHT.get(max_conflict_tier, 1):
                max_conflict_tier = t

    if primary_tier == "high" and max_conflict_tier == "high":
        return "high"
    if primary_tier == "low" or max_conflict_tier == "low":
        return "low"
    return "medium"


def _claim_origin(claim_id: str, graph_ids: list[str]) -> str:
    """Recover which original graph a combined claim came from via its g{i}_ prefix."""
    parts = claim_id.split("_")
    if parts and parts[0].startswith("g"):
        try:
            idx = int(parts[0][1:])
            if idx < len(graph_ids):
                return graph_ids[idx]
        except ValueError:
            pass
    return graph_ids[0] if graph_ids else ""


# ── LLM mapping step ──────────────────────────────────────────────────────────

DISTILL_PROMPT = """You are analyzing research claims gathered to answer a user's question. Your job is to organize them.

Original question: {original_question}

Sub-questions that were searched (these are the angles explicitly covered):
{sub_questions}

Claims (scored by evidential strength — higher score = more corroborated):
{claims}

Your tasks:

1. For each claim, assign it to the sub-question it most directly answers. Use the exact sub-question text verbatim. If a claim genuinely spans multiple sub-questions set cross_cutting to true.

2. Identify emergent topics — claims that are relevant to the original question but do not belong to any sub-question. These are findings the searches surfaced that weren't anticipated. Group related claims together under a short topic label and explain in one sentence why this is relevant to the original question. Do not include claims that are simply tangential or off-topic.

3. Identify gaps — sub-questions where the evidence is thin, weak, or absent. Be specific about what's missing.

Only use sub-question text verbatim from the list above. Do not invent sub-questions."""


async def _llm_map(
    serialized_claims: list[dict],
    sub_questions: list[str],
    original_question: str,
) -> DistillMapping:
    return await llm.chat_structured(
        [{"role": "user", "content": DISTILL_PROMPT.format(
            original_question=original_question,
            sub_questions="\n".join(f"- {q}" for q in sub_questions),
            claims=json.dumps(serialized_claims, indent=2),
        )}],
        response_model=DistillMapping,
        role="main",
    )


# ── Claim serialization helper ────────────────────────────────────────────────

def _serialize_claim(claim: Claim, score: float, cross_query: bool, source_map: dict[str, Source]) -> dict:
    primary = source_map.get(claim.source_id)
    return {
        "claim_id": claim.claim_id,
        "text": claim.text,
        "claim_type": claim.claim_type,
        "score": round(score, 2),
        "cross_query_corroboration": cross_query,
        "source": {
            "publication": primary.publication if primary else None,
            "url": primary.url if primary else None,
            "tier": primary.reliability_tier if primary else "unknown",
            "reliability": round(primary.reliability_score, 2) if primary else None,
        },
        "corroboration": {
            "count": len(claim.corroborated_by),
            "sources": [
                {
                    "publication": source_map[sid].publication if sid in source_map else sid,
                    "tier": source_map[sid].reliability_tier if sid in source_map else "unknown",
                    "original_text": claim.original_texts.get(sid),
                }
                for sid in claim.corroborated_by
                if sid in source_map
            ],
        },
    }


# ── Main distill function ─────────────────────────────────────────────────────

async def distill_graph(
    graph_ids: list[str],
    combined_graph_id: str,
    original_question: str,
    top_n: int = 50,
) -> dict:
    combined_entry = graph_store.get(combined_graph_id)
    if not combined_entry:
        raise ValueError(f"Combined graph {combined_graph_id} not found")
    combined = combined_entry["graph"]

    source_map = {s.source_id: s for s in combined.sources}
    claim_map  = {c.claim_id: c for c in combined.claims}

    sub_questions: list[str] = []
    for gid in graph_ids:
        entry = graph_store.get(gid)
        if entry:
            sub_questions.append(entry["query"])

    log.info("Distilling %s: %d claims, %d sub-questions, top_n=%d",
             combined_graph_id, len(combined.claims), len(sub_questions), top_n)

    url_to_graph = _build_source_origin(graph_ids)

    # Score all claims deterministically
    scored: list[tuple[float, bool, Claim]] = []
    for claim in combined.claims:
        origin = _claim_origin(claim.claim_id, graph_ids)
        score, cross_query = _score_claim(claim, source_map, url_to_graph, origin)
        scored.append((score, cross_query, claim))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    log.info("Score range for top %d: %.1f – %.1f",
             len(top), top[0][0] if top else 0, top[-1][0] if top else 0)

    # Serialize for LLM — lightweight, just enough for mapping judgment
    serialized_for_llm = [
        {
            "claim_id": c.claim_id,
            "text": c.text,
            "claim_type": c.claim_type,
            "score": round(score, 2),
            "source": source_map[c.source_id].publication if c.source_id in source_map else c.source_id,
            "tier": source_map[c.source_id].reliability_tier if c.source_id in source_map else "unknown",
            "corroboration_count": len(c.corroborated_by),
            "cross_query": cross_query,
            "has_conflicts": len(c.conflicts_with) > 0,
        }
        for score, cross_query, c in top
    ]

    mapping = await _llm_map(serialized_for_llm, sub_questions, original_question)
    mapping_index = {m.claim_id: m for m in mapping.mappings}

    # Group claims by sub-question
    grouped: dict[str, list[dict]] = {q: [] for q in sub_questions}
    cross_cutting_claims: list[dict] = []

    for score, cross_query, claim in top:
        mapped = mapping_index.get(claim.claim_id)
        claim_dict = _serialize_claim(claim, score, cross_query, source_map)

        if not mapped:
            continue
        if mapped.cross_cutting:
            cross_cutting_claims.append(claim_dict)
        elif mapped.sub_question in grouped:
            grouped[mapped.sub_question].append(claim_dict)
        else:
            # sub_question text didn't match verbatim — put in cross_cutting rather than lose it
            cross_cutting_claims.append(claim_dict)

    # Resolve emergent topics — attach full claim dicts
    emergent: list[dict] = []
    for topic in mapping.emergent_topics:
        topic_claims = []
        for cid in topic.claim_ids:
            entry = next(((s, cq, c) for s, cq, c in top if c.claim_id == cid), None)
            if entry:
                topic_claims.append(_serialize_claim(entry[2], entry[0], entry[1], source_map))
        if topic_claims:
            emergent.append({
                "topic": topic.topic,
                "relevance": topic.relevance,
                "claims": topic_claims,
            })

    # Conflict summary — high-severity only, deduped across all claims (not just top_n)
    seen_conflicts: set[str] = set()
    conflict_summary: list[dict] = []
    for claim in combined.claims:
        if not claim.conflicts_with:
            continue
        severity = _conflict_severity(claim, claim_map, source_map)
        if severity != "high":
            continue
        for cid in claim.conflicts_with:
            if not isinstance(cid, str):
                continue
            key = ":".join(sorted([claim.claim_id, cid]))
            if key in seen_conflicts:
                continue
            seen_conflicts.add(key)
            other = claim_map.get(cid)
            if not other:
                continue
            pa = source_map.get(claim.source_id)
            pb = source_map.get(other.source_id)
            conflict_summary.append({
                "claim_a": claim.text,
                "source_a": pa.publication if pa else claim.source_id,
                "tier_a": pa.reliability_tier if pa else "unknown",
                "claim_b": other.text,
                "source_b": pb.publication if pb else other.source_id,
                "tier_b": pb.reliability_tier if pb else "unknown",
            })

    return {
        "summary": {
            "original_question": original_question,
            "total_claims": len(combined.claims),
            "total_sources": len(combined.sources),
            "top_n_used": len(top),
            "sub_questions": sub_questions,
        },
        "sub_questions": [
            {
                "query": q,
                "coverage": (
                    "strong"  if len(grouped.get(q, [])) >= 3 else
                    "partial" if len(grouped.get(q, [])) >= 1 else
                    "none"
                ),
                "claims": grouped.get(q, []),
            }
            for q in sub_questions
        ],
        "cross_cutting": cross_cutting_claims,
        "emergent": emergent,
        "conflicts": conflict_summary,
        "gaps": mapping.gaps,
    }
