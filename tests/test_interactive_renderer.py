import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from marketatlas.analysis.factkey import FactKey
from marketatlas.backtesting.portfolio import PortfolioBacktestResult
from marketatlas.data.instrument import Instrument
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.pattern import PullbackFact
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import (
    SRFact,
    SRLevel,
    SwingFact,
    SwingPoint,
    SwingType,
    TrendDirection,
    TrendFact,
)
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.frames.store import FrameStore
from marketatlas.strategy.tradebook import TradeBook
from marketatlas.visualization.context import RenderContext
from marketatlas.visualization.interactive import (
    InteractiveRenderer,
    _extract_atr_per_frame,
    _extract_ema_per_frame,
    _extract_facts_per_frame,
    _extract_frames_json,
    _extract_pullbacks_per_frame,
    _extract_sr_per_frame,
    _extract_trades_json,
)

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _make_candle(offset: int = 0, base_price: float = 100.0) -> Candle:
    ts = BASE + timedelta(days=offset)
    p = base_price + offset
    return Candle(
        timestamp=ts,
        open=p,
        high=p + 5,
        low=p - 5,
        close=p + 2,
        volume=1000.0,
    )


def _make_store(n: int = 10) -> MarketStore:
    candles = tuple(_make_candle(i) for i in range(n))
    return MarketStore(
        MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.D1, candles=candles)
    )


def _make_frame(offset: int = 0) -> AnalysisFrame:
    candle = _make_candle(offset)
    ema = EMAFact(timestamp=candle.timestamp, evidence=(), value=102.0 + offset, period=20)
    atr = ATRFact(timestamp=candle.timestamp, evidence=(), value=3.5, period=14)
    trend = TrendFact(
        timestamp=candle.timestamp,
        evidence=(),
        direction=TrendDirection.BULLISH,
        strength=0.7,
    )
    return AnalysisFrame(
        timestamp=candle.timestamp,
        candle=candle,
        facts={
            FactKey("ema_20"): ema,
            FactKey("atr_14"): atr,
            FactKey("trend"): trend,
        },
        evidence=(EvidenceEntry(text=f"frame {offset}", level=EvidenceLevel.INFO, source="test"),),
    )


def _make_sr_frame(offset: int = 0) -> AnalysisFrame:
    candle = _make_candle(offset)
    sr = SRFact(
        timestamp=candle.timestamp,
        evidence=(),
        levels=(
            SRLevel(price=90.0, strength=2, type="support"),
            SRLevel(price=110.0, strength=3, type="resistance"),
        ),
    )
    return AnalysisFrame(
        timestamp=candle.timestamp,
        candle=candle,
        facts={FactKey("sr"): sr},
        evidence=(),
    )


def _make_pullback_frame(offset: int = 0) -> AnalysisFrame:
    candle = _make_candle(offset)
    pb = PullbackFact(
        timestamp=candle.timestamp,
        evidence=(),
        direction=TrendDirection.BULLISH,
        swing_pattern=(95.0, 110.0, 97.0),
    )
    return AnalysisFrame(
        timestamp=candle.timestamp,
        candle=candle,
        facts={FactKey("pullback"): pb},
        evidence=(),
    )


def _make_frame_store(n: int = 5) -> FrameStore:
    store = FrameStore()
    for i in range(n):
        store.append(_make_frame(i))
    return store


def _make_tradebook_with_trades() -> TradeBook:
    """Create a TradeBook with simulated trades for testing."""
    from marketatlas.facts.structural import TrendDirection
    from marketatlas.strategy.signals import TradeSignal
    from marketatlas.strategy.trade import TradeCandidate

    tb = TradeBook(initial_balance=1000.0)

    signal = TradeSignal(
        direction=TrendDirection.BULLISH,
        entry_zone=(100.0, 105.0),
        confidence=0.8,
        source="test_signal",
        evidence=(),
    )
    candidate = TradeCandidate(
        direction=TrendDirection.BULLISH,
        entry=103.0,
        stop=98.0,
        target=118.0,
        size=0.2,
        risk_amount=10.0,
        reward_amount=30.0,
        rr_ratio=3.0,
        slippage_pct=0.1,
        source="test",
        evidence=(),
    )

    # Submit and fill
    tb.submit_order(candidate, signal, "test_strat", BASE + timedelta(days=5))
    tb.fill_order(103.0, BASE + timedelta(days=6))
    # Win
    tb.close_trade(118.0, BASE + timedelta(days=8))

    # Second trade
    tb.submit_order(candidate, signal, "test_strat", BASE + timedelta(days=10))
    tb.fill_order(103.0, BASE + timedelta(days=11))
    # Loss
    tb.close_trade(98.0, BASE + timedelta(days=13))

    return tb


