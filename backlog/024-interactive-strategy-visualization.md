# Interactive Strategy Visualization

**Epic:** strategy

## Problem

HTML renderer only shows candles + indicators + evidence. No trades visible on chart, no S/R levels, no way to step through frames to watch opportunities develop. Need interactive visualization that shows the full strategy lifecycle.

## Goal

Enhanced HTML output that displays trades (entry/stop/target markers), S/R levels per frame, and a frame-stepping UI so you can watch patterns form, signals fire, trades open, and resolve.

## Design

### 1. Data Requirements

The renderer needs additional data beyond `FrameStore`:

```python
class RenderContext:
    frames: FrameStore
    tradebook: TradeBook
    sr_facts: dict[int, SRFact]      # cursor → SRFact (per frame)
    strategy_names: tuple[str, ...]  # for color-coding trades by source
    max_hold_days: int               # cancel trade after N days
```

### 2. Trade Markers

For each `TradeOutcome` in the TradeBook, render on the chart as a rectangle overlay:

**Shape:** Rectangle spanning horizontally from entry candle to exit candle (or max timespan if still open).

```
        ┌─────────────── target price ───────────────┐
        │              GREEN ZONE                      │
        ├─────────────── entry price ─────────────────┤  ← horizontal line
        │              RED ZONE                        │
        └─────────────── stop price ──────────────────┘
        |                                            |
     entry candle                              exit candle
```

**Components:**
- **Entry line**: solid horizontal line at entry price, spanning full width of trade duration
- **Target zone**: green semi-transparent rectangle between entry and target price
- **Stop zone**: red semi-transparent rectangle between entry and stop price
- **Duration**: rectangle spans from entry candle to exit candle (or `max_hold_days` if still open at backtest end)

**Bullish trade:**
- Target zone ABOVE entry line (green)
- Stop zone BELOW entry line (red)

**Bearish trade:**
- Target zone BELOW entry line (green)
- Stop zone ABOVE entry line (red)

**Timing:** Rectangle appears starting from the fill candle (entry candle), not the signal candle. Rectangle persists until exit (or end of max hold period).

**Visual states:**
- **Open trade**: full opacity rectangles, pulsing border
- **Closed win**: green zone filled, red zone faded, exit marker at target
- **Closed loss**: red zone filled, green zone faded, exit marker at stop

### 3. S/R Levels

For the currently viewed frame, render horizontal lines:

- **Support levels**: blue dashed lines below current price
- **Resistance levels**: orange dashed lines above current price
- **Line thickness**: proportional to strength (more touches = thicker)
- **Labels**: price level + touch count (e.g. "51500 (2)")

S/R levels are per-frame data — they shift as the frame progresses. When stepping through frames, S/R lines move to reflect the levels computed at that point in time. This captures how support/resistance evolves as new swing data becomes available.

### 4. Frame Stepper UI

Replace the static chart with an interactive frame viewer:

```
[◄ Prev] [Frame 127 / 266] [Next ►] [▶ Play] [Speed: ▼]
```

**Controls:**
- **Prev/Next**: step one frame backward/forward
- **Play/Pause**: auto-advance frames at configurable speed
- **Speed**: 1fps, 2fps, 5fps, 10fps
- **Keyboard**: ← → for prev/next, Space for play/pause

**Per-frame update:**
- Candlestick chart updates to show current frame
- Indicators update (EMA overlays, ATR panel)
- S/R levels update
- Trade markers update (show/hide based on whether trade is active at this frame)
- Evidence panel updates
- Balance display updates

### 5. Frame Info Panel

Side panel showing current frame state:

```
┌─ Frame 127 ─────────────────────┐
│ Date: 2024-05-15                │
│ Close: 53,200.00                │
│ Balance: 1,023.50               │
│                                 │
│ ── Indicators ──                │
│ EMA(20): 52,800                 │
│ EMA(50): 51,200                 │
│ ATR(14): 1,450                  │
│ Trend: BULLISH (0.72)           │
│                                 │
│ ── Pattern ──                   │
│ 4-Swing Pullback: CONFIRMED     │
│ HH/HL/HH/HL pattern            │
│ Deviation: 8.2%                 │
│ Confirmation: 72% strength      │
│                                 │
│ ── S/R Levels ──                │
│ R: 54,200 (3 touches)          │
│ R: 55,800 (1 touch)            │
│ S: 51,500 (2 touches)          │
│ S: 49,100 (2 touches)          │
│                                 │
│ ── Trade ──                     │
│ OPEN: LONG 0.187 BTC            │
│ Entry: 53,053 (2024-05-16)      │
│ Stop: 52,100                    │
│ Target: 55,400                  │
│ Max hold: 10 days (expires 26)  │
│ P&L: +147.00 (+1.47%)          │
└─────────────────────────────────┘
```

### 6. Trade Timeline

Below the chart, a horizontal timeline showing all trades:

```
Trade 1: ━━━━━━━━━━━━●━━━━━━━━━  WIN (+2.3%)
Trade 2: ━━━━━●━━━━━━━━━━━━━━━━  LOSS (-1.0%)
Trade 3: ━━━━━━━━━━━━━━━━━━━━━●  OPEN (+0.8%)
```

Each trade bar spans from entry candle to exit candle. Color: green (win), red (loss), blue (open). Clicking a trade jumps the frame stepper to that trade's entry.

### 7. HTML Structure

```html
<div class="strategy-viewer">
  <div class="chart-container">
    <!-- TradingView lightweight-charts -->
    <!-- Trade markers overlaid -->
    <!-- S/R level lines -->
  </div>
  <div class="frame-controls">
    <!-- Prev/Next/Play/Speed -->
  </div>
  <div class="info-panel">
    <!-- Frame state, indicators, pattern, S/R, trade -->
  </div>
  <div class="trade-timeline">
    <!-- Horizontal trade bars -->
  </div>
  <div class="evidence-panel">
    <!-- Evidence entries for current frame -->
  </div>
</div>
```

### 8. Data Flow

```python
class InteractiveRenderer:
    def __init__(self, context: RenderContext) -> None: ...

    def render(self, path: Path) -> None:
        """Generate self-contained HTML with embedded JSON data.
        All frames, trades, and S/R facts embedded as JS data.
        Client-side JS handles frame stepping and rendering."""
```

All data is embedded as JSON in the HTML. No server needed. The JS reads frame index, updates all chart elements.

### 9. Read-Ahead Safety

- Frame stepper only shows data up to the current frame
- Future trade markers are hidden until their entry candle is reached
- S/R levels only shown for the current frame's data
- Balance reflects only trades resolved up to current frame

### 10. Tests

- HTML contains embedded JSON with correct frame count
- HTML contains trade data with correct entry/exit timestamps
- HTML contains S/R data per frame
- Frame stepper JS correctly shows/hides trades based on frame index
- Current frame info panel updates correctly
- No future data leaked in initial render state

## Evidence

- HTML file is self-contained (no external deps except TradingView CDN)
- Trade markers appear/disappear at correct frames
- S/R levels update per frame
- Frame stepping works with keyboard and mouse
- Balance updates as trades resolve
