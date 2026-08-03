"""Backlog 061: timeframe declaration on analysis nodes.

``Definition.timeframe`` declares the timeframe a node runs on; the analysis
carries the derived declared set in ``Analysis.timeframes`` (base first). This
module covers the model fields, builder API, serialization round-trip, cloning,
compilation into ``AnalyzerConfig.timeframe``/``StrategyConfig.timeframes``,
the DSL's reserved ``timeframe`` field, and validation of invalid values.
"""

from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.analysis.ast.builder import AnalysisBuilder
from marketatlas.analysis.ast.clone import clone
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.constructors import build_analysis
from marketatlas.analysis.ast.models import (
    Analysis,
    Definition,
    Provider,
    derive_timeframes,
)
from marketatlas.analysis.ast.parser import DslParseError, parse
from marketatlas.analysis.ast.serialization import from_dict, to_dict
from marketatlas.analysis.ast.validation import validate
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView


class TestModel:
    def test_definition_timeframe_defaults_none(self) -> None:
        d = Definition(name="ema", provider="ema")
        assert d.timeframe is None

    def test_analysis_timeframes_defaults_empty(self) -> None:
        a = Analysis(name="a", version="1.0")
        assert a.timeframes == ()

    def test_definition_timeframe_assigned(self) -> None:
        d = Definition(name="ema", provider="ema", timeframe=Timeframe.H1)
        assert d.timeframe == Timeframe.H1


class TestDeriveTimeframes:
    def _def(self, tf: Timeframe | None) -> Definition:
        return Definition(name="d", provider="ema", timeframe=tf)

    def test_no_base_no_defs_empty(self) -> None:
        assert derive_timeframes(None, ()) == ()

    def test_no_base_no_tfs_empty(self) -> None:
        assert derive_timeframes(None, (self._def(None), self._def(None))) == ()

    def test_base_only(self) -> None:
        assert derive_timeframes(Timeframe.D1, ()) == ("1d",)

    def test_def_tf_first_is_base(self) -> None:
        defs = (self._def(Timeframe.H1), self._def(Timeframe.W1))
        assert derive_timeframes(None, defs) == ("1h", "1w")

    def test_base_plus_def_tfs(self) -> None:
        defs = (self._def(Timeframe.H1), self._def(Timeframe.W1))
        assert derive_timeframes(Timeframe.D1, defs) == ("1d", "1h", "1w")

    def test_dedup(self) -> None:
        defs = (self._def(Timeframe.H1), self._def(None), self._def(Timeframe.H1))
        assert derive_timeframes(None, defs) == ("1h",)


class TestBuilder:
    def test_definition_with_timeframe(self) -> None:
        a = (
            AnalysisBuilder("demo", "1.0")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_timeframe("1h")
            .build()
        )
        assert a.definitions[0].timeframe == Timeframe.H1

    def test_definition_accepts_timeframe_instance(self) -> None:
        a = (
            AnalysisBuilder("demo", "1.0")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_timeframe(Timeframe.W1)
            .build()
        )
        assert a.definitions[0].timeframe == Timeframe.W1

    def test_definition_default_none(self) -> None:
        a = (
            AnalysisBuilder("demo", "1.0").define("ema", "analyzer", "EMAAnalyzer").build()
        )
        assert a.definitions[0].timeframe is None
        assert a.timeframes == ()

    def test_invalid_definition_timeframe_raises(self) -> None:
        b = AnalysisBuilder("demo", "1.0").define("ema", "analyzer", "EMAAnalyzer")
        with pytest.raises(ValueError, match="Invalid timeframe 'bogus'"):
            b.with_timeframe("bogus")

    def test_analysis_base_timeframe(self) -> None:
        a = (
            AnalysisBuilder("demo", "1.0")
            .with_timeframe("1d")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_timeframe("1h")
            .build()
        )
        assert a.timeframes == ("1d", "1h")

    def test_analysis_invalid_base_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid timeframe"):
            AnalysisBuilder("demo", "1.0").with_timeframe("13m")

    def test_analysis_timeframes_derived_from_defs(self) -> None:
        a = (
            AnalysisBuilder("demo", "1.0")
            .define("swings", "analyzer", "SwingStructureAnalyzer")
            .with_timeframe("1w")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_timeframe("1d")
            .build()
        )
        assert a.timeframes == ("1w", "1d")

    def test_builder_equivalent_to_constructors(self) -> None:
        a = (
            AnalysisBuilder("demo", "1.0")
            .define("ema", "analyzer", "EMAAnalyzer")
            .with_timeframe("1h")
            .with_param("period", 20)
            .build()
        )
        b = parse('ema := ema { timeframe: "1h", period: 20 }', name="demo")
        assert a.definitions[0].timeframe == b.definitions[0].timeframe
        assert a.definitions[0].parameters == b.definitions[0].parameters
        assert a.timeframes == b.timeframes


