import asyncio
import json
import logging
import re
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from backend import llm, config
from backend.models import Claim

log = logging.getLogger("research.match")


FAITHFULNESS_PROMPT = """Does the response sentence faithfully represent what the claim says?
Answer only with JSON: {{"faithful": true}} or {{"faithful": false}}

Claim: {claim}
Response sentence: {sentence}
"""


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 20]


async def _check_faithfulness(claim: Claim, sentence: str) -> bool:
    raw = await llm.chat(
        [{"role": "user", "content": FAITHFULNESS_PROMPT.format(
            claim=claim.text, sentence=sentence
        )}],
        role="cheap",
        json_mode=True,
    )
    try:
        return json.loads(raw).get("faithful", False)
    except Exception:
        return False


async def score_claim_chunks(claims: list[Claim]) -> list[Claim]:
    """Embed each claim text and its source chunk, write cosine similarity to embedding_match."""
    if not claims:
        return claims
    texts = [c.text for c in claims] + [c.chunk_text for c in claims]
    vecs = await llm.embed(texts)
    n = len(claims)
    claim_vecs = np.array(vecs[:n])
    chunk_vecs = np.array(vecs[n:])
    sims = cosine_similarity(claim_vecs, chunk_vecs).diagonal()
    for i, claim in enumerate(claims):
        claim.embedding_match = float(sims[i])
    log.info("Scored embedding_match for %d claims", n)
    return claims


async def compute_match_scores(
    claims: list[Claim], response: str
) -> tuple[list[Claim], list[dict]]:
    sentences = _split_sentences(response)
    if not sentences or not claims:
        return claims, []

    log.info("Embedding %d sentences + %d claim chunks", len(sentences), len(claims))
    all_texts = sentences + [c.chunk_text for c in claims]
    vecs = await llm.embed(all_texts)
    sentence_vecs = np.array(vecs[: len(sentences)])
    chunk_vecs = np.array(vecs[len(sentences):])

    sim_matrix = cosine_similarity(sentence_vecs, chunk_vecs)
    # shape: [n_sentences, n_claims]

    # for each claim, find its best matching sentence score
    best_per_claim = sim_matrix.max(axis=0)
    for i, claim in enumerate(claims):
        claim.embedding_match = float(best_per_claim[i])

    # faithfulness check only for high-similarity pairs (avoid N×M LLM calls)
    if config.pipeline_cfg().get("faithfulness_check"):
        faith_tasks = []
        faith_index = []
        for ci, claim in enumerate(claims):
            best_si = int(sim_matrix[:, ci].argmax())
            if best_per_claim[ci] > 0.75:
                faith_tasks.append(_check_faithfulness(claim, sentences[best_si]))
                faith_index.append(ci)

        faith_results = await asyncio.gather(*faith_tasks)
        for ci, faithful in zip(faith_index, faith_results):
            claims[ci].faithfulness_match = faithful
        unfaithful = sum(1 for f in faith_results if not f)
        log.info("Faithfulness check — %d checked, %d unfaithful", len(faith_results), unfaithful)

    # per-sentence scores for studio UI
    sentence_scores = []
    for si, sentence in enumerate(sentences):
        best_ci = int(sim_matrix[si].argmax())
        sentence_scores.append({
            "sentence": sentence,
            "best_claim_id": claims[best_ci].claim_id,
            "score": float(sim_matrix[si, best_ci]),
        })

    return claims, sentence_scores