def _make_tradebook_with_instruments() -> TradeBook:
    """Shared-book fixture with one win on ``A`` and one loss on ``B``."""
    from marketatlas.facts.structural import TrendDirection
    from marketatlas.strategy.signals import TradeSignal
    from marketatlas.strategy.trade import TradeCandidate

    tb = TradeBook(initial_balance=1000.0)

    signal = TradeSignal(
        direction=TrendDirection.BULLISH,
        entry_zone=(100.0, 105.0),
        confidence=0.8,
        source="test_signal",
        evidence=(),
    )
    candidate = TradeCandidate(
        direction=TrendDirection.BULLISH,
        entry=103.0,
        stop=98.0,
        target=118.0,
        size=0.2,
        risk_amount=10.0,
        reward_amount=30.0,
        rr_ratio=3.0,
        slippage_pct=0.1,
        source="test",
        evidence=(),
    )

    tb.submit_order(candidate, signal, "test_strat", BASE + timedelta(days=5), instrument="A")
    tb.fill_order(103.0, BASE + timedelta(days=6))
    tb.close_trade(118.0, BASE + timedelta(days=8))

    tb.submit_order(candidate, signal, "test_strat", BASE + timedelta(days=10), instrument="B")
    tb.fill_order(103.0, BASE + timedelta(days=11))
    tb.close_trade(98.0, BASE + timedelta(days=13))

    return tb


def _make_instrument(canonical: str) -> Instrument:
    return Instrument(
        canonical=canonical,
        asset_class="crypto",
        description=f"{canonical} test asset",
        providers={"yahoo": canonical},
    )


def _make_portfolio_result() -> PortfolioBacktestResult:
    tb = _make_tradebook_with_instruments()
    frames = {"A": _make_frame_store(5), "B": _make_frame_store(5)}
    return PortfolioBacktestResult(
        instruments=(_make_instrument("A"), _make_instrument("B")),
        frames=frames,
        tradebook=tb,
        window_size=100,
        max_hold_days=10,
    )


def _make_canonical_store(canonical: str, n: int = 15) -> MarketStore:
    candles = tuple(_make_candle(i) for i in range(n))
    return MarketStore(
        MarketData(symbol=Symbol(canonical), timeframe=Timeframe.D1, candles=candles)
    )


class TestRenderContext:
    def test_creation(self) -> None:
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        assert ctx.max_hold_days == 10
        assert ctx.title == ""
        assert ctx.min_touches == 2

    def test_custom_title(self) -> None:
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb, title="My Chart")
        assert ctx.title == "My Chart"

    def test_custom_min_touches(self) -> None:
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb, min_touches=3)
        assert ctx.min_touches == 3


class TestExtractFramesJson:
    def test_extracts_timestamps(self) -> None:
        frames = [_make_frame(i) for i in range(3)]
        result = _extract_frames_json(frames)
        assert len(result) == 3
        assert result[0]["time"] == BASE.strftime("%Y-%m-%d")

    def test_includes_evidence(self) -> None:
        frames = [_make_frame(0)]
        result = _extract_frames_json(frames)
        assert len(result[0]["evidence"]) == 1
        assert result[0]["evidence"][0]["text"] == "frame 0"

    def test_empty(self) -> None:
        assert _extract_frames_json([]) == []

    def test_includes_risk_evidence_and_signals(self) -> None:
        candle = _make_candle(0)
        from marketatlas.strategy.signals import TradeSignal

        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={},
            evidence=(),
            signals=(
                TradeSignal(
                    direction=TrendDirection.BULLISH,
                    entry_zone=(100.0, 102.0),
                    confidence=0.8,
                    source="PullbackSignal",
                    evidence=(),
                ),
            ),
            risk_evidence=(
                EvidenceEntry(
                    text="Rejected: no valid RR in [1.0, 4.0] without crossing S/R",
                    level=EvidenceLevel.WARNING,
                    source="RiskEngine",
                ),
            ),
        )
        result = _extract_frames_json([frame])[0]
        assert result["signals"] == [
            {
                "direction": "bullish",
                "confidence": 0.8,
                "source": "PullbackSignal",
                "entry_zone": [100.0, 102.0],
            }
        ]
        assert result["risk_evidence"][0]["text"].startswith("Rejected")
        assert result["risk_evidence"][0]["level"] == "warning"


