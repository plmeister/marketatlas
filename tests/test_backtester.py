from datetime import datetime, timedelta

import pytest
from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.analysis.result import AnalysisResult
from marketatlas.backtesting.backtester import Backtester
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import SRFact, TrendDirection
from marketatlas.strategy.bundle import StrategyBundle
from marketatlas.strategy.config import StrategyConfig
from marketatlas.strategy.risk import RiskEngine
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.strategy import Strategy
from marketatlas.strategy.trade import TradeCandidate
from marketatlas.strategy.tradebook import TradeBook


def _make_candles(n: int, start: datetime | None = None) -> tuple[Candle, ...]:
    base = start or datetime(2024, 1, 1)
    candles = []
    for i in range(n):
        ts = base + timedelta(hours=i)
        price = 100.0 + i
        candles.append(
            Candle(
                timestamp=ts,
                open=price,
                high=price + 5,
                low=price - 5,
                close=price + 2,
                volume=1000.0 + i,
            )
        )
    return tuple(candles)


class StubAnalyzer(Analyzer):
    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey("stub_ema"),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        candle = view.current
        ema = EMAFact(
            timestamp=candle.timestamp,
            evidence=(
                EvidenceEntry(
                    text="stub EMA",
                    level=EvidenceLevel.INFO,
                    source="StubAnalyzer",
                ),
            ),
            value=candle.close,
            period=20,
        )
        return AnalysisResult(
            facts=(ema,),
            evidence=(
                EvidenceEntry(
                    text="stub evidence",
                    level=EvidenceLevel.INFO,
                    source="StubAnalyzer",
                ),
            ),
        )


def _make_store(n: int = 100) -> MarketStore:
    candles = _make_candles(n)
    data = MarketData(
        symbol=Symbol(name="TEST"),
        timeframe=Timeframe.H1,
        candles=candles,
    )
    return MarketStore(data)


def _make_bundle() -> StrategyBundle:
    config = StrategyConfig(
        name="stub_strategy",
        version="1.0",
        analyzers=(),
        signals=(),
    )
    strategy = Strategy("stub", config)
    return StrategyBundle([strategy])


