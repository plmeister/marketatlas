import pytest

from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.constructors import (
    ATR,
    EMA,
    SR,
    DetectPullback,
    GenerateSignal,
    ManageRisk,
    ProviderConstructionError,
    Swings,
    SwingStructure,
    Trend,
    build_analysis,
    construct,
)
from marketatlas.analysis.ast.expressions import Choice, ChoiceExpression, LiteralExpression
from marketatlas.analysis.ast.models import Analysis, Definition, Parameter, Provider
from marketatlas.analysis.ast.registry import ProviderRegistry
from marketatlas.analysis.ast.serialization import from_json, to_json


class TestBasicConstruction:
    def test_ema_period_literal(self) -> None:
        d = EMA(period=20)
        assert isinstance(d, Definition)
        assert d.name == "ema"
        assert d.provider == "ema"
        assert d.parameters == (Parameter(name="period", value=LiteralExpression(20)),)

    def test_ema_choice_param(self) -> None:
        d = EMA(period=Choice([50, 100]))
        assert d.parameters == (Parameter(name="period", value=Choice([50, 100])),)
        assert isinstance(d.parameters[0].value, ChoiceExpression)

    def test_choice_wraps_raw_and_passes_expressions(self) -> None:
        c = Choice([1, LiteralExpression(2), Choice([3])])
        assert c.values == (
            LiteralExpression(1),
            LiteralExpression(2),
            ChoiceExpression((LiteralExpression(3),)),
        )

    def test_explicit_name(self) -> None:
        assert EMA("ema_fast", period=20).name == "ema_fast"
        assert EMA(name="ema_fast", period=20).name == "ema_fast"

    def test_default_params_applied(self) -> None:
        d = EMA()
        assert d.parameters == (Parameter(name="period", value=LiteralExpression(20)),)

    def test_explicit_kwarg_overrides_default(self) -> None:
        d = EMA(period=50)
        assert d.parameters == (Parameter(name="period", value=LiteralExpression(50)),)

    def test_atr_defaults(self) -> None:
        d = ATR()
        assert d.provider == "atr"
        assert d.parameters == (Parameter(name="period", value=LiteralExpression(14)),)

    def test_trend_registered_defaults_absent(self) -> None:
        assert Trend().parameters == ()
        d = Trend(fast_key="ema_10")
        assert d.parameters == (Parameter(name="fast_key", value=LiteralExpression("ema_10")),)

    def test_atr_explicit_overrides_default(self) -> None:
        assert ATR(period=21).parameters == (Parameter(name="period", value=LiteralExpression(21)),)

    def test_all_factories_produce_expected_capabilities(self) -> None:
        cases = {
            "swingstructure": SwingStructure(),
            "swings": Swings(),
            "sr": SR(),
            "detect_pullback": DetectPullback(),
            "generate_signal": GenerateSignal(),
            "manage_risk": ManageRisk(),
        }
        for capability, d in cases.items():
            assert d.provider == capability, capability
            assert d.name == capability


class TestConstructionErrors:
    def test_unknown_kwarg_names_provider(self) -> None:
        with pytest.raises(ProviderConstructionError, match="'bogus'") as exc:
            EMA(bogus=1)
        assert "ema" in str(exc.value)
        assert "period" in str(exc.value)

    def test_wrong_type_names_provider_and_expected(self) -> None:
        with pytest.raises(ProviderConstructionError, match="str") as exc:
            EMA(period="20")
        assert "int" in str(exc.value)
        assert "ema" in str(exc.value)

    def test_choice_leaf_wrong_type(self) -> None:
        with pytest.raises(ProviderConstructionError, match="str"):
            EMA(period=Choice([50, "bad"]))

    def test_int_widens_to_float(self) -> None:
        d = SR(level_tolerance_atr=1)
        assert d.parameters == (Parameter(name="level_tolerance_atr", value=LiteralExpression(1)),)

    def test_unknown_capability(self) -> None:
        with pytest.raises(ProviderConstructionError, match="No provider"):
            construct("no_such_capability")

    def test_missing_required_param(self) -> None:
        class RequiresAlpha:
            def __init__(self, alpha: float) -> None:
                self._alpha = alpha

        registry = ProviderRegistry()
        registry.register("custom", RequiresAlpha)
        with pytest.raises(ProviderConstructionError, match="'alpha'"):
            construct("custom", registry=registry)

        d = construct("custom", alpha=0.5, registry=registry)
        assert d.parameters == (Parameter(name="alpha", value=LiteralExpression(0.5)),)

    def test_opaque_provider_no_false_positive(self) -> None:
        class Opaque:
            def __init__(self, **kwargs: object) -> None:
                self._kwargs = kwargs

        registry = ProviderRegistry()
        registry.register("opaque", Opaque)
        d = construct("opaque", anything=42, registry=registry)
        assert d.parameters == (Parameter(name="anything", value=LiteralExpression(42)),)