class TestExtractEMA:
    def test_extracts_ema_series(self) -> None:
        frames = [_make_frame(i) for i in range(3)]
        result = _extract_ema_per_frame(frames)
        assert "EMA20" in result
        assert len(result["EMA20"]) == 3

    def test_empty(self) -> None:
        assert _extract_ema_per_frame([]) == {}


class TestExtractATR:
    def test_extracts_atr(self) -> None:
        frames = [_make_frame(i) for i in range(3)]
        result = _extract_atr_per_frame(frames)
        assert len(result) == 3
        assert result[0]["value"] == 3.5

    def test_empty(self) -> None:
        assert _extract_atr_per_frame([]) == []


class TestExtractSR:
    def test_extracts_sr_levels(self) -> None:
        frames = [_make_sr_frame(0), _make_sr_frame(1)]
        result = _extract_sr_per_frame(frames)
        assert len(result) == 2
        assert len(result[0]["levels"]) == 2
        assert result[0]["levels"][0]["type"] == "support"
        assert result[0]["levels"][1]["type"] == "resistance"

    def test_no_sr_fact_returns_empty(self) -> None:
        frames = [_make_frame(0)]
        result = _extract_sr_per_frame(frames)
        assert len(result) == 1
        assert result[0]["levels"] == []

    def test_merges_levels_across_timeframes(self) -> None:
        candle = _make_candle(0)
        sr_daily = SRFact(
            timestamp=candle.timestamp,
            evidence=(),
            levels=(SRLevel(price=90.0, strength=2, type="support"),),
        )
        sr_weekly = SRFact(
            timestamp=candle.timestamp,
            evidence=(),
            levels=(SRLevel(price=110.0, strength=3, type="resistance"),),
        )
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={
                FactKey("sr", timeframe=Timeframe.D1): sr_daily,
                FactKey("sr", timeframe=Timeframe.W1): sr_weekly,
            },
            evidence=(),
        )
        result = _extract_sr_per_frame([frame])
        assert result[0]["levels"] == [
            {"price": 90.0, "strength": 2, "type": "support"},
            {"price": 110.0, "strength": 3, "type": "resistance"},
        ]

    def test_empty(self) -> None:
        assert _extract_sr_per_frame([]) == []


class TestExtractPullbacks:
    def test_extracts_detected_pullbacks(self) -> None:
        frames = [_make_pullback_frame(0), _make_pullback_frame(1)]
        result = _extract_pullbacks_per_frame(frames)
        assert len(result) == 2
        assert result[0] is not None
        assert result[0]["position"] == "belowBar"
        assert result[0]["color"] == "#22c55e"
        assert result[0]["shape"] == "arrowUp"

    def test_none_for_no_pullback(self) -> None:
        frames = [_make_frame(0)]
        result = _extract_pullbacks_per_frame(frames)
        assert result[0] is None

    def test_ignores_neutral(self) -> None:
        candle = _make_candle(0)
        pb = PullbackFact(
            timestamp=candle.timestamp,
            evidence=(),
            direction=TrendDirection.NEUTRAL,
            swing_pattern=(),
        )
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={FactKey("pullback"): pb},
            evidence=(),
        )
        result = _extract_pullbacks_per_frame([frame])
        assert result[0] is None

    def test_empty(self) -> None:
        assert _extract_pullbacks_per_frame([]) == []


