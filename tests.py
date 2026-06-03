"""
Pipeline tests — no real LLM calls, no network.
All LLM-dependent functions are mocked with fake structured responses.
Run with: .venv/Scripts/python.exe -m pytest tests.py -v
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from backend.models import Claim, Source, Edge, ClaimGraph
from backend.pipeline.combine import _deduplicate_sources, _remap_claims
from backend.pipeline.merge import CorroborationGroup, CorroborationResponse, ConflictResponse, ConflictPairItem
from backend.pipeline.distill import _score_claim, _conflict_severity, _claim_origin, _build_source_origin
from backend.mcp_server import _unified_graph_output


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_source(source_id: str, url: str, tier: str = "high", score: float = 0.9, pub: str = None) -> Source:
    return Source(
        source_id=source_id,
        url=url,
        publication=pub or url,
        authors=[],
        date="2025-01-01",
        reliability_score=score,
        reliability_tier=tier,
    )


def make_claim(
    claim_id: str,
    text: str,
    source_id: str,
    corroborated_by: list[str] = None,
    conflicts_with: list[str] = None,
    original_texts: dict[str, str] = None,
    claim_type: str = "fact",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        text=text,
        source_id=source_id,
        chunk_text="",
        chunk_id="c0",
        claim_type=claim_type,
        corroborated_by=corroborated_by or [],
        conflicts_with=conflicts_with or [],
        original_texts=original_texts or {},
    )


def make_graph(sources: list[Source], claims: list[Claim], edges: list[Edge] = None) -> ClaimGraph:
    return ClaimGraph(sources=sources, claims=claims, edges=edges or [])


# ── _deduplicate_sources ──────────────────────────────────────────────────────

class TestDeduplicateSources:

    def test_no_overlap(self):
        g0 = make_graph([make_source("s0", "https://reuters.com"), make_source("s1", "https://bbc.com")], [])
        g1 = make_graph([make_source("s0", "https://ft.com")], [])
        sources, remap = _deduplicate_sources([g0, g1])
        assert len(sources) == 3
        assert remap["g0_s0"] == "gs0"
        assert remap["g0_s1"] == "gs1"
        assert remap["g1_s0"] == "gs2"

    def test_same_url_deduplicates(self):
        shared_url = "https://reuters.com"
        g0 = make_graph([make_source("s0", shared_url)], [])
        g1 = make_graph([make_source("s0", shared_url)], [])
        sources, remap = _deduplicate_sources([g0, g1])
        assert len(sources) == 1
        # both old IDs point to the same new ID
        assert remap["g0_s0"] == remap["g1_s0"] == "gs0"

    def test_partial_overlap(self):
        shared_url = "https://reuters.com"
        g0 = make_graph([make_source("s0", shared_url), make_source("s1", "https://bbc.com")], [])
        g1 = make_graph([make_source("s0", shared_url), make_source("s1", "https://ft.com")], [])
        sources, remap = _deduplicate_sources([g0, g1])
        assert len(sources) == 3  # reuters, bbc, ft
        assert remap["g0_s0"] == remap["g1_s0"]  # reuters deduped

    def test_global_ids_sequential(self):
        g0 = make_graph([make_source("s0", "https://a.com"), make_source("s1", "https://b.com")], [])
        g1 = make_graph([make_source("s0", "https://c.com")], [])
        sources, remap = _deduplicate_sources([g0, g1])
        ids = [s.source_id for s in sources]
        assert ids == ["gs0", "gs1", "gs2"]


# ── _remap_claims ─────────────────────────────────────────────────────────────

class TestRemapClaims:

    def _setup(self):
        """Two graphs, one shared URL."""
        g0 = make_graph(
            [make_source("s0", "https://reuters.com"), make_source("s1", "https://bbc.com")],
            [
                make_claim("s0_c0_0", "Claim A", "s0"),
                make_claim("s0_c0_1", "Claim B", "s1"),
            ]
        )
        g1 = make_graph(
            [make_source("s0", "https://ft.com")],
            [make_claim("s0_c0_0", "Claim C", "s0")]
        )
        _, remap = _deduplicate_sources([g0, g1])
        return [g0, g1], remap

    def test_claim_ids_prefixed(self):
        graphs, remap = self._setup()
        claims = _remap_claims(graphs, remap)
        ids = [c.claim_id for c in claims]
        assert "g0_s0_c0_0" in ids
        assert "g0_s0_c0_1" in ids
        assert "g1_s0_c0_0" in ids

    def test_source_ids_remapped(self):
        graphs, remap = self._setup()
        claims = _remap_claims(graphs, remap)
        claim_map = {c.claim_id: c for c in claims}
        # g0 claim with source s0 → gs0
        assert claim_map["g0_s0_c0_0"].source_id == "gs0"
        # g0 claim with source s1 → gs1
        assert claim_map["g0_s0_c0_1"].source_id == "gs1"
        # g1 claim with source s0 → gs2 (ft.com, different URL)
        assert claim_map["g1_s0_c0_0"].source_id == "gs2"

    def test_corroborated_by_reset(self):
        g0 = make_graph(
            [make_source("s0", "https://reuters.com")],
            [make_claim("s0_c0_0", "Claim A", "s0", corroborated_by=["s1", "s2"])]
        )
        _, remap = _deduplicate_sources([g0])
        claims = _remap_claims([g0], remap)
        assert claims[0].corroborated_by == []

    def test_conflicts_with_reset(self):
        g0 = make_graph(
            [make_source("s0", "https://reuters.com")],
            [make_claim("s0_c0_0", "Claim A", "s0", conflicts_with=["s1_c0_0"])]
        )
        _, remap = _deduplicate_sources([g0])
        claims = _remap_claims([g0], remap)
        assert claims[0].conflicts_with == []

    def test_original_texts_keys_remapped(self):
        """The fix we applied — original_texts keys must use global source IDs after remap."""
        g0 = make_graph(
            [make_source("s0", "https://reuters.com"), make_source("s1", "https://bbc.com")],
            [make_claim(
                "s0_c0_0", "Canonical text", "s0",
                original_texts={"s0": "Reuters phrasing", "s1": "BBC phrasing"}
            )]
        )
        _, remap = _deduplicate_sources([g0])
        claims = _remap_claims([g0], remap)
        ot = claims[0].original_texts
        # old local keys s0/s1 must be gone
        assert "s0" not in ot
        assert "s1" not in ot
        # new global keys must be present
        assert "gs0" in ot
        assert "gs1" in ot
        assert ot["gs0"] == "Reuters phrasing"
        assert ot["gs1"] == "BBC phrasing"

    def test_original_texts_empty_stays_empty(self):
        g0 = make_graph(
            [make_source("s0", "https://reuters.com")],
            [make_claim("s0_c0_0", "Claim A", "s0", original_texts={})]
        )
        _, remap = _deduplicate_sources([g0])
        claims = _remap_claims([g0], remap)
        assert claims[0].original_texts == {}

    def test_original_texts_cross_graph_remap(self):
        """Shared URL across graphs — original_texts from g0 must remap to gs0 not gs1."""
        shared = "https://reuters.com"
        g0 = make_graph(
            [make_source("s0", shared), make_source("s1", "https://bbc.com")],
            [make_claim("s0_c0_0", "Canonical", "s0",
                        original_texts={"s0": "Reuters said A", "s1": "BBC said A"})]
        )
        g1 = make_graph(
            [make_source("s0", shared)],  # same URL as g0_s0 → will map to gs0
            []
        )
        _, remap = _deduplicate_sources([g0, g1])
        claims = _remap_claims([g0, g1], remap)
        ot = claims[0].original_texts
        # gs0 = reuters (shared), gs1 = bbc
        assert ot.get("gs0") == "Reuters said A"
        assert ot.get("gs1") == "BBC said A"


# ── _unified_graph_output ─────────────────────────────────────────────────────

class TestUnifiedGraphOutput:

    def _make_graph(self):
        s0 = make_source("gs0", "https://reuters.com", tier="high", score=0.91, pub="Reuters")
        s1 = make_source("gs1", "https://bloomberg.com", tier="high", score=0.89, pub="Bloomberg")
        s2 = make_source("gs2", "https://ft.com", tier="medium", score=0.72, pub="FT")

        c1 = make_claim(
            "g0_c1", "Apple revenue hit $100B", "gs0",
            corroborated_by=["gs1"],
            conflicts_with=["g0_c2"],
            original_texts={"gs0": "Apple revenue reached $100B", "gs1": "Apple posted $100B"},
        )
        c2 = make_claim("g0_c2", "Apple revenue was $98B", "gs2")
        return make_graph([s0, s1, s2], [c1, c2])

    def test_no_top_level_sources(self):
        graph = self._make_graph()
        out = _unified_graph_output(graph)
        assert "sources" not in out

    def test_no_edges(self):
        graph = self._make_graph()
        out = _unified_graph_output(graph)
        assert "edges" not in out

    def test_claim_source_inlined(self):
        graph = self._make_graph()
        out = _unified_graph_output(graph)
        claim = out["claims"]["g0_c1"]
        assert isinstance(claim["source"], dict)
        assert claim["source"]["publication"] == "Reuters"
        assert claim["source"]["tier"] == "high"
        assert claim["source"]["reliability"] == 0.91

    def test_corroborated_by_inlined(self):
        graph = self._make_graph()
        out = _unified_graph_output(graph)
        corr = out["claims"]["g0_c1"]["corroborated_by"]
        assert len(corr) == 1
        assert corr[0]["source"]["publication"] == "Bloomberg"
        assert corr[0]["original_text"] == "Apple posted $100B"

    def test_corroborated_by_original_text_from_primary(self):
        """Primary source's original text should appear in corroborated_by for itself."""
        graph = self._make_graph()
        out = _unified_graph_output(graph)
        # gs0 is the primary source — its original_text is in original_texts["gs0"]
        # corroborated_by only contains non-primary sources (gs1 here)
        corr = out["claims"]["g0_c1"]["corroborated_by"]
        sources_in_corr = [e["source"]["publication"] for e in corr]
        assert "Bloomberg" in sources_in_corr
        assert "Reuters" not in sources_in_corr  # primary not duplicated

    def test_conflicts_with_inlined(self):
        graph = self._make_graph()
        out = _unified_graph_output(graph)
        conflicts = out["claims"]["g0_c1"]["conflicts_with"]
        assert len(conflicts) == 1
        assert conflicts[0]["text"] == "Apple revenue was $98B"
        assert conflicts[0]["source"]["publication"] == "FT"

    def test_missing_corroborating_source_skipped(self):
        """If a source_id in corroborated_by doesn't exist in source_map, skip it."""
        s0 = make_source("gs0", "https://reuters.com", pub="Reuters")
        c1 = make_claim("c1", "Some claim", "gs0", corroborated_by=["gs_MISSING"])
        graph = make_graph([s0], [c1])
        out = _unified_graph_output(graph)
        assert out["claims"]["c1"]["corroborated_by"] == []

    def test_missing_conflict_claim_skipped(self):
        """If a claim_id in conflicts_with doesn't exist in claim_map, skip it."""
        s0 = make_source("gs0", "https://reuters.com", pub="Reuters")
        c1 = make_claim("c1", "Some claim", "gs0", conflicts_with=["c_MISSING"])
        graph = make_graph([s0], [c1])
        out = _unified_graph_output(graph)
        assert out["claims"]["c1"]["conflicts_with"] == []

    def test_summary_counts(self):
        graph = self._make_graph()
        out = _unified_graph_output(graph)
        assert out["summary"]["total_claims"] == 2
        assert out["summary"]["total_sources"] == 3

    def test_conflict_count_in_summary(self):
        graph = self._make_graph()
        out = _unified_graph_output(graph)
        # c1 has conflicts_with, c2 does not
        assert out["summary"]["conflict_count"] == 1


