import pytest

from marketatlas.analysis.ast.models import Analysis, Binding, Definition, Parameter
from marketatlas.analysis.ast.validation import DiagnosticSeverity, ValidationResult, validate


class TestValidationResult:
    def test_ok(self) -> None:
        r = ValidationResult.ok()
        assert r.is_valid
        assert r.errors == ()
        assert r.warnings == ()

    def test_is_valid_false_when_errors(self) -> None:
        r = ValidationResult(is_valid=False, errors=(1,), warnings=())  # type: ignore[arg-type]
        assert not r.is_valid


class TestValidAST:
    def test_minimal(self) -> None:
        a = Analysis(name="test", version="1.0.0")
        r = validate(a)
        assert r.is_valid
        assert r.errors == ()
        assert r.warnings == ()

    def test_single_definition(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="ema20", type="analyzer", impl="EMAAnalyzer"),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_multiple_definitions_no_bindings(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="ema20", type="analyzer", impl="EMAAnalyzer"),
                Definition(name="atr14", type="analyzer", impl="ATRAnalyzer"),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_with_bindings(self) -> None:
        atr = Definition(
            name="atr14", type="analyzer", impl="ATRAnalyzer",
            parameters=(Parameter(name="period", value=14),),
        )
        swing = Definition(
            name="swing", type="analyzer", impl="SwingStructureAnalyzer",
            bindings=(Binding(
                source="atr14", output="atr_14", target="swing", input="atr"
            ),),
        )
        a = Analysis(name="test", version="1.0.0", definitions=(atr, swing))
        r = validate(a)
        assert r.is_valid

    def test_signal_type(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="sig", type="signal", impl="PullbackSignal"),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_risk_type(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="risk", type="risk", impl="RiskEngine"),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_transformer_type(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="norm", type="transformer", impl="Normalizer"
                ),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_definition_with_metadata(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="ema20", type="analyzer", impl="EMAAnalyzer",
                    metadata={"key": "val"},
                ),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_full_strategy(self) -> None:
        ema = Definition(
            name="ema20", type="analyzer", impl="EMAAnalyzer",
            parameters=(Parameter(name="period", value=20),),
        )
        atr = Definition(
            name="atr14", type="analyzer", impl="ATRAnalyzer",
            parameters=(Parameter(name="period", value=14),),
        )
        swing = Definition(
            name="swing", type="analyzer", impl="SwingStructureAnalyzer",
            bindings=(Binding(
                source="atr14", output="atr_14", target="swing", input="atr"
            ),),
        )
        signal = Definition(
            name="signal", type="signal", impl="PullbackSignal",
            bindings=(
                Binding(
                    source="swing", output="pullback",
                    target="signal", input="pullback"
                ),
                Binding(
                    source="ema20", output="ema_20",
                    target="signal", input="trend"
                ),
            ),
        )
        a = Analysis(
            name="pullback_4swing", version="1.0.0",
            definitions=(ema, atr, swing, signal),
        )
        r = validate(a)
        assert r.is_valid
        assert r.warnings == ()


