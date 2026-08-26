"""Backlog 063: instrument runtime expansion.

One instrument-neutral template AST compiles to N isolated per-instrument
``AnalysisGraph`` objects. The DSL never names an instrument — the runtime
supplies the instrument list and materializes per-instrument instances via
``TemplateGraph.instantiate`` / ``instantiate_all`` or, end to end, via
``backtest_template``.
"""

from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.instrument import (

    InstrumentBacktestResult,
    InstrumentGraph,
    TemplateGraph,
    backtest_template,
)
from marketatlas.analysis.ast.parser import parse
from marketatlas.analysis.ast.pipeline import CompilationError
from marketatlas.data.instrument import Instrument
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView

pytestmark = pytest.mark.tier2


def _instrument(canonical: str) -> Instrument:
    return Instrument(
        canonical=canonical,
        asset_class="forex",
        description=f"{canonical} pair",
        providers={"yahoo": canonical},
    )


def _store(n: int = 140, seed: int = 0) -> MarketStore:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    candles = tuple(
        Candle(
            timestamp=base + timedelta(days=i),
            open=100.0 + i * 0.1 + seed,
            high=110.0 + i * 0.1 + seed,
            low=95.0 + i * 0.1 + seed,
            close=105.0 + i * 0.1 + seed,
            volume=5000.0,
        )
        for i in range(n)
    )
    return MarketStore(
        MarketData(symbol=Symbol(f"TEST{seed}"), timeframe=Timeframe.D1, candles=candles)
    )


_FULL_STRATEGY = """
ema20 := ema { period: 20 }
ema50 := ema { period: 50 }
atr_14_series := atr_series { period: 14 }
atr_14 := atr { period: 14 }
swing := swings { lookback: 50 }
trend := trend { ema_20: ema20, ema_50: ema50, atr_14: atr_14 }
sr := sr { swing, atr_14_series }
alternate := swingstructure { swing }
pullback := pullbackpattern { swing_structure: alternate }
"""


def _full_template() -> TemplateGraph:
    return ASTCompiler.compile_template(parse(_FULL_STRATEGY, name="strategy"))


class TestCompileTemplate:
    def test_compile_returns_template(self) -> None:
        template = _full_template()
        assert isinstance(template, TemplateGraph)
        assert template.analysis.name == "strategy"
        assert len(template.config.analyzers) == 9

    def test_reference_graph_equals_compile(self) -> None:
        analysis = parse(_FULL_STRATEGY, name="strategy")
        template = ASTCompiler.compile_template(analysis)
        plain = ASTCompiler.compile(analysis)
        expected = [type(a) for a in plain.execution_order()]
        actual = [type(a) for a in template.graph.execution_order()]
        assert actual == expected

    def test_template_graph_runs(self) -> None:
        template = _full_template()
        facts = template.graph.run(MarketView(_store(), cursor=60, window_size=50))
        assert len(facts) > 0

    def test_choice_template_raises(self) -> None:
        analysis = parse("ema := ema { period: <20 | 50> }", name="t")
        with pytest.raises(CompilationError, match="Pipeline.compile_templates"):
            ASTCompiler.compile_template(analysis)

    def test_choice_template_compiles_to_many(self) -> None:
        analysis = parse("ema := ema { period: <20 | 50> }", name="t")
        templates = ASTCompiler.compile_templates(analysis)
        assert len(templates) == 2
        assert [t.config.analyzers[0].params["period"] for t in templates] == [20, 50]
        assert all(isinstance(t, TemplateGraph) for t in templates)


class TestInstantiate:
    def test_instantiate_carries_instrument(self) -> None:
        template = _full_template()
        ig = template.instantiate(_instrument("EURUSD"))
        assert isinstance(ig, InstrumentGraph)
        assert ig.canonical == "EURUSD"
        assert ig.instrument.canonical == "EURUSD"

    def test_instantiate_fresh_graph_per_call(self) -> None:
        template = _full_template()
        a = template.instantiate(_instrument("EURUSD"))
        b = template.instantiate(_instrument("GBPUSD"))
        assert a.graph is not template.graph
        assert a.graph is not b.graph
        assert a.graph.execution_order()[0] is not b.graph.execution_order()[0]

    def test_instantiate_structure_matches_template(self) -> None:
        template = _full_template()
        ig = template.instantiate(_instrument("EURUSD"))
        assert [type(a) for a in ig.graph.execution_order()] == [
            type(a) for a in template.graph.execution_order()
        ]

    def test_instantiate_all_preserves_order(self) -> None:
        template = _full_template()
        instruments = [
            _instrument("EURUSD"),
            _instrument("GBPUSD"),
            _instrument("USDJPY"),
        ]
        graphs = template.instantiate_all(instruments)
        assert [g.canonical for g in graphs] == ["EURUSD", "GBPUSD", "USDJPY"]
        assert len({id(g.graph) for g in graphs}) == 3

    def test_instantiate_all_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one instrument"):
            _full_template().instantiate_all([])

    def test_instantiate_graphs_run_isolated(self) -> None:
        template = _full_template()
        ig1 = template.instantiate(_instrument("EURUSD"))
        ig2 = template.instantiate(_instrument("GBPUSD"))
        view1 = MarketView(_store(seed=1), cursor=60, window_size=50)
        view2 = MarketView(_store(seed=2), cursor=60, window_size=50)
        facts1 = ig1.graph.run(view1)
        facts2 = ig2.graph.run(view2)
        control = ig1.graph.run(view1)
        assert facts1 == control
        assert facts2 != facts1


class TestBacktestTemplate:
    def test_runs_each_instrument_isolated(self) -> None:
        template = _full_template()
        instruments = [
            _instrument("EURUSD"),
            _instrument("GBPUSD"),
        ]
        results = backtest_template(
            template,
            [(instruments[0], _store(seed=1)), (instruments[1], _store(seed=2))],
            window_size=100,
            max_hold_days=10,
        )
        assert [r.canonical for r in results] == ["EURUSD", "GBPUSD"]
        assert all(isinstance(r, InstrumentBacktestResult) for r in results)
        assert results[0].frames is not results[1].frames
        assert results[0].tradebook is not results[1].tradebook
        assert len(results[0].frames) == 40
        assert len(results[1].frames) == 40
        assert results[0].tradebook.balance > 0
        assert results[1].tradebook.balance > 0

    def test_empty_stores_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            backtest_template(_full_template(), [])