class TestSerialization:
    def test_timeframe_in_dict(self) -> None:
        a = Analysis(
            name="a",
            version="1.0",
            definitions=(Definition(name="ema", provider="ema", timeframe=Timeframe.H1),),
            timeframes=("1d", "1h"),
        )
        obj = to_dict(a)
        defs = obj["definitions"]
        assert isinstance(defs, list)
        assert defs[0]["timeframe"] == "1h"
        assert obj["timeframes"] == ["1d", "1h"]

    def test_absent_fields_omitted(self) -> None:
        a = Analysis(name="a", version="1.0")
        obj = to_dict(a)
        assert "timeframes" not in obj
        defs = obj.get("definitions", [])
        assert isinstance(defs, list)
        assert all("timeframe" not in d for d in defs)

    def test_round_trip(self) -> None:
        a = Analysis(
            name="a",
            version="1.0",
            definitions=(Definition(name="ema", provider="ema", timeframe=Timeframe.W1),),
            timeframes=("1w",),
        )
        assert from_dict(to_dict(a)) == a

    def test_invalid_definition_timeframe_raises(self) -> None:
        data = {
            "name": "a",
            "version": "1.0",
            "definitions": [{"name": "ema", "provider": "ema", "timeframe": "bogus"}],
        }
        with pytest.raises(ValueError, match="Invalid timeframe 'bogus'"):
            from_dict(data)

    def test_invalid_analysis_timeframes_raises(self) -> None:
        data = {"name": "a", "version": "1.0", "timeframes": ["13m"]}
        with pytest.raises(ValueError, match="Invalid timeframe '13m'"):
            from_dict(data)


class TestClone:
    def test_clone_preserves_timeframes(self) -> None:
        a = Analysis(
            name="a",
            version="1.0",
            definitions=(
                Definition(name="ema", provider="ema", timeframe=Timeframe.H1),
                Definition(name="swings", provider="swings", timeframe=Timeframe.W1),
            ),
            timeframes=("1h", "1w"),
        )
        c = clone(a)
        assert c == a
        assert [d.timeframe for d in c.definitions] == [Timeframe.H1, Timeframe.W1]
        assert c.timeframes == ("1h", "1w")


class TestCompile:
    def test_config_sets_timeframe(self) -> None:
        a = parse('ema := ema { timeframe: "1h", period: 20 }', name="demo")
        config = ASTCompiler.to_config(a)
        assert config.analyzers[0].timeframe == "1h"
        assert config.timeframes == ("1h",)

    def test_config_defaults_to_none(self) -> None:
        a = parse("ema := ema { period: 20 }", name="demo")
        config = ASTCompiler.to_config(a)
        assert config.analyzers[0].timeframe is None
        assert config.timeframes == ("1d",)

    def test_graph_analyzers_carry_timeframe(self) -> None:
        a = parse(
            'ema := ema { timeframe: "1d", period: 5 }\n'
            'swings := swingstructure { timeframe: "1w", lookback: 5 }',
            name="demo",
        )
        graph = ASTCompiler.compile(a)
        tfs = sorted(
            tf.value
            for an in graph.execution_order()
            if (tf := an.timeframe) is not None
        )
        assert tfs == ["1d", "1w"]

    def test_graph_run_selects_per_analyzer_view(self) -> None:
        a = parse(
            'ema := ema { timeframe: "1d", period: 5 }\n'
            'swings := swingstructure { timeframe: "1w", lookback: 3 }',
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
            'ema := ema { timeframe: "4h", period: 20 }'
        )
        assert len(graphs) == 1
        assert graphs[0].execution_order()[0].timeframe == Timeframe.H4


class TestDsl:
    def test_timeframe_field_parses(self) -> None:
        a = parse('ema := ema { period: 20, timeframe: "1h" }', name="demo")
        assert a.definitions[0].timeframe == Timeframe.H1
        assert a.definitions[0].parameters == (a.definitions[0].parameters[0],)

    def test_timeframe_not_a_parameter(self) -> None:
        a = parse('ema := ema { timeframe: "1w" }', name="demo")
        assert a.definitions[0].timeframe == Timeframe.W1
        assert a.definitions[0].parameters == ()

    def test_analysis_timeframes_derived(self) -> None:
        a = parse(
            'swings := swingstructure { timeframe: "1w" }\n'
            'ema := ema { timeframe: "1d" }',
            name="demo",
        )
        assert a.timeframes == ("1w", "1d")

    def test_invalid_timeframe_positioned(self) -> None:
        with pytest.raises(DslParseError) as excinfo:
            parse('ema := ema { timeframe: "13m" }', name="demo")
        assert excinfo.value.position.line == 1
        assert excinfo.value.position.col > 0
        assert "invalid timeframe '13m'" in excinfo.value.message
        assert "Valid timeframes" in excinfo.value.message

    def test_unquoted_timeframe_rejected(self) -> None:
        with pytest.raises(DslParseError, match="must be a quoted string"):
            parse("ema := ema { timeframe: 1h }", name="demo")

    def test_bare_timeframe_rejected(self) -> None:
        with pytest.raises(DslParseError, match="expected ':'"):
            parse("ema := ema { timeframe }", name="demo")


class TestValidation:
    def test_rejects_non_timeframe_object(self) -> None:
        a = Analysis(
            name="a",
            version="1.0",
            definitions=(Definition(name="ema", provider="ema", timeframe="bogus"),),  # type: ignore[arg-type]
        )
        result = validate(a)
        assert not result.is_valid
        assert result.errors[0].message.startswith("Definition 'ema' has an invalid timeframe")

    def test_rejects_invalid_analysis_timeframes(self) -> None:
        a = Analysis(name="a", version="1.0", timeframes=("13m",))
        result = validate(a)
        assert not result.is_valid
        assert "invalid timeframe '13m'" in result.errors[0].message

    def test_valid_timeframes_pass(self) -> None:
        a = Analysis(
            name="a",
            version="1.0",
            definitions=(Definition(name="ema", provider="ema", timeframe=Timeframe.H1),),
            providers=(
                Provider(
                    name="ema",
                    capability="ema",
                    category="analyzer",
                    impl="EMAAnalyzer",
                ),
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
    from dataclasses import replace

    from marketatlas.analysis.ast.constructors import EMA

    a = build_analysis(
        "demo",
        (replace(EMA("ema", period=20), timeframe=Timeframe.H1),),
    )
    assert a.timeframes == ("1h",)
