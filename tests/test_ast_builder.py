import pytest
from marketatlas.analysis.ast.builder import AnalysisBuilder
from marketatlas.analysis.ast.expressions import LiteralExpression, ReferenceExpression
from marketatlas.analysis.ast.models import Parameter


class TestAnalysisBuilder:
    def test_minimal_build(self) -> None:
        analysis = AnalysisBuilder("test", "1.0.0").build()
        assert analysis.name == "test"
        assert analysis.version == "1.0.0"
        assert analysis.definitions == ()
        assert analysis.providers == ()
        assert analysis.metadata is None

    def test_single_definition(self) -> None:
        analysis = (
            AnalysisBuilder("test", "1.0.0").define("ema20", "analyzer", "EMAAnalyzer").build()
        )
        assert len(analysis.definitions) == 1
        d = analysis.definitions[0]
        assert d.name == "ema20"
        assert d.provider == "EMAAnalyzer"
        assert d.parameters == ()

    def test_auto_creates_providers(self) -> None:
        analysis = (
            AnalysisBuilder("test", "1.0.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .define("atr14", "analyzer", "ATRAnalyzer")
            .build()
        )
        assert len(analysis.providers) == 2
        provider_names = {p.name for p in analysis.providers}
        assert provider_names == {"EMAAnalyzer", "ATRAnalyzer"}
        ema_prov = next(p for p in analysis.providers if p.name == "EMAAnalyzer")
        assert ema_prov.category == "analyzer"
        assert ema_prov.impl == "EMAAnalyzer"
        assert ema_prov.capability == ""

    def test_multiple_definitions_same_provider(self) -> None:
        a = (
            AnalysisBuilder("multi", "1.0.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define("ema50", "analyzer", "EMAAnalyzer")
            .with_param("period", 50)
            .build()
        )
        assert len(a.definitions) == 2
        assert len(a.providers) == 1
        assert a.providers[0].name == "EMAAnalyzer"

    def test_multiple_definitions(self) -> None:
        a = (
            AnalysisBuilder("multi", "1.0.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .define("atr14", "analyzer", "ATRAnalyzer")
            .define("swing", "analyzer", "SwingStructureAnalyzer")
            .build()
        )
        assert len(a.definitions) == 3
        assert [d.name for d in a.definitions] == ["ema20", "atr14", "swing"]

    def test_with_params(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .with_param("source", "close")
            .build()
        )
        assert len(a.definitions[0].parameters) == 2
        assert a.definitions[0].parameters[0] == Parameter(
            name="period", value=LiteralExpression(20)
        )
        assert a.definitions[0].parameters[1] == Parameter(
            name="source", value=LiteralExpression("close")
        )

    def test_with_reference(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0.0")
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .define("swing", "analyzer", "SwingStructureAnalyzer")
            .with_param("lookback", 100)
            .with_reference("atr_14", "atr14")
            .build()
        )
        swing = a.definitions[1]
        assert len(swing.parameters) == 2
        assert swing.parameters[1] == Parameter(
            name="atr_14", value=ReferenceExpression("atr14")
        )

    def test_params_and_references(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .with_param("source", "close")
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .define("swing", "analyzer", "SwingStructureAnalyzer")
            .with_param("lookback", 100)
            .with_param("min_separation_atr", 1.5)
            .with_reference("atr_14", "atr14")
            .build()
        )
        ema = a.definitions[0]
        assert ema.name == "ema20"
        assert ema.parameters[0].value == 20
        atr = a.definitions[1]
        assert atr.name == "atr14"
        assert atr.parameters[0].value == 14
        swing = a.definitions[2]
        assert swing.name == "swing"
        assert len(swing.parameters) == 3
        assert swing.parameters[2].value == ReferenceExpression("atr14")

    def test_with_metadata(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0.0")
            .with_metadata("author", "Scott")
            .with_metadata("description", "test strategy")
            .build()
        )
        assert a.metadata == {"author": "Scott", "description": "test strategy"}

    def test_duplicate_definition_raises(self) -> None:
        builder = AnalysisBuilder("test", "1.0.0")
        builder.define("ema20", "analyzer", "EMAAnalyzer")
        with pytest.raises(ValueError, match="Duplicate definition name: ema20"):
            builder.define("ema20", "analyzer", "EMAAnalyzer")

    def test_with_reference_unknown_source_raises(self) -> None:
        builder = AnalysisBuilder("test", "1.0.0").define(
            "swing", "analyzer", "SwingStructureAnalyzer"
        )
        with pytest.raises(ValueError, match="Unknown source definition: atr14"):
            builder.with_reference("atr_14", "atr14")

    def test_immutable_analysis(self) -> None:
        a = AnalysisBuilder("test", "1.0.0").define("d", "a", "I").build()
        with pytest.raises(AttributeError):
            a.name = "new"  # type: ignore[misc]

    def test_chainable_return_types(self) -> None:
        builder = AnalysisBuilder("test", "1.0.0")
        result = builder.with_metadata("k", "v")
        assert result is builder

    def test_define_with_provider_only(self) -> None:
        a = (
            AnalysisBuilder("test", "1.0.0")
            .define_provider("EMAAnalyzer", "compute_ema", "analyzer", "EMAAnalyzer")
            .define("ema20", "EMAAnalyzer")
            .with_param("period", 20)
            .build()
        )
        assert len(a.definitions) == 1
        assert a.definitions[0].name == "ema20"
        assert a.definitions[0].provider == "EMAAnalyzer"
        assert a.definitions[0].parameters[0].value == 20
        ema_prov = next(p for p in a.providers if p.name == "EMAAnalyzer")
        assert ema_prov.capability == "compute_ema"

    def test_define_with_provider_only_unknown_raises(self) -> None:
        builder = AnalysisBuilder("test", "1.0.0")
        with pytest.raises(ValueError, match="Unknown provider: NoSuchProvider"):
            builder.define("x", "NoSuchProvider")

    def test_mixed_define_styles(self) -> None:
        a = (
            AnalysisBuilder("mixed", "1.0.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .define_provider("ATRAnalyzer", "compute_atr", "analyzer", "ATRAnalyzer")
            .define("atr14", "ATRAnalyzer")
            .with_param("period", 14)
            .build()
        )
        assert len(a.definitions) == 2
        assert len(a.providers) == 2

    def test_full_strategy_from_sketch(self) -> None:
        analysis = (
            AnalysisBuilder("pullback_4swing", "1.0.0")
            .define("ema20", "analyzer", "EMAAnalyzer")
            .with_param("period", 20)
            .with_param("source", "close")
            .define("atr14", "analyzer", "ATRAnalyzer")
            .with_param("period", 14)
            .define("swing", "analyzer", "SwingStructureAnalyzer")
            .with_param("lookback", 100)
            .with_param("min_separation_atr", 1.5)
            .with_reference("atr_14", "atr14")
            .define("signal", "signal", "PullbackSignal")
            .with_param("min_strength", 0.5)
            .with_reference("four_swing_pullback", "swing")
            .with_reference("trend", "ema20")
            .build()
        )
        assert analysis.name == "pullback_4swing"
        assert analysis.version == "1.0.0"
        assert len(analysis.definitions) == 4

        ema20 = analysis.definitions[0]
        assert ema20.provider == "EMAAnalyzer"
        assert ema20.parameters[0].value == 20

        atr14 = analysis.definitions[1]
        assert atr14.provider == "ATRAnalyzer"

        swing = analysis.definitions[2]
        assert swing.provider == "SwingStructureAnalyzer"
        assert len(swing.parameters) == 3
        assert swing.parameters[2].value == ReferenceExpression("atr14")

        signal = analysis.definitions[3]
        assert signal.provider == "PullbackSignal"
        assert len(signal.parameters) == 3
        assert signal.parameters[1] == Parameter(
            name="four_swing_pullback", value=ReferenceExpression("swing")
        )
        assert signal.parameters[2] == Parameter(
            name="trend", value=ReferenceExpression("ema20")
        )
