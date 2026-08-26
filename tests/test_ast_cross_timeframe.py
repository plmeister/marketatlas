"""Backlog 062: cross-timeframe references — binding semantics.

A reference ``field: producer`` on an analyzer is a dependency edge: the
compiler resolves it to the producer's declared timeframe (backlog 061) and
injects a ``bindings`` override so the consumer's ``requires()``/``analyze()``
resolve the correct ``FactKey`` (including ``name@timeframe`` for cross-TF
references). On a signal the reference becomes a ``requires`` entry carrying
the source timeframe. References are always explicit declarations in the DSL;
an undeclared cross-timeframe dependency fails at graph construction.

    tf1w := timeframe { resolution: "1w" }
    tf1d := timeframe { resolution: "1d" }
    ema  := ema  { timeframe: tf1w, period: 20 }
    trend := trend { timeframe: tf1d, ema_20: ema }
"""

from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.parser import parse
from marketatlas.analysis.ast.pipeline import CompilationError, _ast_to_config
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.graph import AnalysisGraph, UnsatisfiedDependencyError
from marketatlas.analysis.patterns.pullback import PullbackPatternAnalyzer
from marketatlas.analysis.signals.pullback_signal import PullbackSignal
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView


def _cross_tf_source() -> str:
    return (
        'tf1d := timeframe { resolution: "1d" }\n'
        'tf1w := timeframe { resolution: "1w" }\n'
        "ema20 := ema { timeframe: tf1w, period: 20 }\n"
        "ema50 := ema { timeframe: tf1w, period: 50 }\n"
        "swing := swings { timeframe: tf1w, lookback: 50 }\n"
        "trend := trend { timeframe: tf1d, ema_20: ema20, ema_50: ema50 }\n"
        "alternate := swingstructure { timeframe: tf1d, swing: swing }\n"
        "pullback := pullbackpattern { timeframe: tf1d, swing_structure: alternate }\n"
    )


class TestBindings:
    def test_cross_tf_binding_in_requires(self) -> None:
        detector = PullbackPatternAnalyzer(
            timeframe="1d", bindings={"swing_structure": "swing_structure@1w"}
        )
        assert detector.requires() == (
            FactKey("swing_structure", timeframe=Timeframe("1w")),
        )

    def test_produced_key_never_overridden(self) -> None:
        detector = PullbackPatternAnalyzer(
            timeframe="1d", bindings={"pullback_pattern": "pullback_pattern@1w"}
        )
        assert detector.produces() == (FactKey("pullback_pattern", timeframe=Timeframe("1d")),)

    def test_binding_requires_analyze_lookup_consistency(self) -> None:
        detector = PullbackPatternAnalyzer(
            timeframe="1d", bindings={"swing_structure": "swing_structure@1w"}
        )
        assert detector._make_key("swing_structure") == FactKey(
            "swing_structure", timeframe=Timeframe("1w")
        )
        assert detector._make_key("pullback_pattern") == FactKey(
            "pullback_pattern", timeframe=Timeframe("1d")
        )


