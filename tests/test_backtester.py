from datetime import datetime, timedelta

from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.analysis.result import AnalysisResult
from marketatlas.backtesting.backtester import Backtester
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.primitive import EMAFact


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
    def requires(self) -> tuple[type, ...]:
        return ()

    def produces(self) -> tuple[type, ...]:
        return (EMAFact,)

    def analyze(self, view, facts: dict) -> AnalysisResult:
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


def _make_graph() -> AnalysisGraph:
    return AnalysisGraph([StubAnalyzer()])


class TestBacktesterBasic:
    def test_frame_count(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        assert bt.frame_count == 50

    def test_frame_count_insufficient_data(self) -> None:
        store = _make_store(10)
        bt = Backtester(store, _make_graph(), window_size=50)
        assert bt.frame_count == 0

    def test_produces_frame_store(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        result = bt.run()
        assert len(result) == 50

    def test_first_frame_timestamp(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        result = bt.run()
        expected_ts = datetime(2024, 1, 1) + timedelta(hours=50)
        assert result[0].timestamp == expected_ts

    def test_last_frame_timestamp(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        result = bt.run()
        expected_ts = datetime(2024, 1, 1) + timedelta(hours=99)
        assert result[-1].timestamp == expected_ts

    def test_frame_candle_matches_store(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        result = bt.run()
        for i, frame in enumerate(result):
            cursor = 50 + i
            assert frame.candle == store[cursor]

    def test_frame_facts_populated(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        result = bt.run()
        for frame in result:
            assert EMAFact in frame.facts

    def test_frame_evidence_populated(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        result = bt.run()
        for frame in result:
            assert len(frame.evidence) >= 1


class TestBacktesterProgress:
    def test_callback_invoked(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        progress: list[tuple[int, int]] = []
        bt.run_with_progress(lambda cur, total: progress.append((cur, total)))
        assert len(progress) == 50
        assert progress[0] == (1, 50)
        assert progress[-1] == (50, 50)

    def test_no_callback(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        result = bt.run()
        assert len(result) == 50


class TestBacktesterEdgeCases:
    def test_exact_window_size(self) -> None:
        store = _make_store(50)
        bt = Backtester(store, _make_graph(), window_size=50)
        result = bt.run()
        assert len(result) == 0

    def test_window_size_one(self) -> None:
        store = _make_store(10)
        bt = Backtester(store, _make_graph(), window_size=1)
        result = bt.run()
        assert len(result) == 9

    def test_frames_ordered(self) -> None:
        store = _make_store(100)
        bt = Backtester(store, _make_graph(), window_size=50)
        result = bt.run()
        for i in range(1, len(result)):
            assert result[i].timestamp > result[i - 1].timestamp
