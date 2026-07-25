from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from marketatlas.evidence.model import EvidenceEntry
from marketatlas.facts.pattern import PullbackFact, PullbackStatus
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import SRFact, SwingFact, TrendDirection, TrendFact
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.strategy.tradebook import TradeBook
from marketatlas.visualization.context import RenderContext
from marketatlas.visualization.html_renderer import _candle_to_dict


def _extract_frames_json(frames: list[AnalysisFrame]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        evidence = [
            {"text": e.text, "level": e.level.value, "source": e.source}
            for e in frame.evidence
        ]
        result.append({
            "time": int(frame.timestamp.timestamp()),
            "evidence": evidence,
        })
    return result


def _extract_ema_per_frame(
    frames: list[AnalysisFrame],
) -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = {}
    for frame in frames:
        for fact_type_key, fact in frame.facts.items():
            if isinstance(fact, EMAFact) and fact_type_key[0] is EMAFact:
                name = f"EMA{fact.period}"
                if name not in series:
                    series[name] = []
                series[name].append({
                    "time": int(frame.timestamp.timestamp()),
                    "value": fact.value,
                })
    return series


def _extract_atr_per_frame(frames: list[AnalysisFrame]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        for fact in frame.facts.values():
            if isinstance(fact, ATRFact):
                result.append({
                    "time": int(frame.timestamp.timestamp()),
                    "value": fact.value,
                })
                break
    return result


def _extract_sr_per_frame(frames: list[AnalysisFrame]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        sr_fact: SRFact | None = None
        for fact_type_key, fact in frame.facts.items():
            if isinstance(fact, SRFact) and fact_type_key[0] is SRFact:
                sr_fact = fact
                break
        levels = []
        if sr_fact is not None:
            for lv in sr_fact.levels:
                levels.append({
                    "price": lv.price,
                    "strength": lv.strength,
                    "type": lv.type,
                })
        result.append({
            "time": int(frame.timestamp.timestamp()),
            "levels": levels,
        })
    return result


def _extract_pullbacks_per_frame(
    frames: list[AnalysisFrame],
) -> list[dict[str, Any] | None]:
    result: list[dict[str, Any] | None] = []
    for frame in frames:
        pb: PullbackFact | None = None
        for fact in frame.facts.values():
            if isinstance(fact, PullbackFact):
                pb = fact
                break
        if pb is not None and pb.status in (
            PullbackStatus.DETECTED,
            PullbackStatus.CONFIRMED,
        ):
            is_bull = pb.direction == TrendDirection.BULLISH
            result.append({
                "time": int(frame.timestamp.timestamp()),
                "position": "belowBar" if is_bull else "aboveBar",
                "color": "#22c55e" if is_bull else "#ef4444",
                "shape": "arrowUp" if is_bull else "arrowDown",
                "text": f"Pullback ({pb.retracement_atr:.1f} ATR)",
                "status": pb.status.value,
            })
        else:
            result.append(None)
    return result


def _extract_facts_per_frame(frames: list[AnalysisFrame]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        facts: dict[str, Any] = {}
        for fact_type_key, fact in frame.facts.items():
            label = fact_type_key[1]
            if isinstance(fact, EMAFact):
                facts[label] = {"type": "ema", "value": fact.value, "period": fact.period}
            elif isinstance(fact, ATRFact):
                facts[label] = {"type": "atr", "value": fact.value, "period": fact.period}
            elif isinstance(fact, TrendFact):
                facts[label] = {
                    "type": "trend",
                    "direction": fact.direction.value,
                    "strength": fact.strength,
                }
            elif isinstance(fact, PullbackFact):
                facts[label] = {
                    "type": "pullback",
                    "status": fact.status.value,
                    "direction": fact.direction.value,
                    "retracement_atr": fact.retracement_atr,
                    "confirmation_strength": fact.confirmation_strength,
                    "deviation_pct": fact.deviation_pct,
                    "swing_pattern": list(fact.swing_pattern),
                }
            elif isinstance(fact, SRFact):
                levels = [
                    {"price": lv.price, "strength": lv.strength, "type": lv.type}
                    for lv in fact.levels
                ]
                facts[label] = {"type": "sr", "levels": levels}
            elif isinstance(fact, SwingFact):
                swings = [
                    {"price": s.price, "index": s.index, "type": s.type.value}
                    for s in fact.swings
                ]
                facts[label] = {"type": "swing", "swings": swings}
        result.append(facts)
    return result


def _extract_trades_json(tradebook: TradeBook) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for trade in tradebook.trades:
        c = trade.candidate
        result.append({
            "entry_time": int(trade.entry_timestamp.timestamp()),
            "exit_time": (
                int(trade.exit_timestamp.timestamp())
                if trade.exit_timestamp is not None
                else None
            ),
            "entry": c.entry,
            "stop": c.stop,
            "target": c.target,
            "direction": c.direction.value,
            "result": trade.result,
            "pnl": trade.pnl,
            "source": trade.source_strategy,
            "size": c.size,
            "risk_amount": c.risk_amount,
            "rr_ratio": c.rr_ratio,
        })
    return result


def _evidence_to_json(entries: tuple[EvidenceEntry, ...]) -> list[dict[str, str]]:
    return [
        {"text": e.text, "level": e.level.value, "source": e.source}
        for e in entries
    ]


def _build_candle_evidence_map(
    frames: list[AnalysisFrame],
) -> dict[int, list[dict[str, str]]]:
    result: dict[int, list[dict[str, str]]] = {}
    for frame in frames:
        key = int(frame.timestamp.timestamp())
        ev = _evidence_to_json(frame.evidence)
        if ev:
            result[key] = ev
    return result


_INTERACTIVE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #1a1a2e; color: #e0e0e0; }}
  #header {{ padding: 12px 20px; background: #16213e; border-bottom: 1px solid #0f3460;
             display: flex; justify-content: space-between; align-items: center; }}
  #header h1 {{ font-size: 16px; font-weight: 600; color: #e94560; }}
  #header .meta {{ font-size: 12px; color: #888; }}
  #summary-bar {{ display: flex; gap: 20px; padding: 8px 20px; background: #0f3460;
                  font-size: 12px; border-bottom: 1px solid #16213e; }}
  #summary-bar .stat {{ color: #94a3b8; }}
  #summary-bar .stat b {{ color: #e0e0e0; }}
  #summary-bar .pnl-pos {{ color: #22c55e; }}
  #summary-bar .pnl-neg {{ color: #ef4444; }}
  #frame-controls {{ display: flex; align-items: center; gap: 12px; padding: 8px 20px;
                     background: #16213e; border-bottom: 1px solid #0f3460; }}
  #frame-controls button {{ background: #0f3460; color: #e0e0e0; border: 1px solid #1a3a5c;
                            padding: 4px 12px; border-radius: 4px; cursor: pointer;
                            font-size: 13px; }}
  #frame-controls button:hover {{ background: #1a3a5c; }}
  #frame-controls button.active {{ background: #e94560; border-color: #e94560; }}
  #frame-controls .frame-label {{ font-size: 13px; color: #94a3b8; }}
  #frame-controls select {{ background: #0f3460; color: #e0e0e0; border: 1px solid #1a3a5c;
                            padding: 3px 6px; border-radius: 4px; font-size: 12px; }}
  #main-area {{ display: flex; }}
  #chart-col {{ flex: 1; min-width: 0; }}
  #chart-container {{ width: 100%; height: 500px; }}
  #atr-container {{ width: 100%; height: 120px; border-top: 1px solid #0f3460; }}
  #info-panel {{ width: 280px; min-width: 280px; background: #16213e;
                border-left: 1px solid #0f3460; padding: 12px; overflow-y: auto;
                max-height: 620px; font-size: 12px; }}
  #info-panel h3 {{ font-size: 13px; color: #e94560; margin: 8px 0 4px; }}
  #info-panel h3:first-child {{ margin-top: 0; }}
  #info-panel .row {{ display: flex; justify-content: space-between; padding: 2px 0; }}
  #info-panel .label {{ color: #64748b; }}
  #info-panel .value {{ color: #e0e0e0; }}
  #info-panel .bull {{ color: #22c55e; }}
  #info-panel .bear {{ color: #ef4444; }}
  #info-panel .neutral {{ color: #94a3b8; }}
  #info-panel .sr-support {{ color: #3b82f6; }}
  #info-panel .sr-resistance {{ color: #f59e0b; }}
  #info-panel .trade-open {{ color: #22c55e; }}
  #info-panel .trade-closed {{ color: #94a3b8; }}
  #evidence-panel {{ padding: 12px 20px; background: #16213e; border-top: 1px solid #0f3460;
                     min-height: 60px; max-height: 150px; overflow-y: auto; }}
  #evidence-panel h3 {{ font-size: 13px; color: #e94560; margin-bottom: 6px; }}
  .ev-entry {{ font-size: 12px; padding: 2px 0; border-bottom: 1px solid #1a1a2e; }}
  .ev-info {{ color: #94a3b8; }}
  .ev-signal {{ color: #facc15; }}
  .ev-warning {{ color: #f87171; }}
  .ev-source {{ color: #64748b; font-size: 11px; }}
  #trade-timeline {{ padding: 8px 20px; background: #0f3460; border-top: 1px solid #16213e; }}
  #trade-timeline h3 {{ font-size: 12px; color: #94a3b8; margin-bottom: 6px; }}
  .timeline-bar {{ position: relative; height: 24px; background: #1a1a2e; border-radius: 4px; }}
  .timeline-trade {{ position: absolute; height: 20px; top: 2px; border-radius: 3px;
                     opacity: 0.8; cursor: pointer; min-width: 4px; }}
  .timeline-trade:hover {{ opacity: 1.0; }}
  .tl-win {{ background: #22c55e; }}
  .tl-loss {{ background: #ef4444; }}
  .tl-breakeven {{ background: #94a3b8; }}
  .tl-open {{ background: #3b82f6; animation: pulse 1.5s infinite; }}
  @keyframes pulse {{ 0%,100% {{ opacity: 0.6; }} 50% {{ opacity: 1.0; }} }}
  .timeline-cursor {{ position: absolute; width: 2px; height: 24px; top: 0;
                      background: #e94560; z-index: 10; }}
  #legend {{ display: flex; gap: 16px; padding: 6px 20px; font-size: 11px; background: #0f3460; }}
  #legend span {{ display: flex; align-items: center; gap: 4px; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
</style>
</head>
<body>
<div id="header">
  <div>
    <h1>{title}</h1>
    <div class="meta">{meta}</div>
  </div>
</div>
<div id="summary-bar">
  <span class="stat">Balance: <b id="s-balance">{initial_balance}</b></span>
  <span class="stat">P&amp;L: <b id="s-pnl">0.00</b></span>
  <span class="stat">Return: <b id="s-return">0.0%</b></span>
  <span class="stat">Trades: <b id="s-trades">0</b></span>
  <span class="stat">W/L: <b id="s-winrate">0.0%</b></span>
  <span class="stat">PF: <b id="s-pf">0.0</b></span>
  <span class="stat">Avg W: <b id="s-avgwin">0.00</b></span>
  <span class="stat">Avg L: <b id="s-avgloss">0.00</b></span>
  <span class="stat">Drawdown: <b id="s-drawdown">0.0%</b></span>
</div>
<div id="frame-controls">
  <button id="btn-prev" title="Previous frame (Left arrow)">&#9664; Prev</button>
  <span class="frame-label">Frame
    <span id="frame-num">0</span> / <span id="frame-total">0</span></span>
  <button id="btn-next" title="Next frame (Right arrow)">Next &#9654;</button>
  <button id="btn-play" title="Play/Pause (Space)">&#9654; Play</button>
  <select id="speed-select" title="Playback speed">
    <option value="1000">1 fps</option>
    <option value="500" selected>2 fps</option>
    <option value="200">5 fps</option>
    <option value="100">10 fps</option>
  </select>
</div>
<div id="main-area">
  <div id="chart-col">
    <div id="chart-container"></div>
    <div id="atr-container"></div>
  </div>
  <div id="info-panel">
    <h3>Frame Info</h3>
    <div id="info-content">Select a frame.</div>
  </div>
</div>
<div id="evidence-panel">
  <h3>Evidence</h3>
  <div id="evidence-content">Step through frames to see evidence.</div>
</div>
<div id="trade-timeline">
  <h3>Trades</h3>
  <div class="timeline-bar" id="timeline-bar"></div>
</div>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
const CANDLES = {candles_json};
const FRAMES = {frames_json};
const EMA_SERIES = {ema_json};
const ATR_DATA = {atr_json};
const SR_DATA = {sr_json};
const TRADES = {trades_json};
const PULLBACKS = {pullbacks_json};
const FACTS_DATA = {facts_json};
const EVIDENCE_MAP = {evidence_json};
const SUMMARY = {summary_json};
const INITIAL_BALANCE = {initial_balance};

let currentFrame = 0;
let playing = false;
let playInterval = null;

// --- Chart setup ---
const chartContainer = document.getElementById('chart-container');
const chart = LightweightCharts.createChart(chartContainer, {{
  width: chartContainer.clientWidth,
  height: 500,
  layout: {{ background: {{ color: '#1a1a2e' }}, textColor: '#e0e0e0' }},
  grid: {{ vertLines: {{ color: '#1e2a3a' }}, horzLines: {{ color: '#1e2a3a' }} }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  timeScale: {{ borderColor: '#0f3460', timeVisible: true }},
  rightPriceScale: {{ borderColor: '#0f3460' }},
}});

const candleSeries = chart.addCandlestickSeries({{
  upColor: '#22c55e', downColor: '#ef4444',
  borderUpColor: '#22c55e', borderDownColor: '#ef4444',
  wickUpColor: '#22c55e', wickDownColor: '#ef4444',
}});
candleSeries.setData(CANDLES);

const emaColors = {{ EMA10: '#a855f7', EMA20: '#3b82f6', EMA50: '#f59e0b', EMA200: '#ec4899' }};
const emaSeriesMap = {{}};
Object.keys(EMA_SERIES).forEach(name => {{
  const s = chart.addLineSeries({{
    color: emaColors[name] || '#888',
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
  }});
  emaSeriesMap[name] = s;
}});

// ATR panel
const atrContainer = document.getElementById('atr-container');
const atrChart = LightweightCharts.createChart(atrContainer, {{
  width: atrContainer.clientWidth,
  height: 120,
  layout: {{ background: {{ color: '#1a1a2e' }}, textColor: '#e0e0e0' }},
  grid: {{ vertLines: {{ color: '#1e2a3a' }}, horzLines: {{ color: '#1e2a3a' }} }},
  timeScale: {{ borderColor: '#0f3460', timeVisible: true }},
  rightPriceScale: {{ borderColor: '#0f3460' }},
}});
const atrLine = atrChart.addLineSeries({{
  color: '#8b5cf6', lineWidth: 1,
  priceLineVisible: false, lastValueVisible: true, title: 'ATR',
}});

// Sync time scales
chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {{
  if (range) atrChart.timeScale().setVisibleLogicalRange(range);
}});
atrChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {{
  if (range) chart.timeScale().setVisibleLogicalRange(range);
}});

// --- S/R price lines management ---
let srPriceLines = [];
function clearSR() {{
  srPriceLines.forEach(pl => {{
    try {{ candleSeries.removePriceLine(pl); }} catch(e) {{}}
  }});
  srPriceLines = [];
}}
function updateSR(frameIdx) {{
  clearSR();
  if (frameIdx >= SR_DATA.length) return;
  const levels = SR_DATA[frameIdx].levels;
  levels.forEach(lv => {{
    const isSupport = lv.type === 'support';
    const color = isSupport ? '#3b82f6' : '#f59e0b';
    const pl = candleSeries.createPriceLine({{
      price: lv.price,
      color: color,
      lineWidth: Math.min(1 + lv.strength, 3),
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: (isSupport ? 'S' : 'R') + ' ' + lv.price.toFixed(0) + ' (' + lv.strength + ')',
    }});
    srPriceLines.push(pl);
  }});
}}

// --- Trade price lines management ---
let tradePriceLines = [];
function clearTrades() {{
  tradePriceLines.forEach(pl => {{
    try {{ candleSeries.removePriceLine(pl); }} catch(e) {{}}
  }});
  tradePriceLines = [];
}}
function updateTradeLines(frameIdx) {{
  clearTrades();
  if (frameIdx >= FRAMES.length) return;
  const frameTime = FRAMES[frameIdx].time;
  TRADES.forEach(t => {{
    const notExited = t.exit_time === null || t.exit_time >= frameTime;
    const isActive = t.entry_time <= frameTime && notExited;
    if (!isActive) return;
    const entryColor = t.direction === 'bullish' ? '#22c55e' : '#22c55e';
    const stopColor = '#ef4444';
    const targetColor = '#22c55e';
    tradePriceLines.push(candleSeries.createPriceLine({{
      price: t.entry, color: entryColor, lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true, title: 'Entry ' + t.entry.toFixed(2),
    }}));
    tradePriceLines.push(candleSeries.createPriceLine({{
      price: t.stop, color: stopColor, lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true, title: 'Stop ' + t.stop.toFixed(2),
    }});
    tradePriceLines.push(candleSeries.createPriceLine({{
      price: t.target, color: targetColor, lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true, title: 'Target ' + t.target.toFixed(2),
    }});
  }});
}}

// --- Markers management ---
let currentMarkers = [];
function updateMarkers(frameIdx) {{
  const markers = [];
  if (frameIdx < PULLBACKS.length && PULLBACKS[frameIdx]) {{
    const pb = PULLBACKS[frameIdx];
    markers.push({{
      time: pb.time,
      position: pb.position,
      color: pb.color,
      shape: pb.shape,
      text: pb.text,
    }});
  }}
  // Trade entry markers
  TRADES.forEach(t => {{
    if (t.entry_time <= FRAMES[frameIdx].time) {{
      const isBull = t.direction === 'bullish';
      markers.push({{
        time: t.entry_time,
        position: isBull ? 'belowBar' : 'aboveBar',
        color: '#22c55e',
        shape: isBull ? 'arrowUp' : 'arrowDown',
        text: t.source,
      }});
    }}
    if (t.exit_time !== null && t.exit_time <= FRAMES[frameIdx].time) {{
      const isWin = t.result === 'win';
      markers.push({{
        time: t.exit_time,
        position: isWin ? 'aboveBar' : 'belowBar',
        color: isWin ? '#22c55e' : '#ef4444',
        shape: 'circle',
        text: (isWin ? '+' : '') + (t.pnl || 0).toFixed(2),
      }});
    }}
  }});
  markers.sort((a, b) => a.time - b.time);
  candleSeries.setMarkers(markers);
}}

// --- Info panel ---
function updateInfoPanel(frameIdx) {{
  const panel = document.getElementById('info-content');
  if (frameIdx >= FRAMES.length) {{ panel.innerHTML = 'No data.'; return; }}
  const frame = FRAMES[frameIdx];
  const facts = FACTS_DATA[frameIdx] || {{}};
  let html = '';

  html += '<h3>Frame ' + frameIdx + '</h3>';
  const d = new Date(frame.time * 1000);
  html += '<div class="row"><span class="label">Date</span><span class="value">' +
          d.toISOString().slice(0, 10) + '</span></div>';

  // Find close price from candles
  const candle = CANDLES.find(c => c.time === frame.time);
  if (candle) {{
    html += '<div class="row"><span class="label">Close</span><span class="value">' +
            candle.close.toFixed(2) + '</span></div>';
  }}

  // Balance from summary (cumulative)
  let bal = INITIAL_BALANCE;
  TRADES.forEach(t => {{
    if (t.exit_time !== null && t.exit_time <= frame.time && t.pnl !== null) {{
      bal += t.pnl;
    }}
  }});
  html += '<div class="row"><span class="label">Balance</span><span class="value">' +
          bal.toFixed(2) + '</span></div>';

  // Indicators
  html += '<h3>Indicators</h3>';
  Object.entries(facts).forEach(([key, val]) => {{
    if (val.type === 'ema') {{
      html += '<div class="row"><span class="label">' + key + '</span><span class="value">' +
              val.value.toFixed(2) + '</span></div>';
    }} else if (val.type === 'atr') {{
      html += '<div class="row"><span class="label">' + key + '</span><span class="value">' +
              val.value.toFixed(2) + '</span></div>';
    }} else if (val.type === 'trend') {{
      const cls = val.direction === 'bullish' ? 'bull' :
                  val.direction === 'bearish' ? 'bear' : 'neutral';
      html += '<div class="row"><span class="label">Trend</span><span class="value ' + cls + '">' +
              val.direction.toUpperCase() + ' (' + val.strength.toFixed(2) + ')</span></div>';
    }}
  }});

  // Pullback
  Object.entries(facts).forEach(([key, val]) => {{
    if (val.type === 'pullback') {{
      html += '<h3>Pattern</h3>';
      const statusColor = val.status === 'confirmed' ? 'bull' :
                          val.status === 'invalidated' ? 'bear' : 'neutral';
      html += '<div class="row"><span class="label">' + key + '</span><span class="value ' +
              statusColor + '">' + val.status.toUpperCase() + '</span></div>';
      if (val.swing_pattern && val.swing_pattern.length > 0) {{
        html += '<div class="row"><span class="label">Pattern</span><span class="value">' +
                val.swing_pattern.map(p => p.toFixed(0)).join('/') + '</span></div>';
      }}
      if (val.deviation_pct > 0) {{
        html += '<div class="row"><span class="label">Deviation</span><span class="value">' +
                val.deviation_pct.toFixed(1) + '%</span></div>';
      }}
      if (val.confirmation_strength > 0) {{
        html += '<div class="row"><span class="label">Confirmation</span><span class="value">' +
                (val.confirmation_strength * 100).toFixed(0) + '%</span></div>';
      }}
    }}
  }});

  // S/R levels
  if (frameIdx < SR_DATA.length) {{
    const srLevels = SR_DATA[frameIdx].levels;
    if (srLevels.length > 0) {{
      html += '<h3>S/R Levels</h3>';
      srLevels.forEach(lv => {{
        const cls = lv.type === 'support' ? 'sr-support' : 'sr-resistance';
        const label = lv.type === 'support' ? 'S' : 'R';
        html += '<div class="row"><span class="label ' + cls + '">' +
                label + '</span><span class="value">' +
                lv.price.toFixed(0) + ' (' + lv.strength +
                ')</span></div>';
      }});
    }}
  }}

  // Active trade
  const activeTrades = TRADES.filter(t =>
    t.entry_time <= frame.time && (t.exit_time === null || t.exit_time >= frame.time)
  );
  if (activeTrades.length > 0) {{
    html += '<h3>Trade</h3>';
    activeTrades.forEach(t => {{
      const dirLabel = t.direction === 'bullish' ? 'LONG' : 'SHORT';
      html += '<div class="row"><span class="label">Status</span>' +
              '<span class="value trade-open">OPEN ' +
              dirLabel + '</span></div>';
      html += '<div class="row"><span class="label">Entry</span><span class="value">' +
              t.entry.toFixed(2) + '</span></div>';
      html += '<div class="row"><span class="label">Stop</span><span class="value">' +
              t.stop.toFixed(2) + '</span></div>';
      html += '<div class="row"><span class="label">Target</span><span class="value">' +
              t.target.toFixed(2) + '</span></div>';
      html += '<div class="row"><span class="label">Size</span><span class="value">' +
              t.size.toFixed(4) + '</span></div>';
      html += '<div class="row"><span class="label">R:R</span><span class="value">' +
              t.rr_ratio.toFixed(1) + '</span></div>';
    }});
  }} else {{
    // Show last closed trade if any
    const closedTrades = TRADES.filter(t =>
      t.exit_time !== null && t.exit_time <= frame.time
    );
    if (closedTrades.length > 0) {{
      const last = closedTrades[closedTrades.length - 1];
      html += '<h3>Last Trade</h3>';
      const cls = last.result === 'win' ? 'bull' : last.result === 'loss' ? 'bear' : 'neutral';
      html += '<div class="row"><span class="label">Result</span><span class="value ' + cls + '">' +
              (last.result || 'open').toUpperCase() + '</span></div>';
      html += '<div class="row"><span class="label">P&amp;L</span>' +
              '<span class="value ' + cls + '">' +
              (last.pnl >= 0 ? '+' : '') + last.pnl.toFixed(2) +
              '</span></div>';
    }}
  }}

  panel.innerHTML = html;
}}

// --- Evidence panel ---
function updateEvidence(frameIdx) {{
  const panel = document.getElementById('evidence-content');
  if (frameIdx >= FRAMES.length) {{ panel.innerHTML = 'No evidence.'; return; }}
  const frame = FRAMES[frameIdx];
  if (!frame.evidence || frame.evidence.length === 0) {{
    panel.innerHTML = 'No evidence for this frame.';
    return;
  }}
  panel.innerHTML = frame.evidence.map(e => {{
    const cls = 'ev-' + e.level;
    const src = e.source ? ' <span class="ev-source">(' + e.source + ')</span>' : '';
    return '<div class="ev-entry ' + cls + '">' + e.text + src + '</div>';
  }}).join('');
}}

// --- Summary bar ---
function updateSummary(frameIdx) {{
  let bal = INITIAL_BALANCE;
  let wins = 0, losses = 0, pnl = 0;
  let grossProfit = 0, grossLoss = 0;
  let peak = INITIAL_BALANCE, worst = 0;
  TRADES.forEach(t => {{
    if (t.exit_time !== null && t.exit_time <= FRAMES[frameIdx].time && t.pnl !== null) {{
      bal += t.pnl;
      pnl += t.pnl;
      if (t.result === 'win') {{ wins++; grossProfit += t.pnl; }}
      if (t.result === 'loss') {{ losses++; grossLoss += Math.abs(t.pnl); }}
    }}
    if (bal > peak) peak = bal;
    const dd = peak > 0 ? (peak - bal) / peak : 0;
    if (dd > worst) worst = dd;
  }});
  document.getElementById('s-balance').textContent = bal.toFixed(2);
  const pnlEl = document.getElementById('s-pnl');
  pnlEl.textContent = (pnl >= 0 ? '+' : '') + pnl.toFixed(2);
  pnlEl.className = pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
  const retEl = document.getElementById('s-return');
  const retPct = INITIAL_BALANCE > 0 ? (pnl / INITIAL_BALANCE * 100) : 0;
  retEl.textContent = retPct.toFixed(1) + '%';
  retEl.className = retPct >= 0 ? 'pnl-pos' : 'pnl-neg';
  document.getElementById('s-trades').textContent = String(wins + losses);
  const total = wins + losses;
  document.getElementById('s-winrate').textContent =
      total > 0 ? (wins / total * 100).toFixed(0) + '%' : '0.0%';
  const pf = grossLoss > 0 ? (grossProfit / grossLoss) : (grossProfit > 0 ? Infinity : 0);
  document.getElementById('s-pf').textContent =
      pf === Infinity ? '∞' : pf.toFixed(2);
  document.getElementById('s-avgwin').textContent =
      wins > 0 ? (grossProfit / wins).toFixed(2) : '0.00';
  document.getElementById('s-avgloss').textContent =
      losses > 0 ? (-grossLoss / losses).toFixed(2) : '0.00';
  document.getElementById('s-drawdown').textContent = (worst * 100).toFixed(1) + '%';
}}

// --- Trade timeline ---
function buildTimeline() {{
  const bar = document.getElementById('timeline-bar');
  if (CANDLES.length === 0) {{ bar.innerHTML = ''; return; }}
  const minTime = CANDLES[0].time;
  const maxTime = CANDLES[CANDLES.length - 1].time;
  const span = maxTime - minTime || 1;
  let html = '';
  TRADES.forEach((t, i) => {{
    const startPct = ((t.entry_time - minTime) / span * 100).toFixed(2);
    const endPct = t.exit_time !== null
      ? ((t.exit_time - minTime) / span * 100).toFixed(2)
      : '100';
    const width = Math.max(parseFloat(endPct) - parseFloat(startPct), 0.3);
    const cls = t.result === 'win' ? 'tl-win' :
                t.result === 'loss' ? 'tl-loss' :
                t.result === 'breakeven' ? 'tl-breakeven' : 'tl-open';
    html += '<div class="timeline-trade ' + cls + '" style="left:' + startPct +
            '%;width:' + width + '%" title="Trade ' + (i+1) + ': ' +
            (t.result || 'open') + ' PnL: ' + (t.pnl !== null ? t.pnl.toFixed(2) : 'open') +
            '"></div>';
  }});
  html += '<div class="timeline-cursor" id="timeline-cursor" style="left:0%"></div>';
  bar.innerHTML = html;
}}
function updateTimelineCursor(frameIdx) {{
  const cursor = document.getElementById('timeline-cursor');
  if (!cursor || CANDLES.length === 0) return;
  if (frameIdx >= FRAMES.length) return;
  const minTime = CANDLES[0].time;
  const maxTime = CANDLES[CANDLES.length - 1].time;
  const span = maxTime - minTime || 1;
  const pct = ((FRAMES[frameIdx].time - minTime) / span * 100).toFixed(2);
  cursor.style.left = pct + '%';
}}

// --- Frame stepping ---
function updateFrame(idx) {{
  if (idx < 0) idx = 0;
  if (idx >= FRAMES.length) idx = FRAMES.length - 1;
  currentFrame = idx;

  // Update EMA series (truncate to current frame)
  Object.entries(EMA_SERIES).forEach(([name, data]) => {{
    const cutoff = FRAMES[idx].time;
    const sliced = data.filter(d => d.time <= cutoff);
    if (emaSeriesMap[name]) emaSeriesMap[name].setData(sliced);
  }});

  // Update ATR
  const cutoff = FRAMES[idx].time;
  const atrSliced = ATR_DATA.filter(d => d.time <= cutoff);
  atrLine.setData(atrSliced);

  // Update S/R, trades, markers
  updateSR(idx);
  updateTradeLines(idx);
  updateMarkers(idx);
  updateInfoPanel(idx);
  updateEvidence(idx);
  updateSummary(idx);
  updateTimelineCursor(idx);

  // Update frame counter
  document.getElementById('frame-num').textContent = String(idx + 1);

  // Scroll chart to current frame
  const time = FRAMES[idx].time;
  chart.timeScale().scrollToPosition(0.8, false);
}}

// --- Controls ---
document.getElementById('btn-prev').addEventListener('click', () => {{
  stopPlay();
  updateFrame(currentFrame - 1);
}});
document.getElementById('btn-next').addEventListener('click', () => {{
  stopPlay();
  updateFrame(currentFrame + 1);
}});
document.getElementById('btn-play').addEventListener('click', togglePlay);
document.getElementById('speed-select').addEventListener('change', () => {{
  if (playing) {{ stopPlay(); startPlay(); }}
}});

function togglePlay() {{
  if (playing) {{ stopPlay(); }} else {{ startPlay(); }}
}}
function startPlay() {{
  playing = true;
  document.getElementById('btn-play').textContent = '\\u23F8 Pause';
  document.getElementById('btn-play').classList.add('active');
  const speed = parseInt(document.getElementById('speed-select').value, 10);
  playInterval = setInterval(() => {{
    if (currentFrame >= FRAMES.length - 1) {{ stopPlay(); return; }}
    updateFrame(currentFrame + 1);
  }}, speed);
}}
function stopPlay() {{
  playing = false;
  document.getElementById('btn-play').textContent = '\\u25B6 Play';
  document.getElementById('btn-play').classList.remove('active');
  if (playInterval) {{ clearInterval(playInterval); playInterval = null; }}
}}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {{
  if (e.key === 'ArrowLeft') {{ stopPlay(); updateFrame(currentFrame - 1); }}
  else if (e.key === 'ArrowRight') {{ stopPlay(); updateFrame(currentFrame + 1); }}
  else if (e.key === ' ') {{ e.preventDefault(); togglePlay(); }}
}});

// --- Resize ---
window.addEventListener('resize', () => {{
  chart.applyOptions({{ width: chartContainer.clientWidth }});
  atrChart.applyOptions({{ width: atrContainer.clientWidth }});
}});

// --- Init ---
document.getElementById('frame-total').textContent = String(FRAMES.length);
buildTimeline();
if (FRAMES.length > 0) {{
  updateFrame(0);
}} else {{
  document.getElementById('info-content').innerHTML = 'No frames to display.';
  document.getElementById('evidence-content').innerHTML = 'No evidence.';
}}
</script>
</body>
</html>
"""


class InteractiveRenderer:
    def __init__(self, context: RenderContext) -> None:
        self._context = context

    def render(self, output_path: Path) -> None:
        ctx = self._context
        frames = list(ctx.frames)
        candles = [_candle_to_dict(ctx.store[i]) for i in range(len(ctx.store))]

        frames_json = _extract_frames_json(frames)
        ema_json = _extract_ema_per_frame(frames)
        atr_json = _extract_atr_per_frame(frames)
        sr_json = _extract_sr_per_frame(frames)
        pullbacks_json = _extract_pullbacks_per_frame(frames)
        facts_json = _extract_facts_per_frame(frames)
        evidence_map = _build_candle_evidence_map(frames)
        trades_json = _extract_trades_json(ctx.tradebook)

        summary = ctx.tradebook.summary
        summary_json = {
            "initial_balance": summary["initial_balance"],
            "final_balance": summary["final_balance"],
            "total_pnl": summary["total_pnl"],
            "total_return_pct": summary["total_return_pct"],
            "wins": summary["wins"],
            "losses": summary["losses"],
            "win_rate": summary["win_rate"],
            "max_drawdown": summary["max_drawdown"],
        }

        title = ctx.title or f"{ctx.store.symbol.name} — {ctx.store.timeframe.value}"
        meta = (
            f"{len(candles)} candles | {len(frames)} frames | "
            f"{len(ctx.tradebook.trades)} trades"
        )

        html = _INTERACTIVE_TEMPLATE.format(
            title=title,
            meta=meta,
            initial_balance=ctx.tradebook.initial_balance,
            candles_json=json.dumps(candles),
            frames_json=json.dumps(frames_json),
            ema_json=json.dumps(ema_json),
            atr_json=json.dumps(atr_json),
            sr_json=json.dumps(sr_json),
            trades_json=json.dumps(trades_json),
            pullbacks_json=json.dumps(pullbacks_json),
            facts_json=json.dumps(facts_json),
            evidence_json=json.dumps(evidence_map),
            summary_json=json.dumps(summary_json),
        )

        output_path.write_text(html, encoding="utf-8")
