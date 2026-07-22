from datetime import UTC, datetime

import pytest

from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe


@pytest.fixture()
def sample_market_data() -> MarketData:
    candles = tuple(
        Candle(
            timestamp=datetime(2024, 1, i + 1, tzinfo=UTC),
            open=100.0 + i,
            high=105.0 + i,
            low=99.0 + i,
            close=103.0 + i,
            volume=1000.0 + i * 100,
        )
        for i in range(5)
    )
    return MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.H1, candles=candles)


class TestMarketStoreConstruction:
    def test_len_matches_candle_count(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        assert len(store) == 5

    def test_exposes_symbol(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        assert store.symbol == Symbol("BTCUSDT")

    def test_exposes_timeframe(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        assert store.timeframe == Timeframe.H1


class TestMarketStoreAccess:
    def test_getitem_returns_candle(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        candle = store[0]
        assert isinstance(candle, Candle)
        assert candle.open == 100.0

    def test_getitem_negative_index(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        assert store[-1].close == 107.0

    def test_getitem_out_of_range(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        with pytest.raises(IndexError):
            _ = store[100]

    def test_slice_returns_tuple(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        result = store.slice(0, 3)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_slice_first_candle(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        result = store.slice(0, 1)
        assert result[0].open == 100.0

    def test_slice_beyond_end(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        result = store.slice(3, 100)
        assert len(result) == 2

    def test_timestamps_match(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        assert len(store.timestamps) == 5
        assert store.timestamps[0] == datetime(2024, 1, 1, tzinfo=UTC)
