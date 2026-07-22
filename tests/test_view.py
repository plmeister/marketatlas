from datetime import UTC, datetime, timedelta

import pytest

from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView

BASE = datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture()
def store() -> MarketStore:
    candles = tuple(
        Candle(
            timestamp=BASE + timedelta(days=i),
            open=100.0 + i,
            high=105.0 + i,
            low=99.0 + i,
            close=103.0 + i,
            volume=1000.0 + i * 100,
        )
        for i in range(100)
    )
    return MarketStore(MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles))


class TestMarketViewCurrent:
    def test_current_returns_candle_at_cursor(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert view.current == store[50]

    def test_current_open_price(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert view.current.open == 150.0


class TestMarketViewHistory:
    def test_history_excludes_current(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert len(view.history) == 50
        assert view.history[-1] == store[49]

    def test_history_window_limited(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=20)
        assert len(view.history) == 20

    def test_history_empty_at_start(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=0, window_size=10)
        assert len(view.history) == 0


class TestMarketViewSeries:
    def test_prices_match_close(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert view.prices[0] == store[0].close
        assert view.prices[-1] == store[50].close

    def test_volumes_match(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert view.volumes[-1] == store[50].volume

    def test_highs_match(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert view.highs[-1] == store[50].high

    def test_lows_match(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert view.lows[-1] == store[50].low

    def test_timestamps_match(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert view.timestamps[-1] == store[50].timestamp

    def test_series_length_includes_history_plus_current(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert len(view.prices) == 51


class TestMarketViewValidity:
    def test_valid_within_range(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        assert view.is_valid is True

    def test_invalid_cursor_zero(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=0, window_size=10)
        assert view.is_valid is False

    def test_invalid_cursor_beyond_store(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=200, window_size=10)
        assert view.is_valid is False

    def test_invalid_cursor_less_than_window(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=5, window_size=10)
        assert view.is_valid is False
