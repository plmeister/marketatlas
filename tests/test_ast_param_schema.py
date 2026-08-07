from __future__ import annotations

from typing import Any

import pytest
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.analyzers.swing_structure import SwingStructureAnalyzer
from marketatlas.analysis.ast.expressions import Choice, wrap
from marketatlas.analysis.ast.models import Analysis, Definition, Parameter, Provider
from marketatlas.analysis.ast.param_schema import (
    ParamSpec,
    derive_param_schema,
    format_type,
    type_compatible,
)
from marketatlas.analysis.ast.pipeline import (
    CompilationError,
    ParamValidationPass,
    Pipeline,
    RegistryResolutionPass,
    ValidationPass,
)
from marketatlas.analysis.ast.registry import ProviderRegistry, create_default_registry
from marketatlas.strategy.risk import RiskEngine


class _Opaque:
    pass


class _RequiresValue:
    def __init__(self, period: int, name: str = "x") -> None:
        pass


class TestDeriveParamSchema:
    def test_ema_schema(self) -> None:
        schema = {s.name: s for s in derive_param_schema(EMAAnalyzer)}
        assert schema["period"] == ParamSpec(name="period", required=False, expected_type=int)
        assert set(schema) == {"period"}

    def test_swing_schema(self) -> None:
        schema = {s.name: s for s in derive_param_schema(SwingStructureAnalyzer)}
        assert schema["window"] == ParamSpec(name="window", required=False, expected_type=int)
        assert schema["swing_key"].expected_type is str
        assert "kwargs" not in schema

    def test_risk_schema_from_future_annotations(self) -> None:
        schema = {s.name: s for s in derive_param_schema(RiskEngine)}
        assert schema["risk_pct"].expected_type is float
        assert schema["max_hold_days"].expected_type is int
        assert schema["avoid_srxing"].expected_type is bool
        assert all(not s.required for s in schema.values())

    def test_required_param_detected(self) -> None:
        schema = {s.name: s for s in derive_param_schema(_RequiresValue)}
        assert schema["period"].required is True
        assert schema["period"].expected_type is int
        assert schema["name"].required is False
        assert schema["name"].expected_type is str

    def test_opaque_class_empty_schema(self) -> None:
        assert derive_param_schema(_Opaque) == ()

    def test_unannotated_param_accepts_any(self) -> None:
        class _Mixed:
            def __init__(self, untyped, typed: int = 1) -> None:
                pass

        schema = {s.name: s for s in derive_param_schema(_Mixed)}
        assert schema["untyped"].expected_type is None
        assert schema["typed"].expected_type is int


class TestTypeCompatible:
    def test_int(self) -> None:
        assert type_compatible(20, int)
        assert not type_compatible("20", int)
        assert not type_compatible(20.0, int)

    def test_float_numeric_widening(self) -> None:
        assert type_compatible(1.5, float)
        assert type_compatible(2, float)
        assert not type_compatible("2", float)
        assert not type_compatible(True, float)

    def test_bool_is_int(self) -> None:
        assert type_compatible(True, int)

    def test_str(self) -> None:
        assert type_compatible("swing", str)
        assert not type_compatible(5, str)

    def test_union(self) -> None:
        expected: object = int | None
        assert type_compatible(5, expected)
        assert type_compatible(None, expected)
        assert not type_compatible("x", expected)

    def test_any_and_none_accept_all(self) -> None:
        from typing import Any

        assert type_compatible("anything", Any)
        assert type_compatible("anything", None)
        assert type_compatible([1, 2], None)

    def test_generic_origin(self) -> None:
        expected: object = list[float]
        assert type_compatible([1.5], expected)
        assert not type_compatible("nope", expected)


class TestFormatType:
    def test_simple(self) -> None:
        assert format_type(int) == "int"
        assert format_type(None) == "any"

    def test_union(self) -> None:
        assert format_type(int | None) == "int or NoneType"


class TestRegistryParamSchema:
    def test_register_derives_schema(self) -> None:
        r = ProviderRegistry()
        r.register("compute_ema", EMAAnalyzer)
        schema = r.param_schema("compute_ema")
        assert schema is not None
        assert schema[0].name == "period"
        assert r.param_schema("EMAAnalyzer") == schema

    def test_manual_schema(self) -> None:
        r = ProviderRegistry()
        r.register_param_schema("cap", (ParamSpec(name="x", required=True, expected_type=int),))
        schema = r.param_schema("cap")
        assert schema is not None
        assert schema[0].name == "x"

    def test_unknown_key_none(self) -> None:
        r = ProviderRegistry()
        assert r.param_schema("nope") is None

    def test_decorator_and_class_registration(self) -> None:
        r = ProviderRegistry()
        r.register("ema", EMAAnalyzer)
        assert r.param_schema("ema") is not None