class TestExtractFactsPerFrame:
    def test_extracts_all_fact_types(self) -> None:
        frames = [_make_frame(0)]
        result = _extract_facts_per_frame(frames)
        assert len(result) == 1
        facts = result[0]
        assert "ema_20" in facts
        assert facts["ema_20"]["type"] == "ema"
        assert "atr_14" in facts
        assert facts["atr_14"]["type"] == "atr"
        assert "trend" in facts
        assert facts["trend"]["type"] == "trend"
        assert facts["trend"]["direction"] == "bullish"

    def test_sr_fact_included(self) -> None:
        frames = [_make_sr_frame(0)]
        result = _extract_facts_per_frame(frames)
        assert "sr" in result[0]
        assert result[0]["sr"]["type"] == "sr"
        assert len(result[0]["sr"]["levels"]) == 2

    def test_pullback_fact_included(self) -> None:
        frames = [_make_pullback_frame(0)]
        result = _extract_facts_per_frame(frames)
        assert "pullback" in result[0]
        assert result[0]["pullback"]["type"] == "pullback"
        assert result[0]["pullback"]["direction"] == "bullish"

    def test_pullback_with_swing_pattern(self) -> None:
        candle = _make_candle(5)
        pullback = PullbackFact(
            timestamp=candle.timestamp,
            evidence=(),
            direction=TrendDirection.BULLISH,
            swing_pattern=(95.0, 110.0, 97.0, 112.0),
        )
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={FactKey("pullback"): pullback},
            evidence=(),
        )
        result = _extract_facts_per_frame([frame])
        pb = result[0]["pullback"]
        assert pb["swing_pattern"] == [95.0, 110.0, 97.0, 112.0]

    def test_swing_fact_included(self) -> None:
        candle = _make_candle(0)
        ts = candle.timestamp
        swing = SwingFact(
            timestamp=ts,
            evidence=(),
            swings=(
                SwingPoint(price=95.0, index=0, type=SwingType.LOW, timestamp=ts),
                SwingPoint(price=105.0, index=2, type=SwingType.HIGH, timestamp=ts),
            ),
        )
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={FactKey("swing"): swing},
            evidence=(),
        )
        result = _extract_facts_per_frame([frame])
        assert "swing" in result[0]
        assert result[0]["swing"]["type"] == "swing"
        assert len(result[0]["swing"]["swings"]) == 2
        assert result[0]["swing"]["swings"][0]["type"] == "low"

    def test_swing_fact_includes_native_time(self) -> None:
        candle = _make_candle(0)
        ts = candle.timestamp
        swing = SwingFact(
            timestamp=ts,
            evidence=(),
            swings=(SwingPoint(price=95.0, index=0, type=SwingType.LOW, timestamp=ts),),
        )
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={FactKey("swing"): swing},
            evidence=(),
        )
        result = _extract_facts_per_frame([frame])
        point = result[0]["swing"]["swings"][0]
        assert point["time"] == ts.strftime("%Y-%m-%d")
        assert point["index"] == 0  # index kept for reference

    def test_multi_timeframe_swings_kept_separate(self) -> None:
        candle = _make_candle(0)
        ts = candle.timestamp
        swing_daily = SwingFact(
            timestamp=ts,
            evidence=(),
            swings=(
                SwingPoint(price=95.0, index=0, type=SwingType.LOW, timestamp=ts),
                SwingPoint(price=105.0, index=2, type=SwingType.HIGH, timestamp=ts),
            ),
        )
        swing_weekly = SwingFact(
            timestamp=ts,
            evidence=(),
            swings=(SwingPoint(price=90.0, index=1, type=SwingType.LOW, timestamp=ts),),
        )
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={
                FactKey("swing", timeframe=Timeframe.D1): swing_daily,
                FactKey("swing", timeframe=Timeframe.W1): swing_weekly,
            },
            evidence=(),
        )
        result = _extract_facts_per_frame([frame])
        swing_entries = {
            v["timeframe"]: v
            for v in result[0].values()
            if isinstance(v, dict) and v.get("type") == "swing"
        }
        assert set(swing_entries) == {"1d", "1w"}
        assert len(swing_entries["1d"]["swings"]) == 2
        assert len(swing_entries["1w"]["swings"]) == 1

    def test_empty(self) -> None:
        assert _extract_facts_per_frame([]) == []


class TestExtractTrades:
    def test_extracts_trade_data(self) -> None:
        tb = _make_tradebook_with_trades()
        result = _extract_trades_json(tb)
        assert len(result) == 2
        assert result[0]["result"] == "win"
        assert result[1]["result"] == "loss"

    def test_entry_exit_times(self) -> None:
        tb = _make_tradebook_with_trades()
        result = _extract_trades_json(tb)
        assert result[0]["entry_time"] == (BASE + timedelta(days=6)).strftime("%Y-%m-%d")
        assert result[0]["exit_time"] == (BASE + timedelta(days=8)).strftime("%Y-%m-%d")

    def test_empty_tradebook(self) -> None:
        tb = TradeBook()
        assert _extract_trades_json(tb) == []