class TestDuplicateNames:
    def test_raises_error(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="dup", type="analyzer", impl="EMAAnalyzer"
                ),
                Definition(
                    name="dup", type="analyzer", impl="ATRAnalyzer"
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert r.errors[0].severity == DiagnosticSeverity.ERROR
        assert "Duplicate" in r.errors[0].message
        assert "dup" in r.errors[0].message
        assert r.errors[0].node_name == "dup"


class TestUnknownType:
    def test_unknown_type(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="bad", type="watcher", impl="Something"
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert "Unknown definition type" in r.errors[0].message
        assert r.errors[0].severity == DiagnosticSeverity.ERROR
        assert r.errors[0].node_name == "bad"
        assert r.errors[0].node_type == "watcher"

    def test_unknown_type_with_valid_def(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="good", type="analyzer", impl="EMAAnalyzer"
                ),
                Definition(
                    name="bad", type="invalid", impl="Something"
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        type_errors = [
            e for e in r.errors if "Unknown definition type" in e.message
        ]
        assert len(type_errors) == 1

    def test_empty_type_is_invalid(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="x", type="", impl="A"),
            ),
        )
        r = validate(a)
        assert not r.is_valid


class TestSelfReferencingBinding:
    def test_self_referencing(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="a", type="analyzer", impl="A",
                    bindings=(Binding(
                        source="a", output="x", target="a", input="y"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert "Self-referencing" in r.errors[0].message
        assert r.errors[0].severity == DiagnosticSeverity.ERROR


class TestUnknownReferences:
    def test_unknown_source(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="b", type="analyzer", impl="B",
                    bindings=(Binding(
                        source="unknown", output="x",
                        target="b", input="y"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        source_errors = [
            e for e in r.errors if "Unknown source" in e.message
        ]
        assert len(source_errors) == 1

    def test_unknown_target(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="a", type="analyzer", impl="A",
                    bindings=(Binding(
                        source="a", output="x",
                        target="unknown", input="y"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        target_errors = [
            e for e in r.errors if "Unknown target" in e.message
        ]
        assert len(target_errors) == 1

    def test_both_unknown(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="c", type="analyzer", impl="C",
                    bindings=(Binding(
                        source="x", output="o",
                        target="y", input="i"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        assert len(r.errors) == 2


class TestCycleDetection:
    def test_direct_cycle(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="a", type="analyzer", impl="A",
                    bindings=(Binding(
                        source="b", output="x",
                        target="a", input="y"
                    ),),
                ),
                Definition(
                    name="b", type="analyzer", impl="B",
                    bindings=(Binding(
                        source="a", output="x",
                        target="b", input="y"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        cycle_errors = [
            e for e in r.errors if "Cyclic" in e.message
        ]
        assert len(cycle_errors) >= 1

    def test_indirect_cycle(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="a", type="analyzer", impl="A",
                    bindings=(Binding(
                        source="b", output="x",
                        target="a", input="y"
                    ),),
                ),
                Definition(
                    name="b", type="analyzer", impl="B",
                    bindings=(Binding(
                        source="c", output="x",
                        target="b", input="y"
                    ),),
                ),
                Definition(
                    name="c", type="analyzer", impl="C",
                    bindings=(Binding(
                        source="a", output="x",
                        target="c", input="y"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        cycle_errors = [
            e for e in r.errors if "Cyclic" in e.message
        ]
        assert len(cycle_errors) >= 1

    def test_no_cycle_with_valid_dag(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="a", type="analyzer", impl="A"),
                Definition(
                    name="b", type="analyzer", impl="B",
                    bindings=(Binding(
                        source="a", output="x",
                        target="b", input="y"
                    ),),
                ),
                Definition(
                    name="c", type="analyzer", impl="C",
                    bindings=(Binding(
                        source="b", output="x",
                        target="c", input="y"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_fork_graph_no_cycle(self) -> None:
        src = Definition(name="src", type="analyzer", impl="A")
        b1 = Definition(
            name="b1", type="analyzer", impl="B1",
            bindings=(Binding(
                source="src", output="x", target="b1", input="y"
            ),),
        )
        b2 = Definition(
            name="b2", type="analyzer", impl="B2",
            bindings=(Binding(
                source="src", output="x", target="b2", input="y"
            ),),
        )
        a = Analysis(
            name="test", version="1.0.0",
            definitions=(src, b1, b2),
        )
        r = validate(a)
        assert r.is_valid


class TestUnusedDefinitions:
    def test_unused_definition_warning(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="used", type="analyzer", impl="A"),
                Definition(name="unused", type="analyzer", impl="B"),
                Definition(
                    name="ref", type="analyzer", impl="C",
                    bindings=(Binding(
                        source="used", output="x",
                        target="ref", input="y"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert r.is_valid
        assert len(r.warnings) == 1
        assert "unused" in r.warnings[0].message.lower()
        assert r.warnings[0].severity == DiagnosticSeverity.WARNING
        assert r.warnings[0].node_name == "unused"

    def test_multiple_unused(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="a", type="analyzer", impl="A"),
                Definition(name="b", type="analyzer", impl="B"),
            ),
        )
        r = validate(a)
        assert r.is_valid
        assert len(r.warnings) == 2

    def test_no_warning_when_used(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="a", type="analyzer", impl="A"),
                Definition(
                    name="b", type="analyzer", impl="B",
                    bindings=(Binding(
                        source="a", output="x",
                        target="b", input="y"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert r.is_valid
        assert r.warnings == ()

    def test_single_def_no_warning(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(name="only", type="analyzer", impl="A"),
            ),
        )
        r = validate(a)
        assert r.is_valid
        assert r.warnings == ()


class TestMultipleErrors:
    def test_multiple_errors_collected(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="bad_type", type="invalid", impl="X"
                ),
                Definition(
                    name="dup", type="analyzer", impl="A"
                ),
                Definition(
                    name="dup", type="analyzer", impl="B"
                ),
                Definition(
                    name="self_ref", type="analyzer", impl="C",
                    bindings=(Binding(
                        source="self_ref", output="o",
                        target="self_ref", input="i"
                    ),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        assert len(r.errors) >= 3

    def test_error_and_warning_together(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="bad_type", type="invalid", impl="X"
                ),
                Definition(
                    name="unused", type="analyzer", impl="A"
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        assert len(r.errors) >= 1
        assert len(r.warnings) >= 1


class TestDiagnostic:
    def test_diagnostic_construction(self) -> None:
        from marketatlas.analysis.ast.validation import Diagnostic
        d = Diagnostic(
            message="test error",
            severity=DiagnosticSeverity.ERROR,
            node_name="ema20",
            node_type="analyzer",
        )
        assert d.message == "test error"
        assert d.severity == DiagnosticSeverity.ERROR
        assert d.node_name == "ema20"
        assert d.node_type == "analyzer"

    def test_diagnostic_frozen(self) -> None:
        from marketatlas.analysis.ast.validation import Diagnostic
        d = Diagnostic(
            message="m", severity=DiagnosticSeverity.WARNING,
            node_name="n", node_type="t",
        )
        with pytest.raises(AttributeError):
            d.message = "new"  # type: ignore[misc]
