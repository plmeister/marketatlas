"""Backlog 057: DSL parser — DSL text to template AST.

Parses the DSL grammar (055) over the lexer token stream (056) into a
template ``Analysis``: literal params, list literals, ``ChoiceExpression``
nodes (never expanded here), and reference params from ``name: source`` fields
and ``name,`` shorthand. Coverage is per-construct plus error paths with
positioned messages and a round-trip through the compiler pipeline.
"""

import pytest
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.constructors import ATR, EMA, build_analysis
from marketatlas.analysis.ast.expressions import (
    Choice,
    ChoiceExpression,
    LiteralExpression,
    ReferenceExpression,
)
from marketatlas.analysis.ast.lexer import DslSyntaxError, SourcePosition
from marketatlas.analysis.ast.models import Definition, Parameter
from marketatlas.analysis.ast.parser import DslParseError, parse
from marketatlas.analysis.ast.pipeline import (
    CompilationError,
    ParamValidationPass,
    Pipeline,
    RegistryResolutionPass,
    ValidationPass,
    expand,
)
from marketatlas.analysis.ast.registry import create_default_registry
from marketatlas.analysis.ast.serialization import from_json, to_json
from marketatlas.analysis.graph import AnalysisGraph


def _pipeline() -> Pipeline:
    registry = create_default_registry()
    return (
        Pipeline()
        .add_pass(ValidationPass())
        .add_pass(RegistryResolutionPass(registry))
        .add_pass(ParamValidationPass(registry))
    )


class TestBasicDefinitions:
    def test_minimal_definition(self) -> None:
        analysis = parse("ema := ema { period: 20 }", name="demo")
        assert analysis.name == "demo"
        assert analysis.definitions == (
            Definition(
                name="ema",
                provider="ema",
                parameters=(Parameter(name="period", value=LiteralExpression(20)),),
            ),
        )

    def test_multiple_definitions_order_preserved(self) -> None:
        analysis = parse("ema := ema { period: 20 }\natr := atr { period: 14 }", name="demo")
        assert [d.name for d in analysis.definitions] == ["ema", "atr"]
        assert analysis.definitions[1].parameters[0].value == 14

    def test_empty_fields(self) -> None:
        analysis = parse("trend := trend { }", name="demo")
        assert analysis.definitions[0].parameters == ()

    def test_providers_populated_from_registry(self) -> None:
        analysis = parse("ema := ema { period: 20 }", name="demo")
        provider = analysis.providers[0]
        assert provider.name == "ema"
        assert provider.capability == "ema"
        assert provider.impl == "EMAAnalyzer"
        assert provider.default_params == (Parameter(name="period", value=LiteralExpression(20)),)

    def test_providers_deduped(self) -> None:
        analysis = parse("a := ema { period: 20 }\nb := ema { period: 50 }", name="demo")
        assert len(analysis.providers) == 1

    def test_empty_source_ok(self) -> None:
        assert parse("").definitions == ()

    def test_custom_name_and_version(self) -> None:
        analysis = parse("x := ema { }", name="custom", version="2.0")
        assert analysis.name == "custom"
        assert analysis.version == "2.0"


class TestLiterals:
    def test_literal_types(self) -> None:
        analysis = parse(
            'p := ema { i: 5, f: 1.5, s: "hi", t: true, fl: false, n: null }', name="demo"
        )
        values = [p.value for p in analysis.definitions[0].parameters]
        assert values == [5, 1.5, "hi", True, False, None]

    def test_negative_numbers(self) -> None:
        analysis = parse("p := ema { a: -3, b: -1.25 }", name="demo")
        assert analysis.definitions[0].parameters[0].value == -3
        assert analysis.definitions[0].parameters[1].value == -1.25

    def test_quoted_string_not_a_reference(self) -> None:
        analysis = parse('x := ema { fast_key: "close" }', name="demo")
        param = analysis.definitions[0].parameters[0]
        assert param.name == "fast_key"
        assert param.value == "close"


class TestChoices:
    def test_choice_node_preserved(self) -> None:
        analysis = parse("ema := ema { period: <20 | 50> }", name="demo")
        value = analysis.definitions[0].parameters[0].value
        assert value == Choice([20, 50])
        assert isinstance(value, type(Choice([1])))

    def test_choice_members_bool_and_string(self) -> None:
        analysis = parse('x := ema { mult: <1.0 | 2.0>, flag: <true | false> }', name="demo")
        assert analysis.definitions[0].parameters[0].value == Choice([1.0, 2.0])
        assert analysis.definitions[0].parameters[1].value == Choice([True, False])

    def test_nested_choice(self) -> None:
        analysis = parse("ema := ema { period: <20 | <50 | 100>> }", name="demo")
        value = analysis.definitions[0].parameters[0].value
        assert value == Choice([20, Choice([50, 100])])

    def test_trailing_pipe_rejected(self) -> None:
        with pytest.raises(DslParseError):
            parse("ema := ema { period: <20 | 50 | > }", name="demo")

    def test_choice_stays_intact_through_expansion(self) -> None:
        analysis = parse("ema := ema { period: <20 | 50> }", name="demo")
        expanded = _pipeline().expand(analysis)
        assert [o.definitions[0].parameters[0].value for o in expanded] == [20, 50]
        for o in expanded:
            assert not isinstance(o.definitions[0].parameters[0].value, type(Choice([1])))


