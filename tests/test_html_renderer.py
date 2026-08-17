from datetime import datetime, timedelta

from marketatlas.analysis.factkey import FactKey
from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import TrendDirection, TrendFact
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.frames.store import FrameStore
from marketatlas.visualization.html_renderer import (
    HTMLRenderer,
    _build_candle_evidence_map,
    _candle_to_dict,
    _extract_atr,
    _extract_ema_lines,
    _extract_trend_markers,
)


def _make_candle(offset: int = 0) -> Candle:
    ts = datetime(2024, 1, 1) + timedelta(hours=offset)
    base = 100.0 + offset
    return Candle(
        timestamp=ts,
        open=base,
        high=base + 5,
        low=base - 5,
        close=base + 2,
        volume=1000.0,
    )


def _make_market_store(n: int = 5) -> MarketStore:
    candles = tuple(_make_candle(i) for i in range(n))
    return MarketStore(
        MarketData(symbol=Symbol("BTCUSDT"), timeframe=Timeframe.H1, candles=candles)
    )


def _make_frame(offset: int = 0) -> AnalysisFrame:
    candle = _make_candle(offset)
    ema = EMAFact(
        timestamp=candle.timestamp,
        evidence=(),
        value=102.0 + offset,
        period=20,
    )
    atr = ATRFact(
        timestamp=candle.timestamp,
        evidence=(),
        value=3.5,
        period=14,
    )
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
        evidence=(
            EvidenceEntry(
                text=f"price above EMA at {offset}",
                level=EvidenceLevel.INFO,
                source="EMAAnalyzer",
            ),
        ),
    )


def _make_pullback_frame(offset: int) -> AnalysisFrame:
    candle = _make_candle(offset)
    return AnalysisFrame(
        timestamp=candle.timestamp,
        candle=candle,
        facts={},
        evidence=(),
    )


def _make_frame_store(n: int = 5) -> FrameStore:
    store = FrameStore()
    for i in range(n):
        store.append(_make_frame(i))
    return store


class TestCandleToDict:
    def test_basic(self) -> None:
        c = _make_candle(0)
        d = _candle_to_dict(c)
        assert d["open"] == c.open
        assert d["high"] == c.high
        assert d["low"] == c.low
        assert d["close"] == c.close
        assert d["volume"] == c.volume
        assert d["time"] == c.timestamp.strftime("%Y-%m-%d")


class TestExtractEMA:
    def test_extracts_ema_series(self) -> None:
        frames = [_make_frame(i) for i in range(3)]
        result = _extract_ema_lines(frames)
        assert "EMA20" in result
        assert len(result["EMA20"]) == 3
        assert result["EMA20"][0]["value"] == 102.0

    def test_multiple_periods(self) -> None:
        candle = _make_candle(0)
        ema20 = EMAFact(timestamp=candle.timestamp, evidence=(), value=100.0, period=20)
        ema50 = EMAFact(timestamp=candle.timestamp, evidence=(), value=99.0, period=50)
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={FactKey("ema_20"): ema20},
            evidence=(),
        )
        frame2 = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={FactKey("ema_50"): ema50},
            evidence=(),
        )
        result = _extract_ema_lines([frame, frame2])
        assert "EMA20" in result
        assert "EMA50" in result

    def test_empty(self) -> None:
        assert _extract_ema_lines([]) == {}


class TestExtractATR:
    def test_extracts_atr(self) -> None:
        frames = [_make_frame(i) for i in range(3)]
        result = _extract_atr(frames)
        assert len(result) == 3
        assert result[0]["value"] == 3.5

    def test_empty(self) -> None:
        assert _extract_atr([]) == []


class TestExtractTrendMarkers:
    def test_extracts_directions(self) -> None:
        frames = [_make_frame(i) for i in range(3)]
        bull, bear, neut = _extract_trend_markers(frames)
        assert len(bull) == 3
        assert len(bear) == 0
        assert len(neut) == 0

    def test_bearish_and_neutral_directions(self) -> None:
        candle = _make_candle(0)
        bear_frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={
                FactKey("trend"): TrendFact(
                    timestamp=candle.timestamp,
                    evidence=(),
                    direction=TrendDirection.BEARISH,
                    strength=0.5,
                )
            },
            evidence=(),
        )
        neut_frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={
                FactKey("trend"): TrendFact(
                    timestamp=candle.timestamp,
                    evidence=(),
                    direction=TrendDirection.NEUTRAL,
                    strength=0.1,
                )
            },
            evidence=(),
        )
        bull, bear, neut = _extract_trend_markers([bear_frame, neut_frame])
        assert len(bull) == 0
        assert len(bear) == 1
        assert len(neut) == 1

    def test_empty(self) -> None:
        bull, bear, neut = _extract_trend_markers([])
        assert bull == [] and bear == [] and neut == []


