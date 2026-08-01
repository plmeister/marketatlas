"""Backlog 054: compiler golden tests — choice expansion.

Golden tests with explicit inline expected outputs (no file snapshots)
pinning choice expansion and concrete validation behaviour (backlogs
048/050/051). Every case runs through ``Pipeline.expand`` — stages 1-3:
validation, registry resolution, provider param validation, template
expansion, concrete validation — against the default registry, and
asserts the full expected ``Analysis`` via canonical equality and
``to_dict`` comparison.

Stage 4 (graph generation) is deliberately excluded; graph snapshots live
in backlog 046. ``expand`` (the raw pass) is covered by
``test_ast_expand.py``; this suite pins the end-to-end pipeline output.
"""

import pytest
from marketatlas.analysis.ast.constructors import ATR, EMA, SwingStructure, build_analysis
from marketatlas.analysis.ast.expressions import Choice, LiteralExpression, wrap
from marketatlas.analysis.ast.models import (
    Analysis,
    Definition,
    Parameter,
    Provider,
)
from marketatlas.analysis.ast.pipeline import (
    CompilationError,
    ConcreteValidationPass,
    ParamValidationPass,
    Pipeline,
    RegistryResolutionPass,
    ValidationPass,
)
from marketatlas.analysis.ast.registry import create_default_registry
from marketatlas.analysis.ast.serialization import to_dict

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
_ATR_PROVIDER = Provider(
    name="atr",
    capability="atr",
    category="analyzer",
    impl="ATRAnalyzer",
    default_params=(Parameter(name="period", value=LiteralExpression(14)),),
)
_ATR_RESOLVED = Provider(
    name="ATRAnalyzer",
    capability="atr",
    category="analyzer",
    impl="ATRAnalyzer",
    default_params=(Parameter(name="period", value=LiteralExpression(14)),),
)
_SWING_PROVIDER = Provider(
    name="swingstructure",
    capability="swingstructure",
    category="analyzer",
    impl="SwingStructureAnalyzer",
    default_params=(Parameter(name="lookback", value=LiteralExpression(50)),),
)
_SWING_RESOLVED = Provider(
    name="SwingStructureAnalyzer",
    capability="swingstructure",
    category="analyzer",
    impl="SwingStructureAnalyzer",
    default_params=(Parameter(name="lookback", value=LiteralExpression(50)),),
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


def _param(name: str, value: object) -> Parameter:
    return Parameter(name=name, value=wrap(value))


def _variant(*definitions: Definition, providers: tuple[Provider, ...]) -> Analysis:
    return Analysis(name="golden", version="1.0", definitions=definitions, providers=providers)


def _ema_def(name: str, period: int) -> Definition:
    return _def(name, "EMAAnalyzer", _param("period", period))


def _atr_def(name: str, period: int) -> Definition:
    return _def(name, "ATRAnalyzer", _param("period", period))


def _golden_single(period: int) -> Analysis:
    return _variant(_ema_def("ema", period), providers=(_EMA_PROVIDER, _EMA_RESOLVED))


class TestGoldenSingleChoice:
    def test_two_concrete_asts_full_equality(self) -> None:
        template = build_analysis("golden", [EMA(name="ema", period=Choice([50, 100]))])
        expanded = _pipeline().expand(template)
        assert expanded == (_golden_single(50), _golden_single(100))

    def test_serialized_golden(self) -> None:
        template = build_analysis("golden", [EMA(name="ema", period=Choice([50, 100]))])
        expanded = _pipeline().expand(template)
        assert to_dict(expanded[0]) == {
            "name": "golden",
            "version": "1.0",
            "definitions": [
                {
                    "name": "ema",
                    "provider": "EMAAnalyzer",
                    "parameters": [{"name": "period", "value": 50}],
                }
            ],
            "providers": [
                {
                    "name": "ema",
                    "capability": "ema",
                    "category": "analyzer",
                    "impl": "EMAAnalyzer",
                    "default_params": [{"name": "period", "value": 20}],
                },
                {
                    "name": "EMAAnalyzer",
                    "capability": "ema",
                    "category": "analyzer",
                    "impl": "EMAAnalyzer",
                    "default_params": [{"name": "period", "value": 20}],
                },
            ],
        }
        assert to_dict(expanded[1])["definitions"][0]["parameters"][0]["value"] == 100  # type: ignore[index]

    def test_definition_order_preserved(self) -> None:
        template = build_analysis("golden", [EMA(name="ema", period=Choice([50, 100]))])
        expanded = _pipeline().expand(template)
        assert [d.name for d in expanded[0].definitions] == ["ema"]


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
                    lookback=Choice([50, 100]),
                    min_swing_atr=Choice([0.3, 0.5]),
                )
            ],
        )
        expanded = _pipeline().expand(template)
        expected_pairs = [(50, 0.3), (50, 0.5), (100, 0.3), (100, 0.5)]
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
                    _param("lookback", lookback),
                    _param("min_swing_atr", min_swing_atr),
                ),
                providers=(_SWING_PROVIDER, _SWING_RESOLVED),
            )
            for lookback, min_swing_atr in expected_pairs
        )

    def test_across_definitions_cartesian_product(self) -> None:
        template = build_analysis(
            "golden",
            [
                EMA(name="ema", period=Choice([50, 100])),
                ATR(name="atr", period=Choice([14, 21])),
            ],
        )
        expanded = _pipeline().expand(template)
        assert len(expanded) == 4
        providers = (_EMA_PROVIDER, _ATR_PROVIDER, _EMA_RESOLVED, _ATR_RESOLVED)
        assert expanded == tuple(
            _variant(_ema_def("ema", e), _atr_def("atr", a), providers=providers)
            for e, a in [(50, 14), (50, 21), (100, 14), (100, 21)]
        )


