"""HTML output validation tests — catches broken JS, missing data, bad structure."""

import json
import re
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from marketatlas.analysis.factkey import FactKey
from marketatlas.backtesting.portfolio import PortfolioBacktestResult
from marketatlas.data.instrument import Instrument
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
from marketatlas.visualization.portfolio import (
    _fmt_pct,
    _fmt_pf,
    _fmt_pnl,
    _fmt_rate,
    _sign_class,
)

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
                capture_output=True,
                text=True,
                timeout=10,
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
        """Verify the render function exists in JS."""
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        js_block = _extract_js_block(content)
        assert "function render()" in js_block, "render function not found"
        assert "render();" in js_block, "render() call not found"

    def test_no_missing_braces_in_js(self, tmp_path: object) -> None:
        """Count opening/closing braces to catch obvious mismatches."""
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        js_block = _extract_js_block(content)
        # Simple heuristic: count braces (ignoring strings/comments is hard,
        # but a gross mismatch still catches real bugs)
        opens = js_block.count("{")
        closes = js_block.count("}")
        assert opens == closes, f"Brace mismatch: {opens} opening vs {closes} closing"

    def test_init_section_present(self, tmp_path: object) -> None:
        """Verify init code that sets up the chart."""
        path = _render_html(tmp_path)
        content = path.read_text()  # type: ignore[union-attr]
        js_block = _extract_js_block(content)
        assert "timelineBarView.build" in js_block
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


class TestPortfolioIndex:
    """Backlog 077: index page rows, hrefs, and shared-book summary."""

    def _render_index(self, tmp_path: object) -> Path:
        from pathlib import Path

        from marketatlas.visualization.portfolio import render_portfolio_index

        out = Path(tmp_path) / "portfolio"  # type: ignore[arg-type]
        result = _make_portfolio_result()
        return render_portfolio_index(result, out, stem="portfolio")

    def test_summary_bar_from_shared_book(self, tmp_path: object) -> None:
        content = self._render_index(tmp_path).read_text()  # type: ignore[union-attr]
        # A +30.00 win, B -10.00 loss -> shared total +20.00 over 2 trades
        assert "Total P&amp;L" in content
        assert ">+20.00</b>" in content
        assert "Return" in content
        assert "Max Drawdown" in content
        assert "Trades: <b>2</b>" in content
        assert "Balance" in content

    def test_one_row_per_instrument_with_links(self, tmp_path: object) -> None:
        content = self._render_index(tmp_path).read_text()  # type: ignore[union-attr]
        assert '<a href="portfolio.A.html">A</a>' in content
        assert '<a href="portfolio.B.html">B</a>' in content
        assert content.count("<tr><td><a") == 2

    def test_rows_show_pnl_trades_wl_winrate_pf(self, tmp_path: object) -> None:
        content = self._render_index(tmp_path).read_text()  # type: ignore[union-attr]
        # A: win-only -> PF shown as infinity symbol
        assert '<td class="num-pos">+30.00</td>' in content
        assert "<td>1</td>" in content
        assert "<td>1-0</td>" in content
        assert "<td>100.0%</td>" in content
        assert "<td>\u221e</td>" in content
        # B: loss-only -> PF 0.00
        assert '<td class="num-neg">-10.00</td>' in content
        assert "<td>0-1</td>" in content
        assert "<td>0.0%</td>" in content
        assert "<td>0.00</td>" in content

    def test_relative_links_work_from_disk(self, tmp_path: object) -> None:
        content = self._render_index(tmp_path).read_text()  # type: ignore[union-attr]
        assert 'href="portfolio.A.html"' in content
        assert "http" not in content
        assert "lightweight-charts" not in content

    def test_strategy_table(self, tmp_path: object) -> None:
        content = self._render_index(tmp_path).read_text()  # type: ignore[union-attr]
        assert "By Strategy" in content
        assert "<td>test_strat</td>" in content


