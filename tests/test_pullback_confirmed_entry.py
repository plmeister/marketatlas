"""Backlog 067: confirmed pullback entry.

`PullbackPatternAnalyzer` emits `PullbackFact` only on the candle immediately
following the final swing point of the swing structure, and only when that
candle confirms the expected movement (strong body, close beyond the swing).
Rejected confirmations produce per-candle evidence. Confirmed pullbacks flow
through `PullbackSignal` and `RiskEngine` to a sized `TradeCandidate`.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.patterns.pullback import PullbackPatternAnalyzer
from marketatlas.backtesting.backtester import Backtester
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceLevel
from marketatlas.facts.pattern import PullbackFact
from marketatlas.facts.structural import SwingPoint, SwingStructureFact, SwingType, TrendDirection
from marketatlas.strategy.bundle import StrategyBundle
from marketatlas.strategy.config import AnalyzerConfig, RiskConfig, SignalConfig, StrategyConfig
from marketatlas.strategy.strategy import Strategy

BASE = datetime(2024, 1, 1, tzinfo=UTC)

STRUCTURE_KEY = FactKey("swing_structure", timeframe=Timeframe.D1)


def _candles(
    data: list[tuple[float, float, float, float]],
    *,
    start: datetime = BASE,
    step_days: int = 1,
) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            timestamp=start + timedelta(days=i * step_days),
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=1000.0,
        )
        for i, (o, h, lo, c) in enumerate(data)
    )


def _store(
    data: list[tuple[float, float, float, float]],
) -> MarketStore:
    return MarketStore(
        MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=_candles(data))
    )


def _bullish_zigzag() -> list[tuple[float, float, float, float]]:
    """Bullish LHLHL (rising lows + rising highs) with a strong confirmation at 7.

    Swing points: SH 102@1, SL 97@2, SH 108@3, SL 99@4, SH 114@5, SL 101@6.
    """
    return [
        (100.0, 101.0, 99.0, 100.0),  # 0
        (100.0, 102.0, 100.0, 101.0),  # 1: SH 102
        (101.0, 101.0, 97.0, 100.0),  # 2: SL 97
        (100.0, 108.0, 100.0, 106.0),  # 3: SH 108
        (106.0, 106.0, 99.0, 102.0),  # 4: SL 99
        (102.0, 114.0, 102.0, 112.0),  # 5: SH 114
        (112.0, 112.0, 101.0, 106.0),  # 6: SL 101  <- final swing, index 6
        (102.0, 116.0, 104.0, 114.0),  # 7: strong bullish confirmation
        (114.0, 118.0, 113.0, 117.0),  # 8: later candle
    ]


def _bullish_structure(last_index: int = 6) -> SwingStructureFact:
    """LHLHL structure ending at the swing low on ``last_index``."""
    pts = [(97.0, SwingType.LOW), (108.0, SwingType.HIGH), (99.0, SwingType.LOW),
           (114.0, SwingType.HIGH), (101.0, SwingType.LOW)]
    start = last_index - 4
    return SwingStructureFact(
        timestamp=BASE,
        evidence=(),
        points=tuple(
            SwingPoint(
                price=price,
                index=start + i,
                type=stype,
                timestamp=BASE + timedelta(days=start + i),
            )
            for i, (price, stype) in enumerate(pts)
        ),
    )


def _bearish_data() -> list[tuple[float, float, float, float]]:
    """Bearish HLHLH (falling highs + falling lows), final swing HIGH@7.

    Swing points: SH 110@1, SL 98@2, SH 106@3, SL 96@4, SH 103@5, SL 95@6,
    SH 102@7.
    """
    return [
        (100.0, 101.0, 99.0, 100.0),  # 0
        (100.0, 110.0, 100.0, 108.0),  # 1: SH 110
        (108.0, 102.0, 98.0, 100.0),  # 2: SL 98
        (100.0, 106.0, 100.0, 104.0),  # 3: SH 106
        (104.0, 100.0, 96.0, 98.0),  # 4: SL 96
        (98.0, 103.0, 98.0, 101.0),  # 5: SH 103
        (101.0, 99.0, 95.0, 97.0),  # 6: SL 95
        (97.0, 102.0, 97.0, 99.0),  # 7: SH 102  <- final swing, index 7
        (99.0, 100.0, 90.0, 91.0),  # 8: strong bearish confirmation
    ]


def _bearish_structure() -> SwingStructureFact:
    pts = [(106.0, SwingType.HIGH, 3), (96.0, SwingType.LOW, 4), (103.0, SwingType.HIGH, 5),
           (95.0, SwingType.LOW, 6), (102.0, SwingType.HIGH, 7)]
    return SwingStructureFact(
        timestamp=BASE,
        evidence=(),
        points=tuple(
            SwingPoint(
                price=price,
                index=idx,
                type=stype,
                timestamp=BASE + timedelta(days=idx),
            )
            for price, stype, idx in pts
        ),
    )


def _analyzer(**kwargs: Any) -> PullbackPatternAnalyzer:
    return PullbackPatternAnalyzer(timeframe="1d", **kwargs)


def _view(cursor: int, data: list[tuple[float, float, float, float]]) -> MarketView:
    return MarketView(_store(data), cursor=cursor, window_size=len(data))


class TestEntryDayGating:
    def test_fact_placed_exactly_on_entry_candle(self) -> None:
        data = _bullish_zigzag()
        analyzer = _analyzer()
        result = analyzer.analyze(_view(7, data), {STRUCTURE_KEY: _bullish_structure()})
        assert len(result.facts) == 1
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.direction == TrendDirection.BULLISH
        assert fact.swing_pattern != ()

    def test_no_fact_on_swing_candle(self) -> None:
        data = _bullish_zigzag()
        analyzer = _analyzer()
        result = analyzer.analyze(_view(6, data), {STRUCTURE_KEY: _bullish_structure()})
        assert result.facts == ()
        assert any("awaiting entry candle" in e.text for e in result.evidence)

    def test_no_fact_on_later_candle(self) -> None:
        data = _bullish_zigzag()
        analyzer = _analyzer()
        result = analyzer.analyze(_view(8, data), {STRUCTURE_KEY: _bullish_structure()})
        assert result.facts == ()
        assert any("entry window missed" in e.text for e in result.evidence)

    def test_no_structure_returns_no_fact(self) -> None:
        data = _bullish_zigzag()
        analyzer = _analyzer()
        result = analyzer.analyze(_view(7, data), {})
        assert result.facts == ()

    def test_no_readahead_future_candles_do_not_shift_entry(self) -> None:
        future = _bullish_zigzag() + [(117.0, 120.0, 116.0, 119.0)]
        analyzer = _analyzer()
        result = analyzer.analyze(
            _view(8, future), {STRUCTURE_KEY: _bullish_structure()}
        )
        assert result.facts == ()


class TestConfirmationGate:
    def test_strong_candle_places_fact(self) -> None:
        data = _bullish_zigzag()
        analyzer = _analyzer()
        result = analyzer.analyze(_view(7, data), {STRUCTURE_KEY: _bullish_structure()})
        assert len(result.facts) == 1

    def test_weak_body_no_fact_with_evidence(self) -> None:
        data = list(_bullish_zigzag())
        data[7] = (102.0, 116.0, 104.0, 108.0)  # body 6/12 = 0.50 < 0.6
        analyzer = _analyzer()
        result = analyzer.analyze(_view(7, data), {STRUCTURE_KEY: _bullish_structure()})
        assert result.facts == ()
        assert len(result.evidence) == 1
        entry = result.evidence[0]
        assert entry.level == EvidenceLevel.WARNING
        assert "confirmation candle weak" in entry.text
        assert "body 0.50 < 0.60" in entry.text

    def test_wrong_direction_no_fact_with_evidence(self) -> None:
        data = list(_bullish_zigzag())
        data[7] = (114.0, 116.0, 104.0, 107.0)  # bearish candle on bullish pattern
        analyzer = _analyzer()
        result = analyzer.analyze(_view(7, data), {STRUCTURE_KEY: _bullish_structure()})
        assert result.facts == ()
        assert any("confirmation candle weak" in e.text for e in result.evidence)

    def test_close_not_beyond_swing_rejected(self) -> None:
        data = list(_bullish_zigzag())
        data[7] = (95.0, 100.0, 95.0, 99.5)  # body 0.9 but close 99.5 < swing 101
        analyzer = _analyzer()
        result = analyzer.analyze(_view(7, data), {STRUCTURE_KEY: _bullish_structure()})
        assert result.facts == ()
        assert any("not > swing 101.00" in e.text for e in result.evidence)

    def test_close_not_beyond_allowed_when_disabled(self) -> None:
        data = list(_bullish_zigzag())
        data[7] = (95.0, 100.0, 95.0, 99.5)
        analyzer = _analyzer(confirm_beyond_swing=False)
        result = analyzer.analyze(_view(7, data), {STRUCTURE_KEY: _bullish_structure()})
        assert len(result.facts) == 1

    def test_flat_candle_body_ratio_zero(self) -> None:
        data = list(_bullish_zigzag())
        data[7] = (101.0, 101.0, 101.0, 101.0)
        analyzer = _analyzer()
        result = analyzer.analyze(_view(7, data), {STRUCTURE_KEY: _bullish_structure()})
        assert result.facts == ()
        assert any("body 0.00 < 0.60" in e.text for e in result.evidence)

    def test_min_body_pct_threshold(self) -> None:
        data = list(_bullish_zigzag())
        data[7] = (102.0, 116.0, 104.0, 108.0)  # body 0.50
        analyzer = _analyzer(min_body_pct=0.4)
        result = analyzer.analyze(_view(7, data), {STRUCTURE_KEY: _bullish_structure()})
        assert len(result.facts) == 1

    def test_bearish_confirmation(self) -> None:
        data = _bearish_data()
        analyzer = _analyzer()
        result = analyzer.analyze(_view(8, data), {STRUCTURE_KEY: _bearish_structure()})
        assert len(result.facts) == 1
        fact = result.facts[0]
        assert isinstance(fact, PullbackFact)
        assert fact.direction == TrendDirection.BEARISH

    def test_lookback_swings_limits_pattern(self) -> None:
        data = _bullish_zigzag()
        analyzer = _analyzer(lookback_swings=3)
        result = analyzer.analyze(_view(7, data), {STRUCTURE_KEY: _bullish_structure()})
        # 3 points: one high, two lows -> insufficient structure, no pattern.
        assert result.facts == ()
        assert any("not enough structured swings" in e.text for e in result.evidence)


class TestCrossTimeframe:
    def _daily_store(self) -> MarketStore:
        d1_data: list[tuple[float, float, float, float]] = []
        for i in range(35):
            if i == 29:
                d1_data.append((96.0, 108.0, 96.0, 106.0))  # strong bullish confirmation
            else:
                d1_data.append((100.0, 101.0, 99.0, 100.0))
        d1 = _candles(d1_data)
        w1 = _candles([(100.0, 101.0, 99.0, 100.0)] * 6, start=BASE, step_days=7)
        return MarketStore(
            {
                Timeframe.D1: MarketData(
                    symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=d1
                ),
                Timeframe.W1: MarketData(
                    symbol=Symbol("BTCUSDT"), timeframe=Timeframe.W1, candles=w1
                ),
            }
        )

    def _weekly_structure(self) -> SwingStructureFact:
        """LHLHL whose final swing is the week-4 candle (Mon, BASE+28d)."""
        pts = [(94.0, SwingType.LOW), (98.0, SwingType.HIGH), (95.0, SwingType.LOW),
               (100.0, SwingType.HIGH), (96.0, SwingType.LOW)]
        return SwingStructureFact(
            timestamp=BASE,
            evidence=(),
            points=tuple(
                SwingPoint(
                    price=price,
                    index=i,
                    type=stype,
                    timestamp=BASE + timedelta(days=7 * i),
                )
                for i, (price, stype) in enumerate(pts)
            ),
        )

    def test_entry_day_from_swing_timestamp(self) -> None:
        """1w structure -> 1d confirmation: entry day is the 1d candle after the
        swing point's timestamp (Tue w5 = daily index 29), not a raw index."""
        store = self._daily_store()
        analyzer = PullbackPatternAnalyzer(
            timeframe="1d", bindings={"swing_structure": "swing_structure@1w"}
        )
        view = MarketView(store, cursor=29, window_size=35, view_timeframe=Timeframe.D1)
        key = FactKey("swing_structure", timeframe=Timeframe("1w"))
        result = analyzer.analyze(view, {key: self._weekly_structure()})
        assert len(result.facts) == 1
        assert isinstance(result.facts[0], PullbackFact)

    def test_before_entry_day_no_fact(self) -> None:
        store = self._daily_store()
        analyzer = PullbackPatternAnalyzer(
            timeframe="1d", bindings={"swing_structure": "swing_structure@1w"}
        )
        view = MarketView(store, cursor=28, window_size=35, view_timeframe=Timeframe.D1)
        key = FactKey("swing_structure", timeframe=Timeframe("1w"))
        result = analyzer.analyze(view, {key: self._weekly_structure()})
        assert result.facts == ()


