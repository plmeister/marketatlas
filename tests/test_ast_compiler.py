import pytest
from marketatlas.analysis.analyzers.atr import ATRAnalyzer
from marketatlas.analysis.analyzers.ema import EMAAnalyzer
from marketatlas.analysis.ast.builder import AnalysisBuilder
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.expressions import Choice, wrap
from marketatlas.analysis.ast.models import (
    Analysis,
    Definition,
    Parameter,
    Provider,
)
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.strategy.config import (
    AnalyzerConfig,
    RiskConfig,
    SignalConfig,
    StrategyConfig,
)
from marketatlas.strategy.loader import build_analyzers


def _choice_template() -> Analysis:
    provider = Provider(
        name="ema",
        capability="compute_ema",
        category="analyzer",
        impl="EMAAnalyzer",
    )
    return Analysis(
        name="t",
        version="1.0",
        definitions=(
            Definition(
                name="ema",
                provider="ema",
                parameters=(Parameter(name="period", value=wrap(Choice([50, 100]))),),
            ),
        ),
        providers=(provider,),
    )


class TestToConfig:
    def test_analyzer_definitions(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .build()
        )
        config = ASTCompiler.to_config(a)
        assert config.name == "test"
        assert config.version == "1.0"
        assert config.analyzers == (
            AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),
            AnalyzerConfig(type="ATRAnalyzer", params={"period": 14}),
        )

    def test_signal_definition_with_references(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("trend", "analyzer", "TrendAnalyzer")
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .define("signal", "signal", "PullbackSignal")
            .with_param("min_strength", 0.5)
            .with_reference("trend", "trend")
            .with_reference("atr_14", "atr14")
            .build()
        )
        config = ASTCompiler.to_config(a)
        assert len(config.signals) == 1
        sig = config.signals[0]
        assert sig.type == "PullbackSignal"
        assert sig.requires == ("trend", "atr_14")
        assert sig.rules == {"min_strength": 0.5}

    def test_risk_definition(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("risk", "risk", "risk_based")
            .with_param("risk_pct", 1.0)
            .with_param("min_rr", 2.0)
            .build()
        )
        config = ASTCompiler.to_config(a)
        assert config.risk == RiskConfig(
            algorithm="risk_based",
            params={"risk_pct": 1.0, "min_rr": 2.0},
        )

    def test_empty_analysis(self) -> None:
        a = AnalysisBuilder("empty", "1.0").build()
        config = ASTCompiler.to_config(a)
        assert config.name == "empty"
        assert config.analyzers == ()
        assert config.signals == ()
        assert config.risk == RiskConfig(algorithm="none")

    def test_mixed_definitions(self) -> None:
        a = (
            AnalysisBuilder("mixed", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("sig", "signal", "PullbackSignal")
            .with_reference("trend", "ema20")
            .define("risk", "risk", "risk_based")
            .build()
        )
        config = ASTCompiler.to_config(a)
        assert len(config.analyzers) == 1
        assert len(config.signals) == 1
        assert config.risk.algorithm == "risk_based"

    def test_analyzer_without_params(self) -> None:
        a = AnalysisBuilder("test", "1.0").define("trend", "analyzer", "TrendAnalyzer").build()
        config = ASTCompiler.to_config(a)
        assert config.analyzers[0] == AnalyzerConfig(type="TrendAnalyzer", params={})

    def test_signal_without_bindings(self) -> None:
        a = AnalysisBuilder("test", "1.0").define("sig", "signal", "PullbackSignal").build()
        config = ASTCompiler.to_config(a)
        assert config.signals[0].requires == ()

    def test_multiple_signals(self) -> None:
        a = (
            AnalysisBuilder("dual", "1.0")
            .define("atr14", "analyzer", "ATRAnalyzer")
            .define("sig1", "signal", "PullbackSignal")
            .with_reference("atr_14", "atr14")
            .define("sig2", "signal", "PullbackSignal")
            .with_reference("atr_14", "atr14")
            .build()
        )
        config = ASTCompiler.to_config(a)
        assert len(config.signals) == 2
        assert config.signals[0].requires == ("atr_14",)
        assert config.signals[1].requires == ("atr_14",)


class TestCompile:
    def test_builds_graph_from_analyzers(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .build()
        )
        graph = ASTCompiler.compile(a)
        assert isinstance(graph, AnalysisGraph)
        order = graph.execution_order()
        assert len(order) == 2
        assert isinstance(order[0], EMAAnalyzer)
        assert isinstance(order[1], ATRAnalyzer)

    def test_empty_analysis_returns_empty_graph(self) -> None:
        a = AnalysisBuilder("empty", "1.0").build()
        graph = ASTCompiler.compile(a)
        assert isinstance(graph, AnalysisGraph)
        assert graph.execution_order() == []

    def test_signal_and_risk_defs_ignored_for_graph(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("sig", "signal", "PullbackSignal")
            .define("risk", "risk", "risk_based")
            .build()
        )
        graph = ASTCompiler.compile(a)
        order = graph.execution_order()
        assert len(order) == 1
        assert isinstance(order[0], EMAAnalyzer)

    def test_topo_sort_respected(self) -> None:
        a = (
            AnalysisBuilder("deps", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("trend", "analyzer", "TrendAnalyzer")
            .build()
        )
        graph = ASTCompiler.compile(a)
        order = graph.execution_order()
        names = [type(o).__name__ for o in order]
        ema_indices = [i for i, n in enumerate(names) if n == "EMAAnalyzer"]
        trend_idx = names.index("TrendAnalyzer")
        assert all(i < trend_idx for i in ema_indices)

    def test_parity_with_strategy_config(self) -> None:
        config = StrategyConfig(
            name="parity",
            version="1.0",
            analyzers=(
                AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),
                AnalyzerConfig(type="EMAAnalyzer", params={"period": 50}),
                AnalyzerConfig(type="TrendAnalyzer", params={}),
            ),
        )
        graph_from_config = AnalysisGraph(build_analyzers(config))

        analysis = (
            AnalysisBuilder("parity", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("trend", "analyzer", "TrendAnalyzer")
            .build()
        )
        graph_from_ast = ASTCompiler.compile(analysis)

        config_names = [type(a).__name__ for a in graph_from_config.execution_order()]
        ast_names = [type(a).__name__ for a in graph_from_ast.execution_order()]
        assert config_names == ast_names

    def test_parity_with_full_strategy_config(self) -> None:
        config = StrategyConfig(
            name="full_parity",
            version="1.0",
            analyzers=(
                AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),
                AnalyzerConfig(type="EMAAnalyzer", params={"period": 50}),
                AnalyzerConfig(type="ATRAnalyzer", params={"period": 14}),
                AnalyzerConfig(type="TrendAnalyzer", params={}),
                AnalyzerConfig(type="SwingStructureAnalyzer", params={"lookback": 100}),
            ),
            signals=(
                SignalConfig(
                    type="PullbackSignal",
                    requires=("trend", "atr_14", "four_swing_pullback"),
                    rules={"min_strength": 0.5},
                ),
            ),
            risk=RiskConfig(algorithm="risk_based", params={"risk_pct": 1.0}),
        )
        graph_from_config = AnalysisGraph(build_analyzers(config))

        analysis = (
            AnalysisBuilder("full_parity", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .define("trend", "analyzer", "TrendAnalyzer")
            .define("swing", "analyzer", "SwingStructureAnalyzer")
            .with_param("lookback", 100)
            .define("signal", "signal", "PullbackSignal")
            .with_param("min_strength", 0.5)
            .with_reference("trend", "trend")
            .with_reference("atr_14", "atr14")
            .with_reference("four_swing_pullback", "swing")
            .define("risk", "risk", "risk_based")
            .with_param("risk_pct", 1.0)
            .build()
        )
        graph_from_ast = ASTCompiler.compile(analysis)

        config_names = [type(a).__name__ for a in graph_from_config.execution_order()]
        ast_names = [type(a).__name__ for a in graph_from_ast.execution_order()]
        assert config_names == ast_names

    def test_unknown_analyzer_type_raises(self) -> None:
        a = AnalysisBuilder("bad", "1.0").define("fake", "analyzer", "NoSuchAnalyzer").build()
        with pytest.raises(Exception, match="Unknown analyzer type"):
            ASTCompiler.compile(a)


class TestMultiOutput:
    def test_compile_raises_on_choice_template(self) -> None:
        with pytest.raises(Exception, match="compile_all"):
            ASTCompiler.compile(_choice_template())

    def test_expand_returns_concrete_asts(self) -> None:
        variants = ASTCompiler.expand(_choice_template())
        assert len(variants) == 2
        assert variants[0].definitions[0].parameters[0].value == 50
        assert variants[1].definitions[0].parameters[0].value == 100

    def test_compile_all_returns_one_graph_per_variant(self) -> None:
        graphs = ASTCompiler.compile_all(_choice_template())
        assert len(graphs) == 2
        periods = [type(g).__name__ for g in graphs]
        assert periods == ["AnalysisGraph", "AnalysisGraph"]
        for g in graphs:
            order = g.execution_order()
            assert len(order) == 1
            assert isinstance(order[0], EMAAnalyzer)

    def test_compile_all_graphs_distinct_params(self) -> None:
        graphs = ASTCompiler.compile_all(_choice_template())
        keys = [o.instance_key for g in graphs for o in g.execution_order()]
        assert keys == ["ema_50", "ema_100"]

    def test_expand_single_variant_for_choice_free(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        variants = ASTCompiler.expand(a)
        assert len(variants) == 1
        assert variants[0] == a

    def test_compile_all_merges_registry_defaults(self) -> None:
        variants = ASTCompiler.expand(_choice_template())
        merged = [d.parameters for d in variants[0].definitions]
        assert len(merged) == 1
        assert len(merged[0]) == 1