class TestEvidenceMap:
    def test_maps_timestamps(self) -> None:
        frames = [_make_frame(i * 24) for i in range(3)]
        result = _build_candle_evidence_map(frames)
        assert len(result) == 3
        first_key = _make_candle(0).timestamp.strftime("%Y-%m-%d")
        assert first_key in result
        assert result[first_key][0]["text"] == "price above EMA at 0"

    def test_empty_evidence(self) -> None:
        candle = _make_candle(0)
        frame = AnalysisFrame(
            timestamp=candle.timestamp,
            candle=candle,
            facts={},
            evidence=(),
        )
        result = _build_candle_evidence_map([frame])
        assert int(candle.timestamp.timestamp()) not in result


class TestHTMLRenderer:
    def test_creates_html_file(self, tmp_path: object) -> None:
        path = tmp_path / "output.html"  # type: ignore[operator]
        store = _make_market_store(5)
        frame_store = _make_frame_store(5)
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        assert path.exists()  # type: ignore[union-attr]
        content = path.read_text()  # type: ignore[union-attr]
        assert "BTCUSDT" in content
        assert "lightweight-charts" in content
        assert "candlestick" in content.lower() or "CandlestickSeries" in content

    def test_empty_frames(self, tmp_path: object) -> None:
        path = tmp_path / "empty.html"  # type: ignore[operator]
        store = _make_market_store(3)
        frame_store = FrameStore()
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        assert path.exists()  # type: ignore[union-attr]
        content = path.read_text()  # type: ignore[union-attr]
        assert "0 analysis frames" in content

    def test_contains_json_data(self, tmp_path: object) -> None:
        path = tmp_path / "data.html"  # type: ignore[operator]
        store = _make_market_store(3)
        frame_store = _make_frame_store(3)
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert '"open"' in content
        assert '"close"' in content
        assert '"EMA20"' in content

    def test_includes_pullbacks(self, tmp_path: object) -> None:
        path = tmp_path / "pb.html"  # type: ignore[operator]
        store = _make_market_store(3)
        frame_store = FrameStore()
        frame_store.append(_make_pullback_frame(1))
        frame_store.append(_make_frame(0))
        frame_store.append(_make_frame(2))
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "Pullback" in content

    def test_file_size_reasonable(self, tmp_path: object) -> None:
        path = tmp_path / "size.html"  # type: ignore[operator]
        store = _make_market_store(100)
        frame_store = _make_frame_store(100)
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        size = path.stat().st_size  # type: ignore[union-attr]
        assert size < 1_000_000  # under 1MB for 100 candles

    def test_smoke_contains_title(self, tmp_path: object) -> None:
        path = tmp_path / "smoke_title.html"  # type: ignore[operator]
        store = _make_market_store(5)
        frame_store = _make_frame_store(5)
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "<title>" in content
        assert "</title>" in content
        assert "<!DOCTYPE html>" in content

    def test_smoke_contains_chart_div(self, tmp_path: object) -> None:
        path = tmp_path / "smoke_chart.html"  # type: ignore[operator]
        store = _make_market_store(5)
        frame_store = _make_frame_store(5)
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "lightweight-charts" in content
        assert "chart" in content.lower()

    def test_smoke_contains_script_block(self, tmp_path: object) -> None:
        path = tmp_path / "smoke_script.html"  # type: ignore[operator]
        store = _make_market_store(5)
        frame_store = _make_frame_store(5)
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "<script>" in content
        assert "</script>" in content

    def test_smoke_js_constants_present(self, tmp_path: object) -> None:
        path = tmp_path / "smoke_consts.html"  # type: ignore[operator]
        store = _make_market_store(5)
        frame_store = _make_frame_store(5)
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "const DATA =" in content
        assert "const EMA_SERIES =" in content

    def test_smoke_no_unresolved_placeholders(self, tmp_path: object) -> None:
        path = tmp_path / "smoke_placeholders.html"  # type: ignore[operator]
        store = _make_market_store(5)
        frame_store = _make_frame_store(5)
        renderer = HTMLRenderer(frame_store, store)
        renderer.render(path)  # type: ignore[arg-type]
        content = path.read_text()  # type: ignore[union-attr]
        assert "// @data:" not in content
