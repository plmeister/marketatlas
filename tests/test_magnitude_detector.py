from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.analysis.analyzers.range_position import RangePositionAnalyzer
from marketatlas.analysis.analyzers.swing_magnitude import MagnitudeSwingAnalyzer, tf_duration
from marketatlas.analysis.factkey import FactKey
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRPoint, ATRSeriesFact
from marketatlas.facts.structural import RangePositionFact, SwingFact, SwingPoint, SwingType

pytestmark = pytest.mark.tier2
BASE = datetime(2024, 1, 1, tzinfo=UTC)


DAY = timedelta(days=1)
WEEK = timedelta(days=7)


def _candles(
    values: list[tuple[float, float]],
    start: datetime = BASE,
    step: timedelta = DAY,
) -> tuple[Candle, ...]:
    """Build candles from (high, low) pairs; open/close are the midpoint.

    ``step`` must match the timeframe: a weekly series built with the default
    daily step would silently test weekly-bar completion on daily spacing.
    """
    return tuple(
        Candle(
            timestamp=start + step * i,
            open=(h + lo) / 2,
            high=h,
            low=lo,
            close=(h + lo) / 2,
            volume=1000.0,
        )
        for i, (h, lo) in enumerate(values)
    )


def _store(values: list[tuple[float, float]]) -> MarketStore:
    data = MarketData(symbol=Symbol("EURUSD"), timeframe=Timeframe.D1, candles=_candles(values))
    return MarketStore(data)


def _view(values: list[tuple[float, float]], cursor: int | None = None) -> MarketView:
    n = len(values)
    return MarketView(_store(values), cursor=n - 1 if cursor is None else cursor, window_size=n)


def _atr_fact(candles: tuple[Candle, ...], value: float) -> ATRSeriesFact:
    return ATRSeriesFact(
        timestamp=candles[-1].timestamp,
        evidence=(),
        points=tuple(ATRPoint(timestamp=c.timestamp, value=value) for c in candles),
        period=14,
    )


def _atr_facts(candles: tuple[Candle, ...], value: float) -> dict[FactKey, Fact]:
    return {FactKey("atr_14_series"): _atr_fact(candles, value)}


def _swing_facts(*swings: SwingPoint) -> dict[FactKey, Fact]:
    return {FactKey("magnitude_swings_3"): SwingFact(timestamp=BASE, evidence=(), swings=swings)}


def _zigzag(legs: list[float], start: float = 100.0) -> list[tuple[float, float]]:
    """Monotone legs of the given magnitude, direction alternating, 3 bars per leg.

    Sizes are magnitudes: the helper supplies the sign, so pass positives.
    Bars carry no spread (high == low == path) so pivot-to-pivot travel equals
    the leg magnitude exactly. With a non-zero spread every leg would be
    inflated by that spread and the magnitude floor would measure the wrong thing.
    """
    out: list[tuple[float, float]] = []
    price = start
    for i, size in enumerate(legs):
        direction = 1 if i % 2 == 0 else -1
        for step in range(3):
            price = price + direction * size * (step + 1) / 3
            out.append((price, price))
    return out