class TestLists:
    def test_list_is_plain_literal(self) -> None:
        analysis = parse("x := ema { periods: [1, 2, 3] }", name="demo")
        value = analysis.definitions[0].parameters[0].value
        assert value == [1, 2, 3]
        assert isinstance(value, LiteralExpression)

    def test_list_mixed_literals(self) -> None:
        analysis = parse(
            'x := ema { tags: ["a", "b"], nums: [1.5, 2], flags: [true, null] }',
            name="demo",
        )
        assert analysis.definitions[0].parameters[0].value == ["a", "b"]
        assert analysis.definitions[0].parameters[1].value == [1.5, 2]
        assert analysis.definitions[0].parameters[2].value == [True, None]

    def test_empty_list(self) -> None:
        analysis = parse("x := ema { tags: [] }", name="demo")
        assert analysis.definitions[0].parameters[0].value == []

    def test_list_never_expands(self) -> None:
        analysis = parse("x := ema { tags: [1, 2], period: 20 }", name="demo")
        variants = expand(analysis)
        assert len(variants) == 1
        assert variants[0].definitions[0].parameters[0].value == [1, 2]


class TestReferences:
    def test_reference_produces_param(self) -> None:
        analysis = parse(
            "ema := ema { period: 20 }\ntrend := trend { ema_20: ema }", name="demo"
        )
        param = analysis.definitions[1].parameters[0]
        assert param == Parameter(name="ema_20", value=ReferenceExpression("ema"))

    def test_reference_forward_declared_source(self) -> None:
        analysis = parse(
            "trend := trend { ema_20: ema }\nema := ema { period: 20 }", name="demo"
        )
        param = analysis.definitions[0].parameters[0]
        assert param == Parameter(name="ema_20", value=ReferenceExpression("ema"))

    def test_multiple_references_in_order(self) -> None:
        analysis = parse(
            "ema := ema { period: 20 }\n"
            "swing := swings { lookback: 50 }\n"
            "trend := trend { ema_20: ema }\n"
            "pullback := detect_pullback { swing: swing, trend: trend }",
            name="demo",
        )
        pullback = analysis.definitions[3]
        assert [p.name for p in pullback.parameters] == ["swing", "trend"]
        assert [p.value for p in pullback.parameters] == [
            ReferenceExpression("swing"),
            ReferenceExpression("trend"),
        ]


