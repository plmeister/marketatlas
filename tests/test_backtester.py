from datetime import datetime, timedelta

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.analysis.result import AnalysisResult
from marketatlas.backtesting.backtester import Backtester
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import EMAFact
from marketatlas.strategy.bundle import StrategyBundle
from marketatlas.strategy.config import StrategyConfig
from marketatlas.strategy.strategy import Strategy
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
    def requires(self) -> tuple[tuple[type[Fact], str], ...]:
        return ()

    def produces(self) -> tuple[tuple[type[Fact], str], ...]:
        return ((EMAFact, "stub_ema"),)

    def analyze(
        self, view: MarketView, facts: dict[tuple[type[Fact], str], Fact]
    ) -> AnalysisResult:
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
        frame_store, tradebook = bt.run()
        assert len(frame_store) == 50
        assert isinstance(tradebook, TradeBook)

    def test_first_frame_timestamp(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store, _ = bt.run()
        expected_ts = datetime(2024, 1, 1) + timedelta(hours=50)
        assert frame_store[0].timestamp == expected_ts

    def test_last_frame_timestamp(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store, _ = bt.run()
        expected_ts = datetime(2024, 1, 1) + timedelta(hours=99)
        assert frame_store[-1].timestamp == expected_ts

    def test_frame_candle_matches_store(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store, _ = bt.run()
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
        frame_store, _ = bt.run()
        assert len(frame_store) == 50


class TestBacktesterEdgeCases:
    def test_exact_window_size(self) -> None:
        store = _make_store(50)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store, _ = bt.run()
        assert len(frame_store) == 0

    def test_window_size_one(self) -> None:
        store = _make_store(10)
        bt = Backtester(store, _make_bundle(), window_size=1)
        frame_store, _ = bt.run()
        assert len(frame_store) == 9

    def test_frames_ordered(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_bundle(), window_size=50)
        frame_store, _ = bt.run()
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

    def test_has_no_open_trade(self) -> None:
        tb = TradeBook()
        assert tb.has_no_open_trade is True

    def test_has_pending_order(self) -> None:
        tb = TradeBook()
        assert tb.has_pending_order is False


class TestStrategyBundle:
    def test_bundle_creates_tradebook(self) -> None:
        bundle = StrategyBundle([], initial_balance=500.0)
        assert bundle.tradebook.balance == 500.0

    def test_bundle_strategies_dict(self) -> None:
        config = StrategyConfig(
            name="test", version="1.0", analyzers=(), signals=(),
        )
        s1 = Strategy("a", config)
        s2 = Strategy("b", config)
        bundle = StrategyBundle([s1, s2])
        assert "a" in bundle.strategies
        assert "b" in bundle.strategies
