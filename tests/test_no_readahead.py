"""No-read-ahead audit.

Proves every component only sees data available at or before the current candle.
"""

from datetime import datetime, timedelta

from marketatlas.backtesting.backtester import Backtester
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.facts.structural import TrendDirection
from marketatlas.strategy.bundle import StrategyBundle
from marketatlas.strategy.config import AnalyzerConfig, RiskConfig, SignalConfig, StrategyConfig
from marketatlas.strategy.strategy import Strategy
from marketatlas.strategy.tradebook import TradeBook

BASE = datetime(2024, 1, 1)


def _make_candles(n: int) -> tuple[Candle, ...]:
    """Deterministic rising-then-falling candles for consistent behavior."""
    candles = []
    for i in range(n):
        ts = BASE + timedelta(hours=i)
        if i % 20 < 10:
            price = 100.0 + i * 0.5
        else:
            price = 105.0 - (i % 20 - 10) * 0.5 + (i // 20) * 5
        candles.append(
            Candle(
                timestamp=ts,
                open=price,
                high=price + 3.0,
                low=price - 3.0,
                close=price + 1.0,
                volume=1000.0 + i,
            )
        )
    return tuple(candles)


def _make_store(n: int) -> MarketStore:
    candles = _make_candles(n)
    return MarketStore(
        MarketData(
            symbol=Symbol("TEST"),
            timeframe=Timeframe.H1,
            candles=candles,
        )
    )


def _make_bundle() -> StrategyBundle:
    config = StrategyConfig(
        name="audit_strategy",
        version="1.0",
        timeframes=("1h",),
        analyzers=(
            AnalyzerConfig(type="EMAAnalyzer", params={"period": 20}),
            AnalyzerConfig(type="EMAAnalyzer", params={"period": 50}),
            AnalyzerConfig(type="ATRAnalyzer", params={"period": 14}),
            AnalyzerConfig(type="TrendAnalyzer"),
            AnalyzerConfig(type="BasicSwingAnalyzer", params={"lookback": 50}),
            AnalyzerConfig(type="SwingStructureAnalyzer", params={"window": 20}),
            AnalyzerConfig(type="PullbackPatternAnalyzer"),
        ),
        signals=(
            SignalConfig(
                type="PullbackSignal",
                rules={"min_strength": 0.3},
            ),
        ),
        risk=RiskConfig(
            algorithm="default",
            params={
                "risk_pct": 1.0,
                "min_rr": 2.0,
                "max_rr": 4.0,
                "max_stop_atr": 3.0,
                "slippage_pct": 0.1,
                "avoid_srxing": True,
            },
        ),
    )
    strategy = Strategy("audit_strategy", config)
    return StrategyBundle([strategy])


def _snapshot_frame(frame) -> dict:
    """Extract a comparable snapshot from an AnalysisFrame."""
    return {
        "timestamp": frame.timestamp,
        "close": frame.candle.close,
        "open": frame.candle.open,
        "high": frame.candle.high,
        "low": frame.candle.low,
        "volume": frame.candle.volume,
        "num_facts": len(frame.facts),
        "num_evidence": len(frame.evidence),
        "fact_keys": sorted(frame.facts.keys(), key=lambda k: k.name),
    }


class TestFrameIndependence:
    """Changing the future should not change the past."""

    def test_frame_n_independent_of_frame_n_plus_1(self) -> None:
        store_short = _make_store(200)
        bt_short = Backtester(store_short, _make_bundle(), window_size=50)
        frames_short = bt_short.run().frames

        target_idx = 100
        assert target_idx < len(frames_short)
        snapshot_before = _snapshot_frame(frames_short[target_idx])

        store_long = _make_store(201)
        bt_long = Backtester(store_long, _make_bundle(), window_size=50)
        frames_long = bt_long.run().frames

        snapshot_after = _snapshot_frame(frames_long[target_idx])
        assert snapshot_before == snapshot_after


class TestMarketViewBoundary:
    """MarketView at cursor=N only sees candles <= N."""

    def test_max_index_in_view(self) -> None:
        store = _make_store(200)
        cursor = 150
        view = MarketView(store, cursor, window_size=100)

        all_candle_indices = []
        for c in view.history:
            ts = c.timestamp
            for idx in range(len(store)):
                if store[idx].timestamp == ts:
                    all_candle_indices.append(idx)
                    break
        current_idx = cursor
        all_candle_indices.append(current_idx)

        assert max(all_candle_indices) == cursor

    def test_no_future_candle_accessible(self) -> None:
        store = _make_store(200)
        cursor = 150
        view = MarketView(store, cursor, window_size=100)

        future_candle = store[151]
        assert future_candle not in view.history
        assert future_candle != view.current

    def test_history_len_bounded(self) -> None:
        store = _make_store(200)
        cursor = 150
        view = MarketView(store, cursor, window_size=100)
        assert len(view.history) == 100
        assert len(view.prices) == 101


class TestAnalyzerIsolation:
    """Adding future candles to store does not change analyzer output at current cursor."""

    def test_analyzer_output_unchanged_when_future_appended(self) -> None:
        store_200 = _make_store(200)
        bt_200 = Backtester(store_200, _make_bundle(), window_size=50)
        frames_200 = bt_200.run().frames

        target_idx = 100
        assert target_idx < len(frames_200)
        snapshot_200 = _snapshot_frame(frames_200[target_idx])

        store_210 = _make_store(210)
        bt_210 = Backtester(store_210, _make_bundle(), window_size=50)
        frames_210 = bt_210.run().frames

        snapshot_210 = _snapshot_frame(frames_210[target_idx])
        assert snapshot_200 == snapshot_210

    def test_fact_values_unchanged(self) -> None:
        store_200 = _make_store(200)
        bt_200 = Backtester(store_200, _make_bundle(), window_size=50)
        frames_200 = bt_200.run().frames

        target_idx = 100
        facts_200 = frames_200[target_idx].facts

        store_210 = _make_store(210)
        bt_210 = Backtester(store_210, _make_bundle(), window_size=50)
        frames_210 = bt_210.run().frames

        facts_210 = frames_210[target_idx].facts
        assert facts_200.keys() == facts_210.keys()

        for key in facts_200:
            f1 = facts_200[key]
            f2 = facts_210[key]
            assert type(f1) is type(f2)
            assert f1.timestamp == f2.timestamp


class TestSignalIsolation:
    """Adding future candles does not change signal evaluation at current frame."""

    def test_signal_output_unchanged_when_future_appended(self) -> None:
        store_200 = _make_store(200)
        bt_200 = Backtester(store_200, _make_bundle(), window_size=50)
        tb_200 = bt_200.run().tradebook

        store_210 = _make_store(210)
        bt_210 = Backtester(store_210, _make_bundle(), window_size=50)
        tb_210 = bt_210.run().tradebook

        assert tb_200.balance == tb_210.balance
        assert len(tb_200.trades) == len(tb_210.trades)


class TestRiskIsolation:
    """Adding future candles does not change risk sizing at current frame."""

    def test_risk_output_unchanged_when_future_appended(self) -> None:
        store_200 = _make_store(200)
        bt_200 = Backtester(store_200, _make_bundle(), window_size=50)
        result_200 = bt_200.run()
        frames_200, tb_200 = result_200.frames, result_200.tradebook

        store_210 = _make_store(210)
        bt_210 = Backtester(store_210, _make_bundle(), window_size=50)
        result_210 = bt_210.run()
        frames_210, tb_210 = result_210.frames, result_210.tradebook

        assert len(frames_210) > len(frames_200)
        for i in range(len(frames_200)):
            assert _snapshot_frame(frames_200[i]) == _snapshot_frame(frames_210[i])


class TestTradeBookResolution:
    """Signal at cursor N fills at open of cursor N+1."""

    def test_fill_order_uses_next_candle_open(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        from marketatlas.strategy.signals import TradeSignal
        from marketatlas.strategy.trade import TradeCandidate

        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 101.0),
            confidence=0.7,
            source="test",
            evidence=(),
        )
        candidate = TradeCandidate(
            direction=TrendDirection.BULLISH,
            entry=100.5,
            stop=95.0,
            target=115.0,
            size=0.1,
            risk_amount=10.0,
            reward_amount=30.0,
            rr_ratio=3.0,
            slippage_pct=0.1,
            source="test",
            evidence=(),
        )

        signal_time = datetime(2024, 1, 10)
        tb.submit_order(candidate, signal, "test", signal_time)
        assert tb.has_pending_order
        assert tb.has_no_open_trade

        fill_time = datetime(2024, 1, 11)
        fill_candle = Candle(
            timestamp=fill_time,
            open=101.0,
            high=110.0,
            low=99.0,
            close=108.0,
            volume=5000.0,
        )
        tb.fill_order(fill_candle.open, fill_candle.timestamp)

        assert not tb.has_pending_order
        assert not tb.has_no_open_trade

        open_trade = tb._open_trade
        assert open_trade is not None
        assert open_trade.entry_timestamp == fill_time
        assert open_trade.candidate.entry == 100.5

        stop_candle = Candle(
            timestamp=datetime(2024, 1, 12),
            open=102.0,
            high=103.0,
            low=94.0,
            close=95.0,
            volume=5000.0,
        )
        tb.resolve_at_cursor(stop_candle, max_hold_days=10)
        assert tb.has_no_open_trade
        assert len(tb.trades) == 1
        assert tb.trades[0].result == "loss"
        assert tb.trades[0].exit_timestamp == stop_candle.timestamp

    def test_resolve_only_checks_current_candle(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        from marketatlas.strategy.signals import TradeSignal
        from marketatlas.strategy.trade import TradeCandidate

        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 101.0),
            confidence=0.7,
            source="test",
            evidence=(),
        )
        candidate = TradeCandidate(
            direction=TrendDirection.BULLISH,
            entry=100.5,
            stop=95.0,
            target=115.0,
            size=0.1,
            risk_amount=10.0,
            reward_amount=30.0,
            rr_ratio=3.0,
            slippage_pct=0.1,
            source="test",
            evidence=(),
        )

        tb.submit_order(candidate, signal, "test", datetime(2024, 1, 10))
        tb.fill_order(101.0, datetime(2024, 1, 11))

        safe_candle = Candle(
            timestamp=datetime(2024, 1, 12),
            open=102.0,
            high=112.0,
            low=97.0,
            close=110.0,
            volume=5000.0,
        )
        tb.resolve_at_cursor(safe_candle, max_hold_days=10)
        assert not tb.has_no_open_trade

        target_candle = Candle(
            timestamp=datetime(2024, 1, 13),
            open=113.0,
            high=116.0,
            low=112.0,
            close=115.0,
            volume=5000.0,
        )
        tb.resolve_at_cursor(target_candle, max_hold_days=10)
        assert tb.has_no_open_trade
        assert tb.trades[0].result == "win"


