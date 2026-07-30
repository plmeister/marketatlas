import pytest
from marketatlas.analysis.ast.models import (
    Analysis,
    BaseNode,
    Binding,
    Capability,
    Definition,
    Parameter,
    Provider,
)


class TestBaseNode:
    def test_default_construction(self) -> None:
        bn = BaseNode()
        assert bn.id == ""
        assert bn.metadata is None

    def test_custom_construction(self) -> None:
        bn = BaseNode(id="node1", metadata={"author": "test"})
        assert bn.id == "node1"
        assert bn.metadata == {"author": "test"}


class TestParameter:
    def test_construction(self) -> None:
        p = Parameter(name="period", value=20)
        assert p.name == "period"
        assert p.value == 20

    def test_frozen(self) -> None:
        p = Parameter(name="period", value=20)
        with pytest.raises(AttributeError):
            p.name = "new_name"  # type: ignore[misc]

    def test_string_value(self) -> None:
        p = Parameter(name="source", value="close")
        assert p.value == "close"

    def test_float_value(self) -> None:
        p = Parameter(name="threshold", value=1.5)
        assert p.value == 1.5


class TestCapability:
    def test_construction(self) -> None:
        c = Capability(
            id="compute_ema", description="EMA computation", required_params=("period", "source")
        )
        assert c.id == "compute_ema"
        assert c.description == "EMA computation"
        assert c.required_params == ("period", "source")

    def test_default_required_params(self) -> None:
        c = Capability(id="simple", description="simple cap")
        assert c.required_params == ()

    def test_frozen(self) -> None:
        c = Capability(id="c", description="c")
        with pytest.raises(AttributeError):
            c.id = "new"  # type: ignore[misc]


class TestProvider:
    def test_construction(self) -> None:
        p = Provider(
            name="EMAAnalyzer", capability="compute_ema", category="analyzer", impl="EMAAnalyzer"
        )
        assert p.name == "EMAAnalyzer"
        assert p.capability == "compute_ema"
        assert p.category == "analyzer"
        assert p.impl == "EMAAnalyzer"

    def test_with_default_params(self) -> None:
        params = (Parameter(name="period", value=20),)
        p = Provider(
            name="EMAAnalyzer", capability="compute_ema", category="analyzer",
            impl="EMAAnalyzer", default_params=params,
        )
        assert p.default_params == params

    def test_providers_with_same_capability(self) -> None:
        p1 = Provider(name="SMA", capability="compute_ma", category="analyzer", impl="SMAAnalyzer")
        p2 = Provider(name="EMA", capability="compute_ma", category="analyzer", impl="EMAAnalyzer")
        assert p1.capability == p2.capability

    def test_frozen(self) -> None:
        p = Provider(name="n", capability="c", category="a", impl="i")
        with pytest.raises(AttributeError):
            p.name = "new"  # type: ignore[misc]


class TestBinding:
    def test_construction(self) -> None:
        b = Binding(source="atr14", output="atr_14", target="swing", input="atr")
        assert b.source == "atr14"
        assert b.output == "atr_14"
        assert b.target == "swing"
        assert b.input == "atr"

    def test_frozen(self) -> None:
        b = Binding(source="a", output="x", target="b", input="y")
        with pytest.raises(AttributeError):
            b.source = "new"  # type: ignore[misc]


class TestDefinition:
    def test_minimal_construction(self) -> None:
        d = Definition(name="ema20", provider="EMAAnalyzer")
        assert d.name == "ema20"
        assert d.provider == "EMAAnalyzer"
        assert d.parameters == ()
        assert d.bindings == ()
        assert d.id == ""
        assert d.metadata is None

    def test_with_parameters(self) -> None:
        params = (Parameter(name="period", value=20), Parameter(name="source", value="close"))
        d = Definition(name="ema20", provider="EMAAnalyzer", parameters=params)
        assert len(d.parameters) == 2
        assert d.parameters[0].name == "period"
        assert d.parameters[1].value == "close"

    def test_with_bindings(self) -> None:
        bindings = (Binding(source="atr14", output="atr_14", target="swing", input="atr"),)
        d = Definition(name="swing", provider="SwingStructureAnalyzer", bindings=bindings)
        assert len(d.bindings) == 1
        assert d.bindings[0].source == "atr14"

    def test_with_metadata(self) -> None:
        d = Definition(name="t", provider="I", metadata={"key": "val"})
        assert d.metadata == {"key": "val"}

    def test_with_id(self) -> None:
        d = Definition(name="t", provider="I", id="def1")
        assert d.id == "def1"

    def test_frozen(self) -> None:
        d = Definition(name="t", provider="I")
        with pytest.raises(AttributeError):
            d.name = "new"  # type: ignore[misc]

    def test_equality(self) -> None:
        d1 = Definition(name="ema20", provider="EMAAnalyzer")
        d2 = Definition(name="ema20", provider="EMAAnalyzer")
        assert d1 == d2

    def test_inequality(self) -> None:
        d1 = Definition(name="ema20", provider="EMAAnalyzer")
        d2 = Definition(name="ema50", provider="EMAAnalyzer")
        assert d1 != d2