class TestABIndex:
    """Backlog 081: A/B comparison index grid, detail tables, and hrefs."""

    def _render_index(self, tmp_path: object) -> tuple[Path, str]:
        from marketatlas.visualization.portfolio import render_ab_index

        out = Path(tmp_path) / "ab"  # type: ignore[arg-type]
        rows = [
            ({"generate_signal.min_strength": 0.1}, _make_ab_result(118.0, 98.0)),
            ({"generate_signal.min_strength": 0.99}, _make_ab_result(93.0, 113.0)),
        ]
        path = render_ab_index(rows, out, stem="ab")
        return path, path.read_text()

    def test_grid_one_row_per_combination(self, tmp_path: object) -> None:
        _, content = self._render_index(tmp_path)
        # Two choice values -> two grid rows, headers name the choice dimension.
        assert "<th>min_strength</th>" in content
        assert "<td>0.1</td>" in content
        assert "<td>0.99</td>" in content
        assert content.count("<tr>") >= 2

    def test_grid_full_metrics(self, tmp_path: object) -> None:
        _, content = self._render_index(tmp_path)
        # Variant 0: A +30.00 win (re-sized to fixed risk), B -10.00 loss
        # -> +20.00, PF 3.0, 50% win rate.
        assert '<td class="num-pos">+20.00</td>' in content
        assert "<td>2</td>" in content
        assert "<td>1-1</td>" in content
        assert "<td>50.0%</td>" in content
        assert "<td>3.00</td>" in content
        # Variant 1: -2.00 / +2.00 -> breakeven expectancy class.
        assert '<td class="num-zero">+0.00</td>' in content
        assert "<td>1.00</td>" in content

    def test_detail_tables_per_variant(self, tmp_path: object) -> None:
        _, content = self._render_index(tmp_path)
        assert content.count("<h2>Variant:") == 2
        assert "Variant: min_strength=0.1" in content
        assert "Variant: min_strength=0.99" in content
        assert content.count("<h2>By Instrument</h2>") == 2
        assert content.count("By Strategy") == 2
        assert content.count('<section class="variant"') == 2

    def test_links_to_variant_charts(self, tmp_path: object) -> None:
        _, content = self._render_index(tmp_path)
        # Slugs match the 080 output tree; hrefs are relative from ab.html.
        assert '<a href="ms010/portfolio.A.html">A</a>' in content
        assert '<a href="ms010/portfolio.B.html">B</a>' in content
        assert '<a href="ms099/portfolio.A.html">A</a>' in content
        assert '<a href="ms099/portfolio.B.html">B</a>' in content
        assert "http" not in content
        assert "lightweight-charts" not in content


