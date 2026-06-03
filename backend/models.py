from pydantic import BaseModel
from typing import Optional


class Source(BaseModel):
    source_id: str
    url: str
    publication: Optional[str] = None
    authors: list[str] = []
    date: Optional[str] = None
    reliability_score: float
    reliability_tier: str          # high | medium | low
    reliability_reasoning: Optional[dict] = None  # full component breakdown


class Claim(BaseModel):
    claim_id: str
    text: str
    source_id: str
    chunk_text: str
    chunk_id: str
    corroborated_by: list[str] = []   # source_ids
    original_texts: dict[str, str] = {}  # source_id → original text before canonical rewrite
    conflicts_with: list[str] = []    # claim_ids
    embedding_match: Optional[float] = None   # filled post-synthesis
    faithfulness_match: Optional[bool] = None # filled post-synthesis
    claim_type: str = "fact"  # fact | prediction | opinion | reported_speech
class Edge(BaseModel):
    from_claim: str
    to_claim: str
    type: str  # supports | contradicts | qualifies


class ClaimGraph(BaseModel):
    sources: list[Source]
    claims: list[Claim]
    edges: list[Edge]


class ResearchResponse(BaseModel):
    query: str
    graph: ClaimGraph
    response: str
    # per-sentence match scores written back after synthesis
    sentence_scores: list[dict] = []
