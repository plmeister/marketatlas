import pytest
from marketatlas.analysis.ast.expressions import LiteralExpression
from marketatlas.analysis.ast.models import Parameter, Provider
from marketatlas.analysis.ast.registry import (
    ProviderNotFoundError,
    ProviderRegistry,
    create_default_registry,
)


class _DummyAnalyzer:
    pass


class _OtherDummy:
    pass


class TestProviderRegistry:
    def test_register_and_resolve(self) -> None:
        r = ProviderRegistry()
        r.register("compute_ema", _DummyAnalyzer)
        provider = r.resolve("compute_ema")
        assert provider.name == "_DummyAnalyzer"
        assert provider.capability == "compute_ema"
        assert provider.category == "analyzer"
        assert provider.impl == "_DummyAnalyzer"

    def test_register_with_default_params(self) -> None:
        r = ProviderRegistry()
        r.register("compute_ema", _DummyAnalyzer, default_params={"period": 20})
        provider = r.resolve("compute_ema")
        assert len(provider.default_params) == 1
        assert provider.default_params[0].name == "period"
        assert provider.default_params[0].value == 20

    def test_register_with_category(self) -> None:
        r = ProviderRegistry()
        r.register("generate_signal", _DummyAnalyzer, category="signal")
        provider = r.resolve("generate_signal")
        assert provider.category == "signal"

    def test_resolve_unmatched_capability(self) -> None:
        r = ProviderRegistry()
        r.register("compute_ema", _DummyAnalyzer)
        with pytest.raises(ProviderNotFoundError) as exc:
            r.resolve("nonexistent")
        msg = str(exc.value)
        assert "nonexistent" in msg
        assert "compute_ema" in msg

    def test_resolve_empty_registry(self) -> None:
        r = ProviderRegistry()
        with pytest.raises(ProviderNotFoundError) as exc:
            r.resolve("anything")
        assert "anything" in str(exc.value)

    def test_resolve_ambiguous_match_picks_first(self, caplog: pytest.LogCaptureFixture) -> None:
        r = ProviderRegistry()
        r.register("compute_ma", _DummyAnalyzer)
        r.register("compute_ma", _OtherDummy)
        import logging

        caplog.set_level(logging.WARNING)
        provider = r.resolve("compute_ma")
        assert provider.name == "_DummyAnalyzer"
        assert len(caplog.records) == 1
        assert "Multiple providers" in caplog.records[0].message

    def test_resolve_ambiguous_no_warning_with_single(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        r = ProviderRegistry()
        r.register("compute_ema", _DummyAnalyzer)
        import logging

        caplog.set_level(logging.WARNING)
        r.resolve("compute_ema")
        assert len(caplog.records) == 0

    def test_list_providers_empty(self) -> None:
        r = ProviderRegistry()
        assert r.list_providers() == []

    def test_list_providers(self) -> None:
        r = ProviderRegistry()
        r.register("a", _DummyAnalyzer)
        r.register("b", _OtherDummy)
        providers = r.list_providers()
        assert len(providers) == 2
        caps = {p.capability for p in providers}
        assert caps == {"a", "b"}

    def test_register_provider_object(self) -> None:
        r = ProviderRegistry()
        p = Provider(
            name="CustomEMA",
            capability="compute_ema",
            category="analyzer",
            impl="CustomEMAAnalyzer",
            default_params=(Parameter(name="period", value=LiteralExpression(20)),),
        )
        r.register_provider(p)
        resolved = r.resolve("compute_ema")
        assert resolved.name == "CustomEMA"
        assert resolved.impl == "CustomEMAAnalyzer"
        assert resolved.default_params[0].value == 20

    def test_register_provider_via_register_method(self) -> None:
        r = ProviderRegistry()
        p = Provider(
            name="TestProv",
            capability="test_cap",
            category="analyzer",
            impl="TestImpl",
        )
        r.register(p)
        resolved = r.resolve("test_cap")
        assert resolved.name == "TestProv"

    def test_multiple_providers_same_capability(self) -> None:
        r = ProviderRegistry()
        r.register("compute_ema", _DummyAnalyzer)
        r.register("compute_ema", _OtherDummy)
        providers = r.list_providers()
        ema_providers = [p for p in providers if p.capability == "compute_ema"]
        assert len(ema_providers) == 2

    def test_resolve_params_ignored_in_matching(self) -> None:
        r = ProviderRegistry()
        r.register("compute_ema", _DummyAnalyzer, default_params={"period": 20})
        provider = r.resolve("compute_ema", {"period": 50})
        assert provider.default_params[0].value == 20

    def test_multiple_capabilities(self) -> None:
        r = ProviderRegistry()
        r.register("ema", _DummyAnalyzer)
        r.register("atr", _OtherDummy)
        assert r.resolve("ema").name == "_DummyAnalyzer"
        assert r.resolve("atr").name == "_OtherDummy"


class TestDefaultRegistry:
    def test_contains_all_builtin_analyzers(self) -> None:
        r = create_default_registry()
        expected_caps = [
            "ema",
            "atr",
            "atr_series",
            "trend",
            "swingstructure",
            "swings",
            "sr",
            "pullbackpattern",
            "generate_signal",
            "manage_risk",
            "timeframe",
        ]
        for cap in expected_caps:
            provider = r.resolve(cap)
            assert provider.capability == cap

    def test_list_providers_count(self) -> None:
        r = create_default_registry()
        providers = r.list_providers()
        assert len(providers) == 11

    def test_default_params_present(self) -> None:
        r = create_default_registry()
        ema = r.resolve("ema")
        assert len(ema.default_params) == 1
        assert ema.default_params[0].name == "period"
        assert ema.default_params[0].value == 20

        atr = r.resolve("atr")
        assert len(atr.default_params) == 1
        assert atr.default_params[0].name == "period"
        assert atr.default_params[0].value == 14

        swing = r.resolve("swingstructure")
        assert len(swing.default_params) == 1
        assert swing.default_params[0].name == "window"
        assert swing.default_params[0].value == 50

    def test_signal_provider(self) -> None:
        r = create_default_registry()
        signal = r.resolve("generate_signal")
        assert signal.category == "signal"

    def test_risk_provider(self) -> None:
        r = create_default_registry()
        risk = r.resolve("manage_risk")
        assert risk.category == "risk"


class TestDecoratorSyntax:
    def test_decorator_registers_class(self) -> None:
        r = ProviderRegistry()

        @r.register("compute_ema")
        class MyEMA:
            pass

        provider = r.resolve("compute_ema")
        assert provider.name == "MyEMA"
        assert provider.impl == "MyEMA"
        assert MyEMA.__name__ == "MyEMA"

    def test_decorator_with_default_params(self) -> None:
        r = ProviderRegistry()

        @r.register("compute_atr", default_params={"period": 14})
        class MyATR:
            pass

        provider = r.resolve("compute_atr")
        assert provider.name == "MyATR"
        assert len(provider.default_params) == 1
        assert provider.default_params[0].value == 14

    def test_decorator_with_category(self) -> None:
        r = ProviderRegistry()

        @r.register("sig", category="signal")
        class MySignal:
            pass

        provider = r.resolve("sig")
        assert provider.category == "signal"

    def test_class_as_capability_decorator(self) -> None:
        r = ProviderRegistry()

        @r.register
        class ImplicitCap:
            pass

        provider = r.resolve("ImplicitCap")
        assert provider.name == "ImplicitCap"
        assert provider.impl == "ImplicitCap"


class TestProviderNotFoundError:
    def test_is_lookup_error(self) -> None:
        assert issubclass(ProviderNotFoundError, LookupError)
        assert issubclass(ProviderNotFoundError, Exception)

    def test_message_format(self) -> None:
        r = ProviderRegistry()
        try:
            r.resolve("missing")
        except ProviderNotFoundError as e:
            msg = str(e)
            assert "missing" in msg
            assert "Available capabilities" in msg


class TestRoundTripCompatibility:
    def test_registry_provider_roundtrip(self) -> None:
        r = ProviderRegistry()
        r.register("cap", _DummyAnalyzer, default_params={"x": 1, "y": "z"})
        provider = r.resolve("cap")
        assert provider.name == "_DummyAnalyzer"
        assert provider.capability == "cap"
        assert provider.category == "analyzer"
        assert provider.impl == "_DummyAnalyzer"
        assert len(provider.default_params) == 2
        assert provider.default_params[0].name == "x"
        assert provider.default_params[0].value == 1
        assert provider.default_params[1].name == "y"
        assert provider.default_params[1].value == "z"