class TestMagnitudeFloor:
    def test_keeps_large_moves_and_drops_small_bounces(self) -> None:
        # legs: +10, -10, +10 (all >= 3 ATR) then +2, -2 (below the floor)
        values = _zigzag([10, 10, 10, 2, 2, 10])
        candles = _candles(values)
        facts = _atr_facts(candles, 1.0)
        analyzer = MagnitudeSwingAnalyzer(min_travel_atr=3.0)
        result = analyzer.analyze(_view(values), facts)
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        sizes = [
            abs(fact.swings[i].price - fact.swings[i - 1].price) for i in range(1, len(fact.swings))
        ]
        assert sizes, "expected at least one leg"
        assert all(s >= 3.0 for s in sizes), f"sub-floor leg survived: {sizes}"

    def test_output_strictly_alternates(self) -> None:
        values = _zigzag([12, 11, 9, 13, 8, 9, 14])
        candles = _candles(values)
        facts = _atr_facts(candles, 1.0)
        result = MagnitudeSwingAnalyzer(min_travel_atr=3.0).analyze(_view(values), facts)
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        for i in range(1, len(fact.swings)):
            assert fact.swings[i].type != fact.swings[i - 1].type

    def test_spacing_scales_with_atr(self) -> None:
        """Same price path, double the ATR, half the survivors."""
        values = _zigzag([10, 10, 10, 2, 2, 10])
        candles = _candles(values)
        counts = []
        for atr in (1.0, 2.0):
            facts = _atr_facts(candles, atr)
            fact = MagnitudeSwingAnalyzer(min_travel_atr=3.0).analyze(_view(values), facts).facts[0]
            assert isinstance(fact, SwingFact)
            counts.append(len(fact.swings))
        assert counts[1] < counts[0], f"ATR had no effect: {counts}"

    def test_zero_atr_does_not_suppress_swings(self) -> None:
        values = _zigzag([10] * 3)
        candles = _candles(values)
        facts = _atr_facts(candles, 0.0)
        fact = MagnitudeSwingAnalyzer(min_travel_atr=3.0).analyze(_view(values), facts).facts[0]
        assert isinstance(fact, SwingFact)
        assert len(fact.swings) >= 2, "degenerate ATR should not gate detection"

    def test_drops_more_pivots_than_basic_detector(self) -> None:
        # large legs interleaved with 1-ATR noise the basic detector keeps
        values = _zigzag([10, 10, 10, 1, 1, 10, 10, 10])
        candles = _candles(values)
        from marketatlas.analysis.analyzers.swing_basic import BasicSwingAnalyzer

        basic = (
            BasicSwingAnalyzer(
                lookback=len(values), left_bars=2, right_bars=2, enforce_alternation=True
            )
            .analyze(_view(values), {})
            .facts[0]
        )
        facts = _atr_facts(candles, 1.0)
        mag = MagnitudeSwingAnalyzer(min_travel_atr=3.0).analyze(_view(values), facts).facts[0]
        assert isinstance(basic, SwingFact)
        assert isinstance(mag, SwingFact)
        assert len(mag.swings) < len(basic.swings)

    def test_no_swing_beyond_right_bars_of_cursor(self) -> None:
        """Causality: a pivot needs ``right_bars`` later bars to exist."""
        values = _zigzag([10] * 5)
        candles = _candles(values)
        cursor = 8
        facts = _atr_facts(candles, 1.0)
        fact = (
            MagnitudeSwingAnalyzer(right_bars=2, min_travel_atr=3.0)
            .analyze(_view(values, cursor=cursor), facts)
            .facts[0]
        )
        assert isinstance(fact, SwingFact)
        limit = len(candles[: cursor + 1]) - 2 - 1
        assert all(s.index <= limit for s in fact.swings), [(s.index, limit) for s in fact.swings]

    def test_future_bars_do_not_change_earlier_swings(self) -> None:
        base = _zigzag([10] * 6)
        candles = _candles(base)
        facts = _atr_facts(candles, 1.0)
        cut = len(base) - 3
        before = (
            MagnitudeSwingAnalyzer(min_travel_atr=3.0)
            .analyze(_view(base, cursor=cut), facts)
            .facts[0]
        )
        after = MagnitudeSwingAnalyzer(min_travel_atr=3.0).analyze(_view(base), facts).facts[0]
        assert isinstance(before, SwingFact)
        assert isinstance(after, SwingFact)
        assert list(before.swings) == list(after.swings[: len(before.swings)])

    def test_insufficient_candles_returns_empty(self) -> None:
        # 4 bars cannot host a pivot with left_bars=2 and right_bars=2
        values = _zigzag([10, 10])[:4]
        result = MagnitudeSwingAnalyzer(left_bars=2, right_bars=2).analyze(_view(values), {})
        fact = result.facts[0]
        assert isinstance(fact, SwingFact)
        assert fact.swings == ()

    def test_rejects_non_positive_travel(self) -> None:
        with pytest.raises(ValueError, match="min_travel_atr"):
            MagnitudeSwingAnalyzer(min_travel_atr=0.0)

    def test_rejects_wrong_fact_type(self) -> None:
        values = _zigzag([10, 10])
        bad: dict[FactKey, Fact] = {
            FactKey("atr_14_series"): SwingFact(timestamp=BASE, evidence=(), swings=())
        }
        with pytest.raises(TypeError, match="ATRSeriesFact"):
            MagnitudeSwingAnalyzer().analyze(_view(values), bad)


def _weekly_store(
    daily: list[tuple[float, float]],
    weekly: list[tuple[float, float]],
    weekly_start: datetime | None = None,
) -> MarketStore:
    return MarketStore(
        {
            Timeframe.D1: MarketData(
                symbol=Symbol("EURUSD"), timeframe=Timeframe.D1, candles=_candles(daily)
            ),
            Timeframe.W1: MarketData(
                symbol=Symbol("EURUSD"),
                timeframe=Timeframe.W1,
                candles=_candles(
                    weekly,
                    start=BASE - timedelta(days=200) if weekly_start is None else weekly_start,
                    step=WEEK,
                ),
            ),
        }
    )


# ascending weekly highs, so range_bars/lag changes which bar is the window edge
_WEEKLY = [(100.0, 90.0), (110.0, 95.0), (120.0, 100.0), (130.0, 105.0)]


def _range_fact(
    weekly: list[tuple[float, float]],
    swing_price: float,
    swing_type: SwingType,
    *,
    daily_bars: int = 400,
    weekly_start: datetime | None = None,
    **kwargs: object,
) -> RangePositionFact:
    """Run RangePositionAnalyzer over a synthetic D1 + W1 store."""
    daily = [(100.0, 99.0)] * daily_bars
    store = _weekly_store(daily, weekly, weekly_start=weekly_start)
    view = MarketView(store, cursor=daily_bars - 1, window_size=daily_bars)
    swing = SwingPoint(
        price=swing_price,
        index=daily_bars - 1,
        type=swing_type,
        timestamp=view.current.timestamp,
    )
    analyzer = RangePositionAnalyzer(**kwargs)  # type: ignore[arg-type]
    fact = analyzer.analyze(view, _swing_facts(swing)).facts[0]
    assert isinstance(fact, RangePositionFact)
    return fact