# ── distill deterministic functions ──────────────────────────────────────────

class TestDistillScoring:

    def _setup(self):
        self.s_high = make_source("gs0", "https://reuters.com", tier="high", score=0.91)
        self.s_med  = make_source("gs1", "https://bbc.com",     tier="medium", score=0.70)
        self.s_low  = make_source("gs2", "https://blog.com",    tier="low",    score=0.30)
        self.source_map = {
            "gs0": self.s_high,
            "gs1": self.s_med,
            "gs2": self.s_low,
        }
        # url_to_graph: reuters and bbc from graph A, blog from graph B
        self.url_to_graph = {
            "https://reuters.com": "gA",
            "https://bbc.com":     "gA",
            "https://blog.com":    "gB",
        }

    def test_single_source_score_equals_tier_weight(self):
        self._setup()
        claim = make_claim("c1", "text", "gs0")
        score, cross = _score_claim(claim, self.source_map, self.url_to_graph, "gA")
        assert score == 3.0  # high = 3
        assert cross is False

    def test_corroboration_adds_weight(self):
        self._setup()
        claim = make_claim("c1", "text", "gs0", corroborated_by=["gs1"])
        score, cross = _score_claim(claim, self.source_map, self.url_to_graph, "gA")
        # high(3) + medium(2) = 5, no cross-query bonus
        assert score == 5.0
        assert cross is False

    def test_cross_query_bonus_applied(self):
        self._setup()
        # gs0 is gA, gs2 is gB — cross-query corroboration
        claim = make_claim("c1", "text", "gs0", corroborated_by=["gs2"])
        score, cross = _score_claim(claim, self.source_map, self.url_to_graph, "gA")
        # (high(3) + low(1)) * 1.5 = 6.0
        assert score == 6.0
        assert cross is True

    def test_no_cross_query_when_same_graph(self):
        self._setup()
        # gs0 and gs1 both from gA
        claim = make_claim("c1", "text", "gs0", corroborated_by=["gs1"])
        score, cross = _score_claim(claim, self.source_map, self.url_to_graph, "gA")
        assert cross is False

    def test_missing_source_treated_as_weight_1(self):
        self._setup()
        claim = make_claim("c1", "text", "gs_MISSING")
        score, cross = _score_claim(claim, self.source_map, self.url_to_graph, "gA")
        assert score == 1.0  # fallback weight

    def test_conflict_severity_high_vs_high(self):
        self._setup()
        other = make_claim("c2", "conflicting", "gs0")
        claim = make_claim("c1", "text", "gs0", conflicts_with=["c2"])
        claim_map = {"c1": claim, "c2": other}
        severity = _conflict_severity(claim, claim_map, self.source_map)
        assert severity == "high"

    def test_conflict_severity_high_vs_low(self):
        self._setup()
        other = make_claim("c2", "conflicting", "gs2")  # low tier
        claim = make_claim("c1", "text", "gs0", conflicts_with=["c2"])
        claim_map = {"c1": claim, "c2": other}
        severity = _conflict_severity(claim, claim_map, self.source_map)
        assert severity == "low"

    def test_conflict_severity_medium_vs_medium(self):
        self._setup()
        other = make_claim("c2", "conflicting", "gs1")  # medium
        claim = make_claim("c1", "text", "gs1", conflicts_with=["c2"])
        claim_map = {"c1": claim, "c2": other}
        severity = _conflict_severity(claim, claim_map, self.source_map)
        assert severity == "medium"

    def test_conflict_severity_no_conflicts(self):
        self._setup()
        claim = make_claim("c1", "text", "gs0")
        severity = _conflict_severity(claim, {}, self.source_map)
        assert severity == "low"  # no conflicts → low

    def test_claim_origin_extracted_from_prefix(self):
        graph_ids = ["gA", "gB", "gC"]
        assert _claim_origin("g0_s0_c0_0", graph_ids) == "gA"
        assert _claim_origin("g1_s1_c2_3", graph_ids) == "gB"
        assert _claim_origin("g2_s0_c0_0", graph_ids) == "gC"

    def test_claim_origin_fallback(self):
        graph_ids = ["gA"]
        # malformed or no prefix
        assert _claim_origin("no_prefix", graph_ids) == "gA"