class TestEndToEnd:
    def _strategy_config(self) -> StrategyConfig:
        return StrategyConfig(
            name="pullback_e2e",
            version="1.0",
            timeframes=("1d",),
            analyzers=(
                AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),
                AnalyzerConfig(type="EMAAnalyzer", params={"period": 50}),
                AnalyzerConfig(type="ATRAnalyzer", params={"period": 14}),
                AnalyzerConfig(type="ATRSeriesAnalyzer", params={"period": 14}),
                AnalyzerConfig(type="TrendAnalyzer"),
                AnalyzerConfig(
                    type="BasicSwingAnalyzer",
                    params={"lookback": 50, "left_bars": 1, "right_bars": 1},
                ),
                AnalyzerConfig(type="SwingStructureAnalyzer", params={"window": 20}),
                AnalyzerConfig(type="SupportResistanceAnalyzer"),
                AnalyzerConfig(type="PullbackPatternAnalyzer"),
            ),
            signals=(SignalConfig(type="PullbackSignal", rules={}),),
            risk=RiskConfig(
                algorithm="default",
                params={"risk_pct": 1.0, "min_rr": 2.0, "max_rr": 4.0},
            ),
        )

    def _rising_store(self) -> MarketStore:
        data: list[tuple[float, float, float, float]] = []
        for i in range(59):
            price = 100.0 + i * 0.1
            data.append((price, price + 0.5, price - 0.5, price + 0.2))
        data += _bullish_zigzag()
        return _store(data)

    def test_confirmed_pullback_reaches_risk_engine(self) -> None:
        store = self._rising_store()
        strategy = Strategy("pullback_e2e", self._strategy_config())
        view = MarketView(store, cursor=66, window_size=60)
        facts = strategy.graph.run(view)
        signals = strategy.evaluate(view, facts)
        assert len(signals) == 1
        assert signals[0].direction == TrendDirection.BULLISH

        candidate, _ = strategy.risk_engine.evaluate(signals[0], facts, view)
        assert candidate is not None
        assert candidate.size > 0
        assert candidate.entry > 0
        assert candidate.target > candidate.entry

    def test_backtester_records_trade_from_confirmed_pullback(self) -> None:
        store = self._rising_store()
        strategy = Strategy("pullback_e2e", self._strategy_config())
        bundle = StrategyBundle([strategy])
        _, tradebook = Backtester(store, bundle, window_size=60).run()
        assert len(tradebook.trades) >= 1
        assert all(t.candidate.size > 0 for t in tradebook.trades)


class TestRejectionEvidenceOnFrame:
    def test_weak_confirmation_evidence_reaches_frame(self) -> None:
        data = list(_bullish_zigzag())
        data[7] = (102.0, 116.0, 104.0, 108.0)  # weak body -> no fact
        store = _store(data)
        config = StrategyConfig(
            name="weak_pb",
            version="1.0",
            timeframes=("1d",),
            analyzers=(
                AnalyzerConfig(
                    type="BasicSwingAnalyzer",
                    params={"lookback": 50, "left_bars": 1, "right_bars": 1},
                ),
                AnalyzerConfig(type="SwingStructureAnalyzer", params={"window": 20}),
                AnalyzerConfig(type="PullbackPatternAnalyzer"),
            ),
            signals=(),
        )
        strategy = Strategy("weak_pb", config)
        bundle = StrategyBundle([strategy])
        frames, _ = Backtester(store, bundle, window_size=7).run()
        entry_frame = frames[0]
        assert any("confirmation candle weak" in e.text for e in entry_frame.evidence)