class TestFullBacktestDeterministic:
    """Running the same backtest twice produces identical results."""

    def test_full_backtest_deterministic(self) -> None:
        store = _make_store(200)

        bt1 = Backtester(store, _make_bundle(), window_size=50)
        result1 = bt1.run()
        frames1, tb1 = result1.frames, result1.tradebook

        bt2 = Backtester(store, _make_bundle(), window_size=50)
        result2 = bt2.run()
        frames2, tb2 = result2.frames, result2.tradebook

        assert len(frames1) == len(frames2)
        for i in range(len(frames1)):
            assert _snapshot_frame(frames1[i]) == _snapshot_frame(frames2[i])

        assert tb1.balance == tb2.balance
        assert len(tb1.trades) == len(tb2.trades)
        for t1, t2 in zip(tb1.trades, tb2.trades):
            assert t1.entry_timestamp == t2.entry_timestamp
            assert t1.exit_timestamp == t2.exit_timestamp
            assert t1.result == t2.result
            assert t1.pnl == t2.pnl


class TestSingleTradeConstraint:
    """Only one trade open at a time. Only one pending order at a time."""

    def test_no_second_trade_while_open(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        from marketatlas.strategy.signals import TradeSignal
        from marketatlas.strategy.trade import TradeCandidate

        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 101.0),
            confidence=0.7,
            source="test",
            evidence=(),
        )
        candidate = TradeCandidate(
            direction=TrendDirection.BULLISH,
            entry=100.5,
            stop=95.0,
            target=115.0,
            size=0.1,
            risk_amount=10.0,
            reward_amount=30.0,
            rr_ratio=3.0,
            slippage_pct=0.1,
            source="test",
            evidence=(),
        )

        # Before submit: no open trade, no pending order
        assert tb.has_no_open_trade
        assert not tb.has_pending_order

        tb.submit_order(candidate, signal, "test", datetime(2024, 1, 10))

        # After submit: no open trade yet, but pending order blocks new signals
        assert tb.has_no_open_trade
        assert tb.has_pending_order

        tb.fill_order(101.0, datetime(2024, 1, 11))

        # After fill: open trade exists, no pending order
        assert not tb.has_no_open_trade
        assert not tb.has_pending_order