class TestInteractiveRenderer:
    def test_creates_html_file(self, tmp_path: object) -> None:
        path = tmp_path / "interactive.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        assert path.exists()  # type: ignore[union-attr]

    def test_contains_required_js_data(self, tmp_path: object) -> None:
        path = tmp_path / "interactive.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "const CANDLES =" in content
        assert "const FRAMES =" in content
        assert "const EMA_SERIES =" in content
        assert "const ATR_DATA =" in content
        assert "const SR_DATA =" in content
        assert "const TRADES =" in content
        assert "const PULLBACKS =" in content
        assert "const FACTS_DATA =" in content

    def test_data_placeholders_terminated_with_semicolon(self, tmp_path: object) -> None:
        path = tmp_path / "semicolons.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        InteractiveRenderer(ctx).render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        js_match = re.search(r"<script>\n(.*)\n</script>", content, re.S)
        assert js_match is not None, "inline script block not found"
        js = js_match.group(1)
        # Each data placeholder must keep a terminating semicolon; otherwise a
        # following statement starting with '(' is absorbed into the value
        # expression (e.g. `const MIN_TOUCHES = 2(function() {...})()`).
        for name in ("CANDLES", "CANDLES_BY_TF", "FRAMES", "INITIAL_BALANCE", "MIN_TOUCHES"):
            line = next(l for l in js.splitlines() if l.startswith(f"const {name} = "))
            assert line.endswith(";"), f"const {name} missing terminating semicolon"
        # Init IIFE must not be glued onto the last data declaration.
        assert ";(function() {" in js

    def test_contains_controls(self, tmp_path: object) -> None:
        path = tmp_path / "controls.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "btn-first" in content
        assert "btn-prev" in content
        assert "btn-next" in content
        assert "btn-last" in content
        assert "btn-play" in content
        assert "speed-select" in content

    def test_contains_info_panel(self, tmp_path: object) -> None:
        path = tmp_path / "info.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "info-panel" in content
        assert "evidence-panel" in content
        assert "trade-timeline" in content

    def test_contains_title(self, tmp_path: object) -> None:
        path = tmp_path / "title.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb, title="Test Strategy")
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "Test Strategy" in content

    def test_contains_keyboard_shortcuts(self, tmp_path: object) -> None:
        path = tmp_path / "kb.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "Home" in content
        assert "End" in content
        assert "ArrowLeft" in content
        assert "ArrowRight" in content

    def test_with_trades(self, tmp_path: object) -> None:
        path = tmp_path / "trades.html"  # type: ignore[operator]
        store = _make_store(15)
        frame_store = _make_frame_store(10)
        tb = _make_tradebook_with_trades()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert '"win"' in content
        assert '"loss"' in content

    def test_debug_pickle_is_backtest_result(self, tmp_path: object) -> None:
        import pickle

        from marketatlas.backtesting.backtester import BacktestResult

        path = tmp_path / "debug.html"  # type: ignore[operator]
        store = _make_store(15)
        frame_store = _make_frame_store(10)
        tb = _make_tradebook_with_trades()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        InteractiveRenderer(ctx).render(path)  # type: ignore[arg-type]
        pkl_path = path.with_suffix(".pkl")  # type: ignore[operator]
        result = pickle.loads(pkl_path.read_bytes())  # type: ignore[attr-defined]
        assert isinstance(result, BacktestResult)
        assert len(result.tradebook.trades) == 2
        assert len(result.frames) == 10

    def test_with_sr_levels(self, tmp_path: object) -> None:
        path = tmp_path / "sr.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = FrameStore()
        frame_store.append(_make_sr_frame(0))
        frame_store.append(_make_sr_frame(1))
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "support" in content
        assert "resistance" in content

    def test_empty_frames(self, tmp_path: object) -> None:
        path = tmp_path / "empty.html"  # type: ignore[operator]
        store = _make_store(5)
        frame_store = FrameStore()
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "No frames to display" in content

    def test_file_size_reasonable(self, tmp_path: object) -> None:
        path = tmp_path / "size.html"  # type: ignore[operator]
        store = _make_store(100)
        frame_store = _make_frame_store(100)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        size = path.stat().st_size  # type: ignore[union-attr]
        assert size < 2_000_000  # under 2MB for 100 candles

    def test_includes_lightweight_charts(self, tmp_path: object) -> None:
        path = tmp_path / "charts.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "lightweight-charts" in content

    def test_timeline_bars(self, tmp_path: object) -> None:
        path = tmp_path / "timeline.html"  # type: ignore[operator]
        store = _make_store(15)
        frame_store = _make_frame_store(10)
        tb = _make_tradebook_with_trades()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "timeline-bar" in content
        assert "tl-win" in content
        assert "tl-loss" in content

    def test_summary_bar(self, tmp_path: object) -> None:
        path = tmp_path / "summary.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "summary-bar" in content
        assert "s-balance" in content
        assert "s-pnl" in content
        assert "s-expectancy" in content

    def test_breakeven_in_summary(self, tmp_path: object) -> None:
        path = tmp_path / "be.html"  # type: ignore[operator]
        store = _make_store(15)
        frame_store = _make_frame_store(10)
        from marketatlas.facts.structural import TrendDirection
        from marketatlas.strategy.signals import TradeSignal
        from marketatlas.strategy.trade import TradeCandidate

        tb = TradeBook(initial_balance=1000.0)
        signal = TradeSignal(
            direction=TrendDirection.BULLISH,
            entry_zone=(100.0, 105.0),
            confidence=0.8,
            source="test",
            evidence=(),
        )
        candidate = TradeCandidate(
            direction=TrendDirection.BULLISH,
            entry=103.0,
            stop=98.0,
            target=118.0,
            size=0.2,
            risk_amount=10.0,
            reward_amount=30.0,
            rr_ratio=3.0,
            slippage_pct=0.1,
            source="test",
            evidence=(),
        )
        # Breakeven trade: entry == exit
        tb.submit_order(candidate, signal, "test", BASE + timedelta(days=1))
        tb.fill_order(103.0, BASE + timedelta(days=2))
        tb.close_trade(103.0, BASE + timedelta(days=3))
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        InteractiveRenderer(ctx).render(path)
        content = path.read_text()
        assert '"breakeven"' in content
        assert "s-breakevens" in content

    def test_swing_markers_in_output(self, tmp_path: object) -> None:
        path = tmp_path / "swings.html"  # type: ignore[operator]
        store = _make_store(10)
        t0 = _make_candle(0).timestamp
        t2 = _make_candle(2).timestamp
        t4 = _make_candle(4).timestamp
        swing1 = SwingFact(
            timestamp=t0,
            evidence=(),
            swings=(
                SwingPoint(price=95.0, index=0, type=SwingType.LOW, timestamp=t0),
                SwingPoint(price=107.0, index=2, type=SwingType.HIGH, timestamp=t2),
            ),
        )
        swing2 = SwingFact(
            timestamp=_make_candle(1).timestamp,
            evidence=(),
            swings=(
                SwingPoint(price=95.0, index=0, type=SwingType.LOW, timestamp=t0),
                SwingPoint(price=107.0, index=2, type=SwingType.HIGH, timestamp=t2),
                SwingPoint(price=96.0, index=4, type=SwingType.LOW, timestamp=t4),
            ),
        )
        frame0 = AnalysisFrame(
            timestamp=_make_candle(0).timestamp,
            candle=_make_candle(0),
            facts={FactKey("swing"): swing1},
            evidence=(),
        )
        frame1 = AnalysisFrame(
            timestamp=_make_candle(1).timestamp,
            candle=_make_candle(1),
            facts={FactKey("swing"): swing2},
            evidence=(),
        )
        frame_store = FrameStore()
        frame_store.append(frame0)
        frame_store.append(frame1)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert '"swing"' in content
        assert '"swings"' in content
        assert "#f59e0b" in content  # swing high color
        assert "#3b82f6" in content  # swing low color

    def test_zigzag_in_output(self, tmp_path: object) -> None:
        path = tmp_path / "zigzag.html"  # type: ignore[operator]
        store = _make_store(10)
        t1 = _make_candle(1).timestamp
        t3 = _make_candle(3).timestamp
        t5 = _make_candle(5).timestamp
        t7 = _make_candle(7).timestamp
        swing_fact = SwingFact(
            timestamp=t5,
            evidence=(),
            swings=(
                SwingPoint(price=95.0, index=1, type=SwingType.LOW, timestamp=t1),
                SwingPoint(price=110.0, index=3, type=SwingType.HIGH, timestamp=t3),
                SwingPoint(price=97.0, index=5, type=SwingType.LOW, timestamp=t5),
                SwingPoint(price=112.0, index=7, type=SwingType.HIGH, timestamp=t7),
            ),
        )
        pullback = PullbackFact(
            timestamp=_make_candle(5).timestamp,
            evidence=(),
            direction=TrendDirection.BULLISH,
            swing_pattern=(95.0, 110.0, 97.0, 112.0),
        )
        frame = AnalysisFrame(
            timestamp=_make_candle(5).timestamp,
            candle=_make_candle(5),
            facts={
                FactKey("swing"): swing_fact,
                FactKey("pullback"): pullback,
            },
            evidence=(),
        )
        frame_store = FrameStore()
        frame_store.append(frame)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "zigzagBull" in content
        assert "zigzagBear" in content
        assert "updateZigzag" in content
        assert "swing_pattern" in content

    def test_min_touches_in_output(self, tmp_path: object) -> None:
        path = tmp_path / "mt.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb, min_touches=3)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "const MIN_TOUCHES = 3" in content

    def test_sr_levels_below_min_touches_hidden(self, tmp_path: object) -> None:
        path = tmp_path / "sr_filter.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = FrameStore()
        candle = _make_candle(0)
        sr = SRFact(
            timestamp=candle.timestamp,
            evidence=(),
            levels=(
                SRLevel(price=90.0, strength=1, type="support"),
                SRLevel(price=95.0, strength=2, type="support"),
                SRLevel(price=110.0, strength=3, type="resistance"),
            ),
        )
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={FactKey("sr"): sr},
            evidence=(),
        )
        frame_store.append(frame)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb, min_touches=2)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "const MIN_TOUCHES = 2" in content
        assert "lv.strength < this.model.minTouches" in content

    def test_tiered_line_width_in_js(self, tmp_path: object) -> None:
        path = tmp_path / "tier.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "lv.strength >= 5" in content
        assert "lv.strength >= 3" in content

    def test_autoscroll_button_in_output(self, tmp_path: object) -> None:
        path = tmp_path / "scroll.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "btn-autoscroll" in content
        assert "autoScrollDisabled" in content

    def test_candle_ohlcv_in_info_panel(self, tmp_path: object) -> None:
        path = tmp_path / "ohlcv.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        # Info panel renders O/H/L/C/Vol labels dynamically from candle keys
        assert '\'<div class="row"><span class="label">\' +' in content
        assert 'class="label">Vol</span>' in content
        assert "candle[key].toFixed(2)" in content

    def test_crosshair_snap_in_js(self, tmp_path: object) -> None:
        path = tmp_path / "crosshair.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "setCrosshairPosition" in content

    def test_smooth_scroll_function_in_js(self, tmp_path: object) -> None:
        path = tmp_path / "smooth.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "scrollToFrame" in content
        assert "scrollToPosition" in content
        assert "animation" in content

    def test_autoscroll_all_modes_in_js(self, tmp_path: object) -> None:
        path = tmp_path / "modes.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "!model.autoScrollDisabled" in content
        # Ensure no futureVisibility === 'hide' guard on auto-scroll
        segment = content.split("btn-autoscroll")[1].split("}")[0]
        assert "futureVisibility === 'hide'" not in segment

    def test_keyboard_shortcut_a_in_js(self, tmp_path: object) -> None:
        path = tmp_path / "kb_a.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "case 'a':" in content

    def test_volume_container_in_output(self, tmp_path: object) -> None:
        path = tmp_path / "vol.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "volume-container" in content
        assert "volumeChart" in content
        assert "addHistogramSeries" in content

    def test_volume_update_in_frame(self, tmp_path: object) -> None:
        path = tmp_path / "vol_update.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "updateVolume" in content

    def test_volume_resize_handler(self, tmp_path: object) -> None:
        path = tmp_path / "vol_resize.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "containers.volume.clientWidth" in content

    def test_volume_chart_synced_timescales(self, tmp_path: object) -> None:
        path = tmp_path / "vol_sync.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        # Volume chart participates in time scale sync
        assert "sync(this.volumeChart" in content

    def test_candle_highlight_uses_update(self, tmp_path: object) -> None:
        path = tmp_path / "hl.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "highlightCandle" in content
        assert "candleSeries.update" in content
        assert 'borderColor: "#facc15"' in content
        assert 'wickColor: "#facc15"' in content
        assert "candleHighlightLine" not in content

    def test_visibility_button_in_output(self, tmp_path: object) -> None:
        path = tmp_path / "vis.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "btn-visibility" in content
        assert "toggleFutureVisibility" in content
        assert "futureVisibility" in content

    def test_dim_mode_candle_colors_in_js(self, tmp_path: object) -> None:
        path = tmp_path / "dim.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        # JS dim mode should set borderColor and wickColor for dimmed candles
        assert 'borderColor: "rgba(128,128,128,0.3)"' in content
        assert 'wickColor: "rgba(128,128,128,0.3)"' in content

    def test_future_visibility_toggle_cycle(self, tmp_path: object) -> None:
        path = tmp_path / "toggle.html"  # type: ignore[operator]
        store = _make_store(10)
        frame_store = _make_frame_store(5)
        tb = TradeBook()
        ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
        renderer = InteractiveRenderer(ctx)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        # Must cycle hide -> dim -> show
        btn_vis = re.search(r'id="btn-visibility".*?</button>', content)
        assert btn_vis is not None
        assert "futureVisibility" in content
        assert "const labels = {" in content
        assert "updateCandles" in content


