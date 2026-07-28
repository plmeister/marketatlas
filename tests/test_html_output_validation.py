"""HTML output validation tests — catches broken JS, missing data, bad structure."""

import re
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle, MarketData, Symbol, Timeframe
from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import TrendDirection, TrendFact
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.frames.store import FrameStore
from marketatlas.strategy.tradebook import TradeBook
from marketatlas.visualization.context import RenderContext
from marketatlas.visualization.interactive import InteractiveRenderer

BASE = datetime(2024, 1, 1, tzinfo=UTC)

EXPECTED_DATA_CONSTANTS = [
    "CANDLES",
    "FRAMES",
    "EMA_SERIES",
    "ATR_DATA",
    "SR_DATA",
    "TRADES",
    "PULLBACKS",
    "FACTS_DATA",
    "EVIDENCE_MAP",
    "SUMMARY",
    "INITIAL_BALANCE",
]

EXPECTED_DOM_ELEMENTS = [
    "chart-container",
    "volume-container",
    "frame-controls",
    "info-panel",
    "evidence-panel",
    "trade-timeline",
    "timeline-bar",
    "summary-bar",
    "btn-prev",
    "btn-next",
    "btn-play",
    "speed-select",
    "frame-num",
    "frame-total",
]


def _make_candle(offset: int = 0, base_price: float = 100.0) -> Candle:
    ts = BASE + timedelta(days=offset)
    p = base_price + offset
    return Candle(
        timestamp=ts, open=p, high=p + 5, low=p - 5, close=p + 2, volume=1000.0,
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
        timestamp=candle.timestamp, evidence=(),
        direction=TrendDirection.BULLISH, strength=0.7,
    )
    return AnalysisFrame(
        timestamp=candle.timestamp,
        candle=candle,
        facts={
            (EMAFact, "ema_20"): ema,
            (ATRFact, "atr_14"): atr,
            (TrendFact, "trend"): trend,
        },
        evidence=(
            EvidenceEntry(text=f"frame {offset}", level=EvidenceLevel.INFO, source="test"),
        ),
    )


def _make_frame_store(n: int = 5) -> FrameStore:
    store = FrameStore()
    for i in range(n):
        store.append(_make_frame(i))
    return store


def _render_html(tmp_path: object, n_store: int = 10, n_frames: int = 5) -> Path:
    """Render HTML and return path."""
    path = Path(tmp_path) / "test.html"  # type: ignore[operator]
    store = _make_store(n_store)
    frame_store = _make_frame_store(n_frames)
    tb = TradeBook()
    ctx = RenderContext(frames=frame_store, store=store, tradebook=tb)
    renderer = InteractiveRenderer(ctx)
    renderer.render(path)  # type: ignore[arg-type]
    return path  # type: ignore[return-value]


def _extract_js_block(html: str) -> str:
    """Extract JS from the <script> block (not the lightweight-charts CDN script)."""
    # Match <script>\n...content...\n</script> — skip the CDN script
    scripts = re.findall(r"<script>\n(.+?)\n</script>", html, re.DOTALL)
    # The last <script> block is the app JS
    if scripts:
        return scripts[-1]
    return ""


def _extract_js_to_tempfile(js_block: str) -> Path:
    """Write JS to a temp file and return path."""
    tmp = Path(tempfile.mktemp(suffix=".js"))
    tmp.write_text(js_block, encoding="utf-8")
    return tmp


class TestJSValidation:
    """Validate JS syntax and data constants."""

    def test_js_syntax_valid(self, tmp_path: object) -> None:
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        js_block = _extract_js_block(content)
        assert js_block, "No JS block found in rendered HTML"

        tmp_js = _extract_js_to_tempfile(js_block)
        try:
            result = subprocess.run(
                ["node", "--check", str(tmp_js)],
                capture_output=True, text=True, timeout=10,
            )
            assert result.returncode == 0, f"JS syntax error:\n{result.stderr}"
        finally:
            tmp_js.unlink(missing_ok=True)

    def test_all_data_constants_present(self, tmp_path: object) -> None:
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        for name in EXPECTED_DATA_CONSTANTS:
            assert f"const {name} =" in content, f"Missing constant: {name}"

    def test_no_unresolved_placeholders(self, tmp_path: object) -> None:
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        assert "// @data:" not in content, "Unresolved @data placeholder found"


