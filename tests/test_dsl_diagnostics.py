"""Backlog 059: DSL error reporting — positioned diagnostics.

Covers the downstream piece of positioned reporting: ``Diagnostic`` carries an
optional source position, ``SourceMap`` (produced by ``parse_with_positions``)
maps named AST nodes to ``line:col`` locations, the compact formatter and
caret snippet render them, and the compiler pipeline preserves positions on
``CompilationError`` "where source-mapped". Lexer/parser position accuracy is
covered in test_dsl_lexer.py / test_dsl_parser.py.
"""

import pytest
from marketatlas.analysis.ast.compiler import ASTCompiler
from marketatlas.analysis.ast.diagnostics import (
    SourceMap,
    format_diagnostic,
    format_errors,
    render_snippet,
    with_position,
)
from marketatlas.analysis.ast.expressions import Choice
from marketatlas.analysis.ast.lexer import DslSyntaxError, SourcePosition
from marketatlas.analysis.ast.models import Analysis, Definition, Parameter
from marketatlas.analysis.ast.parser import DslParseError, parse_with_positions
from marketatlas.analysis.ast.pipeline import (
    CompilationError,
    ParamValidationPass,
    Pipeline,
    RegistryResolutionPass,
    ValidationPass,
    expand,
)
from marketatlas.analysis.ast.registry import create_default_registry
from marketatlas.analysis.ast.validation import (
    Diagnostic,
    DiagnosticSeverity,
)


def _err(message: str, node_name: str, *, position: SourcePosition | None = None) -> Diagnostic:
    return Diagnostic(
        message=message,
        severity=DiagnosticSeverity.ERROR,
        node_name=node_name,
        node_type="definition",
        position=position,
    )


class TestDiagnosticPosition:
    def test_position_defaults_to_none(self) -> None:
        d = _err("m", "x")
        assert d.position is None

    def test_position_carried(self) -> None:
        d = _err("m", "x", position=SourcePosition(2, 7))
        assert d.position == SourcePosition(2, 7)

    def test_with_position_attaches(self) -> None:
        d = _err("m", "x")
        positioned = with_position(d, SourcePosition(1, 3))
        assert positioned.position == SourcePosition(1, 3)
        assert positioned.message == "m"

    def test_with_position_existing_wins(self) -> None:
        d = _err("m", "x", position=SourcePosition(1, 1))
        assert with_position(d, SourcePosition(9, 9)) is d

    def test_with_position_none_identity(self) -> None:
        d = _err("m", "x")
        assert with_position(d, None) is d


class TestSourceMap:
    def test_empty_map_returns_none(self) -> None:
        sm = SourceMap()
        assert sm.position_for("definition", "anything") is None
        assert sm.position_for("definition", "anything", parameter="p") is None

    def test_position_for_definition(self) -> None:
        sm = SourceMap(definitions={"ema": SourcePosition(1, 1)})
        assert sm.position_for("definition", "ema") == SourcePosition(1, 1)
        assert sm.position_for("definition", "missing") is None

    def test_position_for_parameter(self) -> None:
        sm = SourceMap(parameters={("ema", "period"): SourcePosition(1, 14)})
        assert sm.position_for("definition", "ema", parameter="period") == SourcePosition(1, 14)
        assert sm.position_for("definition", "ema", parameter="other") is None

    def test_definition_fallback_without_parameter(self) -> None:
        sm = SourceMap(
            definitions={"ema": SourcePosition(1, 1)},
            parameters={("ema", "period"): SourcePosition(1, 14)},
        )
        assert sm.position_for("definition", "ema") == SourcePosition(1, 1)


class TestFormatDiagnostic:
    def test_compact_without_position(self) -> None:
        assert format_diagnostic(_err("boom", "x")) == "error: boom"

    def test_compact_with_position(self) -> None:
        d = _err("boom", "x", position=SourcePosition(3, 9))
        assert format_diagnostic(d) == "3:9: error: boom"

    def test_warning_severity(self) -> None:
        w = Diagnostic(
            message="unused",
            severity=DiagnosticSeverity.WARNING,
            node_name="x",
            node_type="definition",
        )
        assert format_diagnostic(w) == "warning: unused"

    def test_with_source_appends_snippet(self) -> None:
        d = _err("boom", "x", position=SourcePosition(2, 4))
        text = format_diagnostic(d, source="line one\nabc def\nline three")
        assert text.splitlines()[0] == "2:4: error: boom"
        assert "abc def" in text
        assert "^" in text


