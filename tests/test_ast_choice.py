import dataclasses

import pytest

from marketatlas.analysis.ast.builder import AnalysisBuilder
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.expressions import (
    Choice,
    ChoiceExpression,
    Expression,
    LiteralExpression,
    wrap,
)
from marketatlas.analysis.ast.models import Analysis, Parameter
from marketatlas.analysis.ast.pipeline import CompilationError
from marketatlas.analysis.ast.serialization import from_dict, from_json, to_dict, to_json


def _ema_analysis(period: object) -> Analysis:
    return (
        AnalysisBuilder("test", "1.0.0")
        .define_provider("EMAAnalyzer", "compute_ema", "analyzer", "EMAAnalyzer")
        .define("ema20", "EMAAnalyzer")
        .with_param("period", period)
        .build()
    )


class TestChoiceFactory:
    def test_wraps_literal_members(self) -> None:
        c = Choice([50, 100])
        assert isinstance(c, ChoiceExpression)
        assert c == ChoiceExpression(
            (LiteralExpression(50), LiteralExpression(100))
        )

    def test_passes_expression_members_through(self) -> None:
        inner = Choice([1, 2])
        c = Choice([inner, 3])
        assert c.values[0] is inner
        assert c.values[1] == LiteralExpression(3)

    def test_accepts_any_iterable(self) -> None:
        c = Choice((50, 100))
        assert len(c.values) == 2
        assert c == Choice([50, 100])

    def test_empty_choice_constructible(self) -> None:
        c = Choice([])
        assert isinstance(c, ChoiceExpression)
        assert c.values == ()

    def test_nested_choice_is_expression(self) -> None:
        assert isinstance(Choice([1, 2]), ChoiceExpression)


class TestChoiceExpressionSemantics:
    def test_equality(self) -> None:
        assert Choice([50, 100]) == Choice([50, 100])
        assert Choice([50, 100]) != Choice([50, 200])
        assert Choice([50, 100]) != Choice([100, 50])

    def test_not_equal_to_raw_list(self) -> None:
        assert Choice([50, 100]) != [50, 100]
        assert [50, 100] != Choice([50, 100])

    def test_nested_choice_equality(self) -> None:
        assert Choice([Choice([1, 2]), 3]) == Choice([Choice([1, 2]), 3])
        assert Choice([Choice([1, 2]), 3]) != Choice([Choice([2, 1]), 3])

    def test_repr(self) -> None:
        r = repr(Choice([50, 100]))
        assert r.startswith("ChoiceExpression(")
        assert "LiteralExpression(50)" in r
        assert "LiteralExpression(100)" in r

    def test_is_expression_instance(self) -> None:
        assert isinstance(Choice([50]), Expression)


class TestSerialization:
    def test_structured_form_distinct_from_list_literal(self) -> None:
        a = _ema_analysis(Choice([50, 100]))
        d = to_dict(a)
        params = d["definitions"][0]["parameters"]  # type: ignore[index]
        assert params == [
            {"name": "period", "value": {"expr": "choice", "values": [50, 100]}}
        ]

    def test_list_literal_stays_raw_list(self) -> None:
        a = _ema_analysis([50, 100])
        d = to_dict(a)
        params = d["definitions"][0]["parameters"]  # type: ignore[index]
        assert params[0]["value"] == [50, 100]

    def test_round_trip(self) -> None:
        a = _ema_analysis(Choice([50, 100]))
        restored = from_dict(to_dict(a))
        assert restored == a
        value = restored.definitions[0].parameters[0].value
        assert isinstance(value, ChoiceExpression)
        assert value == Choice([50, 100])

    def test_nested_round_trip(self) -> None:
        a = _ema_analysis(Choice([Choice([1, 2]), 3]))
        restored = from_dict(to_dict(a))
        assert restored == a
        value = restored.definitions[0].parameters[0].value
        assert isinstance(value, ChoiceExpression)
        assert value.values[0] == Choice([1, 2])

    def test_json_round_trip(self) -> None:
        a = _ema_analysis(Choice([50, 100]))
        restored = from_json(to_json(a))
        assert restored == a
        assert restored.definitions[0].parameters[0].value == Choice([50, 100])

    def test_literal_vs_choice_do_not_round_trip_equal(self) -> None:
        list_lit = from_dict(to_dict(_ema_analysis([50, 100])))
        choice = from_dict(to_dict(_ema_analysis(Choice([50, 100]))))
        assert list_lit != choice
        assert not isinstance(list_lit.definitions[0].parameters[0].value, ChoiceExpression)
        assert list_lit.definitions[0].parameters[0].value == [50, 100]
        assert isinstance(choice.definitions[0].parameters[0].value, ChoiceExpression)


class TestBuilder:
    def test_with_param_choice_keeps_expression(self) -> None:
        a = _ema_analysis(Choice([50, 100]))
        value = a.definitions[0].parameters[0].value
        assert isinstance(value, ChoiceExpression)
        assert value == Choice([50, 100])

    def test_with_param_raw_list_is_literal(self) -> None:
        a = _ema_analysis([50, 100])
        value = a.definitions[0].parameters[0].value
        assert isinstance(value, LiteralExpression)
        assert value == [50, 100]

    def test_choice_through_wrap(self) -> None:
        c = Choice([1, 2])
        assert wrap(c) is c


class TestDefensiveCompileError:
    def test_choice_reaches_config_generation_raises(self) -> None:
        a = _ema_analysis(Choice([50, 100]))
        with pytest.raises(CompilationError, match="'period'.*definition 'ema20'"):
            ASTCompiler.to_config(a)

    def test_choice_in_provider_default_params_raises_after_resolution(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define_provider("EMAAnalyzer", "compute_ema", "analyzer", "EMAAnalyzer")
            .define("ema", "EMAAnalyzer")
            .build()
        )
        p = Parameter(name="period", value=Choice([50, 100]))
        a = _replace_default_param(a, "EMAAnalyzer", p)
        from marketatlas.analysis.ast.pipeline import (
            Pipeline,
            RegistryResolutionPass,
        )
        from marketatlas.analysis.ast.registry import create_default_registry

        resolved = Pipeline().add_pass(
            RegistryResolutionPass(create_default_registry())
        ).run_to_ast(a)
        with pytest.raises(CompilationError, match="'period'.*definition 'ema'"):
            ASTCompiler.to_config(resolved)

    def test_nested_choice_reaches_config_generation_raises(self) -> None:
        a = _ema_analysis(Choice([Choice([1, 2]), 3]))
        with pytest.raises(CompilationError, match="'period'.*definition 'ema20'"):
            ASTCompiler.to_config(a)


def _replace_default_param(a: Analysis, provider_name: str, param: Parameter) -> Analysis:
    providers = tuple(
        (
            dataclasses.replace(p, default_params=(param,))
            if p.name == provider_name
            else p
        )
        for p in a.providers
    )
    return Analysis(
        name=a.name,
        version=a.version,
        definitions=a.definitions,
        providers=providers,
    )