class TestAnalysis:
    def test_minimal_construction(self) -> None:
        a = Analysis(name="test_strategy", version="1.0.0")
        assert a.name == "test_strategy"
        assert a.version == "1.0.0"
        assert a.definitions == ()
        assert a.providers == ()
        assert a.id == ""
        assert a.metadata is None

    def test_with_definitions_and_providers(self) -> None:
        providers = (
            Provider(
                name="EMAAnalyzer",
                capability="compute_ema",
                category="analyzer",
                impl="EMAAnalyzer",
            ),
        )
        defs = (
            Definition(
                name="ema20",
                provider="EMAAnalyzer",
                parameters=(Parameter(name="period", value=20),),
            ),
        )
        a = Analysis(name="test", version="1.0", definitions=defs, providers=providers)
        assert len(a.definitions) == 1
        assert a.definitions[0].name == "ema20"
        assert a.definitions[0].provider == "EMAAnalyzer"
        assert a.providers[0].impl == "EMAAnalyzer"

    def test_with_metadata(self) -> None:
        a = Analysis(name="t", version="1.0", metadata={"author": "test"})
        assert a.metadata == {"author": "test"}

    def test_with_id(self) -> None:
        a = Analysis(name="t", version="1.0", id="analysis1")
        assert a.id == "analysis1"

    def test_frozen(self) -> None:
        a = Analysis(name="t", version="1.0")
        with pytest.raises(AttributeError):
            a.name = "new"  # type: ignore[misc]

    def test_round_trip_definition(self) -> None:
        params = (Parameter(name="period", value=20),)
        bindings = (Binding(source="a", output="x", target="b", input="y"),)
        d = Definition(name="ema20", provider="EMAAnalyzer", parameters=params, bindings=bindings)
        a = Analysis(name="test", version="1.0", definitions=(d,))
        restored = a.definitions[0]
        assert restored == d
        assert restored.parameters[0].value == 20
        assert restored.bindings[0].source == "a"

    def test_multiple_definitions(self) -> None:
        defs = tuple(
            Definition(name=f"d{i}", provider="Analyzer")
            for i in range(5)
        )
        a = Analysis(name="multi", version="1.0", definitions=defs)
        assert len(a.definitions) == 5
        assert [d.name for d in a.definitions] == ["d0", "d1", "d2", "d3", "d4"]


class TestComplexAnalysis:
    def test_full_strategy(self) -> None:
        providers = (
            Provider(
                name="EMAAnalyzer",
                capability="compute_ema",
                category="analyzer",
                impl="EMAAnalyzer",
            ),
            Provider(
                name="ATRAnalyzer",
                capability="compute_atr",
                category="analyzer",
                impl="ATRAnalyzer",
            ),
            Provider(
                name="SwingStructureAnalyzer",
                capability="detect_swings",
                category="analyzer",
                impl="SwingStructureAnalyzer",
            ),
        )
        analysis = Analysis(
            name="pullback_4swing",
            version="1.0.0",
            providers=providers,
            definitions=(
                Definition(
                    name="ema20",
                    provider="EMAAnalyzer",
                    parameters=(
                        Parameter(name="period", value=20),
                        Parameter(name="source", value="close"),
                    ),
                ),
                Definition(
                    name="atr14",
                    provider="ATRAnalyzer",
                    parameters=(Parameter(name="period", value=14),),
                ),
                Definition(
                    name="swing",
                    provider="SwingStructureAnalyzer",
                    parameters=(
                        Parameter(name="lookback", value=100),
                        Parameter(name="min_separation_atr", value=1.5),
                    ),
                    bindings=(
                        Binding(source="atr14", output="atr_14", target="swing", input="atr"),
                    ),
                ),
            ),
            metadata={"author": "Scott", "description": "4-swing pullback strategy"},
        )
        assert analysis.name == "pullback_4swing"
        assert analysis.version == "1.0.0"
        assert len(analysis.definitions) == 3
        assert analysis.metadata == {"author": "Scott", "description": "4-swing pullback strategy"}

        ema = analysis.definitions[0]
        assert ema.name == "ema20"
        assert ema.provider == "EMAAnalyzer"
        assert ema.parameters[0].value == 20

        swing = analysis.definitions[2]
        assert len(swing.bindings) == 1
        assert swing.bindings[0].source == "atr14"
        assert swing.bindings[0].output == "atr_14"
