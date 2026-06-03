import logging
from typing import Optional
from pydantic import BaseModel
from backend import llm

log = logging.getLogger("research.reliability")


class ReliabilityResponse(BaseModel):
    source_authority: float
    author_credibility: Optional[float] = None   # null when authors unknown
    temporal_intent: str                          # none | recent | specific_period
    date_relevance: float
    reliability: float
    tier: str                                     # high | medium | low


RELIABILITY_PROMPT = """Calculate a source reliability score using the formula and rules below. Return only the scores.

FORMULA:
  reliability = (source_authority × 0.35) + (author_credibility × 0.25) + (date_relevance × 0.25) + (tavily_score × 0.15)

RULES:

source_authority — is this a primary/authoritative source for the topic in the query?
  1.0 = official primary source (company's own site, sec.gov, nih.gov/pubmed, arxiv, official govt)
  0.7 = major specialist outlet (Bloomberg/FT for finance, Nature/Lancet for medicine)
  0.4 = credible general outlet (Reuters, BBC, NYT)
  0.1 = UGC, aggregator, blog with no editorial standard

author_credibility — who wrote it relative to the query topic?
  If authors = unknown: set author_credibility = null and use the adjusted formula below.
  1.0 = insider or primary author (executive, lead researcher, official spokesperson)
  0.7 = domain expert or specialist journalist
  0.4 = general journalist or unknown but plausible
  0.1 = anonymous or clearly unrelated

FORMULA ADJUSTMENT when author_credibility = null (authors unknown):
  reliability = (source_authority × 0.47) + (date_relevance × 0.34) + (tavily_score × 0.19)
  (weights are the original three scaled up proportionally to sum to 1.0)

temporal_intent — what time period does the query need?
  "specific_period" = query names a date/quarter/year
  "recent" = query asks for current/latest info
  "none" = no time constraint (default — use this unless query explicitly references time)

date_relevance:
  "none" → always 1.0
  "recent" → max(0.1, 1.0 - (days_since_publication / 365)), today = 2026-05-28
  "specific_period" → 1.0 if within ±90 days of queried period, 0.3 if within ±365 days, else 0.1

tier: high = reliability >= 0.70, medium = 0.45–0.69, low < 0.45

USER TRUST OVERRIDES (apply these before scoring — they reflect the user's domain knowledge):
{trust_context}

INPUTS:
  query: {query}
  url: {url}
  publication: {publication}
  authors: {authors}
  date: {date}
  tavily_score: {tavily_score}
  content_preview: {content_preview}
"""


def _build_trust_context(url: str, publication: str | None, authors: list[str]) -> str:
    from backend import config as cfg
    trusted = cfg.trusted_sources()
    untrusted = cfg.untrusted_sources()
    lines = []

    def _matches(value: str, lst: list[str]) -> bool:
        v = value.lower()
        return any(entry.lower() in v or v in entry.lower() for entry in lst)

    signals = [url, publication or "", *authors]
    if any(_matches(s, trusted) for s in signals if s):
        lines.append("- This source matches the user's trusted list. Bias source_authority and author_credibility upward.")
    if any(_matches(s, untrusted) for s in signals if s):
        lines.append("- This source matches the user's untrusted list. Bias source_authority and author_credibility downward.")
    return "\n".join(lines) if lines else "- No user overrides apply to this source."


async def score_reliability(
    query: str,
    url: str,
    publication: str | None,
    authors: list[str],
    date: str | None,
    tavily_score: float,
    content_preview: str,
) -> tuple[float, str, dict]:
    trust_context = _build_trust_context(url, publication, authors)
    prompt = RELIABILITY_PROMPT.format(
        query=query,
        url=url,
        publication=publication or "unknown",
        authors=", ".join(authors) if authors else "unknown",
        date=date or "unknown",
        tavily_score=round(tavily_score, 3),
        content_preview=content_preview[:800],
        trust_context=trust_context,
    )
    try:
        result: ReliabilityResponse = await llm.chat_structured(
            [{"role": "user", "content": prompt}],
            response_model=ReliabilityResponse,
        )
        author_str = f"{result.author_credibility:.2f}" if result.author_credibility is not None else "n/a"
        log.debug(
            "Reliability %s — authority=%.2f author=%s date=%.2f tavily=%.2f → %.2f (%s)",
            url, result.source_authority, author_str,
            result.date_relevance, tavily_score, result.reliability, result.tier,
        )
        return result.reliability, result.tier, result.model_dump()
    except Exception as e:
        log.warning("Reliability scoring failed for %s: %s", url, e)
        return 0.4, "medium", {}