class TestBacktesterBasic:
    def test_frame_count(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        assert bt.frame_count == 50

    def test_frame_count_insufficient_data(self) -> None:
        store = _make_store(10)
        bt = Backtester(store, _make_bundle(), window_size=50)
        assert bt.frame_count == 0

    def test_produces_frame_store_and_tradebook(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        result = bt.run()
        frame_store, tradebook = result.frames, result.tradebook
        assert len(frame_store) == 50
        assert isinstance(tradebook, TradeBook)

    def test_first_frame_timestamp(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store = bt.run().frames
        expected_ts = datetime(2024, 1, 1) + timedelta(hours=50)
        assert frame_store[0].timestamp == expected_ts

    def test_last_frame_timestamp(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store = bt.run().frames
        expected_ts = datetime(2024, 1, 1) + timedelta(hours=99)
        assert frame_store[-1].timestamp == expected_ts

    def test_frame_candle_matches_store(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store = bt.run().frames
        for i, frame in enumerate(frame_store):
            cursor = 50 + i
            assert frame.candle == store[cursor]


class TestBacktesterProgress:
    def test_callback_invoked(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        progress: list[tuple[int, int]] = []
        bt.run_with_progress(lambda cur, total: progress.append((cur, total)))
        assert len(progress) == 50
        assert progress[0] == (1, 50)
        assert progress[-1] == (50, 50)

    def test_no_callback(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store = bt.run().frames
        assert len(frame_store) == 50


class TestBacktesterEdgeCases:
    def test_exact_window_size(self) -> None:
        store = _make_store(50)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store = bt.run().frames
        assert len(frame_store) == 0

    def test_window_size_one(self) -> None:
        store = _make_store(10)
        bt = Backtester(store, _make_bundle(), window_size=1)
        frame_store = bt.run().frames
        assert len(frame_store) == 9

    def test_frames_ordered(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store = bt.run().frames
        for i in range(1, len(frame_store)):
            assert frame_store[i].timestamp > frame_store[i - 1].timestamp


class TestTradeBook:
    def test_initial_balance(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        assert tb.balance == 1000.0
        assert tb.initial_balance == 1000.0

    def test_no_trades_initially(self) -> None:
        tb = TradeBook()
        assert len(tb.trades) == 0
        assert tb.win_count == 0
        assert tb.loss_count == 0
        assert tb.win_rate == 0.0
        assert tb.total_pnl == 0.0
        assert tb.max_drawdown == 0.0
        assert tb.gross_profit == 0.0
        assert tb.gross_loss == 0.0
        assert tb.profit_factor == 0.0
        assert tb.avg_win == 0.0
        assert tb.avg_loss == 0.0
        assert tb.expectancy == 0.0

    def test_has_no_open_trade(self) -> None:
        tb = TradeBook()
        assert tb.has_no_open_trade is True

    def test_has_pending_order(self) -> None:
        tb = TradeBook()
        assert tb.has_pending_order is False

    def test_summary_includes_new_metrics(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        summary = tb.summary
        assert "gross_profit" in summary
        assert "gross_loss" in summary
        assert "profit_factor" in summary
        assert "avg_win" in summary
        assert "avg_loss" in summary
        assert "expectancy" in summary


class TestTradeBookMetrics:
    def _make_candidate(
        self,
        direction: TrendDirection = TrendDirection.BULLISH,
        entry: float = 100.0,
        stop: float = 98.0,
        target: float = 104.0,
    ) -> TradeCandidate:
        return TradeCandidate(
            direction=direction,
            entry=entry,
            stop=stop,
            target=target,
            size=1.0,
            risk_amount=2.0,
            reward_amount=4.0,
            rr_ratio=2.0,
            slippage_pct=0.0,
            source="test",
            evidence=(),
        )

    def _make_signal(
        self,
        direction: TrendDirection = TrendDirection.BULLISH,
    ) -> TradeSignal:
        return TradeSignal(
            direction=direction,
            entry_zone=(99.0, 101.0),
            confidence=0.8,
            source="test",
            evidence=(),
        )

    def test_single_win(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        candidate = self._make_candidate()
        signal = self._make_signal()
        ts = datetime(2024, 1, 1)
        tb.submit_order(candidate, signal, "test", ts)
        tb.fill_order(100.0, ts)
        tb.close_trade(104.0, ts)
        assert tb.gross_profit == 4.0
        assert tb.gross_loss == 0.0
        assert tb.profit_factor == float("inf")
        assert tb.avg_win == 4.0
        assert tb.avg_loss == 0.0
        assert tb.expectancy == 4.0

    def test_single_loss(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        candidate = self._make_candidate()
        signal = self._make_signal()
        ts = datetime(2024, 1, 1)
        tb.submit_order(candidate, signal, "test", ts)
        tb.fill_order(100.0, ts)
        tb.close_trade(98.0, ts)
        assert tb.gross_profit == 0.0
        assert tb.gross_loss == 2.0
        assert tb.profit_factor == 0.0
        assert tb.avg_win == 0.0
        assert tb.avg_loss == -2.0
        assert tb.expectancy == -2.0

    def test_mixed_trades(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        candidate = self._make_candidate()
        signal = self._make_signal()
        ts = datetime(2024, 1, 1)

        tb.submit_order(candidate, signal, "test", ts)
        tb.fill_order(100.0, ts)
        tb.close_trade(104.0, ts)

        tb.submit_order(candidate, signal, "test", ts)
        tb.fill_order(100.0, ts)
        tb.close_trade(98.0, ts)

        tb.submit_order(candidate, signal, "test", ts)
        tb.fill_order(100.0, ts)
        tb.close_trade(105.0, ts)

        assert tb.win_count == 2
        assert tb.loss_count == 1
        assert tb.gross_profit == 9.0
        assert tb.gross_loss == 2.0
        assert tb.profit_factor == 4.5
        assert tb.avg_win == 4.5
        assert tb.avg_loss == -2.0
        assert tb.expectancy == 7.0 / 3

    def test_bearish_trade_metrics(self) -> None:
        tb = TradeBook(initial_balance=1000.0)
        candidate = self._make_candidate(
            direction=TrendDirection.BEARISH,
            entry=100.0,
            stop=102.0,
            target=96.0,
        )
        signal = self._make_signal(direction=TrendDirection.BEARISH)
        ts = datetime(2024, 1, 1)
        tb.submit_order(candidate, signal, "test", ts)
        tb.fill_order(100.0, ts)
        tb.close_trade(96.0, ts)
        assert tb.gross_profit == 4.0
        assert tb.profit_factor == float("inf")
        assert tb.avg_win == 4.0


class TestStrategyBundle:
    def test_bundle_creates_tradebook(self) -> None:
        bundle = StrategyBundle([], initial_balance=500.0)
        assert bundle.tradebook.balance == 500.0

    def test_bundle_strategies_dict(self) -> None:
        config = StrategyConfig(
            name="test",
            version="1.0",
            analyzers=(),
            signals=(),
        )
        s1 = Strategy("a", config)
        s2 = Strategy("b", config)
        bundle = StrategyBundle([s1, s2])
        assert "a" in bundle.strategies
        assert "b" in bundle.strategies


class StubAnalyzerForSignals(Analyzer):
    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey("atr_14"),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        return AnalysisResult(
            facts=(
                ATRFact(
                    timestamp=view.current.timestamp,
                    evidence=(),
                    value=3.0,
                    period=14,
                ),
            ),
            evidence=(),
        )


class StubSRAnalyzer(Analyzer):
    def requires(self) -> tuple[FactKey, ...]:
        return ()

    def produces(self) -> tuple[FactKey, ...]:
        return (FactKey("sr"),)

    def analyze(self, view: MarketView, facts: dict[FactKey, Fact]) -> AnalysisResult:
        return AnalysisResult(
            facts=(
                SRFact(
                    timestamp=view.current.timestamp,
                    evidence=(),
                    levels=(),
                ),
            ),
            evidence=(),
        )


class _SignalBundle:
    def __init__(
        self,
        signals: list[tuple[str, TradeSignal]],
        risk_engine: RiskEngine,
        graph: AnalysisGraph | None = None,
        tradebook: TradeBook | None = None,
    ) -> None:
        self._signals = signals
        self._risk_engine = risk_engine
        self._graph = graph or AnalysisGraph([])
        self._tradebook = tradebook or TradeBook()
        self._strategies = {name: None for name, _ in signals}

    @property
    def graph(self) -> AnalysisGraph:
        return self._graph

    @property
    def tradebook(self) -> TradeBook:
        return self._tradebook

    @property
    def strategies(self) -> dict[str, object]:
        return dict(self._strategies)

    def evaluate_all(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> list[tuple[str, TradeSignal]]:
        return list(self._signals)

    def get_risk_engine(self, strategy_name: str) -> RiskEngine:
        return self._risk_engine


def _make_signal_bundle(
    signals: list[tuple[str, TradeSignal]],
    risk_engine: RiskEngine | None = None,
) -> _SignalBundle:
    graph = AnalysisGraph([StubAnalyzerForSignals(), StubSRAnalyzer()])
    return _SignalBundle(
        signals=signals,
        risk_engine=risk_engine or RiskEngine(risk_pct=1.0, slippage_pct=0.0, min_rr=0.0),
        graph=graph,
    )


class TestBacktesterSignalEval:
    def test_signal_submitted_with_facts(self) -> None:
        store = _make_store(100)
        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 102.0),
            confidence=0.8,
            source="test_signal",
            evidence=(),
        )
        bundle = _make_signal_bundle(
            signals=[("strat", signal)],
        )
        bt = Backtester(store, bundle, window_size=50)
        result = bt.run()
        frame_store, tradebook = result.frames, result.tradebook
        assert len(frame_store) == 50
        assert tradebook.closed_count >= 1

    def test_close_remaining_open_trade_at_end(self) -> None:
        store = _make_store(100)
        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 102.0),
            confidence=0.8,
            source="test_signal",
            evidence=(),
        )
        risk_engine = RiskEngine(
            risk_pct=1.0,
            slippage_pct=0.0,
            max_stop_atr=100.0,
            min_rr=0.0,
            max_rr=2.0,
            avoid_srxing=False,
        )
        bundle = _make_signal_bundle(
            signals=[("strat", signal)],
            risk_engine=risk_engine,
        )
        bt = Backtester(store, bundle, window_size=50, max_hold_days=9999)
        result = bt.run()
        frame_store, tradebook = result.frames, result.tradebook
        assert len(frame_store) == 50
        assert tradebook.closed_count >= 1

    def test_no_signal_means_no_trades(self) -> None:
        store = _make_store(100)
        bundle = _make_signal_bundle(signals=[])
        bt = Backtester(store, bundle, window_size=50)
        result = bt.run()
        frame_store, tradebook = result.frames, result.tradebook
        assert len(frame_store) == 50
        assert tradebook.closed_count == 0

    def test_risk_engine_rejects_no_trade(self) -> None:
        store = _make_store(100)
        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 102.0),
            confidence=0.8,
            source="test_signal",
            evidence=(),
        )
        bundle = _make_signal_bundle(
            signals=[("strat", signal)],
            risk_engine=RiskEngine(atr_key="atr_missing", sr_key="sr_missing"),
        )
        bt = Backtester(store, bundle, window_size=50)
        result = bt.run()
        frame_store, tradebook = result.frames, result.tradebook
        assert len(frame_store) == 50
        assert tradebook.closed_count == 0

    def test_trades_attributed_to_store_symbol(self) -> None:
        store = _make_store(100)
        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 102.0),
            confidence=0.8,
            source="test_signal",
            evidence=(),
        )
        bundle = _make_signal_bundle(signals=[("strat", signal)])
        bt = Backtester(store, bundle, window_size=50)
        result = bt.run()
        tradebook = result.tradebook
        assert tradebook.closed_count >= 1
        symbol = str(store.symbol)
        assert all(t.instrument == symbol for t in tradebook.trades)
        by_instrument = tradebook.summary["by_instrument"]
        assert isinstance(by_instrument, dict)
        entry = by_instrument[symbol]
        assert isinstance(entry, dict)
        counted = entry["wins"] + entry["losses"] + entry["breakevens"]
        assert counted == tradebook.closed_count
        assert entry["total_pnl"] == pytest.approx(tradebook.total_pnl)


class TestBacktesterFrameRecording:
    def _signal(self) -> TradeSignal:
        return TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 102.0),
            confidence=0.8,
            source="test_signal",
            evidence=(),
        )

    def test_frames_record_signals(self) -> None:
        store = _make_store(100)
        bundle = _make_signal_bundle(signals=[("strat", self._signal())])
        frames = Backtester(store, bundle, window_size=50).run().frames
        assert all(f.signals for f in frames)
        assert all(s.source == "test_signal" for f in frames for s in f.signals)

    def test_frames_record_rejection_evidence(self) -> None:
        store = _make_store(100)
        bundle = _make_signal_bundle(
            signals=[("strat", self._signal())],
            risk_engine=RiskEngine(atr_key="atr_missing", sr_key="sr_missing"),
        )
        frames = Backtester(store, bundle, window_size=50).run().frames
        assert any(f.risk_evidence for f in frames)
        rejected = [f for f in frames if f.risk_evidence]
        assert all(
            any(e.level == EvidenceLevel.WARNING for e in f.risk_evidence)
            for f in rejected
        )

    def test_frames_record_accepted_risk_evidence(self) -> None:
        store = _make_store(100)
        bundle = _make_signal_bundle(signals=[("strat", self._signal())])
        frames = Backtester(store, bundle, window_size=50).run().frames
        placed = [f for f in frames if f.risk_evidence and not any(
            e.level == EvidenceLevel.WARNING for e in f.risk_evidence
        )]
        assert placed


class TestBacktestResultPickle:
    def test_result_round_trips(self) -> None:
        store = _make_store(100)
        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 102.0),
            confidence=0.8,
            source="test_signal",
            evidence=(),
        )
        bundle = _make_signal_bundle(signals=[("strat", signal)])
        result = Backtester(store, bundle, window_size=50).run()

        import pickle

        restored = pickle.loads(pickle.dumps(result))
        assert len(restored.frames) == len(result.frames)
        assert restored.tradebook.trades == result.tradebook.trades
        assert restored.window_size == 50
        first = restored.frames[0]
        assert first.signals and first.risk_evidence