class TestABIndexControls:
    """Backlog 082: embedded JSON, progressive control bar, JS syntax."""

    def _render_index(self, tmp_path: object) -> tuple[Path, str]:
        from marketatlas.visualization.portfolio import render_ab_index

        out = Path(tmp_path) / "ab"  # type: ignore[arg-type]
        rows = [
            ({"generate_signal.min_strength": 0.1}, _make_ab_result(118.0, 98.0)),
            ({"generate_signal.min_strength": 0.99}, _make_ab_result(93.0, 113.0)),
        ]
        path = render_ab_index(rows, out, stem="ab")
        return path, path.read_text()

    @staticmethod
    def _extract_json(content: str, name: str) -> list[dict[str, object]]:
        match = re.search(f"const {name} = (\\[.+?\\]);", content, re.DOTALL)
        assert match, f"{name} JSON not found"
        return json.loads(match.group(1))

    def test_variant_json_matches_server_rendered_grid(self, tmp_path: object) -> None:
        _, content = self._render_index(tmp_path)
        grid = re.search(r'<tbody id="ab-grid-body">\n(.+?)\n    </tbody>', content, re.DOTALL)
        assert grid, "grid body not found"
        grid_html = grid.group(1)
        variants = self._extract_json(content, "AB_VARIANTS")
        assert len(variants) == 2
        for variant in variants:
            m = variant["metrics"]
            assert isinstance(m, dict)
            expected = [
                f"<td>{int(m['total_trades'])}</td>",
                f"<td>{int(m['wins'])}-{int(m['losses'])}</td>",
                _fmt_cell(_fmt_rate(float(m["win_rate"]))),
                _fmt_cell(
                    _fmt_pnl(float(m["total_pnl"])),
                    class_=_sign_class(float(m["total_pnl"])),
                ),
                _fmt_cell(_fmt_pct(float(m["total_return_pct"]))),
                _fmt_cell(_fmt_pct(float(m["max_drawdown"]))),
                _fmt_cell(_fmt_pf(float(m["profit_factor"]))),
                _fmt_cell(
                    _fmt_pnl(float(m["expectancy"])),
                    class_=_sign_class(float(m["expectancy"])),
                ),
            ]
            for cell in expected:
                assert cell in grid_html, f"{cell} not in grid for {variant['slug']}"
            # ident values render as their grid text, in the same JSON order.
            ident_cell = "<td>0.1</td>" if variant["slug"] == "ms010" else "<td>0.99</td>"
            assert ident_cell in grid_html

    def test_grid_rows_rendered_by_json_match_static_count(self, tmp_path: object) -> None:
        _, content = self._render_index(tmp_path)
        variants = self._extract_json(content, "AB_VARIANTS")
        grid = re.search(r'<tbody id="ab-grid-body">\n(.+?)\n    </tbody>', content, re.DOTALL)
        assert grid
        assert grid.group(1).count("<tr>") == len(variants)

    def test_one_select_per_choice_dimension(self, tmp_path: object) -> None:
        _, content = self._render_index(tmp_path)
        dims = self._extract_json(content, "AB_DIMS")
        assert dims == [
            {
                "key": "generate_signal.min_strength",
                "header": "min_strength",
                "values": ["0.1", "0.99"],
            }
        ]
        # The script builds one select per dim; a select element is created.
        assert 'document.createElement("select")' in content
        assert 'id="ab-controls"' in content
        assert 'id="ab-count"' in content

    def test_sections_carry_data_slug(self, tmp_path: object) -> None:
        _, content = self._render_index(tmp_path)
        variants = self._extract_json(content, "AB_VARIANTS")
        slugs = {v["slug"] for v in variants}
        for slug in slugs:
            assert f'<section class="variant" data-slug="{slug}">' in content

    def test_static_tables_present_without_js(self, tmp_path: object) -> None:
        _, content = self._render_index(tmp_path)
        # Progressive enhancement: the full 081 tables are server-rendered and
        # the JSON/controls are purely additive.
        assert '<tbody id="ab-grid-body">' in content
        assert "Variant: min_strength=0.1" in content
        assert "Variant: min_strength=0.99" in content
        assert '<a href="ms010/portfolio.A.html">A</a>' in content
        assert '<a href="ms099/portfolio.B.html">B</a>' in content
        assert content.count("<h2>By Instrument</h2>") == 2

    def test_js_syntax_valid(self, tmp_path: object) -> None:
        path, content = self._render_index(tmp_path)
        scripts = re.findall(r"<script>\n(.+?)\n</script>", content, re.DOTALL)
        assert scripts, "No inline script block found"
        tmp_js = Path(tempfile.mktemp(suffix=".js"))
        try:
            tmp_js.write_text(scripts[-1], encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(tmp_js)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"JS syntax error:\n{result.stderr}"
        finally:
            tmp_js.unlink(missing_ok=True)
        # No unresolved @data placeholder survives into the emitted page.
        assert "// @data:" not in content

    def test_js_filter_smoke(self, tmp_path: object) -> None:
        """Run the page script under a minimal DOM stub and drive the control.

        The default state renders every variant's grid row and detail section;
        selecting a value per choice dimension narrows the grid to the matching
        combination, hides the others, and updates the variant count. Reset to
        "All" restores the full view.
        """
        path, content = self._render_index(tmp_path)
        scripts = re.findall(r"<script>\n(.+?)\n</script>", content, re.DOTALL)
        assert scripts, "No inline script block found"
        page_js = Path(tempfile.mktemp(suffix=".js"))
        harness_js = Path(tempfile.mktemp(suffix=".js"))
        try:
            page_js.write_text(scripts[-1], encoding="utf-8")
            harness_js.write_text(_AB_CONTROLS_SMOKE, encoding="utf-8")
            result = subprocess.run(
                ["node", str(harness_js), str(page_js)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"Smoke test failed:\n{result.stdout}\n{result.stderr}"
        finally:
            page_js.unlink(missing_ok=True)
            harness_js.unlink(missing_ok=True)


def _fmt_cell(text: str, class_: str = "") -> str:
    if class_:
        return f'<td class="{class_}">{text}</td>'
    return f"<td>{text}</td>"


def _make_ab_result(close_a: float, close_b: float) -> PortfolioBacktestResult:
    """Two-instrument result whose closes set distinct variant outcomes."""
    tb = _make_tradebook_with_instruments(close_a=close_a, close_b=close_b)
    return PortfolioBacktestResult(
        instruments=(
            Instrument(canonical="A", asset_class="crypto", description="A test asset"),
            Instrument(canonical="B", asset_class="crypto", description="B test asset"),
        ),
        frames={"A": _make_frame_store(5), "B": _make_frame_store(5)},
        tradebook=tb,
        window_size=100,
        max_hold_days=10,
    )


def _make_tradebook_with_instruments(close_a: float = 118.0, close_b: float = 98.0) -> TradeBook:
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
        slippage_pct=0.0,
        source="test",
        evidence=(),
    )

    tb.submit_order(candidate, signal, "test_strat", BASE + timedelta(days=5), instrument="A")
    tb.fill_order(103.0, BASE + timedelta(days=6))
    tb.close_trade(close_a, BASE + timedelta(days=8))

    tb.submit_order(candidate, signal, "test_strat", BASE + timedelta(days=10), instrument="B")
    tb.fill_order(103.0, BASE + timedelta(days=11))
    tb.close_trade(close_b, BASE + timedelta(days=13))

    return tb


def _make_portfolio_result() -> PortfolioBacktestResult:
    tb = _make_tradebook_with_instruments()
    frames = {"A": _make_frame_store(5), "B": _make_frame_store(5)}
    return PortfolioBacktestResult(
        instruments=(
            Instrument(canonical="A", asset_class="crypto", description="A test asset"),
            Instrument(canonical="B", asset_class="crypto", description="B test asset"),
        ),
        frames=frames,
        tradebook=tb,
        window_size=100,
        max_hold_days=10,
    )


_AB_CONTROLS_SMOKE = r"""
// Backlog 082 smoke test: run the embedded A/B index script against a minimal
// DOM stub and drive the choice controls. Exits non-zero on any failed check.
const fs = require("fs");

function makeEl(tag) {
  return {
    tag: tag,
    children: [],
    value: "",
    textContent: "",
    style: { display: "" },
    _attrs: {},
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    addEventListener(evt, fn) {
      listeners[evt] = listeners[evt] || [];
      listeners[evt].push({ el: this, fn: fn });
    },
    setAttribute(name, value) {
      this._attrs[name] = value;
    },
    getAttribute(name) {
      return this._attrs[name] !== undefined ? this._attrs[name] : null;
    },
  };
}

const listeners = {};
const gridBody = makeEl("tbody");
const controls = makeEl("div");
const countEl = makeEl("span");
const sections = [];

function fail(msg) {
  console.error("FAIL: " + msg);
  process.exit(1);
}

function rowCount() {
  const m = gridBody.innerHTML.match(/<tr>/g);
  return m ? m.length : 0;
}

const pageSrc = fs.readFileSync(process.argv[2], "utf8");
const variantsMatch = pageSrc.match(/const AB_VARIANTS = (\[.+?\]);/s);
if (!variantsMatch) fail("AB_VARIANTS JSON not found in page script");
const variantSlugs = JSON.parse(variantsMatch[1]).map((v) => v.slug);
for (const slug of variantSlugs) {
  sections.push({
    style: { display: "" },
    getAttribute(name) {
      return name === "data-slug" ? slug : null;
    },
  });
}

global.document = {
  getElementById(id) {
    if (id === "ab-grid-body") return gridBody;
    if (id === "ab-controls") return controls;
    if (id === "ab-count") return countEl;
    return null;
  },
  createElement(tag) {
    return makeEl(tag);
  },
  querySelectorAll(sel) {
    if (sel === "section.variant") return sections;
    return [];
  },
};

eval(pageSrc);
if (rowCount() !== 2) fail("default state should render 2 grid rows");
if (countEl.textContent !== "2 variant(s)") fail("default count wrong: " + countEl.textContent);
for (const s of sections) {
  if (s.style.display !== "") fail("default state should show every section");
}

let select = null;
for (const label of controls.children) {
  for (const child of label.children) {
    if (child.tag === "select") select = child;
  }
}
if (!select) fail("no select control found");
if (controls.children.length !== 1) fail("expected one control per choice dimension");

select.value = "0.1";
for (const e of listeners["change"] || []) {
  if (e.el === select) e.fn();
}
if (rowCount() !== 1) fail("filtered grid should keep 1 row");
if (countEl.textContent !== "1 variant(s)") fail("filtered count wrong: " + countEl.textContent);
const visibleSections = sections.filter((s) => s.style.display === "").length;
if (visibleSections !== 1) fail("filtered view should show exactly 1 section");

select.value = "";
for (const e of listeners["change"] || []) {
  if (e.el === select) e.fn();
}
if (rowCount() !== 2) fail("reset to All should restore 2 grid rows");
if (countEl.textContent !== "2 variant(s)") fail("reset count wrong: " + countEl.textContent);

console.log("OK: A/B index controls smoke test");
"""