class TestCompile:
    def test_cross_tf_compiles(self) -> None:
        graph = ASTCompiler.compile(parse(_cross_tf_source(), name="demo"))
        assert isinstance(graph, AnalysisGraph)

    def test_requires_carry_source_timeframe(self) -> None:
        graph = ASTCompiler.compile(parse(_cross_tf_source(), name="demo"))
        by_name = {type(a).__name__: a for a in graph.execution_order()}
        trend = by_name["TrendAnalyzer"]
        assert trend.requires() == (
            FactKey("ema_20", timeframe=Timeframe("1w")),
            FactKey("ema_50", timeframe=Timeframe("1w")),
        )
        alternate = by_name["SwingStructureAnalyzer"]
        assert FactKey("swing", timeframe=Timeframe("1w")) in alternate.requires()
        pullback = by_name["PullbackPatternAnalyzer"]
        assert FactKey("swing_structure", timeframe=Timeframe("1d")) in pullback.requires()

    def test_same_tf_reference_keeps_plain_binding(self) -> None:
        source = (
            'tf1d := timeframe { resolution: "1d" }\n'
            "swing := swings { timeframe: tf1d, lookback: 50 }\n"
            "alternate := swingstructure { timeframe: tf1d, swing: swing }\n"
        )
        config = _ast_to_config(parse(source, name="demo"))
        alternate = config.analyzers[1]
        assert alternate.params["bindings"] == {"swing": "swing"}

    def test_config_bindings_injected(self) -> None:
        config = _ast_to_config(parse(_cross_tf_source(), name="demo"))
        by_type = {c.type: c for c in config.analyzers}
        assert by_type["TrendAnalyzer"].params["bindings"] == {
            "ema_20": "ema_20@1w",
            "ema_50": "ema_50@1w",
        }
        assert by_type["SwingStructureAnalyzer"].params["bindings"] == {
            "swing": "swing@1w",
        }
        assert by_type["PullbackPatternAnalyzer"].params["bindings"] == {
            "swing_structure": "swing_structure",
        }


class TestRiskBindings:
    """Backlog 083: risk nodes consume facts via explicit DSL references."""

    def test_risk_reference_compiles_to_bindings(self) -> None:
        source = (
            'tf1d := timeframe { resolution: "1d" }\n'
            "atr_14 := atr { timeframe: tf1d, period: 14 }\n"
            "sr := sr {}\n"
            "swing1d := swings { timeframe: tf1d, lookback: 50 }\n"
            "risk := manage_risk { atr_14: atr_14, sr: sr, swing: swing1d }\n"
        )
        config = _ast_to_config(parse(source, name="demo"))
        assert config.risk.params["bindings"] == {
            "atr_14": "atr_14@1d",
            "sr": "sr@1d",
            "swing": "swing@1d",
        }

    def test_cross_tf_risk_reference_carries_source_timeframe(self) -> None:
        source = (
            'tf1d := timeframe { resolution: "1d" }\n'
            'tf1w := timeframe { resolution: "1w" }\n'
            "swing1d := swings { timeframe: tf1d, lookback: 50 }\n"
            "swing1w := swings { timeframe: tf1w, lookback: 50 }\n"
            "risk := manage_risk { swing: swing1w }\n"
        )
        config = _ast_to_config(parse(source, name="demo"))
        assert config.risk.params["bindings"] == {"swing": "swing@1w"}

    def test_risk_reference_undeclared_output_fails(self) -> None:
        source = (
            'tf1d := timeframe { resolution: "1d" }\n'
            "swing1d := swings { timeframe: tf1d, lookback: 50 }\n"
            "risk := manage_risk { sr: swing1d }\n"
        )
        with pytest.raises(CompilationError):
            _ast_to_config(parse(source, name="demo"))


class TestSignalRequires:
    def test_cross_tf_requires_carries_source_timeframe(self) -> None:
        source = (
            'tf1d := timeframe { resolution: "1d" }\n'
            'tf1w := timeframe { resolution: "1w" }\n'
            "swing := swings { timeframe: tf1w, lookback: 50 }\n"
            "sig := generate_signal { swing: swing }\n"
        )
        config = _ast_to_config(parse(source, name="demo"))
        assert config.signals[0].requires == ("swing@1w",)

    def test_same_tf_requires_unchanged(self) -> None:
        source = (
            'tf1d := timeframe { resolution: "1d" }\n'
            "atr_14 := atr { timeframe: tf1d, period: 14 }\n"
            "sig := generate_signal { atr_14: atr_14 }\n"
        )
        config = _ast_to_config(parse(source, name="demo"))
        assert config.signals[0].requires == ("atr_14",)