class TestGoldenListLiteral:
    def test_raw_list_stays_single_ast(self) -> None:
        template = Analysis(
            name="golden",
            version="1.0",
            definitions=(_def("feeds", "price", _param("periods", [50, 100])),),
            providers=(
                Provider(
                    name="price",
                    capability="price",
                    category="analyzer",
                    impl="PriceSource",
                ),
            ),
        )
        expanded = _pipeline().expand(template)
        assert len(expanded) == 1
        assert expanded == (template,)

    def test_list_literal_next_to_choice(self) -> None:
        template = Analysis(
            name="golden",
            version="1.0",
            definitions=(
                _def(
                    "feeds",
                    "price",
                    _param("span", Choice([1, 2])),
                    _param("periods", [5, 10]),
                ),
            ),
            providers=(
                Provider(
                    name="price",
                    capability="price",
                    category="analyzer",
                    impl="PriceSource",
                ),
            ),
        )
        expanded = _pipeline().expand(template)
        assert len(expanded) == 2
        for i, o in enumerate(expanded):
            assert o.definitions[0].parameters[0].value == i + 1
            assert o.definitions[0].parameters[1].value == [5, 10]


class TestGoldenEmptyChoice:
    def test_error_names_definition_and_param(self) -> None:
        template = build_analysis("golden", [EMA(name="ema", period=Choice([]))])
        with pytest.raises(CompilationError, match="'period'.*'ema'"):
            _pipeline().expand(template)

    def test_error_alongside_valid_choice(self) -> None:
        template = build_analysis(
            "golden",
            [
                EMA(name="ema", period=Choice([50, 100])),
                ATR(name="atr", period=Choice([])),
            ],
        )
        with pytest.raises(CompilationError, match="'period'.*'atr'"):
            _pipeline().expand(template)


class TestGoldenConvergentDuplicates:
    def test_stage3_reports_duplicate_definition(self) -> None:
        a = Analysis(
            name="bad",
            version="1.0",
            definitions=(
                _def("dup", "ema", _param("period", 50)),
                _def("dup", "ema", _param("period", 50)),
            ),
            providers=(_EMA_PROVIDER,),
        )
        with pytest.raises(CompilationError, match="Duplicate definition 'dup'"):
            ConcreteValidationPass().run(a)

    def test_stage1_catches_duplicates_before_expansion(self) -> None:
        template = Analysis(
            name="bad",
            version="1.0",
            definitions=(
                _def("dup", "ema", _param("period", Choice([50, 100]))),
                _def("dup", "ema", _param("period", Choice([100, 50]))),
            ),
            providers=(_EMA_PROVIDER,),
        )
        with pytest.raises(CompilationError, match="Duplicate definition name"):
            _pipeline().expand(template)


class TestGoldenDeterminism:
    def test_same_input_same_output(self) -> None:
        template = build_analysis(
            "golden",
            [
                EMA(name="ema", period=Choice([50, 100])),
                ATR(name="atr", period=Choice([14, 21])),
            ],
        )
        assert _pipeline().expand(template) == _pipeline().expand(template)
