from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from marketatlas.data.datastore import DataStore
from marketatlas.data.instrument import Instrument, InstrumentRegistry
from marketatlas.data.portfolio import (
    InstrumentDataError,
    PortfolioError,
    PortfolioSpec,
    fetch_instrument_data,
    load_portfolio,
)
from marketatlas.data.providers.base import UnsupportedTimeframeError
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


def _make_instruments() -> list[Instrument]:
    return [
        Instrument("GBPUSD", "forex", "Pound", providers={"yahoo": "GBPUSD=X"}),
        Instrument("BTCUSD", "crypto", "Bitcoin", providers={"yahoo": "BTC-USD"}),
        Instrument("EURUSD", "forex", "Euro", providers={"yahoo": "EURUSD=X"}),
    ]


def _write_registry(tmp_path: Path, instruments: list[Instrument]) -> Path:
    path = tmp_path / "instruments.yaml"
    registry = InstrumentRegistry()
    for inst in instruments:
        registry.add(inst)
    registry.save(path)
    return path


def _write_portfolio(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "portfolio.yaml"
    path.write_text("instruments:\n" + "\n".join(f"  - {n}" for n in names))
    return path


def _make_candles(n: int = 5, base_price: float = 100.0) -> tuple[Candle, ...]:
    from datetime import timedelta

    base = datetime(2024, 1, 1, tzinfo=UTC)
    candles = []
    for i in range(n):
        ts = base + timedelta(days=i)
        p = base_price + i
        candles.append(
            Candle(timestamp=ts, open=p, high=p + 2, low=p - 1, close=p + 1, volume=1000.0 + i)
        )
    return tuple(candles)


def _market_data(symbol: str, timeframe: Timeframe = Timeframe.D1, n: int = 10) -> MarketData:
    return MarketData(
        symbol=Symbol(symbol),
        timeframe=timeframe,
        candles=_make_candles(n),
    )


class TestLoadPortfolio:
    def test_loads_in_order(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        for inst in _make_instruments():
            registry.add(inst)
        path = _write_portfolio(tmp_path, ["GBPUSD", "BTCUSD", "EURUSD"])

        spec = load_portfolio(path, registry)

        assert isinstance(spec, PortfolioSpec)
        assert [i.canonical for i in spec.instruments] == ["GBPUSD", "BTCUSD", "EURUSD"]
        assert len(spec) == 3

    def test_unknown_canonical_errors_with_index(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        registry.add(_make_instruments()[0])
        path = _write_portfolio(tmp_path, ["GBPUSD", "XXX"])

        with pytest.raises(PortfolioError) as exc_info:
            load_portfolio(path, registry)
        assert "Unknown instrument 'XXX' at index 1 in portfolio file" in str(exc_info.value)

    def test_empty_list_errors(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        for inst in _make_instruments():
            registry.add(inst)
        path = _write_portfolio(tmp_path, [])

        with pytest.raises(PortfolioError) as exc_info:
            load_portfolio(path, registry)
        assert "no instruments" in str(exc_info.value)

    def test_missing_file_errors(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        with pytest.raises(PortfolioError) as exc_info:
            load_portfolio(tmp_path / "nope.yaml", registry)
        assert "not found" in str(exc_info.value)

    def test_empty_file_errors(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        path = tmp_path / "portfolio.yaml"
        path.write_text("")
        with pytest.raises(PortfolioError) as exc_info:
            load_portfolio(path, registry)
        assert "empty" in str(exc_info.value)

    def test_malformed_not_mapping_errors(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        path = tmp_path / "portfolio.yaml"
        path.write_text("- just\n- a\n- list\n")
        with pytest.raises(PortfolioError) as exc_info:
            load_portfolio(path, registry)
        assert "mapping" in str(exc_info.value)

    def test_missing_instruments_key_errors(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        path = tmp_path / "portfolio.yaml"
        path.write_text("symbols:\n  - GBPUSD\n")
        with pytest.raises(PortfolioError) as exc_info:
            load_portfolio(path, registry)
        assert "missing 'instruments'" in str(exc_info.value)

    def test_instruments_not_list_errors(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        path = tmp_path / "portfolio.yaml"
        path.write_text("instruments: GBPUSD\n")
        with pytest.raises(PortfolioError) as exc_info:
            load_portfolio(path, registry)
        assert "must be a list" in str(exc_info.value)

    def test_non_string_entry_errors(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        for inst in _make_instruments():
            registry.add(inst)
        path = tmp_path / "portfolio.yaml"
        path.write_text("instruments:\n  - GBPUSD\n  - 123\n")
        with pytest.raises(PortfolioError) as exc_info:
            load_portfolio(path, registry)
        assert "index 1" in str(exc_info.value)

    def test_duplicates_deduped_order_preserved(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        for inst in _make_instruments():
            registry.add(inst)
        path = _write_portfolio(tmp_path, ["BTCUSD", "GBPUSD", "BTCUSD", "EURUSD"])

        spec = load_portfolio(path, registry)

        assert [i.canonical for i in spec.instruments] == ["BTCUSD", "GBPUSD", "EURUSD"]

    def test_none_registry_errors(self, tmp_path: Path) -> None:
        path = _write_portfolio(tmp_path, ["GBPUSD"])
        with pytest.raises(PortfolioError) as exc_info:
            load_portfolio(path, None)  # type: ignore[arg-type]
        assert "registry" in str(exc_info.value)


class TestFetchInstrumentData:
    @pytest.fixture(autouse=True)
    def _isolated_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MARKETATLAS_DATA_DIR", str(tmp_path / "store"))

    def test_fetches_all_timeframes_native(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        registry.add(_make_instruments()[0])
        _write_registry(tmp_path, _make_instruments())
        spec = load_portfolio(_write_portfolio(tmp_path, ["GBPUSD"]), registry)

        provider = MagicMock()
        provider.fetch.side_effect = [
            _market_data("GBPUSD", Timeframe.D1),
            _market_data("GBPUSD", Timeframe.W1),
        ]
        datastore = DataStore(tmp_path / "store")
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        data = fetch_instrument_data(
            provider,
            datastore,
            spec.instruments[0],
            [Timeframe.D1, Timeframe.W1],
            start,
            end,
            Timeframe.D1,
        )

        assert set(data.timeframes) == {Timeframe.D1, Timeframe.W1}
        assert data.resampled == ()
        assert provider.fetch.call_count == 2
        assert (tmp_path / "store" / "GBPUSD.1d.parquet").exists()
        assert (tmp_path / "store" / "GBPUSD.1w.parquet").exists()
        for call in provider.fetch.call_args_list:
            assert call.args[2] == start
            assert call.args[3] == end

    def test_resample_fallback_per_instrument(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        for inst in _make_instruments():
            registry.add(inst)
        _write_registry(tmp_path, _make_instruments())
        spec = load_portfolio(_write_portfolio(tmp_path, ["GBPUSD", "BTCUSD"]), registry)

        datastore = DataStore(tmp_path / "store")
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        for inst in spec.instruments:
            provider = MagicMock()
            # D1 native, W1 raises UnsupportedTimeframeError (unsupported) -> resampled
            provider.fetch.side_effect = [
                _market_data(inst.canonical, Timeframe.D1),
                UnsupportedTimeframeError(Symbol(inst.canonical), Timeframe.W1),
            ]
            data = fetch_instrument_data(
                provider,
                datastore,
                inst,
                [Timeframe.D1, Timeframe.W1],
                start,
                end,
                Timeframe.D1,
            )
            assert set(data.timeframes) == {Timeframe.D1, Timeframe.W1}
            assert data.resampled == ((Timeframe.W1, Timeframe.D1),)
            # resampled output persisted to the store
            assert (tmp_path / "store" / f"{inst.canonical}.1w.parquet").exists()

    def test_second_fetch_served_from_store(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        registry.add(_make_instruments()[0])
        _write_registry(tmp_path, _make_instruments())
        spec = load_portfolio(_write_portfolio(tmp_path, ["GBPUSD"]), registry)

        provider = MagicMock()
        provider.fetch.side_effect = [
            _market_data("GBPUSD", Timeframe.D1, n=200),
            _market_data("GBPUSD", Timeframe.W1, n=200),
        ]
        datastore = DataStore(tmp_path / "store")
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)
        timeframes = [Timeframe.D1, Timeframe.W1]

        fetch_instrument_data(
            provider, datastore, spec.instruments[0], timeframes, start, end, Timeframe.D1
        )
        assert provider.fetch.call_count == 2

        provider.fetch.reset_mock()
        data = fetch_instrument_data(
            provider, datastore, spec.instruments[0], timeframes, start, end, Timeframe.D1
        )
        assert provider.fetch.call_count == 0
        assert set(data.timeframes) == {Timeframe.D1, Timeframe.W1}

    def test_missing_base_timeframe_raises_with_instrument(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        registry.add(_make_instruments()[0])
        _write_registry(tmp_path, _make_instruments())
        spec = load_portfolio(_write_portfolio(tmp_path, ["GBPUSD"]), registry)

        provider = MagicMock()
        provider.fetch.side_effect = RuntimeError("network down")
        datastore = DataStore(tmp_path / "store")

        with pytest.raises(InstrumentDataError) as exc_info:
            fetch_instrument_data(
                provider,
                datastore,
                spec.instruments[0],
                [Timeframe.D1],
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 6, 1, tzinfo=UTC),
                Timeframe.D1,
            )
        assert exc_info.value.instrument == "GBPUSD"
        assert "GBPUSD" in str(exc_info.value)
        assert "primary timeframe" in str(exc_info.value)

    def test_partial_timeframe_failure_keeps_others(self, tmp_path: Path) -> None:
        registry = InstrumentRegistry()
        registry.add(_make_instruments()[0])
        _write_registry(tmp_path, _make_instruments())
        spec = load_portfolio(_write_portfolio(tmp_path, ["GBPUSD"]), registry)

        provider = MagicMock()
        provider.fetch.side_effect = [
            _market_data("GBPUSD", Timeframe.D1),
            RuntimeError("W1 failed"),
        ]
        datastore = DataStore(tmp_path / "store")

        data = fetch_instrument_data(
            provider,
            datastore,
            spec.instruments[0],
            [Timeframe.D1, Timeframe.W1],
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 6, 1, tzinfo=UTC),
            Timeframe.D1,
        )
        assert set(data.timeframes) == {Timeframe.D1}

    def test_chain_unsupported_timeframe_falls_back_to_next(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Forex portfolio path: dukascopy rejects 1d, yahoo serves it (073)."""
        registry = InstrumentRegistry()
        registry.add(_make_instruments()[0])
        spec = load_portfolio(_write_portfolio(tmp_path, ["GBPUSD"]), registry)

        dukas = MagicMock()
        dukas.fetch.side_effect = UnsupportedTimeframeError(Symbol("GBPUSD"), Timeframe.D1)
        yahoo = MagicMock()
        yahoo.fetch.return_value = _market_data("GBPUSD", Timeframe.D1)
        from marketatlas.data.providers.chain import ProviderChain

        provider = ProviderChain([dukas, yahoo])
        datastore = DataStore(tmp_path / "store")
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        data = fetch_instrument_data(
            provider,
            datastore,
            spec.instruments[0],
            [Timeframe.D1],
            start,
            end,
            Timeframe.D1,
        )

        assert set(data.timeframes) == {Timeframe.D1}
        assert dukas.fetch.call_count == 1
        assert yahoo.fetch.call_count == 1
        # chain swallowed the unsupported timeframe: no per-instrument drop log
        assert capsys.readouterr().err == ""

    def test_unsupported_timeframe_log_names_provider_tf_reason(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bare provider rejecting a TF logs provider + timeframe + reason, then resamples."""
        registry = InstrumentRegistry()
        registry.add(_make_instruments()[0])
        _write_registry(tmp_path, _make_instruments())
        spec = load_portfolio(_write_portfolio(tmp_path, ["GBPUSD"]), registry)

        provider = MagicMock()
        provider.fetch.side_effect = [
            _market_data("GBPUSD", Timeframe.D1),
            UnsupportedTimeframeError(Symbol("GBPUSD"), Timeframe.W1),
        ]
        datastore = DataStore(tmp_path / "store")
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        data = fetch_instrument_data(
            provider,
            datastore,
            spec.instruments[0],
            [Timeframe.D1, Timeframe.W1],
            start,
            end,
            Timeframe.D1,
        )

        assert set(data.timeframes) == {Timeframe.D1, Timeframe.W1}
        assert data.resampled == ((Timeframe.W1, Timeframe.D1),)
        err = capsys.readouterr().err
        assert "1w" in err
        assert "unsupported by MagicMock" in err
        assert "Unsupported timeframe" in err
