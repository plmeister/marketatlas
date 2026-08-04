from __future__ import annotations

import json

import pytest
from marketatlas.analysis.ast.builder import AnalysisBuilder
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.serialization import to_json

pytestmark = pytest.mark.snapshot


def _graph_structure_to_dict(graph) -> dict:
    order = graph.execution_order()
    nodes = []
    for a in order:
        nodes.append(
            {
                "type": type(a).__name__,
                "requires": sorted(str(k) for k in a.requires()),
                "produces": sorted(str(k) for k in a.produces()),
            }
        )
    return {"execution_order": nodes}


def assert_ast_snapshot(name: str, analysis, request: pytest.FixtureRequest) -> None:
    from tests.conftest import assert_snapshot as _assert

    _assert(f"{name}_ast", to_json(analysis, pretty=True), request)


def assert_graph_snapshot(name: str, analysis, request: pytest.FixtureRequest) -> None:
    from tests.conftest import assert_snapshot as _assert

    graph = ASTCompiler.compile(analysis)
    graph_dict = _graph_structure_to_dict(graph)
    _assert(f"{name}_graph", json.dumps(graph_dict, indent=2), request)


class TestSingleAnalyzer:
    """EMA(20) — simplest single-analyzer analysis."""

    def test_ema20_ast(self, request: pytest.FixtureRequest) -> None:
        a = (
            AnalysisBuilder("ema20", "1.0")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        assert_ast_snapshot("single_ema20", a, request)

    def test_ema20_graph(self, request: pytest.FixtureRequest) -> None:
        a = (
            AnalysisBuilder("ema20", "1.0")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        assert_graph_snapshot("single_ema20", a, request)

    def test_deterministic_ast(self) -> None:
        a1 = (
            AnalysisBuilder("ema20", "1.0")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        a2 = (
            AnalysisBuilder("ema20", "1.0")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        assert to_json(a1) == to_json(a2)


class TestLinearChain:
    """EMA(20) → Trend — linear dependency chain."""

    def test_ema_trend_ast(self, request: pytest.FixtureRequest) -> None:
        a = (
            AnalysisBuilder("ema_trend", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("trend", "analyzer", "TrendAnalyzer")
            .build()
        )
        assert_ast_snapshot("linear_ema_trend", a, request)

    def test_ema_trend_graph(self, request: pytest.FixtureRequest) -> None:
        a = (
            AnalysisBuilder("ema_trend", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("trend", "analyzer", "TrendAnalyzer")
            .build()
        )
        assert_graph_snapshot("linear_ema_trend", a, request)

    def test_deterministic_graph(self) -> None:
        a1 = (
            AnalysisBuilder("ema_trend", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("trend", "analyzer", "TrendAnalyzer")
            .build()
        )
        a2 = (
            AnalysisBuilder("ema_trend", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("trend", "analyzer", "TrendAnalyzer")
            .build()
        )
        assert _graph_structure_to_dict(ASTCompiler.compile(a1)) == _graph_structure_to_dict(
            ASTCompiler.compile(a2)
        )


class TestBranching:
    """EMA(20) + ATR(14) → Pullback — branching dependency graph."""

    def test_ema_atr_pullback_ast(self, request: pytest.FixtureRequest) -> None:
        a = (
            AnalysisBuilder("ema_atr_pullback", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .define("trend", "analyzer", "TrendAnalyzer")
            .define("swing", "analyzer", "SwingStructureAnalyzer")
            .with_param("lookback", 100)
            .with_reference("atr_14", "atr14")
            .define("pullback", "analyzer", "FourSwingPullbackDetector")
            .build()
        )
        assert_ast_snapshot("branching_ema_atr_pullback", a, request)

    def test_ema_atr_pullback_graph(self, request: pytest.FixtureRequest) -> None:
        a = (
            AnalysisBuilder("ema_atr_pullback", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .define("trend", "analyzer", "TrendAnalyzer")
            .define("swing", "analyzer", "SwingStructureAnalyzer")
            .with_param("lookback", 100)
            .with_reference("atr_14", "atr14")
            .define("pullback", "analyzer", "FourSwingPullbackDetector")
            .build()
        )
        assert_graph_snapshot("branching_ema_atr_pullback", a, request)


class TestFullStrategy:
    """Full multi-analyzer strategy with signal and risk definitions."""

    def test_full_strategy_ast(self, request: pytest.FixtureRequest) -> None:
        a = (
            AnalysisBuilder("full_strategy", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .define("trend", "analyzer", "TrendAnalyzer")
            .define("swing", "analyzer", "SwingStructureAnalyzer")
            .with_param("lookback", 100)
            .with_reference("atr_14", "atr14")
            .define("signal", "signal", "PullbackSignal")
            .with_param("min_strength", 0.5)
            .with_reference("trend", "trend")
            .with_reference("atr_14", "atr14")
            .with_reference("four_swing_pullback", "swing")
            .define("risk", "risk", "risk_based")
            .with_param("risk_pct", 1.0)
            .with_param("min_rr", 2.0)
            .build()
        )
        assert_ast_snapshot("full_strategy", a, request)

    def test_full_strategy_graph(self, request: pytest.FixtureRequest) -> None:
        a = (
            AnalysisBuilder("full_strategy", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .define("trend", "analyzer", "TrendAnalyzer")
            .define("swing", "analyzer", "SwingStructureAnalyzer")
            .with_param("lookback", 100)
            .with_reference("atr_14", "atr14")
            .define("signal", "signal", "PullbackSignal")
            .with_param("min_strength", 0.5)
            .with_reference("trend", "trend")
            .with_reference("atr_14", "atr14")
            .with_reference("four_swing_pullback", "swing")
            .define("risk", "risk", "risk_based")
            .with_param("risk_pct", 1.0)
            .with_param("min_rr", 2.0)
            .build()
        )
        assert_graph_snapshot("full_strategy", a, request)
