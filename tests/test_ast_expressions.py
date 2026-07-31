import pytest
from marketatlas.analysis.ast.builder import AnalysisBuilder
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.expressions import Expression, LiteralExpression, unwrap, wrap
from marketatlas.analysis.ast.models import Analysis, Definition, Parameter, Provider
from marketatlas.analysis.ast.pipeline import CompilationError
from marketatlas.analysis.ast.registry import ProviderRegistry
from marketatlas.analysis.ast.serialization import from_dict, to_dict, to_json


class _OtherExpression(Expression):
    pass


def _ema_analysis(period: object) -> Analysis:
    return (
        AnalysisBuilder("test", "1.0.0")
        .define_provider("EMAAnalyzer", "compute_ema", "analyzer", "EMAAnalyzer")
        .define("ema20", "EMAAnalyzer")
        .with_param("period", period)
        .build()
    )


class TestLiteralExpression:
    def test_value_attribute(self) -> None:
        assert LiteralExpression(20).value == 20
        assert LiteralExpression("close").value == "close"
        assert LiteralExpression([1, 2]).value == [1, 2]

    def test_equality_with_itself(self) -> None:
        assert LiteralExpression(20) == LiteralExpression(20)
        assert LiteralExpression("x") == LiteralExpression("x")

    def test_equality_with_raw_value(self) -> None:
        assert LiteralExpression(20) == 20
        assert 20 == LiteralExpression(20)

    def test_equality_different_value(self) -> None:
        assert LiteralExpression(20) != LiteralExpression(50)
        assert LiteralExpression(20) != 50

    def test_equality_with_other_expression(self) -> None:
        assert LiteralExpression(1) != _OtherExpression()

    def test_repr(self) -> None:
        assert repr(LiteralExpression(20)) == "LiteralExpression(20)"
        assert repr(LiteralExpression("close")) == "LiteralExpression('close')"


class TestWrapUnwrap:
    def test_wrap_raw_value(self) -> None:
        assert wrap(20) == LiteralExpression(20)
        assert wrap("x") == LiteralExpression("x")

    def test_wrap_expression_passthrough(self) -> None:
        e = LiteralExpression(20)
        assert wrap(e) is e
        other = _OtherExpression()
        assert wrap(other) is other

    def test_unwrap_literal(self) -> None:
        assert unwrap(LiteralExpression(20)) == 20

    def test_unwrap_raw_passthrough(self) -> None:
        assert unwrap(20) == 20

    def test_unwrap_non_literal_raises(self) -> None:
        with pytest.raises(ValueError, match="non-literal"):
            unwrap(_OtherExpression())


class TestBuilderWrapping:
    def test_with_param_wraps_raw_value(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define_provider("EMAAnalyzer", "compute_ema", "analyzer", "EMAAnalyzer")
            .define("ema20", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        param = a.definitions[0].parameters[0]
        assert isinstance(param.value, LiteralExpression)
        assert param.value == 20

    def test_with_param_accepts_expression(self) -> None:
        expr = LiteralExpression(50)
        a = (
            AnalysisBuilder("test", "1.0")
            .define_provider("EMAAnalyzer", "compute_ema", "analyzer", "EMAAnalyzer")
            .define("ema20", "EMAAnalyzer")
            .with_param("period", expr)
            .build()
        )
        assert a.definitions[0].parameters[0].value is expr

    def test_define_provider_wraps_default_params(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define_provider("EMAAnalyzer", "compute_ema", "analyzer", "EMAAnalyzer", period=20)
            .build()
        )
        param = a.providers[0].default_params[0]
        assert isinstance(param.value, LiteralExpression)
        assert param.value == 20


class TestRegistryWrapping:
    def test_register_wraps_default_params(self) -> None:
        r = ProviderRegistry()
        r.register("compute_ema", object, default_params={"period": 20})  # type: ignore[arg-type]
        provider = r.resolve("compute_ema")
        assert isinstance(provider.default_params[0].value, LiteralExpression)
        assert provider.default_params[0].value == 20

    def test_direct_provider_params_unchanged(self) -> None:
        p = Provider(
            name="P",
            capability="c",
            category="analyzer",
            impl="P",
            default_params=(Parameter(name="period", value=20),),
        )
        assert p.default_params[0].value == 20


class TestSerialization:
    def test_literal_serializes_as_raw_value(self) -> None:
        a = _ema_analysis(20)
        d = to_dict(a)
        assert d["definitions"][0]["parameters"] == [{"name": "period", "value": 20}]

    def test_json_round_trip(self) -> None:
        a = _ema_analysis(20)
        restored = from_dict(to_dict(a))
        assert restored == a
        assert restored.definitions[0].parameters[0].value == 20

    def test_list_value_stays_raw_list(self) -> None:
        a = _ema_analysis([50, 100])
        d = to_dict(a)
        assert d["definitions"][0]["parameters"][0]["value"] == [50, 100]
        restored = from_dict(to_dict(a))
        assert restored.definitions[0].parameters[0].value == [50, 100]

    def test_non_literal_expression_serialization_raises(self) -> None:
        a = Analysis(
            name="t",
            version="1.0",
            definitions=(
                Definition(
                    name="d",
                    provider="P",
                    parameters=(Parameter(name="p", value=_OtherExpression()),),
                ),
            ),
        )
        with pytest.raises(ValueError, match="Unsupported expression node in parameter 'p'"):
            to_json(a)


class TestPipeline:
    def test_compiles_literal_only(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define_provider("EMAAnalyzer", "compute_ema", "analyzer", "EMAAnalyzer")
            .define("ema20", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        config = ASTCompiler.to_config(a)
        assert config.analyzers[0].params == {"period": 20}

    def test_non_literal_expression_raises_compilation_error(self) -> None:
        a = Analysis(
            name="t",
            version="1.0",
            definitions=(
                Definition(
                    name="ema20",
                    provider="EMAAnalyzer",
                    parameters=(Parameter(name="period", value=_OtherExpression()),),
                ),
            ),
            providers=(
                Provider(
                    name="EMAAnalyzer",
                    capability="compute_ema",
                    category="analyzer",
                    impl="EMAAnalyzer",
                ),
            ),
        )
        with pytest.raises(CompilationError, match="parameter 'period'.*definition 'ema20'"):
            ASTCompiler.to_config(a)
