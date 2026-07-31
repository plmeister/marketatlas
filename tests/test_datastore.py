from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from marketatlas.data.datastore import DataStore, default_store_path
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe

_START = datetime(2024, 1, 1, tzinfo=UTC)


def _candles(start: datetime = _START, n: int = 30, price: float = 100.0) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            timestamp=start + timedelta(days=i),
            open=price + i,
            high=price + i + 2,
            low=price + i - 1,
            close=price + i + 1,
            volume=1000.0 + i,
        )
        for i in range(n)
    )


def _md(
    symbol: str = "BTC",
    timeframe: Timeframe = Timeframe.D1,
    candles: tuple[Candle, ...] | None = None,
) -> MarketData:
    return MarketData(
        symbol=Symbol(symbol),
        timeframe=timeframe,
        candles=candles if candles is not None else _candles(),
    )


class StubProvider:
    def __init__(self, candles: tuple[Candle, ...] | None = None) -> None:
        self._candles = candles
        self.calls: list[tuple[Symbol, Timeframe, datetime, datetime]] = []

    def fetch(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> MarketData:
        self.calls.append((symbol, timeframe, start, end))
        n = max(1, (end - start).days + 1)
        return MarketData(
            symbol=symbol,
            timeframe=timeframe,
            candles=_candles(start, n),
        )


class TestCoverage:
    def test_put_then_has_full_range(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md())
        assert ds.has(Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=29))

    def test_has_on_exact_bounds(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md())
        assert ds.has(Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=29))

    def test_has_false_when_start_before_stored(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md())
        assert not ds.has(
            Symbol("BTC"), Timeframe.D1, _START - timedelta(days=5), _START + timedelta(days=29)
        )

    def test_has_false_when_end_after_stored(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md())
        assert not ds.has(Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=50))

    def test_has_false_when_nothing_stored(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        assert not ds.has(Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=10))

    def test_missing_ranges_none_when_covered(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md())
        end = _START + timedelta(days=10)
        assert ds.missing_ranges(Symbol("BTC"), Timeframe.D1, _START, end) == ()

    def test_missing_ranges_leading_and_trailing(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md())
        missing = ds.missing_ranges(
            Symbol("BTC"), Timeframe.D1, _START - timedelta(days=5), _START + timedelta(days=40)
        )
        assert missing == (
            (_START - timedelta(days=5), _START),
            (_START + timedelta(days=29), _START + timedelta(days=40)),
        )

    def test_missing_ranges_whole_range_when_empty(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        start, end = _START, _START + timedelta(days=10)
        assert ds.missing_ranges(Symbol("BTC"), Timeframe.D1, start, end) == ((start, end),)

    def test_get_returns_clipped_candles(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md())
        md = ds.get(
            Symbol("BTC"), Timeframe.D1,
            _START + timedelta(days=5), _START + timedelta(days=9),
        )
        assert md is not None
        assert len(md.candles) == 5
        assert md.candles[0].timestamp == _START + timedelta(days=5)

    def test_get_none_when_no_overlap(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md())
        far = _START + timedelta(days=100)
        assert ds.get(Symbol("BTC"), Timeframe.D1, far, far + timedelta(days=10)) is None

    def test_get_none_when_empty(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        assert ds.get(Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=5)) is None


class TestPersistence:
    def test_survives_fresh_instance(self, tmp_path: Path) -> None:
        DataStore(tmp_path).put(_md())
        ds = DataStore(tmp_path)
        assert ds.has(Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=29))
        md = ds.get(Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=4))
        assert md is not None and len(md.candles) == 5

    def test_survives_process_restart(self, tmp_path: Path) -> None:
        src_root = Path(__file__).parent.parent / "src"
        script = tmp_path / "seed_store.py"
        script.write_text(
            "import sys\n"
            "from datetime import UTC, datetime, timedelta\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from marketatlas.data.datastore import DataStore\n"
            "from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe\n"
            "base = datetime(2024, 1, 1, tzinfo=UTC)\n"
            "candles = tuple(\n"
            "    Candle(timestamp=base + timedelta(days=i), open=1.0, high=2.0, low=0.5,\n"
            "           close=1.5, volume=100.0) for i in range(10)\n"
            ")\n"
            "DataStore(Path(sys.argv[2])).put(\n"
            "    MarketData(symbol=Symbol('SYM'), timeframe=Timeframe.D1, candles=candles)\n"
            ")\n"
        )
        result = subprocess.run(
            [sys.executable, str(script), str(src_root), str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

        ds = DataStore(tmp_path)
        assert ds.has(Symbol("SYM"), Timeframe.D1, _START, _START + timedelta(days=9))
        md = ds.get(Symbol("SYM"), Timeframe.D1, _START, _START + timedelta(days=2))
        assert md is not None and len(md.candles) == 3


class TestFetchOrGet:
    def test_first_fetch_then_cached_for_fifty_runs(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        provider = StubProvider()
        start, end = _START, _START + timedelta(days=60)
        for _ in range(50):
            md = ds.fetch_or_get(provider, Symbol("BTC"), Timeframe.D1, start, end)
            assert len(md.candles) > 0
        assert len(provider.calls) == 1

    def test_partial_range_fetches_only_missing(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md(candles=_candles(n=10)))
        provider = StubProvider()
        md = ds.fetch_or_get(
            provider, Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=20)
        )
        assert len(provider.calls) == 1
        gap_start, gap_end = provider.calls[0][2], provider.calls[0][3]
        assert gap_start == _START + timedelta(days=9)
        assert gap_end == _START + timedelta(days=20)
        assert len(md.candles) == 21

        provider.calls.clear()
        ds.fetch_or_get(provider, Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=20))
        assert provider.calls == []

    def test_merge_dedupes_overlapping_puts(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        first = _md(candles=_candles(n=10))
        second = _md(candles=_candles(n=5))
        ds.put(first)
        ds.put(second)
        md = ds.get(Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=20))
        assert md is not None
        timestamps = [c.timestamp for c in md.candles]
        assert len(timestamps) == 10
        assert timestamps == sorted(timestamps)


class TestIsolation:
    def test_instrument_isolation(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md(symbol="BTC"))
        assert not ds.has(Symbol("ETH"), Timeframe.D1, _START, _START + timedelta(days=5))
        assert ds.get(Symbol("ETH"), Timeframe.D1, _START, _START + timedelta(days=5)) is None
        assert ds.has(Symbol("BTC"), Timeframe.D1, _START, _START + timedelta(days=5))

    def test_timeframe_isolation(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md(timeframe=Timeframe.D1))
        assert not ds.has(Symbol("BTC"), Timeframe.H1, _START, _START + timedelta(days=5))
        assert ds.get(Symbol("BTC"), Timeframe.H1, _START, _START + timedelta(days=5)) is None

    def test_cached_symbols_and_timeframes(self, tmp_path: Path) -> None:
        ds = DataStore(tmp_path)
        ds.put(_md(symbol="BTC", timeframe=Timeframe.D1))
        ds.put(_md(symbol="BTC", timeframe=Timeframe.H1))
        ds.put(_md(symbol="ETH", timeframe=Timeframe.D1))
        assert ds.cached_symbols() == [Symbol("BTC"), Symbol("ETH")]
        assert ds.cached_timeframes(Symbol("BTC")) == [Timeframe.H1, Timeframe.D1]


class TestDefaults:
    def test_configurable_path(self, tmp_path: Path) -> None:
        store_path = tmp_path / "nested" / "cache"
        ds = DataStore(store_path)
        assert ds.base_path == store_path
        ds.put(_md())
        assert (store_path / "BTC.1d.parquet").exists()

    def test_default_store_path_uses_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom = tmp_path / "custom-cache"
        monkeypatch.setenv("MARKETATLAS_DATA_DIR", str(custom))
        assert default_store_path() == custom

    def test_default_store_path_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MARKETATLAS_DATA_DIR", raising=False)
        path = default_store_path()
        assert path.is_absolute()
        assert "marketatlas" in str(path)
        assert path.name == "data"