class TestRenderSnippet:
    def test_caret_alignment(self) -> None:
        source = "ema := ema { bogus: 20 }"
        snippet = render_snippet(source, SourcePosition(1, 14))
        lines = snippet.splitlines()
        assert lines[0] == "  " + source
        assert lines[1].index("^") == lines[0].index("b")

    def test_second_line(self) -> None:
        source = "ema := ema { period: 20 }\nbogus := nope { }"
        snippet = render_snippet(source, SourcePosition(2, 9))
        assert snippet.splitlines()[0] == "  bogus := nope { }"

    def test_position_beyond_eof(self) -> None:
        snippet = render_snippet("short", SourcePosition(50, 1))
        assert snippet == "  \n  ^"

    def test_empty_source(self) -> None:
        assert render_snippet("", SourcePosition(1, 1)) == "  \n  ^"


class TestFormatErrors:
    def test_empty(self) -> None:
        assert format_errors([]) == ""
        assert format_errors(()) == ""

    def test_single_error(self) -> None:
        assert format_errors([_err("one", "x")]) == "1 error:\nerror: one"

    def test_multi_error(self) -> None:
        errors = [
            _err("first", "a", position=SourcePosition(1, 3)),
            _err("second", "b", position=SourcePosition(2, 5)),
        ]
        text = format_errors(errors)
        lines = text.splitlines()
        assert lines[0] == "2 errors:"
        assert lines[1] == "1:3: error: first"
        assert lines[2] == "2:5: error: second"


class TestParseWithPositions:
    def test_returns_analysis_and_map(self) -> None:
        source = "ema := ema { period: 20 }\ntrend := trend { ema_20: ema }"
        analysis, sm = parse_with_positions(source, name="demo")
        assert analysis.name == "demo"
        assert sm.definitions == {
            "ema": SourcePosition(1, 1),
            "trend": SourcePosition(2, 1),
        }

    def test_parameter_positions_recorded(self) -> None:
        source = 'ema := ema {\n  period: 20,\n  fast_key: "close",\n}'
        _, sm = parse_with_positions(source, name="demo")
        assert sm.parameters[("ema", "period")] == SourcePosition(2, 3)
        assert sm.parameters[("ema", "fast_key")] == SourcePosition(3, 3)

    def test_reference_param_positions_recorded(self) -> None:
        source = "ema := ema { period: 20 }\ntrend := trend { ema_20: ema }"
        _, sm = parse_with_positions(source, name="demo")
        assert ("trend", "ema_20") in sm.parameters
        assert sm.parameters[("trend", "ema_20")] == SourcePosition(2, 18)

    def test_source_text_preserved(self) -> None:
        source = "a := ema { period: 20 }"
        _, sm = parse_with_positions(source, name="demo")
        assert sm.source == source

    def test_parse_wraps_without_map(self) -> None:
        from marketatlas.analysis.ast.parser import parse

        assert parse("ema := ema { period: 20 }", name="d").name == "d"


def _positioned_pipeline(registry, source_map):
    return (
        Pipeline(source_map)
        .add_pass(ValidationPass(source_map))
        .add_pass(RegistryResolutionPass(registry))
        .add_pass(ParamValidationPass(registry, source_map))
    )