class TestErrors:
    def test_reference_to_undeclared_output(self) -> None:
        source = (
            "ema20 := ema { period: 20 }\n"
            "trend := trend { ema_20: ema20, ema_50: ema20 }\n"
        )
        with pytest.raises(CompilationError, match="ema_50.*not declared by provider 'ema'"):
            _ast_to_config(parse(source, name="demo"))

    def test_reference_to_undeclared_output_named(self) -> None:
        source = (
            "swing := swings { lookback: 50 }\n"
            "sr := sr { swing: swing, atr_14_series: swing }\n"
        )
        with pytest.raises(CompilationError, match="atr_14_series"):
            _ast_to_config(parse(source, name="demo"))

    def test_unknown_reference_raises(self) -> None:
        with pytest.raises(CompilationError, match="Unknown reference"):
            _ast_to_config(parse("trend := trend { ema_20: ghost }\n", name="demo"))

    def test_undeclared_cross_tf_dependency_fails_at_graph_build(self) -> None:
        source = (
            'tf1d := timeframe { resolution: "1d" }\n'
            'tf1w := timeframe { resolution: "1w" }\n'
            "alternate := swingstructure { timeframe: tf1w }\n"
            "swing := swings { timeframe: tf1d, lookback: 50 }\n"
        )
        with pytest.raises(CompilationError, match="missing required input 'swing'"):
            ASTCompiler.compile(parse(source, name="demo"))


class TestSignalKeyParsing:
    def test_fact_key_plain(self) -> None:
        assert PullbackSignal._fact_key("trend") == FactKey("trend")

    def test_fact_key_with_timeframe(self) -> None:
        assert PullbackSignal._fact_key("trend@1w") == FactKey(
            "trend", timeframe=Timeframe("1w")
        )


class TestGraphRun:
    def test_run_selects_views_per_cross_tf_node(self) -> None:
        graph = ASTCompiler.compile(parse(_cross_tf_source(), name="demo"))
        view = MarketView(_multi_store(), cursor=59, window_size=50)
        facts = graph.run(view)
        names = {str(k) for k in facts}
        assert "ema_20_tf_1w" in names
        assert "ema_50_tf_1w" in names
        assert "swing_tf_1w" in names
        assert "trend_tf_1d" in names
        assert "swing_structure_tf_1d" in names
        # Backlog 067: PullbackPatternAnalyzer emits a fact only on the entry
        # candle that follows the final swing point. The weekly swing that
        # finalizes the structure is confirmed by a weekly candle arriving
        # after the daily entry day has already passed, so at this cursor the
        # entry window is gone and no pullback fact is produced.
        assert "pullback_pattern_tf_1d" not in names

    def test_single_tf_analysis_unchanged(self) -> None:
        source = (
            "ema20 := ema { period: 20 }\n"
            "ema50 := ema { period: 50 }\n"
            "trend := trend { ema_20: ema20, ema_50: ema50 }\n"
        )
        graph = ASTCompiler.compile(parse(source, name="demo"))
        by_name = {type(a).__name__: a for a in graph.execution_order()}
        tf = Timeframe("1d")
        assert by_name["TrendAnalyzer"].requires() == (
            FactKey("ema_20", timeframe=tf),
            FactKey("ema_50", timeframe=tf),
        )


def _multi_store() -> MarketStore:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    daily = tuple(
        Candle(
            timestamp=base + timedelta(days=i),
            open=100.0 + i,
            high=110.0 + i,
            low=95.0 + i,
            close=105.0 + i,
            volume=5000.0,
        )
        for i in range(60)
    )
    weekly = tuple(
        Candle(
            timestamp=base + timedelta(weeks=i),
            open=100.0 + i * 5,
            high=110.0 + i * 5,
            low=95.0 + i * 5,
            close=105.0 + i * 5,
            volume=5000.0,
        )
        for i in range(12)
    )
    return MarketStore(
        {
            Timeframe.D1: MarketData(symbol=Symbol("TEST"), timeframe=Timeframe.D1, candles=daily),
            Timeframe.W1: MarketData(symbol=Symbol("TEST"), timeframe=Timeframe.W1, candles=weekly),
        }
    )
