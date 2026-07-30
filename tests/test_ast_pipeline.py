import pytest
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.ast.builder import AnalysisBuilder
from marketatlas.analysis.ast.models import Analysis, Definition, Parameter, Provider
from marketatlas.analysis.ast.pipeline import (
    CompilationError,
    DefinitionExpansionPass,
    GraphGenerationPass,
    Pipeline,
    RegistryResolutionPass,
    ValidationPass,
    _ast_to_config,
)
from marketatlas.analysis.ast.registry import ProviderRegistry, create_default_registry
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.strategy.config import AnalyzerConfig, StrategyConfig


def _p(**kw: object) -> Provider:
    return Provider(
        name=str(kw.get("name", "")),
        capability=str(kw.get("capability", "")),
        category=str(kw.get("category", "analyzer")),
        impl=str(kw.get("impl", "")),
    )


class TestValidationPass:
    def test_passes_valid_analysis(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .define("atr14", "analyzer", "ATRAnalyzer")
            .build()
        )
        result = ValidationPass().run(a)
        assert result is a

    def test_raises_on_duplicate_definitions(self) -> None:
        a = Analysis(
            name="bad",
            version="1.0",
            definitions=(
                Definition(name="dup", provider="EMAAnalyzer"),
                Definition(name="dup", provider="ATRAnalyzer"),
            ),
            providers=(
                _p(name="EMAAnalyzer", capability="compute_ema", impl="EMAAnalyzer"),
                _p(name="ATRAnalyzer", capability="compute_atr", impl="ATRAnalyzer"),
            ),
        )
        with pytest.raises(CompilationError, match="Duplicate definition name"):
            ValidationPass().run(a)

    def test_raises_on_unknown_provider(self) -> None:
        a = Analysis(
            name="bad",
            version="1.0",
            definitions=(Definition(name="fake", provider="NoSuchProvider"),),
            providers=(),
        )
        with pytest.raises(CompilationError, match="Unknown provider"):
            ValidationPass().run(a)

    def test_passes_valid_analysis_with_providers(self) -> None:
        a = Analysis(
            name="valid",
            version="1.0",
            definitions=(Definition(name="ema20", provider="EMAAnalyzer"),),
            providers=(_p(name="EMAAnalyzer", capability="compute_ema", impl="EMAAnalyzer"),),
        )
        ValidationPass().run(a)


class TestRegistryResolutionPass:
    def test_resolves_provider_names_via_registry(self) -> None:
        registry = create_default_registry()
        a = Analysis(
            name="test",
            version="1.0",
            definitions=(Definition(name="ema20", provider="compute_ema"),),
            providers=(_p(name="compute_ema", capability="compute_ema", impl="EMAAnalyzer"),),
        )
        result = RegistryResolutionPass(registry).run(a)
        assert len(result.definitions) == 1
        assert result.definitions[0].provider == "EMAAnalyzer"

    def test_raises_on_missing_provider(self) -> None:
        registry = create_default_registry()
        a = Analysis(
            name="test",
            version="1.0",
            definitions=(Definition(name="bad", provider="no_such_provider"),),
            providers=(),
        )
        with pytest.raises(CompilationError, match="not found"):
            RegistryResolutionPass(registry).run(a)

    def test_merges_default_params_from_registry(self) -> None:
        registry = ProviderRegistry()
        registry.register("compute_ema", EMAAnalyzer, default_params={"period": 20})
        a = Analysis(
            name="test",
            version="1.0",
            definitions=(Definition(name="ema20", provider="compute_ema"),),
            providers=(_p(name="compute_ema", capability="compute_ema", impl="EMAAnalyzer"),),
        )
        result = RegistryResolutionPass(registry).run(a)
        params = {p.name: p.value for p in result.definitions[0].parameters}
        assert params.get("period") == 20

    def test_user_params_override_defaults(self) -> None:
        registry = ProviderRegistry()
        registry.register("compute_ema", EMAAnalyzer, default_params={"period": 20})
        a = Analysis(
            name="test",
            version="1.0",
            definitions=(
                Definition(
                    name="ema50",
                    provider="compute_ema",
                    parameters=(Parameter(name="period", value=50),),
                ),
            ),
            providers=(_p(name="compute_ema", capability="compute_ema", impl="EMAAnalyzer"),),
        )
        result = RegistryResolutionPass(registry).run(a)
        params = {p.name: p.value for p in result.definitions[0].parameters}
        assert params.get("period") == 50


class TestDefinitionExpansionPass:
    def test_expands_default_params(self) -> None:
        registry = ProviderRegistry()
        registry.register("compute_ema", EMAAnalyzer, default_params={"period": 20})
        a = Analysis(
            name="test",
            version="1.0",
            definitions=(Definition(name="ema20", provider="EMAAnalyzer"),),
            providers=(
                Provider(
                    name="EMAAnalyzer",
                    capability="compute_ema",
                    category="analyzer",
                    impl="EMAAnalyzer",
                    default_params=(Parameter(name="period", value=20),),
                ),
            ),
        )
        result = DefinitionExpansionPass(registry).run(a)
        params = {p.name: p.value for p in result.definitions[0].parameters}
        assert params.get("period") == 20

    def test_does_not_override_explicit_params(self) -> None:
        registry = ProviderRegistry()
        registry.register("compute_ema", EMAAnalyzer, default_params={"period": 20})
        a = Analysis(
            name="test",
            version="1.0",
            definitions=(
                Definition(
                    name="ema50",
                    provider="EMAAnalyzer",
                    parameters=(Parameter(name="period", value=50),),
                ),
            ),
            providers=(
                Provider(
                    name="EMAAnalyzer",
                    capability="compute_ema",
                    category="analyzer",
                    impl="EMAAnalyzer",
                    default_params=(Parameter(name="period", value=20),),
                ),
            ),
        )
        result = DefinitionExpansionPass(registry).run(a)
        params = {p.name: p.value for p in result.definitions[0].parameters}
        assert params.get("period") == 50

    def test_no_defaults_no_change(self) -> None:
        registry = create_default_registry()
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        result = DefinitionExpansionPass(registry).run(a)
        params = {p.name: p.value for p in result.definitions[0].parameters}
        assert params.get("period") == 20
        assert len(result.definitions[0].parameters) == 1