class TestShorthand:
    def test_shorthand_dependency(self) -> None:
        analysis = parse(
            "atr_14 := atr { period: 14 }\nsr := sr { atr_14 }", name="demo"
        )
        param = analysis.definitions[1].parameters[0]
        assert param == Parameter(name="atr_14", value=ReferenceExpression("atr_14"))

    def test_shorthand_single_field_no_trailing_comma(self) -> None:
        analysis = parse(
            "atr_14 := atr { period: 14 }\nsr := sr { atr_14 }", name="demo"
        )
        assert len(analysis.definitions[1].parameters) == 1

    def test_shorthand_must_be_provider_input(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("x := ema { nonexistent }", name="demo")
        assert exc.value.position == SourcePosition(1, 12)
        assert "not a declared input" in exc.value.message
        assert "ema" in exc.value.message

    def test_shorthand_unknown_input_lists_known_inputs(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("x := sr { bogus }", name="demo")
        err = exc.value
        assert "not a declared input of provider 'sr'" in err.message
        assert "swing, atr_14" in err.message

    def test_mixed_shorthand_and_params(self) -> None:
        analysis = parse(
            "atr_14 := atr { period: 14 }\nsr := sr { level_tolerance_atr: 0.5, atr_14 }",
            name="demo",
        )
        definition = analysis.definitions[1]
        assert definition.parameters[0].name == "level_tolerance_atr"
        assert definition.parameters[1] == Parameter(
            name="atr_14", value=ReferenceExpression("atr_14")
        )


class TestEqualityWithBuilder:
    def test_parse_equals_build_analysis(self) -> None:
        registry = create_default_registry()
        expected = build_analysis(
            "demo",
            [EMA(name="ema", period=20)],
            version="1.0",
            registry=registry,
        )
        assert parse("ema := ema { period: 20 }", name="demo") == expected

    def test_choice_template_equals_builder(self) -> None:
        registry = create_default_registry()
        expected = build_analysis(
            "demo",
            [EMA(name="ema", period=Choice([50, 100])), ATR(name="atr", period=14)],
            version="1.0",
            registry=registry,
        )
        source = "ema := ema { period: <50 | 100> }\natr := atr { period: 14 }"
        assert parse(source, name="demo") == expected

    def test_serialization_round_trip(self) -> None:
        source = "ema := ema { period: <20 | 50> }\ntrend := trend { ema_20: ema }"
        analysis = parse(source, name="demo")
        assert from_json(to_json(analysis)) == analysis


class TestErrors:
    def test_unknown_provider_type(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("ema := bogus { period: 20 }", name="demo")
        err = exc.value
        assert err.position == SourcePosition(1, 8)
        assert "unknown provider type 'bogus'" in err.message
        assert "ema" in err.message  # available capabilities listed

    def test_duplicate_definition_name(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("ema := ema { period: 20 }\nema := ema { period: 50 }", name="demo")
        assert exc.value.position == SourcePosition(2, 1)
        assert "duplicate definition name 'ema'" in exc.value.message

    def test_unknown_reference_reported_by_pipeline(self) -> None:
        analysis = parse("trend := trend { ema_20: ghost }", name="demo")
        assert analysis.definitions[0].parameters[0] == Parameter(
            name="ema_20", value=ReferenceExpression("ghost")
        )
        with pytest.raises(CompilationError, match="Unknown reference"):
            _pipeline().expand(analysis)

    def test_missing_assign(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("ema ema { period: 20 }", name="demo")
        assert exc.value.position == SourcePosition(1, 5)
        assert "':='" in exc.value.message

    def test_missing_brace(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("ema := ema { period: 20", name="demo")
        assert exc.value.position == SourcePosition(1, 22)
        assert "expected ',' or '}}'" in exc.value.message

    def test_field_without_colon_comma_or_brace(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("ema := ema { period 20 }", name="demo")
        assert exc.value.position == SourcePosition(1, 21)

    def test_double_comma_rejected(self) -> None:
        with pytest.raises(DslParseError):
            parse("ema := ema { period: 20,, }", name="demo")

    def test_stray_tokens_after_definition(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("ema := ema { period: 20 } }", name="demo")
        assert "unexpected token" in exc.value.message

    def test_reference_inside_choice_parses(self) -> None:
        analysis = parse("x := ema { period: <ema | ema> }", name="demo")
        value = analysis.definitions[0].parameters[0].value
        assert isinstance(value, ChoiceExpression)
        assert value.values[0] == ReferenceExpression("ema")

    def test_reference_inside_list_rejected(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("x := ema { tags: [ema] }", name="demo")
        assert "not allowed inside a list" in exc.value.message

    def test_lexer_error_propagates_positioned(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            parse("ema := ema { period: <20 }", name="demo")
        assert exc.value.position == SourcePosition(1, 22)

    def test_reference_as_value_after_reserved(self) -> None:
        # 'true' is a literal, never a reference
        analysis = parse("x := ema { flag: true }", name="demo")
        assert analysis.definitions[0].parameters[0].value == True  # noqa: E712


class TestPipelineIntegration:
    def test_spec_template_parses_expands_and_compiles(self) -> None:
        source = """
        ema := ema { period: <20 | 50> }
        atr_14 := atr { period: 14 }
        swing := swings { lookback: 50 }
        trend := trend { ema_20: ema, ema_50: ema50 }
        ema50 := ema { period: 50 }
        sr := sr { swing, atr_14 }
        pullback := detect_pullback { swing, trend, atr_14 }
        signal := generate_signal { four_swing_pullback: pullback, trend: trend, atr_14: atr_14 }
        """
        analysis = parse(source, name="strategy")
        expanded = _pipeline().expand(analysis)
        assert len(expanded) == 2
        for concrete in expanded:
            assert all(
                not isinstance(p.value, type(Choice([1])))
                for d in concrete.definitions
                for p in d.parameters
            )

    def test_literal_template_compiles_to_graph(self) -> None:
        source = """
        ema20 := ema { period: 20 }
        ema50 := ema { period: 50 }
        atr_14 := atr { period: 14 }
        swing := swings { lookback: 50 }
        trend := trend { ema_20: ema20, ema_50: ema50 }
        sr := sr { swing, atr_14 }
        pullback := detect_pullback { swing, trend, atr_14 }
        signal := generate_signal { four_swing_pullback: pullback, trend: trend, atr_14: atr_14 }
        """
        graph = ASTCompiler.compile(parse(source, name="strategy"))
        assert isinstance(graph, AnalysisGraph)
        names = sorted(type(a).__name__ for a in graph._analyzers)
        assert names == [
            "ATRAnalyzer",
            "BasicSwingAnalyzer",
            "EMAAnalyzer",
            "EMAAnalyzer",
            "FourSwingPullbackDetector",
            "SupportResistanceAnalyzer",
            "TrendAnalyzer",
        ]

    def test_empty_choice_rejected_at_parse(self) -> None:
        with pytest.raises(DslParseError) as exc:
            parse("ema := ema { period: <> }", name="demo")
        assert exc.value.position == SourcePosition(1, 23)

    def test_unknown_param_flagged_by_pipeline(self) -> None:
        analysis = parse("ema := ema { bogus: 20 }", name="demo")
        with pytest.raises(CompilationError, match="Unknown parameter 'bogus'"):
            _pipeline().expand(analysis)

    def test_deterministic_parse(self) -> None:
        source = "ema := ema { period: <20 | 50> }\ntrend := trend { ema_20: ema }"
        assert parse(source, name="demo") == parse(source, name="demo")