class TestPipelinePositions:
    def test_validation_error_positioned(self) -> None:
        analysis, sm = parse_with_positions("ema := ema { period: 20, x: ema }", name="demo")
        with pytest.raises(CompilationError) as exc:
            _positioned_pipeline(create_default_registry(), sm).run_to_ast(analysis)
        errors = exc.value.errors
        assert any("Cyclic dependency detected" in d.message for d in errors)
        self_ref = next(d for d in errors if "Cyclic dependency detected" in d.message)
        assert self_ref.position is not None

    def test_param_validation_error_positioned(self) -> None:
        analysis, sm = parse_with_positions("ema := ema { bogus: 20 }", name="demo")
        with pytest.raises(CompilationError) as exc:
            _positioned_pipeline(create_default_registry(), sm).run_to_ast(analysis)
        assert exc.value.errors[0].position == SourcePosition(1, 14)

    def test_expansion_empty_choice_positioned(self) -> None:
        analysis = Analysis(
            name="demo",
            version="1.0",
            definitions=(
                Definition(
                    name="ema",
                    provider="ema",
                    parameters=(Parameter(name="period", value=Choice([])),),
                ),
            ),
        )
        sm = SourceMap(
            definitions={"ema": SourcePosition(3, 1)},
            parameters={("ema", "period"): SourcePosition(3, 14)},
        )
        with pytest.raises(CompilationError) as exc:
            expand(analysis, sm)
        assert exc.value.errors[0].position == SourcePosition(3, 14)

    def test_multi_error_reporting(self) -> None:
        analysis = Analysis(
            name="bad",
            version="1.0",
            definitions=(
                Definition(name="a", provider="nope"),
                Definition(name="b", provider="nope2"),
            ),
        )
        sm = SourceMap(
            definitions={"a": SourcePosition(1, 1), "b": SourcePosition(2, 1)},
            source="a := nope { }\nb := nope2 { }",
        )
        with pytest.raises(CompilationError) as exc:
            ValidationPass(sm).run(analysis)
        errors = exc.value.errors
        assert len(errors) == 2
        positions = {d.node_name: d.position for d in errors}
        assert positions["a"] == SourcePosition(1, 1)
        assert positions["b"] == SourcePosition(2, 1)
        rendered = format_errors(errors, sm.source)
        assert "2 errors:" in rendered
        assert "1:1: error:" in rendered
        assert "2:1: error:" in rendered

    def test_without_source_map_positions_none(self) -> None:
        analysis = Analysis(
            name="bad",
            version="1.0",
            definitions=(Definition(name="a", provider="nope"),),
        )
        with pytest.raises(CompilationError) as exc:
            ValidationPass().run(analysis)
        assert exc.value.errors[0].position is None


class TestCompileDsl:
    def test_valid_spec_compiles(self) -> None:
        spec = """
        ema20 := ema { period: 20 }
        ema50 := ema { period: 50 }
        trend := trend { ema_20: ema20, ema_50: ema50 }
        """
        graphs = ASTCompiler.compile_dsl(spec, name="s")
        assert len(graphs) == 1
        from marketatlas.analysis.graph import AnalysisGraph

        assert isinstance(graphs[0], AnalysisGraph)

    def test_choice_spec_expands(self) -> None:
        graphs = ASTCompiler.compile_dsl(
            "ema20 := ema { period: <20 | 50> }\natr := atr { period: 14 }", name="s"
        )
        assert len(graphs) == 2

    def test_unknown_param_positioned(self) -> None:
        source = "ema := ema { bogus: 20 }"
        with pytest.raises(CompilationError) as exc:
            ASTCompiler.compile_dsl(source, name="s")
        error = exc.value.errors[0]
        assert error.position == SourcePosition(1, 14)
        assert format_diagnostic(error, source).startswith("1:14: error:")

    def test_parse_error_propagates_positioned(self) -> None:
        with pytest.raises(DslParseError) as exc:
            ASTCompiler.compile_dsl("ema := ghost { period: 20 }", name="s")
        assert exc.value.position == SourcePosition(1, 8)

    def test_lexer_error_propagates_positioned(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            ASTCompiler.compile_dsl("ema := ema { period: <20 }", name="s")
        assert exc.value.position == SourcePosition(1, 22)

    def test_unknown_param_choice_leaf_positioned(self) -> None:
        source = "x := ema { period: <20 | 50>, bogus: 5 }"
        with pytest.raises(CompilationError) as exc:
            ASTCompiler.compile_dsl(source, name="s")
        bogus_error = next(d for d in exc.value.errors if "bogus" in d.message)
        assert bogus_error.position == SourcePosition(1, source.index("bogus") + 1)

    def test_deterministic_error_positions(self) -> None:
        source = "ema := ema { bogus: 20 }"
        for _ in range(3):
            with pytest.raises(CompilationError) as exc:
                ASTCompiler.compile_dsl(source, name="s")
            assert exc.value.errors[0].position == SourcePosition(1, 14)