class TestPortfolioChartRendering:
    """Backlog 077: per-instrument charts filtered from the shared book."""

    def _render(self, tmp_path: object) -> tuple[Path, tuple[Path, ...]]:
        from pathlib import Path

        from marketatlas.visualization.portfolio import render_portfolio

        out = Path(tmp_path) / "portfolio"  # type: ignore[arg-type]
        result = _make_portfolio_result()
        stores = {"A": _make_canonical_store("A"), "B": _make_canonical_store("B")}
        return render_portfolio(result, stores, out, stem="portfolio")

    def test_renders_index_and_per_instrument_charts(self, tmp_path: object) -> None:
        index, charts = self._render(tmp_path)
        assert index.name == "portfolio.html"
        assert {c.name for c in charts} == {"portfolio.A.html", "portfolio.B.html"}
        assert index.exists()
        assert all(c.exists() for c in charts)

    def _trades_array(self, path: Path) -> list[dict[str, object]]:
        import json

        content = path.read_text()
        match = re.search(r"const TRADES = (\[.+?\]);", content, re.DOTALL)
        assert match is not None, "TRADES constant not found"
        return json.loads(match.group(1))

    def _summary(self, path: Path) -> dict[str, object]:
        import json

        content = path.read_text()
        match = re.search(r"const SUMMARY = (\{.+?\});", content, re.DOTALL)
        assert match is not None, "SUMMARY constant not found"
        return json.loads(match.group(1))

    def test_chart_trades_only_matching_instrument(self, tmp_path: object) -> None:
        _, charts = self._render(tmp_path)
        chart_a = next(c for c in charts if c.stem.endswith(".A"))
        chart_b = next(c for c in charts if c.stem.endswith(".B"))

        assert [t["instrument"] for t in self._trades_array(chart_a)] == ["A"]
        assert [t["instrument"] for t in self._trades_array(chart_b)] == ["B"]

    def test_chart_summary_scoped_to_instrument(self, tmp_path: object) -> None:
        _, charts = self._render(tmp_path)
        chart_a = next(c for c in charts if c.stem.endswith(".A"))
        chart_b = next(c for c in charts if c.stem.endswith(".B"))

        summary_a = self._summary(chart_a)
        summary_b = self._summary(chart_b)
        assert summary_a["wins"] == 1 and summary_a["losses"] == 0
        assert summary_b["wins"] == 0 and summary_b["losses"] == 1
        assert summary_a["final_balance"] == pytest.approx(1003.0)
        assert summary_b["final_balance"] == pytest.approx(999.0)

    def test_chart_title_carries_canonical(self, tmp_path: object) -> None:
        _, charts = self._render(tmp_path)
        chart_a = next(c for c in charts if c.stem.endswith(".A"))
        content = chart_a.read_text()
        assert "<h1>A</h1>" in content
        assert "<title>A</title>" in content