class TestRangePosition:
    def test_uses_only_completed_weekly_bars(self) -> None:
        """A weekly bar stamped d covers [d, d+7) and must not be read at d+3."""
        fact = _range_fact(_WEEKLY, 115.0, SwingType.HIGH, confirmation_lag=0)
        assert (fact.high, fact.low) == (130.0, 90.0)
        assert fact.position == pytest.approx((115.0 - 90.0) / 40.0)

    def test_excludes_the_incomplete_weekly_bar(self) -> None:
        """The bar containing 'now' must not raise the range high."""
        fact = _range_fact(
            [(100.0, 90.0), (110.0, 95.0)],
            105.0,
            SwingType.LOW,
            confirmation_lag=0,
            weekly_start=BASE - timedelta(days=2),  # week in progress
        )
        assert fact.high == 110.0, "in-progress weekly bar leaked into the range"
        assert fact.low == 90.0

    def test_position_exceeds_one_on_breakout(self) -> None:
        fact = _range_fact(
            [(100.0, 90.0), (105.0, 95.0)], 150.0, SwingType.HIGH, confirmation_lag=0
        )
        assert fact.position is not None
        assert fact.position > 1.0
        assert any(e.level.name == "WARNING" for e in fact.evidence)

    def test_confirmation_lag_shifts_the_window_back(self) -> None:
        """Weekly bars stamped BASE-21, BASE-14, BASE-7, BASE; cursor 10 bars in."""
        common = {
            "daily_bars": 11,
            "weekly_start": BASE - timedelta(days=21),
            "range_bars": 1,
        }
        no_lag = _range_fact(_WEEKLY, 112.0, SwingType.HIGH, confirmation_lag=0, **common)
        lagged = _range_fact(_WEEKLY, 112.0, SwingType.HIGH, confirmation_lag=2, **common)
        assert no_lag.high == 130.0, "lag=0 should read the most recent completed week"
        assert lagged.high == 110.0, "lag=2 should have dropped the two most recent weeks"

    def test_range_bars_limits_the_window(self) -> None:
        common = {
            "daily_bars": 11,
            "weekly_start": BASE - timedelta(days=21),
            "confirmation_lag": 0,
        }
        wide = _range_fact(_WEEKLY, 112.0, SwingType.HIGH, range_bars=4, **common)
        narrow = _range_fact(_WEEKLY, 112.0, SwingType.HIGH, range_bars=2, **common)
        assert (wide.high, wide.low) == (130.0, 90.0)
        assert (narrow.high, narrow.low) == (130.0, 100.0)

    def test_flat_range_yields_none_position(self) -> None:
        fact = _range_fact(
            [(100.0, 100.0), (100.0, 100.0)], 100.0, SwingType.LOW, confirmation_lag=0
        )
        assert fact.position is None

    def test_missing_weekly_data_raises(self) -> None:
        store = _store([(100.0, 99.0)] * 400)
        view = MarketView(store, cursor=399, window_size=400)
        with pytest.raises(ValueError, match="1w"):
            RangePositionAnalyzer().analyze(view, {})

    def test_rejects_bad_params(self) -> None:
        with pytest.raises(ValueError, match="range_bars"):
            RangePositionAnalyzer(range_bars=0)
        with pytest.raises(ValueError, match="confirmation_lag"):
            RangePositionAnalyzer(confirmation_lag=-1)


class TestRegistryWiring:
    def test_capabilities_registered(self) -> None:
        from marketatlas.analysis.ast.registry import create_default_registry

        caps = create_default_registry().capabilities()
        assert "magnitudeswings" in caps
        assert "rangeposition" in caps

    def test_contract_chain_is_wired(self) -> None:
        from marketatlas.analysis.ast.registry import create_default_registry

        registry = create_default_registry()
        mag = registry.contract("magnitudeswings")
        rp = registry.contract("rangeposition")
        assert mag is not None and rp is not None
        assert mag.inputs == ("atr_14_series",)
        assert mag.outputs == ("magnitude_swings_3",)
        assert rp.inputs == mag.outputs, "range position must consume the detector output"
        assert rp.outputs == ("range_position_1w_12",)

    def test_constructors_build_definitions(self) -> None:
        from marketatlas.analysis.ast import MagnitudeSwings, RangePosition

        d = MagnitudeSwings("magsw", min_travel_atr=4.0)
        assert d.name == "magsw"
        rp = RangePosition("rp", range_bars=8)
        assert rp.name == "rp"

    def test_tf_duration_covers_all_timeframes(self) -> None:
        assert tf_duration(Timeframe.W1) == timedelta(days=7)
        assert tf_duration(Timeframe.D1) == timedelta(days=1)
        assert tf_duration(Timeframe.H4) == timedelta(hours=4)
