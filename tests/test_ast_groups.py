"""Backlog 064: market groups — cross-instrument nodes.

A group is a named collection of instruments supplied at runtime (outside the
DSL, like the instrument list of backlog 063). A ``group``-scoped node
aggregates the outputs of per-instrument sibling nodes across the whole group:
one group node instance wiring together N per-instrument instances. The DSL
declares the scope with the contextual ``group`` keyword and the spanning
reference with a trailing ``*``; ``TemplateGraph.instantiate_group``
materializes N per-instrument graphs plus 1 group node graph.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.ast.builder import AnalysisBuilder
from marketatlas.analysis.ast.clone import clone
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.expressions import (
    ReferenceExpression,
    SpanningReferenceExpression,
)
from marketatlas.analysis.ast.instrument import GroupGraph, TemplateGraph
from marketatlas.analysis.ast.models import SCOPE_GROUP, SCOPE_INSTRUMENT
from marketatlas.analysis.ast.parser import parse
from marketatlas.analysis.ast.pipeline import CompilationError
from marketatlas.analysis.ast.registry import ProviderContract, create_default_registry
from marketatlas.analysis.ast.serialization import from_dict, to_dict
from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.result import AnalysisResult
from marketatlas.data.instrument import Instrument
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact


class NumericFact(Fact):
    """Aggregate fact: a plain numeric value plus its timestamp."""

    def __init__(self, value: float, timestamp: datetime) -> None:
        super().__init__(timestamp=timestamp, evidence=())
        self.value = value


class DollarStrengthAnalyzer(Analyzer):
    """Dollar-strength-style group provider: sums one fact per member.

    Consumes the same fact (``bindings`` field) from every group member and
    produces a single aggregate. ``members`` is injected at instantiation by
    ``TemplateGraph.instantiate_group`` — it is never a DSL parameter.
    """

    def __init__(self, members: tuple[str, ...] = (), **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._members = tuple(members)

    @property
    def instance_key(self) -> str:
        return "dollar_strength"

    def _member_keys(self) -> tuple[FactKey, ...]:
        keys: list[FactKey] = []
        for binding in self._bindings.values():
            name, _, tf = binding.partition("@")
            timeframe = Timeframe(tf) if tf else Timeframe("1d")
            keys.extend(FactKey(f"{m}/{name}", timeframe=timeframe) for m in self._members)
        return tuple(keys)

    def requires(self) -> tuple[FactKey, ...]:
        return self._member_keys()

    def produces(self) -> tuple[FactKey, ...]:
        return (self._make_key(self.instance_key),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        total = sum(cast(NumericFact, facts[fk]).value for fk in self._member_keys())
        return AnalysisResult(
            facts=(NumericFact(total, view.current.timestamp),),
            evidence=(),
        )


def _registry():
    registry = create_default_registry()
    registry.register("dollar_strength", DollarStrengthAnalyzer)
    registry.register_contract("dollar_strength", ProviderContract(inputs=("ema_20",)))
    return registry


_GROUP_STRATEGY = """
rel := ema { period: 20 }
group strength := dollar_strength { ema_20: rel* }
"""


def _instrument(canonical: str) -> Instrument:
    return Instrument(
        canonical=canonical,
        asset_class="forex",
        description=f"{canonical} pair",
        providers={"yahoo": canonical},
    )


def _store(seed: int = 0) -> MarketStore:
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
        for i in range(140)
    )
    return MarketStore(
        MarketData(symbol=Symbol(f"TEST{seed}"), timeframe=Timeframe.D1, candles=candles)
    )


def _template() -> TemplateGraph:
    return ASTCompiler.compile_template(
        parse(_GROUP_STRATEGY, name="strategy", registry=_registry()), registry=_registry()
    )


class TestDslParse:
    def test_group_keyword_marks_scope(self) -> None:
        analysis = parse(_GROUP_STRATEGY, name="strategy", registry=_registry())
        assert [(d.name, d.scope) for d in analysis.definitions] == [
            ("rel", SCOPE_INSTRUMENT),
            ("strength", SCOPE_GROUP),
        ]

    def test_spanning_reference_parsed(self) -> None:
        analysis = parse(_GROUP_STRATEGY, name="strategy", registry=_registry())
        strength = analysis.definitions[1]
        param = strength.parameters[0]
        assert param.name == "ema_20"
        assert param.value == SpanningReferenceExpression("rel")

    def test_contextual_keyword_still_a_name(self) -> None:
        analysis = parse("group := ema { period: 20 }", name="t")
        assert analysis.definitions[0].name == "group"
        assert analysis.definitions[0].scope == SCOPE_INSTRUMENT

    def test_contextual_keyword_as_reference_target(self) -> None:
        analysis = parse("group := ema { period: 20 }\nother := trend { ema_20: group }", name="t")
        assert [d.name for d in analysis.definitions] == ["group", "other"]

    def test_group_shorthand_is_spanning(self) -> None:
        analysis = parse(
            "rel := ema { period: 20 }\n" "group strength := dollar_strength { ema_20, }",
            name="t",
            registry=_registry(),
        )
        strength = analysis.definitions[1]
        assert isinstance(strength.parameters[0].value, SpanningReferenceExpression)
        assert strength.parameters[0].value.name == "ema_20"

    def test_plain_reference_not_spanning(self) -> None:
        analysis = parse("rel := ema { period: 20 }\nother := trend { ema_20: rel }", name="t")
        value = analysis.definitions[1].parameters[0].value
        assert isinstance(value, ReferenceExpression)
        assert not isinstance(value, SpanningReferenceExpression)


class TestBuilder:
    def test_with_scope_and_spanning_reference(self) -> None:
        analysis = (
            AnalysisBuilder("t", "1.0")
            .define("rel", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("strength", "analyzer", "DollarStrengthAnalyzer")
            .with_scope(SCOPE_GROUP)
            .with_spanning_reference("ema_20", "rel")
            .build()
        )
        strength = analysis.definitions[1]
        assert strength.scope == SCOPE_GROUP
        assert strength.parameters[0].value == SpanningReferenceExpression("rel")

    def test_builder_equals_dsl(self) -> None:
        dsl = parse(_GROUP_STRATEGY, name="strategy", registry=_registry())
        manual = (
            AnalysisBuilder("strategy", "1.0")
            .define_provider("ema", "compute_ema", "analyzer", "EMAAnalyzer")
            .define("rel", "ema")
            .with_param("period", 20)
            .define_provider("dollar_strength", "aggregate", "analyzer", "DollarStrengthAnalyzer")
            .define("strength", "dollar_strength")
            .with_scope(SCOPE_GROUP)
            .with_spanning_reference("ema_20", "rel")
            .build()
        )
        assert dsl.definitions == manual.definitions

    def test_invalid_scope_rejected(self) -> None:
        builder = AnalysisBuilder("t", "1.0").define("x", "analyzer", "EMAAnalyzer")
        with pytest.raises(ValueError, match="Invalid scope"):
            builder.with_scope("nope")


class TestSerializationClone:
    def test_round_trip_preserves_scope_and_spanning(self) -> None:
        analysis = parse(_GROUP_STRATEGY, name="strategy", registry=_registry())
        restored = from_dict(to_dict(analysis))
        assert restored.definitions == analysis.definitions
        assert restored.definitions[1].scope == SCOPE_GROUP
        assert isinstance(restored.definitions[1].parameters[0].value, SpanningReferenceExpression)

    def test_clone_preserves_scope_and_spanning(self) -> None:
        analysis = parse(_GROUP_STRATEGY, name="strategy", registry=_registry())
        copied = clone(analysis)
        assert copied.definitions == analysis.definitions
        assert copied.definitions[1].scope == SCOPE_GROUP
        value = copied.definitions[1].parameters[0].value
        assert isinstance(value, SpanningReferenceExpression)


class TestValidation:
    def test_spanning_on_instrument_scope_rejected(self) -> None:
        analysis = parse(
            "rel := ema { period: 20 }\nstrength := dollar_strength { ema_20: rel* }",
            name="t",
            registry=_registry(),
        )
        with pytest.raises(CompilationError, match="only valid on a group-scoped definition"):
            ASTCompiler.compile_template(analysis, registry=_registry())

    def test_group_plain_reference_rejected(self) -> None:
        analysis = parse(
            "rel := ema { period: 20 }\ngroup strength := dollar_strength { ema_20: rel }",
            name="t",
            registry=_registry(),
        )
        with pytest.raises(CompilationError, match="spanning reference"):
            ASTCompiler.compile_template(analysis, registry=_registry())

    def test_cross_group_reference_rejected(self) -> None:
        analysis = parse(
            "rel := ema { period: 20 }\n"
            "group strength := dollar_strength { ema_20: rel* }\n"
            "other := ema { period: 10, ema_20: strength }",
            name="t",
            registry=_registry(),
        )
        with pytest.raises(CompilationError, match="Cross-group reference"):
            ASTCompiler.compile_template(analysis, registry=_registry())

    def test_spanning_to_timeframe_rejected(self) -> None:
        analysis = parse(
            'tf1d := timeframe { resolution: "1d" }\n'
            "group strength := dollar_strength { timeframe: tf1d* }",
            name="t",
            registry=_registry(),
        )
        with pytest.raises(CompilationError, match="TimeFrame"):
            ASTCompiler.compile_template(analysis, registry=_registry())

    def test_group_signal_rejected(self) -> None:
        registry = create_default_registry()
        registry.register("sig", DollarStrengthAnalyzer, category="signal")
        analysis = parse(
            "rel := ema { period: 20 }\ngroup s := sig { ema_20: rel* }",
            name="t",
            registry=registry,
        )
        with pytest.raises(CompilationError, match="must be an analyzer"):
            ASTCompiler.compile_template(analysis, registry=registry)

    def test_plain_graph_compile_rejects_group_defs(self) -> None:
        analysis = parse(_GROUP_STRATEGY, name="strategy", registry=_registry())
        with pytest.raises(CompilationError, match="instantiate_group"):
            ASTCompiler.compile(analysis, registry=_registry())


class TestCompileTemplate:
    def test_member_config_excludes_group_nodes(self) -> None:
        template = _template()
        assert [a.type for a in template.config.analyzers] == ["EMAAnalyzer"]
        assert [type(a) for a in template.graph.execution_order()] == [EMAAnalyzer]

    def test_group_config_holds_only_group_nodes(self) -> None:
        template = _template()
        assert template.has_group
        group_config = template.group_config
        assert group_config is not None
        assert [a.type for a in group_config.analyzers] == ["DollarStrengthAnalyzer"]

    def test_group_binding_is_member_agnostic(self) -> None:
        template = _template()
        group_config = template.group_config
        assert group_config is not None
        params = group_config.analyzers[0].params
        assert params["bindings"] == {"ema_20": "ema_20@1d"}
        assert "members" not in params

    def test_no_group_template(self) -> None:
        template = ASTCompiler.compile_template(parse("rel := ema { period: 20 }", name="t"))
        assert not template.has_group

    def test_choice_template_still_expands(self) -> None:
        source = (
            "rel := ema { period: 20 }\n"
            "group strength := dollar_strength { ema_20: rel* }\n"
            "alt := ema { period: <30 | 40> }"
        )
        templates = ASTCompiler.compile_templates(
            parse(source, name="t", registry=_registry()), registry=_registry()
        )
        assert len(templates) == 2
        assert all(t.has_group for t in templates)


class TestInstantiateGroup:
    def test_structure_n_plus_one(self) -> None:
        template = _template()
        instruments = [
            _instrument("EURUSD"),
            _instrument("GBPUSD"),
            _instrument("USDJPY"),
        ]
        gg = template.instantiate_group("majors", instruments)
        assert isinstance(gg, GroupGraph)
        assert gg.canonical == "majors"
        assert [m.canonical for m in gg.members] == ["EURUSD", "GBPUSD", "USDJPY"]
        assert [g.canonical for g in gg.member_graphs] == ["EURUSD", "GBPUSD", "USDJPY"]
        assert len(gg.group_graph.execution_order()) == 1
        assert type(gg.group_graph.execution_order()[0]) is DollarStrengthAnalyzer

    def test_member_graphs_isolated_and_fresh(self) -> None:
        gg1 = _template().instantiate_group("a", [_instrument("EURUSD"), _instrument("GBPUSD")])
        gg2 = _template().instantiate_group("b", [_instrument("EURUSD"), _instrument("GBPUSD")])
        a1 = gg1.member_graphs[0].graph
        b1 = gg2.member_graphs[0].graph
        assert a1 is not b1
        assert a1.execution_order()[0] is not b1.execution_order()[0]
        assert gg1.group_graph is not gg2.group_graph

    def test_empty_members_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one instrument"):
            _template().instantiate_group("majors", [])

    def test_no_group_defs_raises(self) -> None:
        template = ASTCompiler.compile_template(parse("rel := ema { period: 20 }", name="t"))
        with pytest.raises(ValueError, match="no group-scoped definitions"):
            template.instantiate_group("majors", [_instrument("EURUSD")])

    def test_group_node_sees_per_member_facts(self) -> None:
        template = _template()
        instruments = [
            _instrument("EURUSD"),
            _instrument("GBPUSD"),
            _instrument("USDJPY"),
        ]
        gg = template.instantiate_group("majors", instruments)
        views = [MarketView(_store(seed=i), cursor=60, window_size=50) for i in range(3)]
        facts = gg.run(views)

        member_keys = [k for k in facts if "/" in k.name]
        assert len(member_keys) == 3
        assert {k.name.split("/")[0] for k in member_keys} == {
            "EURUSD",
            "GBPUSD",
            "USDJPY",
        }
        per_member = sum(cast(NumericFact, facts[k]).value for k in member_keys)
        group_key = next(k for k in facts if k.name == "dollar_strength")
        assert cast(NumericFact, facts[group_key]).value == pytest.approx(per_member)

    def test_group_result_matches_manual_sum(self) -> None:
        template = _template()
        gg = template.instantiate_group("majors", [_instrument("EURUSD"), _instrument("GBPUSD")])
        views = [MarketView(_store(seed=i), cursor=60, window_size=50) for i in range(2)]
        facts = gg.run(views)
        control = [g.graph.run(v) for g, v in zip(gg.member_graphs, views)]
        expected = sum(cast(NumericFact, f).value for facts in control for f in facts.values())
        group_key = next(k for k in facts if k.name == "dollar_strength")
        assert cast(NumericFact, facts[group_key]).value == pytest.approx(expected)

    def test_run_requires_one_view_per_member(self) -> None:
        gg = _template().instantiate_group("majors", [_instrument("EURUSD"), _instrument("GBPUSD")])
        with pytest.raises(ValueError, match="one view per group member"):
            gg.run([MarketView(_store(), cursor=60, window_size=50)])