# ── merge_claims integration (mocked LLM) ────────────────────────────────────

@pytest.mark.asyncio
class TestMergeClaims:

    async def test_corroboration_merges_claims(self):
        from backend.pipeline.merge import merge_claims

        claims = [
            make_claim("s0_c0_0", "Apple revenue hit $100B", "s0"),
            make_claim("s1_c0_0", "Apple posted $100B in revenue", "s1"),
            make_claim("s2_c0_0", "Completely unrelated claim", "s2"),
        ]

        mock_corr = CorroborationResponse(groups=[
            CorroborationGroup(
                claim_ids=["s0_c0_0", "s1_c0_0"],
                canonical_text="Apple revenue reached $100B",
            )
        ])
        mock_conflict = ConflictResponse(conflicts=[])

        with patch("backend.pipeline.merge._find_corroborations", new=AsyncMock(return_value=mock_corr)), \
             patch("backend.pipeline.merge._find_conflicts",      new=AsyncMock(return_value=mock_conflict)):
            merged, conflict_pairs = await merge_claims(claims)

        assert len(merged) == 2  # one representative + one unrelated
        rep = next(c for c in merged if c.text == "Apple revenue reached $100B")
        assert "s1" in rep.corroborated_by
        assert rep.original_texts["s0"] == "Apple revenue hit $100B"
        assert rep.original_texts["s1"] == "Apple posted $100B in revenue"
        assert conflict_pairs == []

    async def test_conflict_detection(self):
        from backend.pipeline.merge import merge_claims

        claims = [
            make_claim("s0_c0_0", "Apple revenue hit $100B", "s0"),
            make_claim("s1_c0_0", "Apple revenue was $98B", "s1"),
        ]

        mock_corr = ConflictResponse(conflicts=[])
        mock_conflict = ConflictResponse(conflicts=[
            ConflictPairItem(a="s0_c0_0", b="s1_c0_0")
        ])

        with patch("backend.pipeline.merge._find_corroborations", new=AsyncMock(return_value=CorroborationResponse(groups=[]))), \
             patch("backend.pipeline.merge._find_conflicts",      new=AsyncMock(return_value=mock_conflict)):
            merged, conflict_pairs = await merge_claims(claims)

        assert len(conflict_pairs) == 1
        assert set(conflict_pairs[0]) == {"s0_c0_0", "s1_c0_0"}
        c0 = next(c for c in merged if c.claim_id == "s0_c0_0")
        c1 = next(c for c in merged if c.claim_id == "s1_c0_0")
        assert "s1_c0_0" in c0.conflicts_with
        assert "s0_c0_0" in c1.conflicts_with

    async def test_singleton_not_merged(self):
        from backend.pipeline.merge import merge_claims

        claims = [make_claim("s0_c0_0", "Only claim", "s0")]

        with patch("backend.pipeline.merge._find_corroborations", new=AsyncMock(return_value=CorroborationResponse(groups=[]))), \
             patch("backend.pipeline.merge._find_conflicts",      new=AsyncMock(return_value=ConflictResponse(conflicts=[]))):
            merged, conflict_pairs = await merge_claims(claims)

        assert len(merged) == 1
        assert merged[0].claim_id == "s0_c0_0"
        assert merged[0].corroborated_by == []

    async def test_group_with_one_valid_id_skipped(self):
        """A group where only one claim ID is valid should not be merged."""
        from backend.pipeline.merge import merge_claims

        claims = [make_claim("s0_c0_0", "Claim A", "s0")]
        mock_corr = CorroborationResponse(groups=[
            CorroborationGroup(claim_ids=["s0_c0_0", "NONEXISTENT"], canonical_text="Canonical")
        ])

        with patch("backend.pipeline.merge._find_corroborations", new=AsyncMock(return_value=mock_corr)), \
             patch("backend.pipeline.merge._find_conflicts",      new=AsyncMock(return_value=ConflictResponse(conflicts=[]))):
            merged, _ = await merge_claims(claims)

        # group had only 1 valid ID so it should be skipped — claim survives as-is
        assert len(merged) == 1
        assert merged[0].corroborated_by == []


