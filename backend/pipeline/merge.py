import asyncio
import json
import logging
from pydantic import BaseModel
from backend import llm
from backend.models import Claim

log = logging.getLogger("research.merge")


class CorroborationGroup(BaseModel):
    claim_ids: list[str]
    canonical_text: str


class CorroborationResponse(BaseModel):
    groups: list[CorroborationGroup]


class ConflictPairItem(BaseModel):
    a: str
    b: str


class ConflictResponse(BaseModel):
    conflicts: list[ConflictPairItem]


CORROBORATION_PROMPT = """You are given a list of claims extracted from different sources.

Identify groups of claims that assert the same core fact — i.e. they would all be saying the same thing if worded identically. Minor differences in phrasing, level of detail, or exact numbers due to rounding are fine, but the underlying assertion must be the same.

For each group, also provide a canonical_text: the clearest single-sentence phrasing that best captures the shared fact.

Only group claims that genuinely agree. Do not force groupings. Claims about related but distinct facts should NOT be grouped.
Singleton claims (no corroboration) should not appear in any group.

Use exact claim_id values from the input.

Claims:
{claims}"""


CONFLICT_PROMPT = """You are given a list of claims extracted from different sources.

Identify pairs of claims that directly contradict each other — i.e. they assert mutually exclusive values for the same specific fact.

A real conflict requires: same subject + same predicate + incompatible values.
Examples of real conflicts:
- "IPO planned for 2026" vs "IPO planned for 2027"
- "Company valued at $10B" vs "Company valued at $5B" (same point in time)

NOT conflicts:
- Different facts about the same topic
- More detail than another claim
- Values that changed over time (different dates)
- One claim qualifying or adding nuance to another

Use exact claim_id values from the input.

Claims:
{claims}"""


def _serialize_claims(claims: list[Claim]) -> str:
    return json.dumps(
        [{"claim_id": c.claim_id, "text": c.text, "source_id": c.source_id} for c in claims],
        indent=2,
    )


async def _find_corroborations(claims: list[Claim]) -> CorroborationResponse:
    return await llm.chat_structured(
        [{"role": "user", "content": CORROBORATION_PROMPT.format(claims=_serialize_claims(claims))}],
        response_model=CorroborationResponse,
    )


async def _find_conflicts(claims: list[Claim]) -> ConflictResponse:
    return await llm.chat_structured(
        [{"role": "user", "content": CONFLICT_PROMPT.format(claims=_serialize_claims(claims))}],
        response_model=ConflictResponse,
    )


async def merge_claims(claims: list[Claim]) -> tuple[list[Claim], list[tuple[str, str]]]:
    if not claims:
        return [], []

    log.info("Running corroboration + conflict detection on %d claims", len(claims))
    corroboration_result, conflict_result = await asyncio.gather(
        _find_corroborations(claims),
        _find_conflicts(claims),
    )

    claim_map = {c.claim_id: c for c in claims}

    # Apply corroborations — merge each group to a single canonical claim
    absorbed: set[str] = set()
    merged: list[Claim] = []

    for group in corroboration_result.groups:
        valid_ids = [cid for cid in group.claim_ids if cid in claim_map]
        if len(valid_ids) < 2:
            continue
        representative = claim_map[valid_ids[0]].model_copy()
        representative.original_texts = {claim_map[cid].source_id: claim_map[cid].text for cid in valid_ids}
        representative.text = group.canonical_text
        representative.corroborated_by = list({claim_map[cid].source_id for cid in valid_ids[1:]})
        merged.append(representative)
        for cid in valid_ids:
            absorbed.add(cid)

    # Keep all claims not absorbed into a corroboration group
    for claim in claims:
        if claim.claim_id not in absorbed:
            merged.append(claim)

    log.info("After corroboration merge: %d → %d claims", len(claims), len(merged))

    # Apply conflicts
    merged_ids = {c.claim_id for c in merged}
    conflict_pairs: list[tuple[str, str]] = []
    conflict_map: dict[str, list[str]] = {}

    for pair in conflict_result.conflicts:
        a, b = pair.a, pair.b
        if a in merged_ids and b in merged_ids and a != b:
            key = tuple(sorted([a, b]))
            if key not in {tuple(sorted(p)) for p in conflict_pairs}:
                conflict_pairs.append((a, b))
            conflict_map.setdefault(a, []).append(b)
            conflict_map.setdefault(b, []).append(a)

    for claim in merged:
        claim.conflicts_with = conflict_map.get(claim.claim_id, [])

    log.info("Conflicts detected: %d pairs", len(conflict_pairs))
    return merged, conflict_pairs
