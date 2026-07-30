import pytest
from marketatlas.analysis.ast.models import Analysis, Binding, Definition, Parameter, Provider
from marketatlas.analysis.ast.validation import DiagnosticSeverity, ValidationResult, validate


def _p(name: str) -> Provider:
    """Quick provider factory for tests."""
    return Provider(name=name, capability="", category="analyzer", impl=name)


def _ps(*names: str) -> tuple[Provider, ...]:
    return tuple(_p(n) for n in names)


class TestValidationResult:
    def test_ok(self) -> None:
        r = ValidationResult.ok()
        assert r.is_valid
        assert r.errors == ()
        assert r.warnings == ()

    def test_is_valid_false_when_errors(self) -> None:
        r = ValidationResult(is_valid=False, errors=(1,), warnings=())  # type: ignore[arg-type]
        assert not r.is_valid


def _providers() -> tuple[Provider, ...]:
    return (
        Provider(name="EMAAnalyzer", capability="ema", category="analyzer", impl="EMAAnalyzer"),
        Provider(name="ATRAnalyzer", capability="atr", category="analyzer", impl="ATRAnalyzer"),
        Provider(
            name="TrendAnalyzer", capability="trend", category="analyzer", impl="TrendAnalyzer"
        ),
        Provider(
            name="SwingStructureAnalyzer",
            capability="swing",
            category="analyzer",
            impl="SwingStructureAnalyzer",
        ),
        Provider(
            name="PullbackSignal", capability="signal", category="signal", impl="PullbackSignal"
        ),
        Provider(name="RiskEngine", capability="risk", category="risk", impl="RiskEngine"),
        Provider(
            name="Normalizer", capability="normalize", category="transformer", impl="Normalizer"
        ),
    )


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
            providers=_providers(),
            definitions=(Definition(name="ema20", provider="EMAAnalyzer"),),
        )
        r = validate(a)
        assert r.is_valid

    def test_multiple_definitions_no_bindings(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_providers(),
            definitions=(
                Definition(name="ema20", provider="EMAAnalyzer"),
                Definition(name="atr14", provider="ATRAnalyzer"),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_with_bindings(self) -> None:
        atr = Definition(
            name="atr14",
            provider="ATRAnalyzer",
            parameters=(Parameter(name="period", value=14),),
        )
        swing = Definition(
            name="swing",
            provider="SwingStructureAnalyzer",
            bindings=(Binding(source="atr14", output="atr_14", target="swing", input="atr"),),
        )
        a = Analysis(name="test", version="1.0.0", providers=_providers(), definitions=(atr, swing))
        r = validate(a)
        assert r.is_valid

    def test_signal_type(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_providers(),
            definitions=(Definition(name="sig", provider="PullbackSignal"),),
        )
        r = validate(a)
        assert r.is_valid

    def test_risk_type(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_providers(),
            definitions=(Definition(name="risk", provider="RiskEngine"),),
        )
        r = validate(a)
        assert r.is_valid

    def test_transformer_type(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_providers(),
            definitions=(Definition(name="norm", provider="Normalizer"),),
        )
        r = validate(a)
        assert r.is_valid

    def test_definition_with_metadata(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_providers(),
            definitions=(
                Definition(
                    name="ema20",
                    provider="EMAAnalyzer",
                    metadata={"key": "val"},
                ),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_full_strategy(self) -> None:
        ema = Definition(
            name="ema20",
            provider="EMAAnalyzer",
            parameters=(Parameter(name="period", value=20),),
        )
        atr = Definition(
            name="atr14",
            provider="ATRAnalyzer",
            parameters=(Parameter(name="period", value=14),),
        )
        swing = Definition(
            name="swing",
            provider="SwingStructureAnalyzer",
            bindings=(Binding(source="atr14", output="atr_14", target="swing", input="atr"),),
        )
        signal = Definition(
            name="signal",
            provider="PullbackSignal",
            bindings=(
                Binding(source="swing", output="pullback", target="signal", input="pullback"),
                Binding(source="ema20", output="ema_20", target="signal", input="trend"),
            ),
        )
        a = Analysis(
            name="pullback_4swing",
            version="1.0.0",
            providers=_providers(),
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
            providers=_providers(),
            definitions=(
                Definition(name="dup", provider="EMAAnalyzer"),
                Definition(name="dup", provider="ATRAnalyzer"),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert r.errors[0].severity == DiagnosticSeverity.ERROR
        assert "Duplicate" in r.errors[0].message
        assert "dup" in r.errors[0].message
        assert r.errors[0].node_name == "dup"


class TestUnknownProvider:
    def test_unknown_provider(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(Definition(name="bad", provider="NoSuchProvider"),),
        )
        r = validate(a)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert "Unknown provider" in r.errors[0].message
        assert r.errors[0].severity == DiagnosticSeverity.ERROR
        assert r.errors[0].node_name == "bad"

    def test_unknown_provider_with_valid_one(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_providers(),
            definitions=(
                Definition(name="good", provider="EMAAnalyzer"),
                Definition(name="bad", provider="NoSuchProvider"),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        provider_errors = [e for e in r.errors if "Unknown provider" in e.message]
        assert len(provider_errors) == 1

    def test_empty_provider_is_invalid(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(Definition(name="x", provider=""),),
        )
        r = validate(a)
        assert not r.is_valid


class TestSelfReferencingBinding:
    def test_self_referencing(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_ps("A"),
            definitions=(
                Definition(
                    name="a",
                    provider="A",
                    bindings=(Binding(source="a", output="x", target="a", input="y"),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        assert len(r.errors) == 1
        assert "Self-referencing" in r.errors[0].message
        assert r.errors[0].severity == DiagnosticSeverity.ERROR

    def test_no_provider_needed_for_self_ref_check(self) -> None:
        """Self-referencing binding check works alongside empty provider error."""
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="a",
                    provider="",
                    bindings=(Binding(source="a", output="x", target="a", input="y"),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        self_ref = [e for e in r.errors if "Self-referencing" in e.message]
        assert len(self_ref) == 1
        empty_prov = [e for e in r.errors if "empty provider" in e.message]
        assert len(empty_prov) == 1


class TestUnknownReferences:
    def test_unknown_source(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="b",
                    provider="B",
                    bindings=(Binding(source="unknown", output="x", target="b", input="y"),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        source_errors = [e for e in r.errors if "Unknown source" in e.message]
        assert len(source_errors) == 1

    def test_unknown_target(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="a",
                    provider="A",
                    bindings=(Binding(source="a", output="x", target="unknown", input="y"),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        target_errors = [e for e in r.errors if "Unknown target" in e.message]
        assert len(target_errors) == 1

    def test_both_unknown(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_ps("C"),
            definitions=(
                Definition(
                    name="c",
                    provider="C",
                    bindings=(Binding(source="x", output="o", target="y", input="i"),),
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
            providers=_ps("A", "B"),
            definitions=(
                Definition(
                    name="a",
                    provider="A",
                    bindings=(Binding(source="b", output="x", target="a", input="y"),),
                ),
                Definition(
                    name="b",
                    provider="B",
                    bindings=(Binding(source="a", output="x", target="b", input="y"),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        cycle_errors = [e for e in r.errors if "Cyclic" in e.message]
        assert len(cycle_errors) >= 1

    def test_indirect_cycle(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_ps("A", "B", "C"),
            definitions=(
                Definition(
                    name="a",
                    provider="A",
                    bindings=(Binding(source="b", output="x", target="a", input="y"),),
                ),
                Definition(
                    name="b",
                    provider="B",
                    bindings=(Binding(source="c", output="x", target="b", input="y"),),
                ),
                Definition(
                    name="c",
                    provider="C",
                    bindings=(Binding(source="a", output="x", target="c", input="y"),),
                ),
            ),
        )
        r = validate(a)
        assert not r.is_valid
        cycle_errors = [e for e in r.errors if "Cyclic" in e.message]
        assert len(cycle_errors) >= 1

    def test_no_cycle_with_valid_dag(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_ps("A", "B", "C"),
            definitions=(
                Definition(name="a", provider="A"),
                Definition(
                    name="b",
                    provider="B",
                    bindings=(Binding(source="a", output="x", target="b", input="y"),),
                ),
                Definition(
                    name="c",
                    provider="C",
                    bindings=(Binding(source="b", output="x", target="c", input="y"),),
                ),
            ),
        )
        r = validate(a)
        assert r.is_valid

    def test_fork_graph_no_cycle(self) -> None:
        src = Definition(name="src", provider="A")
        b1 = Definition(
            name="b1",
            provider="B1",
            bindings=(Binding(source="src", output="x", target="b1", input="y"),),
        )
        b2 = Definition(
            name="b2",
            provider="B2",
            bindings=(Binding(source="src", output="x", target="b2", input="y"),),
        )
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_ps("A", "B1", "B2"),
            definitions=(src, b1, b2),
        )
        r = validate(a)
        assert r.is_valid


class TestUnusedDefinitions:
    def test_unused_definition_warning(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_ps("A", "B", "C"),
            definitions=(
                Definition(name="used", provider="A"),
                Definition(name="unused", provider="B"),
                Definition(
                    name="ref",
                    provider="C",
                    bindings=(Binding(source="used", output="x", target="ref", input="y"),),
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
            providers=_ps("A", "B"),
            definitions=(
                Definition(name="a", provider="A"),
                Definition(name="b", provider="B"),
            ),
        )
        r = validate(a)
        assert r.is_valid
        assert len(r.warnings) == 2

    def test_no_warning_when_used(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_ps("A", "B"),
            definitions=(
                Definition(name="a", provider="A"),
                Definition(
                    name="b",
                    provider="B",
                    bindings=(Binding(source="a", output="x", target="b", input="y"),),
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
            providers=_ps("A"),
            definitions=(Definition(name="only", provider="A"),),
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
                Definition(name="bad_prov", provider="NoSuchProvider"),
                Definition(name="dup", provider="A"),
                Definition(name="dup", provider="B"),
                Definition(
                    name="self_ref",
                    provider="C",
                    bindings=(
                        Binding(source="self_ref", output="o", target="self_ref", input="i"),
                    ),
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
                Definition(name="bad_prov", provider="NoSuchProvider"),
                Definition(name="unused", provider="A"),
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
            node_type="definition",
        )
        assert d.message == "test error"
        assert d.severity == DiagnosticSeverity.ERROR
        assert d.node_name == "ema20"
        assert d.node_type == "definition"

    def test_diagnostic_frozen(self) -> None:
        from marketatlas.analysis.ast.validation import Diagnostic

        d = Diagnostic(
            message="m",
            severity=DiagnosticSeverity.WARNING,
            node_name="n",
            node_type="t",
        )
        with pytest.raises(AttributeError):
            d.message = "new"  # type: ignore[misc]
