from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from marketatlas.data.instrument import Instrument, InstrumentRegistry
from marketatlas.data.provider_names import DEFAULT_PROVIDER_ORDER
from marketatlas.data.types import Symbol


class TestInstrument:
    def test_basic_creation(self) -> None:
        inst = Instrument("EURUSD", "forex", "Euro / US Dollar")
        assert inst.canonical == "EURUSD"
        assert inst.asset_class == "forex"
        assert inst.description == "Euro / US Dollar"
        assert inst.providers == {}

    def test_with_providers(self) -> None:
        inst = Instrument(
            "BTCUSD",
            "crypto",
            "Bitcoin / US Dollar",
            providers={"yahoo": "BTC-USD", "dukascopy": "BTCUSD"},
        )
        assert inst.providers["yahoo"] == "BTC-USD"
        assert inst.providers["dukascopy"] == "BTCUSD"

    def test_to_dict_round_trip(self) -> None:
        inst = Instrument(
            "EURUSD",
            "forex",
            "Euro / US Dollar",
            providers={"yahoo": "EURUSD=X"},
        )
        d = inst.to_dict()
        assert d["class"] == "forex"
        assert d["description"] == "Euro / US Dollar"
        assert d["providers"] == {"yahoo": "EURUSD=X"}

        restored = Instrument.from_dict("EURUSD", d)
        assert restored == inst

    def test_equality(self) -> None:
        a = Instrument("BTCUSD", "crypto", "Bitcoin")
        b = Instrument("BTCUSD", "crypto", "Bitcoin")
        c = Instrument("ETHUSD", "crypto", "Ethereum")
        assert a == b
        assert a != c

    def test_hashable(self) -> None:
        s = {Instrument("BTCUSD", "crypto", "Bitcoin")}
        assert len(s) == 1


class TestProviderPriority:
    def test_default_priority_empty(self) -> None:
        inst = Instrument("EURUSD", "forex", "Euro")
        assert inst.provider_priority == ()

    def test_explicit_priority(self) -> None:
        inst = Instrument(
            "GBPUSD", "forex", "Pound", provider_priority=("dukascopy", "yahoo")
        )
        assert inst.provider_priority == ("dukascopy", "yahoo")

    def test_unknown_provider_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            Instrument("X", "crypto", "X", provider_priority=("nonexistent",))

    def test_partially_unknown_priority_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            Instrument(
                "X", "crypto", "X", provider_priority=("yahoo", "nonexistent")
            )

    def test_to_dict_round_trip_with_priority(self) -> None:
        inst = Instrument(
            "GBPUSD",
            "forex",
            "Pound",
            providers={"dukascopy": "GBP/USD"},
            provider_priority=("dukascopy",),
        )
        d = inst.to_dict()
        assert d["provider_priority"] == ["dukascopy"]
        restored = Instrument.from_dict("GBPUSD", d)
        assert restored == inst

    def test_to_dict_omits_empty_priority(self) -> None:
        inst = Instrument("EURUSD", "forex", "Euro")
        assert "provider_priority" not in inst.to_dict()

    def test_equality_includes_priority(self) -> None:
        a = Instrument("GBPUSD", "forex", "Pound", provider_priority=("dukascopy",))
        b = Instrument("GBPUSD", "forex", "Pound")
        assert a != b

    def test_hash_includes_priority(self) -> None:
        a = Instrument("GBPUSD", "forex", "Pound", provider_priority=("dukascopy",))
        b = Instrument("GBPUSD", "forex", "Pound", provider_priority=("dukascopy",))
        assert hash(a) == hash(b)
        s = {a}
        assert s == {b}

    def test_yaml_round_trip_priority(self, tmp_path: Path) -> None:
        path = tmp_path / "instruments.yaml"
        registry = InstrumentRegistry()
        registry.add(
            Instrument(
                "GBPUSD",
                "forex",
                "Pound",
                providers={"dukascopy": "GBP/USD", "yahoo": "GBPUSD=X"},
                provider_priority=("dukascopy", "yahoo"),
            )
        )
        registry.save(path)

        loaded = InstrumentRegistry(path)
        inst = loaded.get("GBPUSD")
        assert inst is not None
        assert inst.provider_priority == ("dukascopy", "yahoo")

    def test_load_unknown_priority_provider_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "instruments.yaml"
        data = {
            "instruments": {
                "GBPUSD": {
                    "class": "forex",
                    "description": "Pound",
                    "provider_priority": ["nonexistent"],
                }
            }
        }
        path.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="Unknown provider"):
            InstrumentRegistry(path)


class TestRegistryGetPriority:
    def test_declared_priority(self) -> None:
        registry = InstrumentRegistry()
        registry.add(
            Instrument("GBPUSD", "forex", "Pound", provider_priority=("dukascopy",))
        )
        assert registry.get_priority("GBPUSD") == ("dukascopy",)

    def test_default_priority_when_undeclared(self) -> None:
        registry = InstrumentRegistry()
        registry.add(Instrument("EURUSD", "forex", "Euro"))
        assert registry.get_priority("EURUSD") == DEFAULT_PROVIDER_ORDER

    def test_default_priority_for_unknown_canonical(self) -> None:
        registry = InstrumentRegistry()
        registry.add(Instrument("EURUSD", "forex", "Euro"))
        assert registry.get_priority("NONEXISTENT") == DEFAULT_PROVIDER_ORDER


