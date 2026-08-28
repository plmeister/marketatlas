"""Backlog 075: portfolio backtester — merged calendar + one shared tradebook.

``PortfolioBacktester`` runs a strategy bundle across a portfolio of
instruments over the same period with a single tradebook shared by every
instrument. At most one trade is open across the portfolio at a time; fill and
resolution always use the position's own instrument candles.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pathlib import Path
from marketatlas.analysis.base import Analyzer
from marketatlas.analysis.factkey import FactKey
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.analysis.result import AnalysisResult
from marketatlas.backtesting.portfolio import PortfolioBacktester, PortfolioBacktestResult
from marketatlas.data.instrument import Instrument
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.data.view import MarketView
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.base import Fact
from marketatlas.facts.primitive import ATRFact
from marketatlas.facts.structural import SRFact, TrendDirection
from marketatlas.strategy.risk import RiskEngine
from marketatlas.strategy.signals import TradeSignal
from marketatlas.strategy.trade import TradeCandidate
from marketatlas.strategy.tradebook import TradeBook


pytestmark = pytest.mark.tier1
HOUR = timedelta(hours=1)


def _instrument(canonical: str) -> Instrument:
    return Instrument(
        canonical=canonical,
        asset_class="crypto",
        description=f"{canonical} asset",
        providers={"yahoo": canonical},
    )


def _candles(
    n: int,
    start: datetime,
    *,
    step: timedelta = timedelta(days=1),
    close_base: float = 100.0,
    ramp: float = 0.1,
    high_pad: float = 0.5,
    low_pad: float = 0.5,
    dip_to: float | None = None,
) -> tuple[Candle, ...]:
    candles = []
    for i in range(n):
        close = close_base + ramp * i
        ts = start + step * i
        low = close - low_pad
        if dip_to is not None and low > dip_to:
            low = dip_to
        candles.append(
            Candle(
                timestamp=ts,
                open=close,
                high=close + high_pad,
                low=low,
                close=close,
                volume=1000.0,
            )
        )
    return tuple(candles)


def _store(canonical: str, candles: tuple[Candle, ...]) -> MarketStore:
    return MarketStore(
        MarketData(symbol=Symbol(canonical), timeframe=Timeframe.D1, candles=candles)
    )


def _default_candles(n: int = 100, start: datetime | None = None) -> tuple[Candle, ...]:
    return _candles(n, start or datetime(2024, 1, 1, tzinfo=UTC))


def _fill_candles(n: int = 100, start: datetime | None = None) -> tuple[Candle, ...]:
    """Candles whose low dips to the default entry (100) every bar.

    The ramped close stays above entry (wins on max-hold close) while the low
    crosses it, so a bullish trigger-fill can fire at any index.
    """
    return _candles(n, start or datetime(2024, 1, 1, tzinfo=UTC), dip_to=100.0)


def _candidate(
    entry: float = 100.0,
    stop: float = 1.0,
    target: float = 500.0,
    size: float = 1.0,
) -> TradeCandidate:
    return TradeCandidate(
        direction=TrendDirection.BULLISH,
        entry=entry,
        stop=stop,
        target=target,
        size=size,
        risk_amount=100.0,
        reward_amount=400.0,
        rr_ratio=4.0,
        slippage_pct=0.0,
        source="test",
        evidence=(),
    )


def _signal(direction: TrendDirection = TrendDirection.BULLISH) -> TradeSignal:
    return TradeSignal(
        direction=direction,
        entry_zone=(99.0, 101.0),
        confidence=0.8,
        source="test",
        evidence=(),
    )


class _StubAtrAnalyzer(Analyzer):
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


class _StubSrAnalyzer(Analyzer):
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


class _FixedRiskEngine:
    """Returns a fixed candidate (or rejects) and records balances seen."""

    def __init__(self, candidate: TradeCandidate | None = None, reject: bool = False) -> None:
        self._candidate = None if reject else candidate
        self.balances_seen: list[float] = []

    def evaluate(
        self,
        signal: TradeSignal,
        facts: dict[FactKey, Fact],
        view: MarketView,
        balance: float = 1000.0,
    ) -> tuple[TradeCandidate | None, tuple[EvidenceEntry, ...]]:
        self.balances_seen.append(balance)
        if self._candidate is None:
            return None, (
                EvidenceEntry(
                    text="rejected by fixed engine",
                    level=EvidenceLevel.WARNING,
                    source="FixedRiskEngine",
                ),
            )
        return self._candidate, (
            EvidenceEntry(
                text="accepted by fixed engine",
                level=EvidenceLevel.INFO,
                source="FixedRiskEngine",
            ),
        )


class _PortfolioBundle:
    """Stub bundle: emits per-instrument, per-candle-index signals.

    ``signals`` entries are ``(strategy, canonical, indices, TradeSignal)``;
    an entry fires when the aligned view's candle index is in ``indices`` for
    that instrument. ``strategies`` preserves bundle priority order.
    """

    def __init__(
        self,
        signals: list[tuple[str, str, tuple[int, ...], TradeSignal]] | None = None,
        strategies: list[str] | None = None,
        engines: dict[str, _FixedRiskEngine] | None = None,
        balance: float = 1000.0,
    ) -> None:
        self._signals = signals or []
        self._strategies = {name: None for name in (strategies or ["strat"])}
        for strategy, _, _, _ in self._signals:
            self._strategies.setdefault(strategy, None)
        self._engines = engines or {}
        self._graph = AnalysisGraph([_StubAtrAnalyzer(), _StubSrAnalyzer()])
        self._tradebook = TradeBook(balance)

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
        canonical = view.store.symbol.name
        return [
            (strategy, signal)
            for strategy, inst, indices, signal in self._signals
            if inst == canonical and view.index in indices
        ]

    def evaluate_all_with_rejections(
        self, view: MarketView, facts: dict[FactKey, Fact]
    ) -> tuple[list[tuple[str, TradeSignal]], list[tuple[str, TradeSignal]]]:
        all_emitted = self.evaluate_all(view, facts)
        valid = [(n, s) for n, s in all_emitted if s.confidence > 0]
        rejected = [(n, s) for n, s in all_emitted if s.confidence == 0]
        return valid, rejected

    def get_risk_engine(self, strategy_name: str) -> RiskEngine:
        if strategy_name in self._engines:
            return self._engines[strategy_name]  # type: ignore[return-value]
        raise KeyError(strategy_name)


def _default_engine(
    candidate: TradeCandidate | None = None, reject: bool = False
) -> _FixedRiskEngine:
    return _FixedRiskEngine(candidate=candidate, reject=reject)


def _signal_entry(
    strategy: str, canonical: str, indices: tuple[int, ...], signal: TradeSignal
) -> tuple[str, str, tuple[int, ...], TradeSignal]:
    return (strategy, canonical, indices, signal)


class TestMergedCalendar:
    def test_union_sorted_timestamps(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        a_candles = _candles(5, start, ramp=0.0)
        b_candles = _candles(5, start + timedelta(days=2), ramp=0.0)
        bt = PortfolioBacktester(
            _PortfolioBundle(),
            [
                (_instrument("A"), _store("A", a_candles)),
                (_instrument("B"), _store("B", b_candles)),
            ],
            window_size=2,
        )
        expected = sorted({c.timestamp for c in a_candles} | {c.timestamp for c in b_candles})
        assert bt._merged == tuple(expected)
        assert bt.frame_count == len(expected) - 2

    def test_empty_portfolio_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            PortfolioBacktester(_PortfolioBundle(), [], window_size=2)

    def test_weekend_calendar_alignment(self) -> None:
        monday = datetime(2024, 1, 1, tzinfo=UTC)
        crypto = _candles(7, monday)  # Mon..Sun
        fx = _candles(5, monday)  # Mon..Fri
        bt = PortfolioBacktester(
            _PortfolioBundle(),
            [
                (_instrument("CRYPTO"), _store("CRYPTO", crypto)),
                (_instrument("FX"), _store("FX", fx)),
            ],
            window_size=2,
        )
        result = bt.run()
        frames_a = result.frames["CRYPTO"]
        frames_b = result.frames["FX"]

        assert [f.timestamp for f in frames_a] == [c.timestamp for c in crypto[2:]]
        assert [f.timestamp for f in frames_b] == [c.timestamp for c in fx[2:]]

        # Saturday/Sunday cursors keep FX aligned at Friday (never advances)
        assert frames_b[-1].timestamp == fx[4].timestamp
        assert len(frames_b) == 3

    def test_interleaved_calendars_align_latest_at_or_before_cursor(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        even = _candles(50, start, step=2 * HOUR, ramp=0.0)
        odd = _candles(50, start + HOUR, step=2 * HOUR, ramp=0.0)
        bt = PortfolioBacktester(
            _PortfolioBundle(),
            [(_instrument("EVEN"), _store("EVEN", even)), (_instrument("ODD"), _store("ODD", odd))],
            window_size=5,
        )
        result = bt.run()
        frames_even = result.frames["EVEN"]
        frames_odd = result.frames["ODD"]

        # One frame per own candle; the first aligned candle never exceeds
        # the first cursor timestamp (latest candle at-or-before cursor)
        first_cursor = bt._merged[5]
        assert len(frames_even) == len(frames_odd) == 48
        assert [f.timestamp for f in frames_even] == [c.timestamp for c in even[2:]]
        assert [f.timestamp for f in frames_odd] == [c.timestamp for c in odd[2:]]
        assert frames_even[0].timestamp <= first_cursor
        assert frames_odd[0].timestamp <= first_cursor


class TestTradeAttribution:
    def _run_two_instrument(
        self, signals: list[tuple[str, str, tuple[int, ...], TradeSignal]]
    ) -> PortfolioBacktestResult:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        a = _store("A", _fill_candles(100, start))
        b = _store("B", _fill_candles(100, start))
        bundle = _PortfolioBundle(
            signals=signals,
            strategies=["strat"],
            engines={"strat": _default_engine(_candidate())},
        )
        return PortfolioBacktester(
            bundle,
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=50,
            max_hold_days=1,
        ).run()

    def test_trades_attributed_to_correct_canonical(self) -> None:
        result = self._run_two_instrument(
            [
                _signal_entry("strat", "A", (60,), _signal()),
                _signal_entry("strat", "B", (70,), _signal()),
            ]
        )
        trades = result.tradebook.trades
        assert len(trades) == 2
        assert [t.instrument for t in trades] == ["A", "B"]

        by_instrument = result.tradebook.summary["by_instrument"]
        assert isinstance(by_instrument, dict)
        a_entry = by_instrument["A"]
        b_entry = by_instrument["B"]
        assert isinstance(a_entry, dict) and isinstance(b_entry, dict)
        assert a_entry["wins"] == 1 and b_entry["wins"] == 1
        assert a_entry["losses"] == 0 and b_entry["losses"] == 0

    def test_trade_outcome_instrument_populated(self) -> None:
        result = self._run_two_instrument(
            [_signal_entry("strat", "A", (60,), _signal())]
        )
        assert len(result.tradebook.trades) == 1
        assert result.tradebook.trades[0].instrument == "A"

    def test_no_overlap_between_trades(self) -> None:
        result = self._run_two_instrument(
            [
                _signal_entry("strat", "A", (60,), _signal()),
                _signal_entry("strat", "B", (70,), _signal()),
            ]
        )
        trades = result.tradebook.trades
        assert trades[0].exit_timestamp is not None
        assert trades[0].exit_timestamp <= trades[1].entry_timestamp


class TestSingleOpenTrade:
    def test_concurrent_signals_single_trade(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        a = _store("A", _fill_candles(100, start))
        b = _store("B", _fill_candles(100, start))
        bundle = _PortfolioBundle(
            signals=[
                _signal_entry("strat", "A", (60,), _signal()),
                _signal_entry("strat", "B", (60,), _signal()),
            ],
            strategies=["strat"],
            engines={"strat": _default_engine(_candidate())},
        )
        result = PortfolioBacktester(
            bundle,
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=50,
            max_hold_days=1,
        ).run()
        # Both instruments signal at the same cursor; only the first (A) fills
        assert len(result.tradebook.trades) == 1
        assert result.tradebook.trades[0].instrument == "A"

    def test_second_instrument_trades_after_close(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        a = _store("A", _fill_candles(100, start))
        b = _store("B", _fill_candles(100, start))
        bundle = _PortfolioBundle(
            signals=[
                _signal_entry("strat", "A", (60,), _signal()),
                _signal_entry("strat", "B", (70,), _signal()),
            ],
            strategies=["strat"],
            engines={"strat": _default_engine(_candidate())},
        )
        result = PortfolioBacktester(
            bundle,
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=50,
            max_hold_days=1,
        ).run()
        trades = result.tradebook.trades
        assert len(trades) == 2
        assert [t.instrument for t in trades] == ["A", "B"]
        # A's trade closes before B's opens: never two open at once
        assert trades[0].exit_timestamp is not None
        assert trades[0].exit_timestamp <= trades[1].entry_timestamp


class TestOwnInstrumentResolution:
    def test_resolution_ignores_other_instruments_candles(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        # A: benign candles that never breach the stop/target
        a = _store("A", _candles(40, start, ramp=0.0, high_pad=0.5, low_pad=0.5))
        # B: violent candles that WOULD breach A's stop (98) and target (102)
        b = _store("B", _candles(40, start, ramp=0.0, high_pad=200.0, low_pad=200.0))
        bundle = _PortfolioBundle(
            signals=[_signal_entry("strat", "A", (5,), _signal())],
            strategies=["strat"],
            engines={"strat": _default_engine(_candidate(stop=98.0, target=102.0))},
        )
        result = PortfolioBacktester(
            bundle,
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=3,
            max_hold_days=2,
        ).run()

        trades = result.tradebook.trades
        assert len(trades) == 1
        trade = trades[0]
        # Closed by max-hold on A's own candle, not by B's violent candle
        assert trade.exit_timestamp == a[8].timestamp
        # Exit price is A's close, never B's
        assert trade.pnl == pytest.approx(
            (a[8].close - trade.candidate.entry) * trade.candidate.size
        )
        assert trade.result == "breakeven"


class TestSharedBalance:
    def test_balance_compounds_across_instruments(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        a = _store("A", _fill_candles(100, start))
        b = _store("B", _fill_candles(100, start))
        engine = _default_engine(_candidate())
        bundle = _PortfolioBundle(
            signals=[
                _signal_entry("strat", "A", (60,), _signal()),
                _signal_entry("strat", "B", (70,), _signal()),
            ],
            strategies=["strat"],
            engines={"strat": engine},
        )
        result = PortfolioBacktester(
            bundle,
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=50,
            max_hold_days=1,
        ).run()
        book = result.tradebook

        assert book.closed_count == 2
        pnls = [float(t.pnl) if t.pnl is not None else 0.0 for t in book.trades]
        assert book.balance == pytest.approx(book.initial_balance + sum(pnls))
        # risk sizing saw the grown shared balance on the second signal
        first_pnl = book.trades[0].pnl
        assert first_pnl is not None
        assert engine.balances_seen == pytest.approx([1000.0, 1000.0 + first_pnl])

        by_instrument = book.summary["by_instrument"]
        assert isinstance(by_instrument, dict)
        total = sum(float(entry["total_pnl"]) for entry in by_instrument.values())
        assert total == pytest.approx(book.total_pnl)


class TestDeterministicOrdering:
    def _bundle(self, primary_reject: bool) -> tuple[_PortfolioBundle, PortfolioBacktester]:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        a = _store("A", _fill_candles(100, start))
        b = _store("B", _fill_candles(100, start))
        primary = _default_engine(_candidate(), reject=primary_reject)
        secondary = _default_engine(_candidate())
        bundle = _PortfolioBundle(
            signals=[
                _signal_entry("primary", "B", (60,), _signal()),
                _signal_entry("secondary", "A", (60,), _signal()),
            ],
            strategies=["primary", "secondary"],
            engines={"primary": primary, "secondary": secondary},
        )
        bt = PortfolioBacktester(
            bundle,
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=50,
            max_hold_days=1,
        )
        return bundle, bt

    def test_strategy_priority_beats_instrument_order(self) -> None:
        _, bt = self._bundle(primary_reject=False)
        result = bt.run()
        assert len(result.tradebook.trades) == 1
        assert result.tradebook.trades[0].instrument == "B"
        assert result.tradebook.trades[0].source_strategy == "primary"

    def test_rejected_primary_falls_to_secondary(self) -> None:
        _, bt = self._bundle(primary_reject=True)
        result = bt.run()
        assert len(result.tradebook.trades) == 1
        assert result.tradebook.trades[0].instrument == "A"
        assert result.tradebook.trades[0].source_strategy == "secondary"

        # B's frame records the primary rejection evidence
        b_frames = result.frames["B"]
        assert len(b_frames) > 10
        rejected = b_frames[10]
        assert any(e.level == EvidenceLevel.WARNING for e in rejected.risk_evidence)

    def test_run_is_deterministic(self) -> None:
        _, bt1 = self._bundle(primary_reject=False)
        result1 = bt1.run()
        _, bt2 = self._bundle(primary_reject=False)
        result2 = bt2.run()
        assert result1.tradebook.trades == result2.tradebook.trades


class TestPortfolioResult:
    def test_by_instrument_mapping(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        a = _store("A", _default_candles(100, start))
        b = _store("B", _default_candles(100, start))
        bundle = _PortfolioBundle()
        result = PortfolioBacktester(
            bundle,
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=50,
        ).run()
        assert [r.canonical for r in result.by_instrument] == ["A", "B"]
        for r in result.by_instrument:
            assert r.frames is result.frames[r.canonical]
            assert r.tradebook is result.tradebook

    def test_progress_callback(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        a = _store("A", _default_candles(100, start))
        b = _store("B", _default_candles(100, start))
        bt = PortfolioBacktester(
            _PortfolioBundle(),
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=50,
        )
        progress: list[tuple[int, int]] = []
        result = bt.run_with_progress(lambda cur, total: progress.append((cur, total)))
        assert len(progress) == 50
        assert progress[0] == (1, 50)
        assert progress[-1] == (50, 50)
        assert len(result.frames["A"]) == 50
        assert len(result.frames["B"]) == 50

    def test_no_signals_no_trades(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        a = _store("A", _default_candles(100, start))
        b = _store("B", _default_candles(100, start))
        result = PortfolioBacktester(
            _PortfolioBundle(),
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=50,
        ).run()
        assert result.tradebook.closed_count == 0
        assert len(result.frames["A"]) == 50
        assert len(result.frames["B"]) == 50

    def test_result_pickles(self) -> None:
        import pickle

        start = datetime(2024, 1, 1, tzinfo=UTC)
        a = _store("A", _default_candles(100, start))
        b = _store("B", _default_candles(100, start))
        bundle = _PortfolioBundle(
            signals=[_signal_entry("strat", "A", (60,), _signal())],
            strategies=["strat"],
            engines={"strat": _default_engine(_candidate())},
        )
        result = PortfolioBacktester(
            bundle,
            [(_instrument("A"), a), (_instrument("B"), b)],
            window_size=50,
            max_hold_days=1,
        ).run()

        restored = pickle.loads(pickle.dumps(result))
        assert list(restored.frames.keys()) == ["A", "B"]
        assert len(restored.frames["A"]) == len(result.frames["A"])
        assert restored.tradebook.trades == result.tradebook.trades
        assert [r.canonical for r in restored.by_instrument] == ["A", "B"]


class TestMonthlyIndex:
    def _candle(self, ts: datetime, high: float, low: float) -> Candle:
        return Candle(timestamp=ts, open=100.0, high=high, low=low, close=100.0, volume=1000.0)

    def _closed_trade(self, tb: TradeBook, t0: datetime) -> None:
        cand = _candidate(entry=100.0, stop=95.0, target=115.0, size=0.4)
        tb.submit_order(cand, _signal(), "A", t0)
        tb.fill_order(self._candle(t0, high=110.0, low=90.0))
        tb.resolve_at_cursor(self._candle(t0 + timedelta(days=1), high=116.0, low=108.0))

    def test_index_renders_monthly_summary(self, tmp_path: Path) -> None:
        from marketatlas.visualization.portfolio import render_portfolio_index

        book = TradeBook(initial_balance=1000.0)
        self._closed_trade(book, datetime(2024, 1, 3, tzinfo=UTC))
        self._closed_trade(book, datetime(2024, 2, 5, tzinfo=UTC))
        result = PortfolioBacktestResult(
            instruments=(_instrument("A"),),
            frames={},
            tradebook=book,
            window_size=100,
            max_hold_days=10,
        )

        render_portfolio_index(result, tmp_path, "portfolio")

        html = (tmp_path / "portfolio.html").read_text(encoding="utf-8")
        assert "<h2>Monthly</h2>" in html
        assert "2024-01" in html
        assert "2024-02" in html
        assert "1-0" in html

    def test_index_omits_monthly_when_no_trades(self, tmp_path: Path) -> None:
        from marketatlas.visualization.portfolio import render_portfolio_index

        result = PortfolioBacktestResult(
            instruments=(_instrument("A"),),
            frames={},
            tradebook=TradeBook(initial_balance=1000.0),
            window_size=100,
            max_hold_days=10,
        )

        render_portfolio_index(result, tmp_path, "portfolio")

        html = (tmp_path / "portfolio.html").read_text(encoding="utf-8")
        assert "<h2>Monthly</h2>" not in html