class TestGraphGenerationPass:
    def test_produces_analysis_graph(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .build()
        )
        graph = GraphGenerationPass().run(a)
        assert isinstance(graph, AnalysisGraph)
        order = graph.execution_order()
        assert len(order) == 2

    def test_empty_analysis_empty_graph(self) -> None:
        a = AnalysisBuilder("empty", "1.0").build()
        graph = GraphGenerationPass().run(a)
        assert isinstance(graph, AnalysisGraph)
        assert graph.execution_order() == []

    def test_unknown_analyzer_raises(self) -> None:
        a = AnalysisBuilder("bad", "1.0").define("fake", "analyzer", "NoSuchAnalyzer").build()
        with pytest.raises(Exception, match="Unknown analyzer type"):
            GraphGenerationPass().run(a)


class TestPipeline:
    def test_full_pipeline_produces_graph(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .build()
        )
        registry = create_default_registry()
        pipeline = (
            Pipeline()
            .add_pass(ValidationPass())
            .add_pass(RegistryResolutionPass(registry))
            .add_pass(DefinitionExpansionPass(registry))
            .add_pass(GraphGenerationPass())
        )
        graph = pipeline.run(a)
        assert isinstance(graph, AnalysisGraph)
        order = graph.execution_order()
        assert len(order) == 2

    def test_pipeline_composable_passes(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        partial = Pipeline().add_pass(ValidationPass())
        result = partial.run_to_ast(a)
        assert isinstance(result, Analysis)
        assert result is a

    def test_run_to_ast_stops_before_graph(self) -> None:
        registry = create_default_registry()
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        pipeline = (
            Pipeline()
            .add_pass(ValidationPass())
            .add_pass(RegistryResolutionPass(registry))
            .add_pass(DefinitionExpansionPass(registry))
            .add_pass(GraphGenerationPass())
        )
        ast_result = pipeline.run_to_ast(a)
        assert isinstance(ast_result, Analysis)

    def test_pipeline_without_graph_pass_raises(self) -> None:
        a = AnalysisBuilder("test", "1.0").define("ema20", "analyzer", "EMAAnalyzer").build()
        pipeline = Pipeline().add_pass(ValidationPass())
        with pytest.raises(CompilationError, match="without producing"):
            pipeline.run(a)

    def test_validation_failure_stops_pipeline(self) -> None:
        a = Analysis(
            name="bad",
            version="1.0",
            definitions=(
                Definition(name="dup", provider="EMAAnalyzer"),
                Definition(name="dup", provider="ATRAnalyzer"),
            ),
            providers=(
                _p(name="EMAAnalyzer", capability="compute_ema", impl="EMAAnalyzer"),
                _p(name="ATRAnalyzer", capability="compute_atr", impl="ATRAnalyzer"),
            ),
        )
        pipeline = Pipeline().add_pass(ValidationPass()).add_pass(GraphGenerationPass())
        with pytest.raises(CompilationError, match="Duplicate definition name"):
            pipeline.run(a)

    def test_parity_with_ast_compiler(self) -> None:
        a = (
            AnalysisBuilder("parity", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("trend", "analyzer", "TrendAnalyzer")
            .build()
        )
        registry = create_default_registry()
        pipeline = (
            Pipeline()
            .add_pass(ValidationPass())
            .add_pass(RegistryResolutionPass(registry))
            .add_pass(DefinitionExpansionPass(registry))
            .add_pass(GraphGenerationPass())
        )
        graph = pipeline.run(a)
        order = graph.execution_order()
        names = [type(o).__name__ for o in order]
        ema_indices = [i for i, n in enumerate(names) if n == "EMAAnalyzer"]
        trend_idx = names.index("TrendAnalyzer")
        assert all(i < trend_idx for i in ema_indices)


class TestAstToConfig:
    def test_analyzer_only(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        config = _ast_to_config(a)
        assert config == StrategyConfig(
            name="test",
            version="1.0",
            analyzers=(AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),),
        )

    def test_mixed_categories(self) -> None:
        a = (
            AnalysisBuilder("mixed", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .define("sig", "signal", "PullbackSignal")
            .bind("ema20", "ema_20", "sig", "trend_key")
            .define("risk", "risk", "risk_based")
            .build()
        )
        config = _ast_to_config(a)
        assert len(config.analyzers) == 1
        assert len(config.signals) == 1
        assert config.risk.algorithm == "risk_based"

    def test_unknown_provider_raises(self) -> None:
        a = Analysis(
            name="bad",
            version="1.0",
            definitions=(Definition(name="x", provider="NoSuchProvider"),),
            providers=(),
        )
        with pytest.raises(CompilationError, match="Unknown provider"):
            _ast_to_config(a)