class TestInstrumentRegistry:
    def test_empty_registry(self) -> None:
        registry = InstrumentRegistry()
        assert registry.list_all() == []
        assert registry.get("NONEXISTENT") is None

    def test_add_and_get(self) -> None:
        registry = InstrumentRegistry()
        inst = Instrument("EURUSD", "forex", "Euro / US Dollar")
        registry.add(inst)
        assert registry.get("EURUSD") == inst
        assert registry.get("NONEXISTENT") is None

    def test_get_symbol(self) -> None:
        registry = InstrumentRegistry()
        inst = Instrument(
            "BTCUSD",
            "crypto",
            "Bitcoin",
            providers={"yahoo": "BTC-USD", "dukascopy": "BTCUSD"},
        )
        registry.add(inst)
        assert registry.get_symbol("BTCUSD", "yahoo") == "BTC-USD"
        assert registry.get_symbol("BTCUSD", "dukascopy") == "BTCUSD"
        assert registry.get_symbol("BTCUSD", "oanda") is None
        assert registry.get_symbol("NONEXISTENT", "yahoo") is None

    def test_resolve_reverse_lookup(self) -> None:
        registry = InstrumentRegistry()
        registry.add(Instrument("EURUSD", "forex", "Euro", providers={"yahoo": "EURUSD=X"}))
        registry.add(Instrument("BTCUSD", "crypto", "Bitcoin", providers={"yahoo": "BTC-USD"}))
        assert registry.resolve("EURUSD=X", "yahoo") == "EURUSD"
        assert registry.resolve("BTC-USD", "yahoo") == "BTCUSD"
        assert registry.resolve("MISSING", "yahoo") is None

    def test_list_all(self) -> None:
        registry = InstrumentRegistry()
        registry.add(Instrument("EURUSD", "forex", "Euro"))
        registry.add(Instrument("BTCUSD", "crypto", "Bitcoin"))
        instruments = registry.list_all()
        assert len(instruments) == 2

    def test_yaml_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "instruments.yaml"
        registry = InstrumentRegistry()
        registry.add(
            Instrument(
                "EURUSD",
                "forex",
                "Euro / US Dollar",
                providers={"yahoo": "EURUSD=X"},
            )
        )
        registry.add(
            Instrument(
                "BTCUSD",
                "crypto",
                "Bitcoin / US Dollar",
                providers={"yahoo": "BTC-USD", "dukascopy": "BTCUSD"},
            )
        )
        registry.save(path)

        assert path.exists()
        loaded = InstrumentRegistry(path)
        assert len(loaded.list_all()) == 2
        assert loaded.get("EURUSD") is not None
        assert loaded.get("BTCUSD") is not None
        assert loaded.get_symbol("EURUSD", "yahoo") == "EURUSD=X"
        assert loaded.get_symbol("BTCUSD", "yahoo") == "BTC-USD"

    def test_load_from_nonexistent_path(self) -> None:
        registry = InstrumentRegistry(Path("/nonexistent/path.yaml"))
        assert registry.list_all() == []

    def test_load_from_empty_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("")
        registry = InstrumentRegistry(path)
        assert registry.list_all() == []

    def test_yaml_structure(self, tmp_path: Path) -> None:
        path = tmp_path / "instruments.yaml"
        data = {
            "instruments": {
                "EURUSD": {
                    "class": "forex",
                    "description": "Euro / US Dollar",
                    "providers": {"yahoo": "EURUSD=X"},
                }
            }
        }
        path.write_text(yaml.dump(data))
        registry = InstrumentRegistry(path)
        inst = registry.get("EURUSD")
        assert inst is not None
        assert inst.asset_class == "forex"
        assert inst.providers["yahoo"] == "EURUSD=X"

    def test_save_without_path_raises(self) -> None:
        registry = InstrumentRegistry()
        with pytest.raises(ValueError, match="No path specified"):
            registry.save()

    def test_provider_works_with_and_without_registry(self) -> None:
        from marketatlas.data.providers.yahoo import YahooProvider

        p1 = YahooProvider()
        assert p1._registry is None

        reg = InstrumentRegistry()
        reg.add(Instrument("BTCUSD", "crypto", "Bitcoin", providers={"yahoo": "BTC-USD"}))
        p2 = YahooProvider(registry=reg)
        assert p2._registry is not None

        resolved = p2._resolve_symbol(Symbol("BTCUSD"))
        assert resolved.name == "BTC-USD"

        unresolved = p2._resolve_symbol(Symbol("ETHUSD"))
        assert unresolved.name == "ETHUSD"

        p3 = YahooProvider()
        passthrough = p3._resolve_symbol(Symbol("BTC-USD"))
        assert passthrough.name == "BTC-USD"