# ── combine_graphs integration (mocked LLM + score_claim_chunks) ─────────────

@pytest.mark.asyncio
class TestCombineGraphs:

    async def test_full_combine_original_texts_remapped(self):
        """
        End-to-end test of the remap fix: original_texts written during a within-graph
        merge must use global source IDs after combine_graphs runs.
        """
        from backend.pipeline.combine import combine_graphs

        s0 = make_source("s0", "https://reuters.com", pub="Reuters")
        s1 = make_source("s1", "https://bbc.com",     pub="BBC")

        # Simulate a claim already merged within graph 0 — has original_texts with local IDs
        c_merged = make_claim(
            "s0_c0_0", "Canonical A", "s0",
            original_texts={"s0": "Reuters phrasing", "s1": "BBC phrasing"},
        )
        g0 = make_graph([s0, s1], [c_merged])

        s2 = make_source("s0", "https://ft.com", pub="FT")
        c_other = make_claim("s0_c0_0", "Unrelated claim", "s0")
        g1 = make_graph([s2], [c_other])

        # Mock merge_claims to return claims as-is (no further merging)
        async def fake_merge(claims):
            for c in claims:
                c.corroborated_by = c.corroborated_by or []
                c.conflicts_with  = c.conflicts_with or []
            return claims, []

        with patch("backend.pipeline.combine.merge_claims",       new=fake_merge), \
             patch("backend.pipeline.combine.build_edges",        new=AsyncMock(return_value=[])), \
             patch("backend.pipeline.combine.score_claim_chunks", new=AsyncMock(side_effect=lambda x: x)):
            result = combine_graphs([g0, g1])
            import asyncio
            result = await result

        # Find the claim that had original_texts
        claim_map = {c.claim_id: c for c in result.claims}
        remapped = claim_map.get("g0_s0_c0_0")
        assert remapped is not None, "Expected g0_s0_c0_0 in combined claims"

        ot = remapped.original_texts
        # local IDs must be gone
        assert "s0" not in ot
        assert "s1" not in ot
        # global IDs must be present
        assert any(k.startswith("gs") for k in ot), f"No global keys in original_texts: {ot}"
        assert "Reuters phrasing" in ot.values()
        assert "BBC phrasing" in ot.values()

    async def test_source_dedup_across_graphs(self):
        from backend.pipeline.combine import combine_graphs

        shared_url = "https://reuters.com"
        g0 = make_graph([make_source("s0", shared_url)], [make_claim("c0", "Claim A", "s0")])
        g1 = make_graph([make_source("s0", shared_url)], [make_claim("c0", "Claim B", "s0")])

        async def fake_merge(claims):
            return claims, []

        with patch("backend.pipeline.combine.merge_claims",       new=fake_merge), \
             patch("backend.pipeline.combine.build_edges",        new=AsyncMock(return_value=[])), \
             patch("backend.pipeline.combine.score_claim_chunks", new=AsyncMock(side_effect=lambda x: x)):
            result = await combine_graphs([g0, g1])

        # shared URL should produce exactly 1 source
        assert len(result.sources) == 1
        assert result.sources[0].url == shared_url