class TestHTMLStructure:
    """Validate HTML structure and DOM elements."""

    def test_contains_all_dom_elements(self, tmp_path: object) -> None:
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        for elem in EXPECTED_DOM_ELEMENTS:
            assert elem in content, f"Missing DOM element: {elem}"

    def test_contains_doctype(self, tmp_path: object) -> None:
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        assert content.startswith("<!DOCTYPE html>")

    def test_contains_lightweight_charts_cdn(self, tmp_path: object) -> None:
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        assert "lightweight-charts" in content

    def test_contains_evidence_panel(self, tmp_path: object) -> None:
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        assert "evidence-content" in content


class TestDataIntegrity:
    """Validate rendered data is non-empty and structurally sound."""

    def test_candles_array_not_empty(self, tmp_path: object) -> None:
        path = _render_html(tmp_path, n_store=10, n_frames=5)
        content = path.read_text()  # type: ignore[union-attr]
        # Extract the CANDLES array value — find "const CANDLES = " then the array
        match = re.search(r"const CANDLES = (\[.+?\]);", content, re.DOTALL)
        assert match, "CANDLES constant not found or not an array"
        candles_str = match.group(1)
        assert len(candles_str) > 2, "CANDLES array is empty"
        assert candles_str.startswith("[")
        assert candles_str.endswith("]")

    def test_frames_array_nonempty(self, tmp_path: object) -> None:
        path = _render_html(tmp_path, n_store=10, n_frames=5)
        content = path.read_text()  # type: ignore[union-attr]
        match = re.search(r"const FRAMES = (\[.+?\]);", content, re.DOTALL)
        assert match, "FRAMES constant not found"
        frames_str = match.group(1)
        assert frames_str != "[]", "FRAMES is empty for non-trivial data"

    def test_initial_balance_is_number(self, tmp_path: object) -> None:
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        match = re.search(r"const INITIAL_BALANCE = (\d+\.?\d*)", content)
        assert match, "INITIAL_BALANCE not found or not a number"
        val = float(match.group(1))
        assert val > 0


class TestSmokeTests:
    """Basic smoke tests that generated HTML is functionally complete."""

    def test_update_frame_callable_pattern(self, tmp_path: object) -> None:
        """Verify updateFrame function exists in JS."""
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        js_block = _extract_js_block(content)
        assert "function updateFrame" in js_block, "updateFrame function not found"
        assert "updateFrame(0)" in js_block, "updateFrame(0) call not found"

    def test_no_missing_braces_in_js(self, tmp_path: object) -> None:
        """Count opening/closing braces to catch obvious mismatches."""
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        js_block = _extract_js_block(content)
        # Simple heuristic: count braces (ignoring strings/comments is hard,
        # but a gross mismatch still catches real bugs)
        opens = js_block.count("{")
        closes = js_block.count("}")
        assert opens == closes, (
            f"Brace mismatch: {opens} opening vs {closes} closing"
        )

    def test_init_section_present(self, tmp_path: object) -> None:
        """Verify init code that sets up the chart."""
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        js_block = _extract_js_block(content)
        assert "buildTimeline" in js_block
        assert "frame-total" in js_block

    def test_chart_creation_present(self, tmp_path: object) -> None:
        """Verify chart setup code."""
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        js_block = _extract_js_block(content)
        assert "createChart" in js_block
        assert "addCandlestickSeries" in js_block
        assert "addLineSeries" in js_block

    def test_controls_event_listeners(self, tmp_path: object) -> None:
        """Verify event listeners for controls."""
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        js_block = _extract_js_block(content)
        assert "addEventListener" in js_block
        assert "keydown" in js_block
