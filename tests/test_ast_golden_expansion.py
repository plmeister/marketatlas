"""Backlog 054: compiler golden tests — choice expansion.

Three representative cases pinning choice expansion behaviour:
single choice, nested choice, and cross-definition cartesian product.
"""

import pytest
from marketatlas.analysis.ast.constructors import EMA, SwingStructure, build_analysis
from marketatlas.analysis.ast.expressions import Choice
from marketatlas.analysis.ast.models import (
    Analysis,
    Definition,
    Parameter,
    Provider,
)
from marketatlas.analysis.ast.pipeline import (
    Pipeline,
    RegistryResolutionPass,
    ValidationPass,
    ParamValidationPass,
)
from marketatlas.analysis.ast.registry import create_default_registry
from marketatlas.analysis.ast.expressions import LiteralExpression

_EMA_PROVIDER = Provider(
    name="ema",
    capability="ema",
    category="analyzer",
    impl="EMAAnalyzer",
    default_params=(Parameter(name="period", value=LiteralExpression(20)),),
)
_EMA_RESOLVED = Provider(
    name="EMAAnalyzer",
    capability="ema",
    category="analyzer",
    impl="EMAAnalyzer",
    default_params=(Parameter(name="period", value=LiteralExpression(20)),),
)
_SWING_PROVIDER = Provider(
    name="swingstructure",
    capability="swingstructure",
    category="analyzer",
    impl="SwingStructureAnalyzer",
    default_params=(Parameter(name="window", value=LiteralExpression(50)),),
)
_SWING_RESOLVED = Provider(
    name="SwingStructureAnalyzer",
    capability="swingstructure",
    category="analyzer",
    impl="SwingStructureAnalyzer",
    default_params=(Parameter(name="window", value=LiteralExpression(50)),),
)


def _pipeline() -> Pipeline:
    registry = create_default_registry()
    return (
        Pipeline()
        .add_pass(ValidationPass())
        .add_pass(RegistryResolutionPass(registry))
        .add_pass(ParamValidationPass(registry))
    )


def _def(name: str, provider: str, *params: Parameter) -> Definition:
    return Definition(name=name, provider=provider, parameters=params)


def _variant(*definitions: Definition, providers: tuple[Provider, ...]) -> Analysis:
    return Analysis(name="golden", version="1.0", definitions=definitions, providers=providers)


def _ema_def(name: str, period: int) -> Definition:
    from marketatlas.analysis.ast.expressions import wrap
    return _def(name, "EMAAnalyzer", Parameter(name="period", value=wrap(period)))


def _golden_single(period: int) -> Analysis:
    return _variant(_ema_def("ema", period), providers=(_EMA_PROVIDER, _EMA_RESOLVED))


class TestGoldenSingleChoice:
    def test_two_concrete_asts_full_equality(self) -> None:
        template = build_analysis("golden", [EMA(name="ema", period=Choice([50, 100]))])
        expanded = _pipeline().expand(template)
        assert expanded == (_golden_single(50), _golden_single(100))


class TestGoldenNestedChoice:
    def test_nested_flattened_in_order(self) -> None:
        template = build_analysis("golden", [EMA(name="ema", period=Choice([Choice([1, 2]), 3]))])
        expanded = _pipeline().expand(template)
        assert expanded == tuple(_golden_single(p) for p in (1, 2, 3))


class TestGoldenMultipleChoices:
    def test_same_definition_cartesian_product(self) -> None:
        template = build_analysis(
            "golden",
            [
                SwingStructure(
                    name="sw",
                    window=Choice([50, 100]),
                    swing_key=Choice(["swing", "other"]),
                )
            ],
        )
        expanded = _pipeline().expand(template)
        expected_pairs = [(50, "swing"), (50, "other"), (100, "swing"), (100, "other")]
        assert [
            (
                o.definitions[0].parameters[0].value,
                o.definitions[0].parameters[1].value,
            )
            for o in expanded
        ] == expected_pairs
        assert expanded == tuple(
            _variant(
                _def(
                    "sw",
                    "SwingStructureAnalyzer",
                    Parameter(name="window", value=LiteralExpression(window)),
                    Parameter(name="swing_key", value=LiteralExpression(swing_key)),
                ),
                providers=(_SWING_PROVIDER, _SWING_RESOLVED),
            )
            for window, swing_key in expected_pairs
        )
