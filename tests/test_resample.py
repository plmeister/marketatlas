from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marketatlas.data.resample import CannotResampleError, resample, tf_minutes
from marketatlas.data.types import Candle, Timeframe


def _d(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=UTC)


def _h(day: int, hour: int) -> datetime:
    return datetime(2024, 1, day, hour, tzinfo=UTC)


def _h4(day: int, hour: int) -> datetime:
    h = hour // 4 * 4
    return datetime(2024, 1, day, h, tzinfo=UTC)


def _w(m: int, d: int) -> datetime:
    return datetime(2024, m, d, tzinfo=UTC)


class TestTfMinutes:
    def test_m1(self) -> None:
        assert tf_minutes(Timeframe.M1) == 1

    def test_h1(self) -> None:
        assert tf_minutes(Timeframe.H1) == 60

    def test_d1(self) -> None:
        assert tf_minutes(Timeframe.D1) == 1440

    def test_w1(self) -> None:
        assert tf_minutes(Timeframe.W1) == 10080


class TestCannotResampleError:
    def test_message(self) -> None:
        e = CannotResampleError(Timeframe.D1, Timeframe.H1)
        assert "1d" in str(e)
        assert "1h" in str(e)

    def test_attributes(self) -> None:
        e = CannotResampleError(Timeframe.W1, Timeframe.D1)
        assert e.source == Timeframe.W1
        assert e.target == Timeframe.D1


class TestResampleIdentity:
    def test_same_timeframe_returns_unchanged(self) -> None:
        candles = (
            Candle(_d(1), 100.0, 105.0, 99.0, 103.0, 1000.0),
            Candle(_d(2), 102.0, 106.0, 101.0, 104.0, 1100.0),
        )
        result = resample(candles, Timeframe.D1, Timeframe.D1)
        assert result == candles

    def test_empty_candles(self) -> None:
        result = resample((), Timeframe.H1, Timeframe.D1)
        assert result == ()


class TestResampleLowerToHigherErrors:
    def test_h1_to_m5_raises(self) -> None:
        candles = (Candle(_h(1, 0), 100.0, 105.0, 99.0, 103.0, 1000.0),)
        with pytest.raises(CannotResampleError):
            resample(candles, Timeframe.H1, Timeframe.M5)

    def test_d1_to_h1_raises(self) -> None:
        candles = (Candle(_d(1), 100.0, 105.0, 99.0, 103.0, 1000.0),)
        with pytest.raises(CannotResampleError):
            resample(candles, Timeframe.D1, Timeframe.H1)


class TestResampleH1toD1:
    def test_single_day(self) -> None:
        candles = tuple(
            Candle(_h(1, i), 100.0 + i, 105.0 + i, 99.0 + i, 103.0 + i, 100.0 + i)
            for i in range(24)
        )
        result = resample(candles, Timeframe.H1, Timeframe.D1)
        assert len(result) == 1
        assert result[0].open == 100.0
        assert result[0].high == 128.0
        assert result[0].low == 99.0
        assert result[0].close == 126.0
        assert result[0].volume == sum(100.0 + i for i in range(24))

    def test_multiple_days(self) -> None:
        candles = []
        for day in range(1, 4):
            for hour in range(0, 24, 1):
                candles.append(
                    Candle(
                        _h(day, hour),
                        100.0 + day,
                        105.0 + day,
                        99.0 + day,
                        103.0 + day,
                        1000.0 + day,
                    )
                )
        result = resample(tuple(candles), Timeframe.H1, Timeframe.D1)
        assert len(result) == 3

    def test_partial_day(self) -> None:
        candles = tuple(
            Candle(_h(1, i), 100.0, 105.0, 99.0, 103.0, 1000.0)
            for i in range(1, 6)
        )
        result = resample(candles, Timeframe.H1, Timeframe.D1)
        assert len(result) == 1
        assert result[0].open == 100.0
        assert result[0].close == 103.0


class TestResampleH1toH4:
    def test_single_block(self) -> None:
        candles = tuple(
            Candle(_h(1, i), 100.0 + i, 105.0 + i, 99.0 + i, 103.0 + i, 100.0 + i)
            for i in range(4)
        )
        result = resample(candles, Timeframe.H1, Timeframe.H4)
        assert len(result) == 1
        assert result[0].open == 100.0
        assert result[0].high == 108.0
        assert result[0].low == 99.0
        assert result[0].close == 106.0
        assert result[0].volume == sum(100.0 + i for i in range(4))

    def test_multiple_blocks(self) -> None:
        candles = tuple(
            Candle(_h(1, i), 100.0, 105.0, 99.0, 103.0, 1000.0)
            for i in range(8)
        )
        result = resample(candles, Timeframe.H1, Timeframe.H4)
        assert len(result) == 2

    def test_cross_day_blocks(self) -> None:
        candles = (
            Candle(_h(1, 22), 100.0, 105.0, 99.0, 103.0, 1000.0),
            Candle(_h(1, 23), 102.0, 106.0, 100.0, 104.0, 1100.0),
            Candle(_h(2, 0), 103.0, 107.0, 101.0, 105.0, 1200.0),
            Candle(_h(2, 1), 105.0, 108.0, 102.0, 106.0, 1300.0),
        )
        result = resample(candles, Timeframe.H1, Timeframe.H4)
        assert len(result) == 2
        assert result[0].timestamp.hour == 20  # block 20-23
        assert result[1].timestamp.hour == 0   # block 0-3 day 2


class TestResampleD1toW1:
    def test_single_week(self) -> None:
        candles = tuple(
            Candle(
                _d(i + 1), 100.0 + i, 105.0 + i, 99.0 + i, 103.0 + i, 1000.0 + i
            )
            for i in range(5)
        )
        result = resample(candles, Timeframe.D1, Timeframe.W1)
        assert len(result) == 1
        assert result[0].open == 100.0
        assert result[0].high == 109.0
        assert result[0].low == 99.0
        assert result[0].close == 107.0
        assert result[0].volume == sum(1000.0 + i for i in range(5))

    def test_multi_week(self) -> None:
        candles = []
        for day in range(1, 32):
            candles.append(
                Candle(
                    datetime(2024, 1, day, tzinfo=UTC),
                    100.0,
                    105.0,
                    99.0,
                    103.0,
                    1000.0,
                )
            )
        result = resample(tuple(candles), Timeframe.D1, Timeframe.W1)
        assert 4 <= len(result) <= 5  # Jan 2024 has 4-5 ISO weeks

    def test_week_starts_monday(self) -> None:
        # 2024-01-01 is Monday, Jan 7 (same ISO week), Jan 8 (next ISO week)
        candles = (
            Candle(_d(1), 100.0, 105.0, 99.0, 103.0, 1000.0),
            Candle(_d(7), 110.0, 115.0, 109.0, 113.0, 2000.0),
            Candle(_d(8), 120.0, 125.0, 119.0, 123.0, 3000.0),
        )
        result = resample(candles, Timeframe.D1, Timeframe.W1)
        assert len(result) == 2  # Jan 1-7 same week, Jan 8 next week
        assert result[0].open == 100.0
        assert result[0].close == 113.0  # Jan 7 close
        assert result[0].high == 115.0
        assert result[0].low == 99.0
        assert result[0].volume == 3000.0  # 1000 + 2000


class TestResampleH4toD1:
    def test_daily_aggregation(self) -> None:
        candles = tuple(
            Candle(_h4(1, i), 100.0, 105.0, 99.0, 103.0, 1000.0)
            for i in range(0, 24, 4)
        )
        result = resample(candles, Timeframe.H4, Timeframe.D1)
        assert len(result) == 1
