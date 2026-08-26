"""Backlog 061: timeframes as ``TimeFrame`` definitions + reference params.

A ``TimeFrame`` definition is an ordinary value-producing definition::

    tf1w := timeframe { resolution: "1w" }
    ema  := ema { timeframe: tf1w, period: 20 }

The ``timeframe: tf1w`` field is a ``ReferenceExpression`` parameter; the
compiler resolves it into ``AnalyzerConfig.timeframe``. ``Analysis.timeframes``
carries the derived declared set (first-seen, deduplicated). This module
covers the model helpers, builder API, DSL, serialization round-trip, cloning,
compilation, and validation of the reference-param model.
"""

from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.analysis.ast.builder import AnalysisBuilder
from marketatlas.analysis.ast.clone import clone
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.constructors import EMA, TimeFrame, build_analysis
from marketatlas.analysis.ast.expressions import Choice, ReferenceExpression, wrap
from marketatlas.analysis.ast.models import (
    Analysis,
    Definition,
    Parameter,
    Provider,
    derive_timeframes,
)
from marketatlas.analysis.ast.parser import parse
from marketatlas.analysis.ast.serialization import from_dict, to_dict
from marketatlas.analysis.ast.validation import validate
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView


def _tf_def(name: str, resolution: object) -> Definition:
    return Definition(
        name=name,
        provider="timeframe",
        parameters=(Parameter(name="resolution", value=wrap(resolution)),),
    )


class TestModel:
    def test_analysis_timeframes_defaults_empty(self) -> None:
        a = Analysis(name="a", version="1.0")
        assert a.timeframes == ()

    def test_definition_has_no_timeframe_field(self) -> None:
        d = Definition(name="ema", provider="ema")
        assert not hasattr(d, "timeframe")

    def test_timeframe_definition_marker(self) -> None:
        assert _tf_def("tf", "1w").provider == "timeframe"


class TestDeriveTimeframes:
    def test_no_defs_empty(self) -> None:
        assert derive_timeframes(()) == ()

    def test_no_timeframe_defs_empty(self) -> None:
        defs = (Definition(name="ema", provider="ema"), Definition(name="atr", provider="atr"))
        assert derive_timeframes(defs) == ()

    def test_single_tf(self) -> None:
        assert derive_timeframes((_tf_def("tf1w", "1w"),)) == ("1w",)

    def test_first_seen_order(self) -> None:
        defs = (_tf_def("tf1h", "1h"), _tf_def("tf1w", "1w"))
        assert derive_timeframes(defs) == ("1h", "1w")

    def test_dedup(self) -> None:
        defs = (_tf_def("a", "1h"), _tf_def("b", "1d"), _tf_def("c", "1h"))
        assert derive_timeframes(defs) == ("1h", "1d")

    def test_non_literal_resolution_skipped(self) -> None:
        defs = (_tf_def("t", Choice(["1h", "1w"])),)
        assert derive_timeframes(defs) == ()


class TestBuilder:
    def _builder(self) -> AnalysisBuilder:
        return AnalysisBuilder("demo", "1.0").define_provider(
            "timeframe", "timeframe", "timeframe", "TimeFrame"
        )

    def test_reference_to_timeframe_param(self) -> None:
        a = (
            self._builder()
            .define("tf1w", "timeframe")
            .with_param("resolution", "1w")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_reference("timeframe", "tf1w")
            .build()
        )
        assert a.definitions[1].parameters == (
            Parameter(name="timeframe", value=ReferenceExpression("tf1w")),
        )

    def test_with_timeframe_helper(self) -> None:
        a = (
            self._builder()
            .define("tf1w", "timeframe")
            .with_param("resolution", "1w")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_timeframe("tf1w")
            .build()
        )
        assert a.definitions[1].parameters == (
            Parameter(name="timeframe", value=ReferenceExpression("tf1w")),
        )

    def test_analysis_timeframes_derived(self) -> None:
        a = (
            self._builder()
            .define("tf1w", "timeframe")
            .with_param("resolution", "1w")
            .define("tf1d", "timeframe")
            .with_param("resolution", "1d")
            .define("ema", "analyzer", "EMAAnalyzer")
            .build()
        )
        assert a.timeframes == ("1w", "1d")

    def test_no_timeframe_defs_no_timeframes(self) -> None:
        a = (
            AnalysisBuilder("demo", "1.0").define("ema", "analyzer", "EMAAnalyzer").build()
        )
        assert a.definitions[0].parameters == ()
        assert a.timeframes == ()

    def test_unknown_reference_source_raises(self) -> None:
        builder = self._builder().define("ema", "analyzer", "EMAAnalyzer")
        with pytest.raises(ValueError, match="Unknown source definition: ghost"):
            builder.with_reference("timeframe", "ghost")

    def test_with_timeframe_requires_timeframe_def(self) -> None:
        builder = self._builder().define("ema", "analyzer", "EMAAnalyzer")
        with pytest.raises(ValueError, match="'ema' is not a TimeFrame definition"):
            builder.with_timeframe("ema")

    def test_builder_equivalent_to_parse(self) -> None:
        a = (
            self._builder()
            .define("tf1w", "timeframe")
            .with_param("resolution", "1w")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_reference("timeframe", "tf1w")
            .with_param("period", 20)
            .build()
        )
        b = parse(
            'tf1w := timeframe { resolution: "1w" }\n'
            "ema := ema { timeframe: tf1w, period: 20 }",
            name="demo",
        )
        assert a.definitions[1].parameters == b.definitions[1].parameters
        assert a.timeframes == b.timeframes


