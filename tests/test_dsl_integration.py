"""Backlog 060: DSL integration tests — text to graph.

End-to-end golden tests over the full path: DSL text → lexer (056) →
parser (057) → template AST → pipeline (051: validation, registry
resolution, provider param validation, choice expansion (050), concrete
validation, graph compilation) → ``AnalysisGraph``. Anchors the DSL feature
to the spec examples (docs/dsl.md §7) at the text level; the AST-level
choice goldens live in backlog 054.

Test classes are organised by pipeline stage, and stage boundaries are
visible in the class names:

* ``TestStage0_Parse`` — text → template AST (057) plus builder equality.
* ``TestStage1_Validate`` — registry resolution, provider param validation
  (052) and positioned diagnostics (059).
* ``TestStage2_Expand`` — choice expansion (050) and expansion counts.
* ``TestStage3_Concrete`` — concrete-AST guards (choice-free, duplicates).
* ``TestStage4_Graph`` — graph structure and config generation (040/051).
* ``TestEndToEnd`` — ``compile_dsl`` full-path regression.
"""

import pytest
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.constructors import build_analysis
from marketatlas.analysis.ast.expressions import (

    Choice,
    ChoiceExpression,
    ReferenceExpression,
    wrap,
)
from marketatlas.analysis.ast.lexer import SourcePosition
from marketatlas.analysis.ast.models import Analysis, Definition, Parameter
from marketatlas.analysis.ast.parser import DslParseError, parse, parse_with_positions
from marketatlas.analysis.ast.pipeline import CompilationError, expand
from marketatlas.analysis.ast.registry import create_default_registry
from marketatlas.analysis.graph import (
    AnalysisGraph,
    CyclicDependencyError,
    UnsatisfiedDependencyError,
)
from marketatlas.strategy.config import RiskConfig

pytestmark = pytest.mark.tier2

# -- spec fixtures (docs/dsl.md §7) --------------------------------------

SINGLE = "ema := ema { period: 20 }"

LINEAR = """
ema := ema { period: 20 }
atr_14 := atr { period: 14 }
trend := trend { ema_20: ema, ema_50: ema50 }
ema50 := ema { period: 50 }
"""

BRANCHING = """
swing := swings { lookback: 50 }
atr_14_series := atr_series { period: 14 }
sr := sr { swing, atr_14_series }
"""

PULLBACK_TREE = """
swing := swings { lookback: 50 }
atr_14_series := atr_series { period: 14 }
sr := sr { swing, atr_14_series }
alternate := swingstructure { swing }
pullback := pullbackpattern { swing_structure: alternate }
"""

FULL_TEMPLATE = """
ema := ema { period: <20 | 50> }
atr_14_series := atr_series { period: 14 }
swing := swings { lookback: 50 }
trend := trend { ema_20: ema, ema_50: ema50 }
ema50 := ema { period: 50 }
sr := sr { swing, atr_14_series }
alternate := swingstructure { swing }
pullback := pullbackpattern { swing_structure: alternate }
"""

FULL_LITERAL = """
ema := ema { period: 20 }
atr_14_series := atr_series { period: 14 }
swing := swings { lookback: 50 }
trend := trend { ema_20: ema, ema_50: ema50 }
ema50 := ema { period: 50 }
sr := sr { swing, atr_14_series }
alternate := swingstructure { swing }
pullback := pullbackpattern { swing_structure: alternate }
"""

TIMEFRAME = """
tf1w := timeframe { resolution: "1w" }
ema1w := ema { period: 20, timeframe: tf1w }
"""


# -- helpers -------------------------------------------------------------


def _def(name: str, provider: str, *params: Parameter) -> Definition:
    return Definition(name=name, provider=provider, parameters=params)


def _param(name: str, value: object) -> Parameter:
    return Parameter(name=name, value=wrap(value))


def _ref(name: str, source: str) -> Parameter:
    return Parameter(name=name, value=ReferenceExpression(source))


