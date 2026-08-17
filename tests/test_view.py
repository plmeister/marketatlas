from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView


pytestmark = pytest.mark.tier2
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
    data = MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
    return MarketStore(data)


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


class TestMarketViewSelect:
    @pytest.fixture()
    def multi_store(self) -> MarketStore:
        daily = tuple(
            Candle(
                timestamp=BASE + timedelta(days=i),
                open=100.0 + i,
                high=105.0 + i,
                low=99.0 + i,
                close=103.0 + i,
                volume=1000.0,
            )
            for i in range(100)
        )
        weekly = tuple(
            Candle(
                timestamp=BASE + timedelta(weeks=i),
                open=100.0 + i * 5,
                high=110.0 + i * 5,
                low=95.0 + i * 5,
                close=105.0 + i * 5,
                volume=5000.0,
            )
            for i in range(15)
        )
        dd = MarketData(symbol=Symbol("TEST"), timeframe=Timeframe.D1, candles=daily)
        ww = MarketData(symbol=Symbol("TEST"), timeframe=Timeframe.W1, candles=weekly)
        return MarketStore({Timeframe.D1: dd, Timeframe.W1: ww})

    def test_select_weekly_returns_view_with_timeframe(self, multi_store: MarketStore) -> None:
        view = MarketView(multi_store, cursor=99, window_size=50)
        wv = view.select(Timeframe.W1)
        assert wv.view_timeframe == Timeframe.W1
        assert wv.cursor < view.cursor  # fewer weekly candles

    def test_select_weekly_current_is_weekly_candle(self, multi_store: MarketStore) -> None:
        view = MarketView(multi_store, cursor=99, window_size=50)
        wv = view.select(Timeframe.W1)
        assert wv.current.timestamp == BASE + timedelta(weeks=14)

    def test_select_weekly_history_weekly_bars(self, multi_store: MarketStore) -> None:
        view = MarketView(multi_store, cursor=99, window_size=50)
        wv = view.select(Timeframe.W1, window_size=5)
        assert len(wv.history) == 5
        # All history candles should be weekly
        for c in wv.history:
            assert c.timestamp.weekday() == 0  # Monday (weekly candle)

    def test_select_weekly_prices_are_weekly_closes(self, multi_store: MarketStore) -> None:
        view = MarketView(multi_store, cursor=99, window_size=50)
        wv = view.select(Timeframe.W1, window_size=5)
        assert len(wv.prices) == 6  # 5 history + current
        assert wv.prices[-1] == multi_store.get_candles(Timeframe.W1)[-1].close

    def test_select_without_window_uses_default(self, multi_store: MarketStore) -> None:
        view = MarketView(multi_store, cursor=99, window_size=50)
        wv = view.select(Timeframe.W1)
        assert wv.window_size == 50

    def test_select_with_custom_window(self, multi_store: MarketStore) -> None:
        view = MarketView(multi_store, cursor=99, window_size=50)
        wv = view.select(Timeframe.W1, window_size=10)
        assert wv.window_size == 10

    def test_select_missing_timeframe_raises(self, multi_store: MarketStore) -> None:
        view = MarketView(multi_store, cursor=50, window_size=50)
        with pytest.raises(ValueError, match="No data available for timeframe"):
            view.select(Timeframe.H1)

    def test_select_cursor_alignment(self, multi_store: MarketStore) -> None:
        # At day 10, should map to week 1 (since week 1 starts at day 7)
        view = MarketView(multi_store, cursor=10, window_size=50)
        wv = view.select(Timeframe.W1)
        weekly = multi_store.get_candles(Timeframe.W1)
        expected_week = max(
            i for i, c in enumerate(weekly) if c.timestamp <= view.current.timestamp
        )
        assert wv.cursor == expected_week

    def test_is_valid_on_weekly_view(self, multi_store: MarketStore) -> None:
        view = MarketView(multi_store, cursor=99, window_size=50)
        wv = view.select(Timeframe.W1, window_size=5)
        assert wv.is_valid is True
        wv_bad = MarketView(multi_store, cursor=0, window_size=10, view_timeframe=Timeframe.W1)
        assert wv_bad.is_valid is False


class TestMarketViewAlign:
    @pytest.fixture()
    def multi_store(self) -> MarketStore:
        daily = tuple(
            Candle(
                timestamp=BASE + timedelta(days=i),
                open=100.0 + i,
                high=105.0 + i,
                low=99.0 + i,
                close=103.0 + i,
                volume=1000.0,
            )
            for i in range(100)
        )
        weekly = tuple(
            Candle(
                timestamp=BASE + timedelta(weeks=i),
                open=100.0 + i * 5,
                high=110.0 + i * 5,
                low=95.0 + i * 5,
                close=105.0 + i * 5,
                volume=5000.0,
            )
            for i in range(15)
        )
        dd = MarketData(symbol=Symbol("TEST"), timeframe=Timeframe.D1, candles=daily)
        ww = MarketData(symbol=Symbol("TEST"), timeframe=Timeframe.W1, candles=weekly)
        return MarketStore({Timeframe.D1: dd, Timeframe.W1: ww})

    def test_align_exact_timestamp(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=99, window_size=50)
        aligned = view.align(BASE + timedelta(days=25))
        assert aligned.cursor == 25
        assert aligned.current.timestamp == BASE + timedelta(days=25)

    def test_align_at_or_before(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=99, window_size=50)
        aligned = view.align(BASE + timedelta(days=25, hours=12))
        assert aligned.cursor == 25

    def test_align_before_first_clamps_to_zero(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=50, window_size=50)
        aligned = view.align(BASE - timedelta(days=1))
        assert aligned.cursor == 0

    def test_align_after_last_reaches_end(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=0, window_size=50)
        aligned = view.align(BASE + timedelta(days=1000))
        assert aligned.cursor == len(store) - 1

    def test_align_preserves_window_and_timeframe(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=99, window_size=20)
        aligned = view.align(BASE + timedelta(days=10))
        assert aligned.window_size == 20
        assert aligned.view_timeframe is None

    def test_align_on_view_timeframe(self, multi_store: MarketStore) -> None:
        view = MarketView(multi_store, cursor=99, window_size=50)
        wv = view.select(Timeframe.W1)
        aligned = wv.align(BASE + timedelta(weeks=9, days=3))
        assert aligned.view_timeframe == Timeframe.W1
        assert aligned.current.timestamp == BASE + timedelta(weeks=9)

    def test_align_returns_valid_view_after_warmup(self, store: MarketStore) -> None:
        view = MarketView(store, cursor=99, window_size=50)
        aligned = view.align(BASE + timedelta(days=60))
        assert aligned.is_valid is True
        assert aligned.current.timestamp == BASE + timedelta(days=60)