class TestSerialization:
    def test_reference_param_in_dict(self) -> None:
        a = parse(
            'tf1w := timeframe { resolution: "1w" }\n'
            "ema := ema { timeframe: tf1w, period: 20 }",
            name="a",
        )
        obj = to_dict(a)
        defs = obj["definitions"]
        assert isinstance(defs, list)
        assert {
            "name": "timeframe",
            "value": {"expr": "reference", "name": "tf1w"},
        } in defs[1]["parameters"]  # type: ignore[index]
        assert obj["timeframes"] == ["1w"]

    def test_round_trip(self) -> None:
        a = parse(
            'tf1w := timeframe { resolution: "1w" }\n'
            "ema := ema { timeframe: tf1w, period: 20 }",
            name="a",
        )
        restored = from_dict(to_dict(a))
        assert restored == a
        assert restored.definitions[1].parameters[0].value == ReferenceExpression("tf1w")
        assert restored.timeframes == ("1w",)

    def test_absent_fields_omitted(self) -> None:
        a = Analysis(name="a", version="1.0")
        obj = to_dict(a)
        assert "timeframes" not in obj
        assert "definitions" not in obj

    def test_invalid_analysis_timeframes_raises(self) -> None:
        data = {"name": "a", "version": "1.0", "timeframes": ["13m"]}
        with pytest.raises(ValueError, match="Invalid timeframe '13m'"):
            from_dict(data)


class TestClone:
    def test_clone_preserves_references_and_timeframes(self) -> None:
        a = parse(
            'tf1w := timeframe { resolution: "1w" }\n'
            'tf1d := timeframe { resolution: "1d" }\n'
            "ema := ema { timeframe: tf1w, period: 20 }",
            name="a",
        )
        c = clone(a)
        assert c == a
        assert c.definitions[2].parameters[0].value == ReferenceExpression("tf1w")
        assert c.timeframes == ("1w", "1d")


class TestCompile:
    def test_config_sets_timeframe(self) -> None:
        a = parse(
            'tf1w := timeframe { resolution: "1w" }\n'
            "ema := ema { timeframe: tf1w, period: 20 }",
            name="demo",
        )
        config = ASTCompiler.to_config(a)
        assert config.analyzers[0].timeframe == "1w"
        assert config.timeframes == ("1w",)

    def test_config_defaults_to_none(self) -> None:
        a = parse("ema := ema { period: 20 }", name="demo")
        config = ASTCompiler.to_config(a)
        assert config.analyzers[0].timeframe is None
        assert config.timeframes == ("1d",)

    def test_graph_analyzers_carry_timeframe(self) -> None:
        a = parse(
            'tf1d := timeframe { resolution: "1d" }\n'
            'tf1w := timeframe { resolution: "1w" }\n'
            "ema := ema { timeframe: tf1d, period: 5 }\n"
            "swings := swings { timeframe: tf1w }\n"
            "structure := swingstructure { timeframe: tf1w, window: 5, swing: swings }",
            name="demo",
        )
        graph = ASTCompiler.compile(a)
        tfs = sorted(
            {tf.value for an in graph.execution_order() if (tf := an.timeframe) is not None}
        )
        assert tfs == ["1d", "1w"]

    def test_graph_run_selects_per_analyzer_view(self) -> None:
        a = parse(
            'tf1d := timeframe { resolution: "1d" }\n'
            'tf1w := timeframe { resolution: "1w" }\n'
            "ema := ema { timeframe: tf1d, period: 5 }\n"
            "swings := swings { timeframe: tf1w }\n"
            "structure := swingstructure { timeframe: tf1w, window: 3, swing: swings }",
            name="demo",
        )
        graph = ASTCompiler.compile(a)
        view = MarketView(_multi_store(), cursor=59, window_size=50)
        facts = graph.run(view)
        names = {str(k) for k in facts}
        assert any(k.endswith("tf_1d") for k in names)
        assert any(k.endswith("tf_1w") for k in names)

    def test_compile_dsl_end_to_end(self) -> None:
        graphs = ASTCompiler.compile_dsl(
            'tf4h := timeframe { resolution: "4h" }\n'
            "ema := ema { timeframe: tf4h, period: 20 }"
        )
        assert len(graphs) == 1
        assert graphs[0].execution_order()[0].timeframe == Timeframe.H4


