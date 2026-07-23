from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from marketatlas.data.repository import MarketRepository
from marketatlas.data.types import MarketData, Symbol, Timeframe


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def sample_candles() -> list[dict[str, object]]:
    return [
        {
            "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 103.0,
            "volume": 1000.0,
        },
        {
            "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
            "open": 103.0,
            "high": 110.0,
            "low": 102.0,
            "close": 108.0,
            "volume": 1500.0,
        },
        {
            "timestamp": datetime(2024, 1, 3, tzinfo=UTC),
            "open": 108.0,
            "high": 112.0,
            "low": 107.0,
            "close": 105.0,
            "volume": 800.0,
        },
    ]


def _write_parquet(
    data_dir: Path, symbol: str, timeframe: str, candles: list[dict[str, object]]
) -> None:
    table = pa.table(
        {
            "timestamp": [c["timestamp"] for c in candles],
            "open": [c["open"] for c in candles],
            "high": [c["high"] for c in candles],
            "low": [c["low"] for c in candles],
            "close": [c["close"] for c in candles],
            "volume": [c["volume"] for c in candles],
        }
    )
    path = data_dir / f"{symbol}.{timeframe}.parquet"
    pq.write_table(table, path)


class TestMarketRepositoryLoad:
    def test_load_returns_market_data(
        self, data_dir: Path, sample_candles: list[dict[str, object]]
    ) -> None:
        _write_parquet(data_dir, "BTCUSDT", "1h", sample_candles)
        repo = MarketRepository(data_dir)
        result = repo.load(Symbol("BTCUSDT"), Timeframe.H1)
        assert isinstance(result, MarketData)
        assert result.symbol == Symbol("BTCUSDT")
        assert result.timeframe == Timeframe.H1

    def test_load_correct_candle_count(
        self, data_dir: Path, sample_candles: list[dict[str, object]]
    ) -> None:
        _write_parquet(data_dir, "ETHUSDT", "1d", sample_candles)
        repo = MarketRepository(data_dir)
        result = repo.load(Symbol("ETHUSDT"), Timeframe.D1)
        assert len(result.candles) == 3

    def test_load_candle_values(
        self, data_dir: Path, sample_candles: list[dict[str, object]]
    ) -> None:
        _write_parquet(data_dir, "BTCUSDT", "1h", sample_candles)
        repo = MarketRepository(data_dir)
        result = repo.load(Symbol("BTCUSDT"), Timeframe.H1)
        first = result.candles[0]
        assert first.open == 100.0
        assert first.high == 105.0
        assert first.low == 99.0
        assert first.close == 103.0
        assert first.volume == 1000.0

    def test_load_missing_file_raises(self, data_dir: Path) -> None:
        repo = MarketRepository(data_dir)
        with pytest.raises(FileNotFoundError, match="No data file"):
            repo.load(Symbol("MISSING"), Timeframe.H1)

    def test_load_malformed_parquet_raises(self, data_dir: Path) -> None:
        table = pa.table({"price": [100.0], "volume": [1000.0]})
        pq.write_table(table, data_dir / "BAD.1h.parquet")
        repo = MarketRepository(data_dir)
        with pytest.raises(ValueError, match="missing columns"):
            repo.load(Symbol("BAD"), Timeframe.H1)


class TestMarketRepositoryListSymbols:
    def test_list_symbols_empty(self, data_dir: Path) -> None:
        repo = MarketRepository(data_dir)
        assert repo.list_symbols() == []

    def test_list_symbols(self, data_dir: Path, sample_candles: list[dict[str, object]]) -> None:
        _write_parquet(data_dir, "BTCUSDT", "1h", sample_candles)
        _write_parquet(data_dir, "ETHUSDT", "1d", sample_candles)
        _write_parquet(data_dir, "BTCUSDT", "1d", sample_candles)
        repo = MarketRepository(data_dir)
        symbols = repo.list_symbols()
        assert symbols == [Symbol("BTCUSDT"), Symbol("ETHUSDT")]

    def test_list_symbols_sorted(
        self, data_dir: Path, sample_candles: list[dict[str, object]]
    ) -> None:
        _write_parquet(data_dir, "ZBTC", "1h", sample_candles)
        _write_parquet(data_dir, "ABTC", "1h", sample_candles)
        _write_parquet(data_dir, "MBTC", "1h", sample_candles)
        repo = MarketRepository(data_dir)
        symbols = repo.list_symbols()
        names = [s.name for s in symbols]
        assert names == sorted(names)