class TestDefaultRegistrySchemas:
    def test_builtin_schemas_present(self) -> None:
        r = create_default_registry()
        assert {s.name for s in r.param_schema("ema") or ()} == {"period"}
        assert {s.name for s in r.param_schema("atr") or ()} == {"period"}
        assert "window" in {s.name for s in r.param_schema("swingstructure") or ()}
        assert "level_tolerance_atr" in {s.name for s in r.param_schema("sr") or ()}
        risk = {s.name for s in r.param_schema("manage_risk") or ()}
        assert {"risk_pct", "min_rr", "max_rr"} <= risk


def _ema_analysis(**params: object) -> Analysis:
    provider = Provider(name="ema", capability="ema", category="analyzer", impl="EMAAnalyzer")
    return Analysis(
        name="t",
        version="1.0",
        definitions=(
            Definition(
                name="ema",
                provider="ema",
                parameters=tuple(Parameter(name=k, value=wrap(v)) for k, v in params.items()),
            ),
        ),
        providers=(provider,),
    )


def _stage1(analysis: Analysis, registry: ProviderRegistry | None = None) -> Analysis:
    registry = registry or create_default_registry()
    pipeline = (
        Pipeline()
        .add_pass(ValidationPass())
        .add_pass(RegistryResolutionPass(registry))
        .add_pass(ParamValidationPass(registry))
    )
    return pipeline.run_to_ast(analysis)


class TestParamValidationPass:
    def test_valid_params_pass(self) -> None:
        _stage1(_ema_analysis(period=20))

    def test_valid_choice_pass(self) -> None:
        a = _stage1(_ema_analysis(period=Choice([20, 50])))
        assert a.definitions[0].parameters[0].value is not None

    def test_unknown_param(self) -> None:
        with pytest.raises(CompilationError, match="Unknown parameter 'bogus'.*'ema'"):
            _stage1(_ema_analysis(bogus=20))

    def test_wrong_type(self) -> None:
        with pytest.raises(CompilationError, match="'period'.*'ema'.*expects int"):
            _stage1(_ema_analysis(period="abc"))

    def test_choice_bad_leaf_type(self) -> None:
        with pytest.raises(CompilationError, match="expects int"):
            _stage1(_ema_analysis(period=Choice([20, "x"])))

    def test_provider_without_schema_skipped(self) -> None:
        from marketatlas.analysis.ast.builder import AnalysisBuilder

        a = (
            AnalysisBuilder("t", "1.0")
            .define("ema20", "analyzer", "CustomEMA")
            .with_param("period", 20)
            .with_param("bogus", 1)
            .build()
        )
        _stage1(a)


class TestMissingRequiredParam:
    def test_missing_required(self) -> None:
        r = ProviderRegistry()
        r.register("custom", _RequiresValue)
        provider = Provider(name="custom", capability="custom", category="analyzer", impl="X")
        a = Analysis(
            name="t",
            version="1.0",
            definitions=(Definition(name="d", provider="custom"),),
            providers=(provider,),
        )
        with pytest.raises(CompilationError, match="Missing required parameter 'period'.*'d'"):
            _stage1(a, registry=r)

    def test_required_present_passes(self) -> None:
        r = ProviderRegistry()
        r.register("custom", _RequiresValue)
        provider = Provider(name="custom", capability="custom", category="analyzer", impl="X")
        a = Analysis(
            name="t",
            version="1.0",
            definitions=(
                Definition(
                    name="d",
                    provider="custom",
                    parameters=(Parameter(name="period", value=wrap(5)),),
                ),
            ),
            providers=(provider,),
        )
        _stage1(a, registry=r)

    def test_wrong_type_optional_param(self) -> None:
        r = ProviderRegistry()
        r.register("custom", _RequiresValue)
        provider = Provider(name="custom", capability="custom", category="analyzer", impl="X")
        a = Analysis(
            name="t",
            version="1.0",
            definitions=(
                Definition(
                    name="d",
                    provider="custom",
                    parameters=(
                        Parameter(name="period", value=wrap(5)),
                        Parameter(name="name", value=wrap(3)),
                    ),
                ),
            ),
            providers=(provider,),
        )
        with pytest.raises(CompilationError, match="'name'.*expects str"):
            _stage1(a, registry=r)


class TestAnyAnnotation:
    def test_any_param_accepts_all(self) -> None:
        class _Lenient:
            def __init__(self, mode: Any = "x") -> None:
                pass

        r = ProviderRegistry()
        r.register("lenient", _Lenient)
        provider = Provider(name="lenient", capability="lenient", category="analyzer", impl="X")
        for value in (5, "str", [1, 2], None):
            a = Analysis(
                name="t",
                version="1.0",
                definitions=(
                    Definition(
                        name="d",
                        provider="lenient",
                        parameters=(Parameter(name="mode", value=wrap(value)),),
                    ),
                ),
                providers=(provider,),
            )
            _stage1(a, registry=r)
