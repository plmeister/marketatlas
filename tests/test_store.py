from __future__ import annotations

from datetime import UTC, datetime

import pytest
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe



pytestmark = pytest.mark.tier2
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


class TestMarketStoreMultiTimeframe:
    @pytest.fixture()
    def dd(self) -> MarketData:
        from datetime import timedelta

        base = datetime(2024, 1, 1, tzinfo=UTC)
        candles = tuple(
            Candle(
                timestamp=base + timedelta(days=i),
                open=100.0 + i, high=105.0 + i,
                low=99.0 + i, close=103.0 + i, volume=1000.0 + i * 100,
            )
            for i in range(100)
        )
        return MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)

    @pytest.fixture()
    def wd(self) -> MarketData:
        from datetime import timedelta

        base = datetime(2024, 1, 1, tzinfo=UTC)
        candles = tuple(
            Candle(
                timestamp=base + timedelta(weeks=i),
                open=100.0 + i, high=110.0 + i * 2,
                low=95.0 + i, close=105.0 + i, volume=7000.0 + i * 500,
            )
            for i in range(15)
        )
        return MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.W1, candles=candles)

    def test_primary_tf_is_highest_resolution(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        assert store.timeframe == Timeframe.D1

    def test_len_reflects_primary(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        assert len(store) == 100

    def test_getitem_on_primary(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        assert store[0].open == 100.0
        assert store[-1].open == 199.0

    def test_available_timeframes(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        tfs = store.available_timeframes
        assert Timeframe.D1 in tfs
        assert Timeframe.W1 in tfs

    def test_available_timeframes_sorted_by_resolution(
        self, dd: MarketData, wd: MarketData
    ) -> None:
        store = MarketStore({Timeframe.W1: wd, Timeframe.D1: dd})
        tfs = store.available_timeframes
        assert tfs == (Timeframe.D1, Timeframe.W1)

    def test_get_candles_returns_primary(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        candles = store.get_candles(Timeframe.D1)
        assert len(candles) == 100

    def test_get_candles_returns_secondary(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        candles = store.get_candles(Timeframe.W1)
        assert len(candles) == 15

    def test_get_candles_nonexistent(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        candles = store.get_candles(Timeframe.H1)
        assert candles == ()

    def test_contains(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        assert Timeframe.D1 in store
        assert Timeframe.W1 in store
        assert Timeframe.H1 not in store

    def test_single_market_data_still_works(self, dd: MarketData) -> None:
        store = MarketStore(dd)
        assert len(store) == 100
        assert store.timeframe == Timeframe.D1
        assert store.available_timeframes == (Timeframe.D1,)

    def test_single_timeframe_dict(self, dd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd})
        assert len(store) == 100
        assert store.timeframe == Timeframe.D1

    def test_symbol_from_any_timeframe(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        assert store.symbol == Symbol("BTCUSDT")

    def test_weekly_get_candles_contents(self, dd: MarketData, wd: MarketData) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        candles = store.get_candles(Timeframe.W1)
        assert len(candles) == 15
        assert candles[0].open == 100.0


class TestMarketStoreTimeQueries:
    @pytest.fixture()
    def dd(self) -> MarketData:
        from datetime import timedelta

        base = datetime(2024, 1, 1, tzinfo=UTC)
        candles = tuple(
            Candle(
                timestamp=base + timedelta(days=i),
                open=100.0 + i, high=105.0 + i,
                low=99.0 + i, close=103.0 + i, volume=1000.0 + i * 100,
            )
            for i in range(100)
        )
        return MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)

    @pytest.fixture()
    def wd(self) -> MarketData:
        from datetime import timedelta

        base = datetime(2024, 1, 1, tzinfo=UTC)
        candles = tuple(
            Candle(
                timestamp=base + timedelta(weeks=i),
                open=100.0 + i, high=110.0 + i * 2,
                low=95.0 + i, close=105.0 + i, volume=7000.0 + i * 500,
            )
            for i in range(15)
        )
        return MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.W1, candles=candles)

    def test_timestamp_index_exact_match(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        assert store.timestamp_index(datetime(2024, 1, 3, tzinfo=UTC)) == 2

    def test_timestamp_index_before_first(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        assert store.timestamp_index(datetime(2023, 12, 31, tzinfo=UTC)) == -1

    def test_timestamp_index_at_or_before(
        self, sample_market_data: MarketData
    ) -> None:
        store = MarketStore(sample_market_data)
        assert store.timestamp_index(datetime(2024, 1, 3, 6, tzinfo=UTC)) == 2

    def test_timestamp_index_after_last(
        self, sample_market_data: MarketData
    ) -> None:
        store = MarketStore(sample_market_data)
        assert store.timestamp_index(datetime(2024, 2, 1, tzinfo=UTC)) == 4

    def test_timestamp_index_primary_default(
        self, sample_market_data: MarketData
    ) -> None:
        store = MarketStore(sample_market_data)
        assert store.timestamp_index(datetime(2024, 1, 5, tzinfo=UTC)) == 4

    def test_timestamp_index_unknown_timeframe_raises(
        self, sample_market_data: MarketData
    ) -> None:
        store = MarketStore(sample_market_data)
        with pytest.raises(ValueError, match="No data available for timeframe"):
            store.timestamp_index(datetime(2024, 1, 5, tzinfo=UTC), Timeframe.D1)

    def test_in_range_inclusive_bounds(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        candles = store.in_range(
            datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 4, tzinfo=UTC)
        )
        assert len(candles) == 3
        assert candles[0].open == 101.0
        assert candles[-1].open == 103.0

    def test_in_range_full_series(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        candles = store.in_range(
            datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 5, tzinfo=UTC)
        )
        assert len(candles) == 5

    def test_in_range_no_overlap(self, sample_market_data: MarketData) -> None:
        store = MarketStore(sample_market_data)
        candles = store.in_range(
            datetime(2024, 2, 1, tzinfo=UTC), datetime(2024, 2, 5, tzinfo=UTC)
        )
        assert candles == ()

    def test_in_range_specific_timeframe(
        self, dd: MarketData, wd: MarketData
    ) -> None:
        store = MarketStore({Timeframe.D1: dd, Timeframe.W1: wd})
        candles = store.in_range(
            datetime(2024, 1, 8, tzinfo=UTC),
            datetime(2024, 1, 29, tzinfo=UTC),
            Timeframe.W1,
        )
        assert len(candles) == 4  # weeks 1..4 start on/after Jan 8
        assert candles[0].open == 101.0

    def test_in_range_unknown_timeframe_raises(
        self, sample_market_data: MarketData
    ) -> None:
        store = MarketStore(sample_market_data)
        with pytest.raises(ValueError, match="No data available for timeframe"):
            store.in_range(
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 5, tzinfo=UTC),
                Timeframe.D1,
            )