# ── distill_graph integration (mocked LLM + graph_store) ─────────────────────

@pytest.mark.asyncio
class TestDistillGraph:

    def _build_store_entries(self):
        """Two subgraphs and one combined graph for distill testing."""
        s0 = make_source("gs0", "https://reuters.com", tier="high", score=0.91, pub="Reuters")
        s1 = make_source("gs1", "https://bloomberg.com", tier="high", score=0.88, pub="Bloomberg")
        s2 = make_source("gs2", "https://ft.com", tier="medium", score=0.70, pub="FT")

        # Subgraph 0 — query: "Apple earnings Q1"
        sub0_s = make_source("s0", "https://reuters.com", tier="high", score=0.91, pub="Reuters")
        sub0_c = make_claim("s0_c0_0", "Apple revenue hit $100B", "s0")
        sub0 = make_graph([sub0_s], [sub0_c])

        # Subgraph 1 — query: "Apple iPhone sales"
        sub1_s = make_source("s0", "https://ft.com", tier="medium", score=0.70, pub="FT")
        sub1_c = make_claim("s0_c0_0", "iPhone unit sales fell 5%", "s0")
        sub1 = make_graph([sub1_s], [sub1_c])

        # Combined graph — post combine_graphs
        c1 = make_claim(
            "g0_s0_c0_0", "Apple revenue reached $100B", "gs0",
            corroborated_by=["gs1"],
            original_texts={"gs0": "Apple revenue hit $100B", "gs1": "Apple posted $100B"},
        )
        c2 = make_claim("g1_s0_c0_0", "iPhone unit sales fell 5%", "gs2")
        combined = make_graph([s0, s1, s2], [c1, c2])

        return sub0, sub1, combined

    async def test_distill_returns_expected_structure(self):
        from backend.pipeline.distill import distill_graph
        from backend.pipeline.distill import DistillMapping, MappedClaim, EmergentTopic

        sub0, sub1, combined = self._build_store_entries()

        store = {
            "gA": {"query": "Apple earnings Q1", "graph": sub0},
            "gB": {"query": "Apple iPhone sales", "graph": sub1},
            "gC": {"query": "Apple earnings Q1 + Apple iPhone sales", "graph": combined},
        }

        mock_mapping = DistillMapping(
            mappings=[
                MappedClaim(claim_id="g0_s0_c0_0", sub_question="Apple earnings Q1",  cross_cutting=False),
                MappedClaim(claim_id="g1_s0_c0_0", sub_question="Apple iPhone sales", cross_cutting=False),
            ],
            emergent_topics=[],
            gaps=[],
        )

        with patch("backend.pipeline.distill.graph_store") as mock_store, \
             patch("backend.pipeline.distill._llm_map", new=AsyncMock(return_value=mock_mapping)):
            mock_store.get.side_effect = lambda gid: store.get(gid)
            result = await distill_graph(["gA", "gB"], "gC", "What is Apple's outlook?")

        assert "sub_questions" in result
        assert "emergent" in result
        assert "conflicts" in result
        assert "gaps" in result
        assert result["summary"]["original_question"] == "What is Apple's outlook?"

        sq_map = {sq["query"]: sq for sq in result["sub_questions"]}
        assert "Apple earnings Q1" in sq_map
        assert "Apple iPhone sales" in sq_map
        assert sq_map["Apple earnings Q1"]["coverage"] in ("strong", "partial", "none")

    async def test_distill_inlines_source_in_claims(self):
        from backend.pipeline.distill import distill_graph
        from backend.pipeline.distill import DistillMapping, MappedClaim, EmergentTopic

        sub0, sub1, combined = self._build_store_entries()
        store = {
            "gA": {"query": "Apple earnings Q1",  "graph": sub0},
            "gB": {"query": "Apple iPhone sales", "graph": sub1},
            "gC": {"query": "combined",            "graph": combined},
        }

        mock_mapping = DistillMapping(
            mappings=[
                MappedClaim(claim_id="g0_s0_c0_0", sub_question="Apple earnings Q1",  cross_cutting=False),
                MappedClaim(claim_id="g1_s0_c0_0", sub_question="Apple iPhone sales", cross_cutting=False),
            ],
            emergent_topics=[],
            gaps=[],
        )

        with patch("backend.pipeline.distill.graph_store") as mock_store, \
             patch("backend.pipeline.distill._llm_map", new=AsyncMock(return_value=mock_mapping)):
            mock_store.get.side_effect = lambda gid: store.get(gid)
            result = await distill_graph(["gA", "gB"], "gC", "What is Apple's outlook?")

        sq_map = {sq["query"]: sq for sq in result["sub_questions"]}
        earnings_claims = sq_map["Apple earnings Q1"]["claims"]
        assert len(earnings_claims) == 1
        claim = earnings_claims[0]
        assert "source" in claim
        assert claim["source"]["publication"] == "Reuters"
        assert claim["source"]["tier"] == "high"
        assert "corroboration" in claim
        assert claim["corroboration"]["count"] == 1

    async def test_distill_unknown_combined_graph_raises(self):
        from backend.pipeline.distill import distill_graph

        with patch("backend.pipeline.distill.graph_store") as mock_store:
            mock_store.get.return_value = None
            with pytest.raises(ValueError, match="not found"):
                await distill_graph(["gA"], "NONEXISTENT", "question")