def _builder_full_strategy(registry=None) -> Analysis:
    return build_analysis(
        "strategy",
        [
            _def("ema", "ema", _param("period", 20)),
            _def("atr_14_series", "atr_series", _param("period", 14)),
            _def("swing", "swings", _param("lookback", 50)),
            _def("trend", "trend", _ref("ema_20", "ema"), _ref("ema_50", "ema50")),
            _def("ema50", "ema", _param("period", 50)),
            _def("sr", "sr", _ref("swing", "swing"), _ref("atr_14_series", "atr_14_series")),
            _def("alternate", "swingstructure", _ref("swing", "swing")),
            _def(
                "pullback",
                "pullbackpattern",
                _ref("swing_structure", "alternate"),
            ),
        ],
        version="1.0",
        registry=registry if registry is not None else create_default_registry(),
    )


def _graph_nodes(graph: AnalysisGraph) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Analyzer class name → (consumed facts, produced facts) for the graph."""
    return {
        type(a).__name__: (
            tuple(sorted(fk.name for fk in a.requires())),
            tuple(sorted(fk.name for fk in a.produces())),
        )
        for a in graph._analyzers
    }


def _variant_periods(analysis: Analysis) -> list[object]:
    return [v.definitions[0].parameters[0].value for v in expand(analysis)]


# -- stage 0: text → template AST ----------------------------------------


class TestStage0Parse:
    def test_single_definition(self) -> None:
        analysis = parse(SINGLE, name="strategy")
        assert analysis.definitions == (_def("ema", "ema", _param("period", 20)),)

    def test_linear_chain_forward_reference(self) -> None:
        analysis = parse(LINEAR, name="strategy")
        assert [d.name for d in analysis.definitions] == ["ema", "atr_14", "trend", "ema50"]
        trend = analysis.definitions[2]
        assert trend.parameters == (
            _ref("ema_20", "ema"),
            _ref("ema_50", "ema50"),
        )

    def test_branching_shorthand_becomes_reference(self) -> None:
        analysis = parse(BRANCHING, name="strategy")
        sr = analysis.definitions[2]
        assert sr.parameters == (
            _ref("swing", "swing"),
            _ref("atr_14_series", "atr_14_series"),
        )

    def test_full_template_keeps_choices_intact(self) -> None:
        analysis = parse(FULL_TEMPLATE, name="strategy")
        assert len(analysis.definitions) == 8
        assert analysis.definitions[0].parameters[0].value == Choice([20, 50])
        pullback = analysis.definitions[7]
        assert pullback.parameters == (
            _ref("swing_structure", "alternate"),
        )

    def test_text_equals_builder_equivalent(self) -> None:
        assert parse(FULL_LITERAL, name="strategy") == _builder_full_strategy()

    def test_parse_is_deterministic(self) -> None:
        assert parse(SINGLE, name="strategy") == parse(SINGLE, name="strategy")


# -- stage 1: validation, registry resolution, param schema ---------------


class TestStage1Validate:
    def test_unknown_provider_type_positioned(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("ema := bogus { period: 20 }", name="strategy")
        assert exc.value.position == SourcePosition(1, 8)
        assert "unknown provider type 'bogus'" in exc.value.message
        assert "ema" in exc.value.message  # available capabilities listed

    def test_unknown_param_positioned(self) -> None:
        source = "ema := ema { bogus: 20 }"
        with pytest.raises(CompilationError) as exc:
            ASTCompiler.compile_dsl(source, name="s")
        error = exc.value.errors[0]
        assert error.position == SourcePosition(1, 14)
        assert "Unknown parameter 'bogus'" in error.message

    def test_wrong_literal_type_positioned(self) -> None:
        source = 'ema := ema { period: "20" }'
        with pytest.raises(CompilationError) as exc:
            ASTCompiler.compile_dsl(source, name="s")
        error = exc.value.errors[0]
        assert error.position == SourcePosition(1, 14)
        assert "expects int" in error.message

    def test_wrong_type_choice_leaf_positioned(self) -> None:
        source = 'ema := ema { period: <20 | "50"> }'
        with pytest.raises(CompilationError) as exc:
            ASTCompiler.compile_dsl(source, name="s")
        error = exc.value.errors[0]
        assert error.position == SourcePosition(1, 14)
        assert "expects int" in error.message

    def test_missing_required_timeframe_resolution_positioned(self) -> None:
        with pytest.raises(CompilationError) as exc:
            ASTCompiler.compile_dsl("tf := timeframe { }", name="s")
        error = exc.value.errors[0]
        assert error.position == SourcePosition(1, 1)
        assert "missing the required 'resolution' parameter" in error.message

    def test_unknown_reference_positioned(self) -> None:
        with pytest.raises(CompilationError) as exc:
            ASTCompiler.compile_dsl("trend := trend { ema_20: ghost }", name="s")
        error = exc.value.errors[0]
        assert error.position == SourcePosition(1, 1)
        assert "Unknown reference" in error.message
        assert "'ghost'" in error.message

    def test_shorthand_not_declared_input_positioned(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("x := ema { bogus }", name="strategy")
        assert exc.value.position == SourcePosition(1, 12)
        assert "not a declared input" in exc.value.message

    def test_forward_reference_resolves(self) -> None:
        # ema50 is defined after trend (spec §7 ex.2); post-parse resolution
        # must bind it before graph construction.
        graphs = ASTCompiler.compile_dsl(LINEAR, name="strategy")
        assert len(graphs) == 1
        nodes = _graph_nodes(graphs[0])
        assert nodes["TrendAnalyzer"][0] == ("ema_20", "ema_50")


# -- stage 2: template expansion ------------------------------------------


class TestStage2Expand:
    def test_single_choice_two_concrete_asts(self) -> None:
        analysis = parse("ema := ema { period: <20 | 50> }", name="strategy")
        variants = expand(analysis)
        assert len(variants) == 2
        assert _variant_periods(analysis) == [20, 50]

    def test_nested_choice_flattened(self) -> None:
        analysis = parse("ema := ema { period: <20 | <50 | 100>> }", name="strategy")
        assert _variant_periods(analysis) == [20, 50, 100]

    def test_cartesian_across_definitions(self) -> None:
        source = "ema := ema { period: <20 | 50> }\natr := atr { period: <14 | 21> }"
        analysis = parse(source, name="strategy")
        variants = expand(analysis)
        assert len(variants) == 4
        pairs = [
            (v.definitions[0].parameters[0].value, v.definitions[1].parameters[0].value)
            for v in variants
        ]
        assert pairs == [(20, 14), (20, 21), (50, 14), (50, 21)]

    def test_list_literal_stays_single_ast(self) -> None:
        analysis = parse("x := ema { periods: [1, 2, 3] }", name="strategy")
        variants = expand(analysis)
        assert len(variants) == 1
        assert variants[0].definitions[0].parameters[0].value == [1, 2, 3]

    def test_full_template_expansion_count(self) -> None:
        analysis = parse(FULL_TEMPLATE, name="strategy")
        variants = expand(analysis)
        assert len(variants) == 2
        assert [v.definitions[0].parameters[0].value for v in variants] == [20, 50]

    def test_expanded_variants_choice_free(self) -> None:
        for variant in expand(parse(FULL_TEMPLATE, name="strategy")):
            for d in variant.definitions:
                for p in d.parameters:
                    assert not isinstance(p.value, ChoiceExpression)


# -- stage 3: concrete AST validation -------------------------------------


class TestStage3Concrete:
    def test_empty_choice_rejected_at_parse(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("ema := ema { period: <> }", name="strategy")
        assert exc.value.position == SourcePosition(1, 23)

    def test_empty_choice_at_expansion_positioned(self) -> None:
        # DSL text cannot express an empty choice (`<>` is rejected at parse);
        # the expansion guard is reached by emptying the parsed template's
        # choice and re-running the pipeline with the parse's SourceMap.
        source = "ema := ema { period: <20 | 50> }"
        analysis, source_map = parse_with_positions(source, name="strategy")
        template = Analysis(
            name=analysis.name,
            version=analysis.version,
            definitions=(
                _def(
                    "ema",
                    analysis.definitions[0].provider,
                    _param("period", Choice([])),
                ),
            ),
            providers=analysis.providers,
        )
        with pytest.raises(CompilationError) as exc:
            expand(template, source_map)
        error = exc.value.errors[0]
        assert error.position == SourcePosition(1, 14)
        assert "Empty choice for parameter 'period' of definition 'ema'" in error.message

    def test_duplicate_definition_names_rejected_at_parse(self) -> None:
        source = "ema := ema { period: 20 }\nema := ema { period: 50 }"
        with pytest.raises(DslParseError) as exc:
            parse(source, name="strategy")
        assert exc.value.position == SourcePosition(2, 1)
        assert "duplicate definition name 'ema'" in exc.value.message


# -- stage 4: graph generation ---------------------------------------------


class TestStage4Graph:
    def test_single_definition_single_analyzer(self) -> None:
        graph = ASTCompiler.compile(parse(SINGLE, name="strategy"))
        assert _graph_nodes(graph) == {
            "EMAAnalyzer": ((), ("ema_20",)),
        }

    def test_linear_chain_edges(self) -> None:
        graph = ASTCompiler.compile(parse(LINEAR, name="strategy"))
        nodes = _graph_nodes(graph)
        assert nodes["TrendAnalyzer"] == (("ema_20", "ema_50"), ("trend",))
        order = [type(a).__name__ for a in graph.execution_order()]
        assert order.index("EMAAnalyzer") < order.index("TrendAnalyzer")

    def test_branching_shorthand_edges(self) -> None:
        graph = ASTCompiler.compile(parse(BRANCHING, name="strategy"))
        nodes = _graph_nodes(graph)
        assert nodes["SupportResistanceAnalyzer"] == (("atr_14_series", "swing"), ("sr",))
        assert nodes["BasicSwingAnalyzer"] == ((), ("swing",))
        assert nodes["ATRSeriesAnalyzer"] == ((), ("atr_14_series",))

    def test_pullback_tree_edges(self) -> None:
        graph = ASTCompiler.compile(parse(PULLBACK_TREE, name="strategy"))
        nodes = _graph_nodes(graph)
        assert nodes["SwingStructureAnalyzer"] == (("swing",), ("swing_structure",))
        assert nodes["PullbackPatternAnalyzer"] == (
            ("swing_structure",),
            ("pullback_pattern",),
        )
        assert nodes["SupportResistanceAnalyzer"] == (("atr_14_series", "swing"), ("sr",))

    def test_full_literal_eight_analyzer_graph(self) -> None:
        graph = ASTCompiler.compile(parse(FULL_LITERAL, name="strategy"))
        types = sorted(type(a).__name__ for a in graph._analyzers)
        assert types == [
            "ATRSeriesAnalyzer",
            "BasicSwingAnalyzer",
            "EMAAnalyzer",
            "EMAAnalyzer",
            "PullbackPatternAnalyzer",
            "SupportResistanceAnalyzer",
            "SwingStructureAnalyzer",
            "TrendAnalyzer",
        ]

    def test_full_literal_matches_builder_graph(self) -> None:
        dsl_graph = ASTCompiler.compile(parse(FULL_LITERAL, name="strategy"))
        builder_graph = ASTCompiler.compile(_builder_full_strategy())
        assert _graph_nodes(dsl_graph) == _graph_nodes(builder_graph)

    def test_duplicate_fact_producer_rejected(self) -> None:
        source = "ema := ema { period: 20 }\nema2 := ema { period: 20 }"
        with pytest.raises(CyclicDependencyError):
            ASTCompiler.compile(parse(source, name="strategy"))

    def test_undeclared_dependency_rejected(self) -> None:
        # trend declares only its fast binding; the default slow key ema_50
        # has no producer at graph construction (spec §7.2).
        source = "ema := ema { period: 20 }\ntrend := trend { ema_20: ema }"
        with pytest.raises(UnsatisfiedDependencyError):
            ASTCompiler.compile(parse(source, name="strategy"))

    def test_full_template_only_consistent_variant_compiles(self) -> None:
        analysis = parse(FULL_TEMPLATE, name="strategy")
        variants = expand(analysis)
        assert len(variants) == 2
        # period-20 variant: ema produces ema_20, matching trend's reference.
        graph = ASTCompiler.compile(variants[0])
        assert len(graph._analyzers) == 8
        # period-50 variant: ema now produces ema_50, so the ema_20 reference
        # is inconsistent and fails before graph construction.
        with pytest.raises(CompilationError) as exc:
            ASTCompiler.compile(variants[1])
        assert "Reference to 'ema_20'" in exc.value.message

    def test_choice_over_reference_expands_to_graphs(self) -> None:
        source = """
        ema20 := ema { period: 20 }
        ema := ema { period: 50 }
        trend := trend { ema_20: ema20, ema_50: <ema | ema> }
        """
        graphs = ASTCompiler.compile_dsl(source, name="strategy")
        assert len(graphs) == 2
        for graph in graphs:
            ema_producers = sorted(
                fk.name
                for a in graph._analyzers
                if type(a).__name__ == "EMAAnalyzer"
                for fk in a.produces()
            )
            assert ema_producers == ["ema_20", "ema_50"]
            assert _graph_nodes(graph)["TrendAnalyzer"] == (("ema_20", "ema_50"), ("trend",))


# -- stage 4: config generation --------------------------------------------


class TestStage4Config:
    def test_full_literal_config(self) -> None:
        config = ASTCompiler.to_config(parse(FULL_LITERAL, name="strategy"))
        assert config.name == "strategy"
        assert config.version == "1.0"
        assert len(config.analyzers) == 8
        assert config.signals == ()
        assert config.risk == RiskConfig(algorithm="none")

    def test_timeframe_reference_config(self) -> None:
        config = ASTCompiler.to_config(parse(TIMEFRAME, name="strategy"))
        assert config.timeframes == ("1w",)
        assert config.analyzers[0].timeframe == "1w"


# -- end to end ------------------------------------------------------------


class TestEndToEnd:
    def test_compile_dsl_single_graph(self) -> None:
        graphs = ASTCompiler.compile_dsl(SINGLE, name="strategy")
        assert len(graphs) == 1
        assert isinstance(graphs[0], AnalysisGraph)

    def test_compile_dsl_choice_multi_graph(self) -> None:
        graphs = ASTCompiler.compile_dsl(
            "ema := ema { period: <20 | 50> }\natr := atr { period: 14 }", name="strategy"
        )
        assert len(graphs) == 2

    def test_compile_dsl_deterministic(self) -> None:
        first = ASTCompiler.compile_dsl(FULL_LITERAL, name="strategy")
        second = ASTCompiler.compile_dsl(FULL_LITERAL, name="strategy")
        assert len(first) == len(second) == 1
        assert _graph_nodes(first[0]) == _graph_nodes(second[0])

    def test_compile_dsl_graphs_are_distinct(self) -> None:
        graphs = ASTCompiler.compile_dsl("ema := ema { period: <20 | 50> }", name="strategy")
        assert graphs[0] is not graphs[1]

    def test_compile_dsl_positioned_error_formats(self) -> None:
        source = "ema := ema { bogus: 20 }"
        with pytest.raises(CompilationError) as exc:
            ASTCompiler.compile_dsl(source, name="s")
        error = exc.value.errors[0]
        assert error.position == SourcePosition(1, 14)
        from marketatlas.analysis.ast.diagnostics import format_diagnostic

        assert format_diagnostic(error, source).startswith("1:14: error:")
