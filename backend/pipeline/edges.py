from backend.models import Claim, Edge


async def build_edges(claims: list[Claim], conflict_pairs: list[tuple[str, str]]) -> list[Edge]:
    claim_map = {c.claim_id: c for c in claims}
    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()

    for a_id, b_id in conflict_pairs:
        key = tuple(sorted([a_id, b_id]))
        if key in seen:
            continue
        seen.add(key)
        if a_id in claim_map and b_id in claim_map:
            edges.append(Edge(from_claim=a_id, to_claim=b_id, type="contradicts"))

    return edges
