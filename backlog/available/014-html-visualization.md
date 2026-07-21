# HTML Visualization Report

**Epic:** mvp

## Problem

No way to see analysis results visually. Need a static HTML report showing price chart, indicators, and pattern markers.

## Goal

`HTMLRenderer` consumes `FrameStore` and produces a self-contained HTML file with interactive chart.

## Design

### 1. HTMLRenderer

File: `src/marketatlas/visualization/html_renderer.py`

```python
class HTMLRenderer:
    def __init__(self, frame_store: FrameStore, store: MarketStore): ...

    def render(self, output_path: Path) -> None: ...
```

### 2. Output Content

Single self-contained HTML file with:

- **Price chart**: Candlestick chart (using lightweight-charts or similar JS lib via CDN)
- **EMA overlay**: EMA20 and EMA50 lines on price chart
- **ATR panel**: ATR line below price chart
- **Trend markers**: Color-coded background or arrows for bullish/bearish
- **Pullback markers**: Arrows or circles at pullback detection points
- **Evidence panel**: Click a candle → see evidence entries for that timestamp
- **Time slider**: Scroll through time, see facts at each point

### 3. Implementation

- Embed data as JSON in `<script>` tag
- Use TradingView lightweight-charts (CDN) for candlestick rendering
- Custom panels for ATR and evidence
- No server required — fully static

### 4. Tests

- `renderer.render(output_path)` creates valid HTML file
- HTML file contains embedded data JSON
- File size reasonable for 1000 candles

## Evidence

- Opening `output.html` in browser shows interactive chart
- Pullback markers visible at correct timestamps
- Evidence panel shows analysis context per candle
