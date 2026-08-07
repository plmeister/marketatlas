"""Backlog 058: provider contract metadata — inputs/outputs.

The registry derives a ``ProviderContract`` from each analyzer's runtime
``requires()``/``produces()`` at registration time (default constructor
arguments) and exposes it keyed by both provider name and capability. This is
the fact-level contract the DSL shorthand disambiguation (backlog 057) and
later binding validation consume.
"""

from marketatlas.analysis.ast.registry import (
    ProviderContract,
    ProviderRegistry,
    create_default_registry,
)


class _Opaque:
    """No requires()/produces() — represents signals, risk engines."""


class _Bare:
    def requires(self) -> tuple[object, ...]:
        return ()

    def produces(self) -> tuple[object, ...]:
        return ()


class _Broken:
    def __init__(self) -> None:
        raise RuntimeError("cannot construct with defaults")

    def requires(self) -> tuple[object, ...]:
        return ()

    def produces(self) -> tuple[object, ...]:
        return ()


class TestContractDerivation:
    def test_derives_inputs_and_outputs(self) -> None:
        registry = create_default_registry()
        contract = registry.contract("trend")
        assert contract == ProviderContract(inputs=("ema_20", "ema_50"), outputs=("trend",))

    def test_builtin_analyzer_contracts(self) -> None:
        registry = create_default_registry()
        expected = {
            "ema": ("ema_20",),
            "atr": ("atr_14",),
            "trend": ("trend",),
            "swingstructure": ("swing_structure",),
            "swings": ("swing",),
            "sr": ("sr",),
            "pullbackpattern": ("pullback_pattern",),
        }
        for capability, outputs in expected.items():
            contract = registry.contract(capability)
            assert contract is not None
            assert contract.outputs == outputs, f"capability {capability}"

    def test_signal_and_risk_have_empty_contracts(self) -> None:
        registry = create_default_registry()
        for capability in ("generate_signal", "manage_risk"):
            assert registry.contract(capability) == ProviderContract()

    def test_contract_keyed_by_provider_name_too(self) -> None:
        registry = create_default_registry()
        by_capability = registry.contract("trend")
        by_name = registry.contract("TrendAnalyzer")
        assert by_name == by_capability

    def test_detector_inputs_from_requires(self) -> None:
        registry = create_default_registry()
        contract = registry.contract("pullbackpattern")
        assert contract is not None
        assert contract.inputs == ("swing_structure",)

    def test_unknown_key_returns_none(self) -> None:
        registry = create_default_registry()
        assert registry.contract("nope") is None

    def test_manual_contract_registration(self) -> None:
        registry = create_default_registry()
        registry.register_contract("opaque_cap", ProviderContract(inputs=("x",), outputs=("y",)))
        assert registry.contract("opaque_cap") == ProviderContract(inputs=("x",), outputs=("y",))


class TestOpaqueAndFragileClasses:
    def test_opaque_class_empty_contract(self) -> None:
        registry = ProviderRegistry()
        registry.register("opaque", _Opaque)
        assert registry.contract("opaque") == ProviderContract()

    def test_class_without_contract_methods_skips_instantiation(self) -> None:
        registry = ProviderRegistry()
        registry.register("bare", _Bare)
        assert registry.contract("bare") == ProviderContract(inputs=(), outputs=())

    def test_unconstructable_class_empty_contract(self) -> None:
        registry = ProviderRegistry()
        registry.register("broken", _Broken)
        assert registry.contract("broken") == ProviderContract()

    def test_register_class_directly_derives_contract(self) -> None:
        registry = ProviderRegistry()
        registry.register(_Bare)
        assert registry.contract("_Bare") == ProviderContract(inputs=(), outputs=())


class TestCapabilities:
    def test_lists_all_capabilities_sorted(self) -> None:
        registry = create_default_registry()
        assert registry.capabilities() == (
            "atr",
            "atr_series",
            "ema",
            "generate_signal",
            "manage_risk",
            "pullbackpattern",
            "sr",
            "swings",
            "swingstructure",
            "timeframe",
            "trend",
        )