class TestDsl:
    def test_timeframe_reference_parses(self) -> None:
        a = parse(
            'tf1h := timeframe { resolution: "1h" }\n'
            "ema := ema { period: 20, timeframe: tf1h }",
            name="demo",
        )
        ema = a.definitions[1]
        assert ema.parameters[1] == Parameter(name="timeframe", value=ReferenceExpression("tf1h"))
        assert ema.parameters[0] == Parameter(name="period", value=wrap(20))

    def test_timeframe_def_ordinary_definition(self) -> None:
        a = parse('tf1w := timeframe { resolution: "1w" }', name="demo")
        assert a.definitions[0].provider == "timeframe"
        assert a.timeframes == ("1w",)

    def test_analysis_timeframes_derived(self) -> None:
        a = parse(
            'tf1w := timeframe { resolution: "1w" }\n'
            'tf1d := timeframe { resolution: "1d" }\n'
            "swings := swingstructure { timeframe: tf1w }\n"
            "ema := ema { timeframe: tf1d }",
            name="demo",
        )
        assert a.timeframes == ("1w", "1d")


class TestValidation:
    def test_valid_timeframe_reference_passes(self) -> None:
        a = parse(
            'tf1h := timeframe { resolution: "1h" }\n'
            "ema := ema { timeframe: tf1h, period: 20 }",
            name="demo",
        )
        assert validate(a).is_valid

    def test_rejects_invalid_resolution(self) -> None:
        a = parse('tf := timeframe { resolution: "13m" }', name="demo")
        result = validate(a)
        assert not result.is_valid
        assert "invalid resolution '13m'" in result.errors[0].message

    def test_rejects_missing_resolution(self) -> None:
        a = parse("tf := timeframe { }", name="demo")
        result = validate(a)
        assert not result.is_valid
        assert "missing the required 'resolution'" in result.errors[0].message

    def test_rejects_timeframe_ref_on_signal(self) -> None:
        a = parse(
            'tf1d := timeframe { resolution: "1d" }\n'
            "sig := generate_signal { timeframe: tf1d }",
            name="demo",
        )
        result = validate(a)
        assert not result.is_valid
        assert "only valid on analyzer definitions, not 'signal'" in result.errors[0].message

    def test_rejects_unknown_reference(self) -> None:
        a = parse("ema := ema { timeframe: ghost, period: 20 }", name="demo")
        result = validate(a)
        assert not result.is_valid
        assert "Unknown reference" in result.errors[0].message

    def test_rejects_invalid_analysis_timeframes(self) -> None:
        a = Analysis(name="a", version="1.0", timeframes=("13m",))
        result = validate(a)
        assert not result.is_valid
        assert "invalid timeframe '13m'" in result.errors[0].message

    def test_valid_manual_analysis(self) -> None:
        a = Analysis(
            name="a",
            version="1.0",
            definitions=(
                _tf_def("tf1h", "1h"),
                Definition(
                    name="ema",
                    provider="ema",
                    parameters=(Parameter(name="timeframe", value=ReferenceExpression("tf1h")),),
                ),
            ),
            providers=(
                Provider(
                    name="timeframe",
                    capability="timeframe",
                    category="timeframe",
                    impl="TimeFrame",
                ),
                Provider(name="ema", capability="ema", category="analyzer", impl="EMAAnalyzer"),
            ),
            timeframes=("1h",),
        )
        assert validate(a).is_valid


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


def test_build_analysis_derives_timeframes() -> None:
    a = build_analysis("demo", (TimeFrame("tf1h", resolution="1h"), EMA("ema", period=20)))
    assert a.timeframes == ("1h",)