class TestComposition:
    def test_build_analysis_populates_providers(self) -> None:
        a = build_analysis("demo", [EMA(period=20), ATR(period=14)])
        assert isinstance(a, Analysis)
        assert [d.name for d in a.definitions] == ["ema", "atr"]
        assert a.providers == (
            Provider(
                name="ema",
                capability="ema",
                category="analyzer",
                impl="EMAAnalyzer",
                default_params=(Parameter(name="period", value=LiteralExpression(20)),),
            ),
            Provider(
                name="atr",
                capability="atr",
                category="analyzer",
                impl="ATRAnalyzer",
                default_params=(Parameter(name="period", value=LiteralExpression(14)),),
            ),
        )

    def test_providers_deduplicated_by_name(self) -> None:
        a = build_analysis("demo", [EMA("a", period=20), EMA("b", period=50)])
        assert len(a.providers) == 1

    def test_duplicate_definition_names_raise(self) -> None:
        with pytest.raises(ValueError, match="Duplicate definition name: ema"):
            build_analysis("demo", [EMA(period=20), EMA(period=50)])

    def test_signal_and_risk_categories_kept(self) -> None:
        a = build_analysis("s", [GenerateSignal(), ManageRisk()])
        categories = {p.capability: p.category for p in a.providers}
        assert categories["generate_signal"] == "signal"
        assert categories["manage_risk"] == "risk"

    def test_serialization_round_trip(self) -> None:
        a = build_analysis("demo", [EMA(period=20), ATR(period=14), Trend()])
        restored = from_json(to_json(a))
        assert restored == a

    def test_manual_definition_passthrough(self) -> None:
        manual = Definition(name="x", provider="y")
        a = build_analysis("demo", [manual])
        assert a.providers == (Provider(name="y", capability="y", category="analyzer", impl="y"),)


class TestCompilation:
    def test_literal_only_compiles_single_graph(self) -> None:
        a = build_analysis(
            "demo",
            [EMA("ema20", period=20), EMA("ema50", period=50), ATR(period=14), Trend()],
        )
        graph = ASTCompiler.compile(a)
        names = [type(o).__name__ for o in graph.execution_order()]
        assert names == ["EMAAnalyzer", "EMAAnalyzer", "ATRAnalyzer", "TrendAnalyzer"]

    def test_choice_template_expands(self) -> None:
        a = build_analysis("t", [EMA(period=Choice([50, 100]))])
        variants = ASTCompiler.expand(a)
        assert len(variants) == 2
        assert variants[0].definitions[0].parameters[0].value == 50
        assert variants[1].definitions[0].parameters[0].value == 100

    def test_multi_choice_cartesian(self) -> None:
        a = build_analysis(
            "t",
            [EMA(period=Choice([10, 20])), ATR(period=Choice([7, 14]))],
        )
        variants = ASTCompiler.expand(a)
        assert len(variants) == 4
        combos = [
            (v.definitions[0].parameters[0].value, v.definitions[1].parameters[0].value)
            for v in variants
        ]
        assert combos == [(10, 7), (10, 14), (20, 7), (20, 14)]

    def test_choice_template_compile_requires_compile_all(self) -> None:
        a = build_analysis("t", [EMA(period=Choice([50, 100]))])
        with pytest.raises(Exception, match="compile_all"):
            ASTCompiler.compile(a)

    def test_choice_compiled_graph_params(self) -> None:
        a = build_analysis("t", [EMA(period=Choice([50, 100]))])
        graphs = ASTCompiler.compile_all(a)
        keys = [o.instance_key for g in graphs for o in g.execution_order()]
        assert keys == ["ema_50", "ema_100"]

    def test_compiled_graph_uses_ema_analyzer(self) -> None:
        a = build_analysis("t", [EMA(period=20)])
        graph = ASTCompiler.compile(a)
        assert isinstance(graph.execution_order()[0], EMAAnalyzer)
