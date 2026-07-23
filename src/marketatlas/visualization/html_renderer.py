from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from marketatlas.data.store import MarketStore
from marketatlas.data.types import Candle
from marketatlas.evidence.model import EvidenceEntry
from marketatlas.facts.pattern import PullbackFact, PullbackStatus
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import TrendDirection, TrendFact
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.frames.store import FrameStore


def _candle_to_dict(c: Candle) -> dict[str, Any]:
    return {
        "time": int(c.timestamp.timestamp()),
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume,
    }


def _extract_ema_lines(
    frames: list[AnalysisFrame],
) -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = {}
    for frame in frames:
        for fact_type, fact in frame.facts.items():
            if isinstance(fact, EMAFact) and fact_type[0] is EMAFact:
                key = f"EMA{fact.period}"
                if key not in series:
                    series[key] = []
                series[key].append(
                    {"time": int(frame.timestamp.timestamp()), "value": fact.value}
                )
    return series


def _extract_atr(frames: list[AnalysisFrame]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        for fact in frame.facts.values():
            if isinstance(fact, ATRFact):
                result.append(
                    {"time": int(frame.timestamp.timestamp()), "value": fact.value}
                )
                break
    return result


def _extract_trend_markers(
    frames: list[AnalysisFrame],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    bullish: list[dict[str, Any]] = []
    bearish: list[dict[str, Any]] = []
    neutral: list[dict[str, Any]] = []
    for frame in frames:
        for fact in frame.facts.values():
            if isinstance(fact, TrendFact):
                entry = {"time": int(frame.timestamp.timestamp())}
                if fact.direction == TrendDirection.BULLISH:
                    bullish.append(entry)
                elif fact.direction == TrendDirection.BEARISH:
                    bearish.append(entry)
                else:
                    neutral.append(entry)
                break
    return bullish, bearish, neutral


def _extract_pullbacks(
    frames: list[AnalysisFrame],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        for fact in frame.facts.values():
            if isinstance(fact, PullbackFact) and fact.status == PullbackStatus.DETECTED:
                is_bull = fact.direction == TrendDirection.BULLISH
                result.append(
                    {
                        "time": int(frame.timestamp.timestamp()),
                        "position": "belowBar" if is_bull else "aboveBar",
                        "color": "#22c55e" if is_bull else "#ef4444",
                        "shape": "arrowUp" if is_bull else "arrowDown",
                        "text": f"Pullback ({fact.retracement_atr:.1f} ATR)",
                    }
                )
                break
    return result


def _evidence_to_json(entries: tuple[EvidenceEntry, ...]) -> list[dict[str, str]]:
    return [
        {
            "text": e.text,
            "level": e.level.value,
            "source": e.source,
            "annotation_hint": e.annotation_hint,
        }
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


_HTML_TEMPLATE = """\
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
  #header {{ padding: 12px 20px; background: #16213e; border-bottom: 1px solid #0f3460; }}
  #header h1 {{ font-size: 16px; font-weight: 600; color: #e94560; }}
  #header .meta {{ font-size: 12px; color: #888; margin-top: 4px; }}
  #chart-container {{ width: 100%; height: 500px; }}
  #atr-container {{ width: 100%; height: 150px; border-top: 1px solid #0f3460; }}
  #evidence-panel {{ padding: 12px 20px; background: #16213e; border-top: 1px solid #0f3460;
                     min-height: 80px; max-height: 200px; overflow-y: auto; }}
  #evidence-panel h3 {{ font-size: 13px; color: #e94560; margin-bottom: 6px; }}
  .ev-entry {{ font-size: 12px; padding: 3px 0; border-bottom: 1px solid #1a1a2e; }}
  .ev-info {{ color: #94a3b8; }}
  .ev-signal {{ color: #facc15; }}
  .ev-warning {{ color: #f87171; }}
  .ev-source {{ color: #64748b; font-size: 11px; }}
  #legend {{ display: flex; gap: 16px; padding: 6px 20px; font-size: 11px; background: #0f3460; }}
  #legend span {{ display: flex; align-items: center; gap: 4px; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
</style>
</head>
<body>
<div id="header">
  <h1>{title}</h1>
  <div class="meta">{meta}</div>
</div>
<div id="legend">
  <span><span class="dot" style="background:#22c55e"></span> Bullish</span>
  <span><span class="dot" style="background:#ef4444"></span> Bearish</span>
  <span><span class="dot" style="background:#eab308"></span> Pullback</span>
</div>
<div id="chart-container"></div>
<div id="atr-container"></div>
<div id="evidence-panel">
  <h3>Evidence</h3>
  <div id="evidence-content">Click a candle to see evidence.</div>
</div>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
const DATA = {data_json};
const EMA_SERIES = {ema_json};
const ATR_DATA = {atr_json};
const PULLBACKS = {pullbacks_json};
const EVIDENCE_MAP = {evidence_json};

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
candleSeries.setData(DATA);

const emaColors = {{ EMA20: '#3b82f6', EMA50: '#f59e0b', EMA10: '#a855f7', EMA200: '#ec4899' }};
Object.entries(EMA_SERIES).forEach(([name, data]) => {{
  const lineSeries = chart.addLineSeries({{
    color: emaColors[name] || '#888',
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
  }});
  lineSeries.setData(data);
}});

if (PULLBACKS.length > 0) {{
  candleSeries.setMarkers(PULLBACKS);
}}

// ATR panel
const atrContainer = document.getElementById('atr-container');
const atrChart = LightweightCharts.createChart(atrContainer, {{
  width: atrContainer.clientWidth,
  height: 150,
  layout: {{ background: {{ color: '#1a1a2e' }}, textColor: '#e0e0e0' }},
  grid: {{ vertLines: {{ color: '#1e2a3a' }}, horzLines: {{ color: '#1e2a3a' }} }},
  timeScale: {{ borderColor: '#0f3460', timeVisible: true }},
  rightPriceScale: {{ borderColor: '#0f3460' }},
}});

if (ATR_DATA.length > 0) {{
  const atrLine = atrChart.addLineSeries({{
    color: '#8b5cf6', lineWidth: 1,
    priceLineVisible: false, lastValueVisible: true,
    title: 'ATR',
  }});
  atrLine.setData(ATR_DATA);
}}

// Sync time scales
chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {{
  if (range) atrChart.timeScale().setVisibleLogicalRange(range);
}});
atrChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {{
  if (range) chart.timeScale().setVisibleLogicalRange(range);
}});

// Evidence panel on click
chart.subscribeCrosshairMove((param) => {{
  const time = param.time;
  const content = document.getElementById('evidence-content');
  if (time && EVIDENCE_MAP[time]) {{
    const entries = EVIDENCE_MAP[time];
    content.innerHTML = entries.map(e => {{
      const cls = 'ev-' + e.level;
      const src = e.source ? '<span class="ev-source"> (' + e.source + ')</span>' : '';
      return '<div class="ev-entry ' + cls + '">' + e.text + src + '</div>';
    }}).join('');
  }} else {{
    content.innerHTML = 'No evidence for this candle.';
  }}
}});

// Resize handler
window.addEventListener('resize', () => {{
  chart.applyOptions({{ width: chartContainer.clientWidth }});
  atrChart.applyOptions({{ width: atrContainer.clientWidth }});
}});
</script>
</body>
</html>
"""


class HTMLRenderer:
    def __init__(self, frame_store: FrameStore, store: MarketStore) -> None:
        self._frame_store = frame_store
        self._store = store

    def render(self, output_path: Path) -> None:
        frames = list(self._frame_store)
        candles = [_candle_to_dict(self._store[i]) for i in range(len(self._store))]

        # Filter frames to only those within the store range
        store_ts = {int(self._store[i].timestamp.timestamp()) for i in range(len(self._store))}
        viz_frames = [f for f in frames if int(f.timestamp.timestamp()) in store_ts]

        ema_series = _extract_ema_lines(viz_frames)
        atr_data = _extract_atr(viz_frames)
        pullbacks = _extract_pullbacks(viz_frames)
        evidence_map = _build_candle_evidence_map(viz_frames)

        title = f"{self._store.symbol.name} — {self._store.timeframe.value}"
        meta = f"{len(candles)} candles | {len(frames)} analysis frames"

        html = _HTML_TEMPLATE.format(
            title=title,
            meta=meta,
            data_json=json.dumps(candles),
            ema_json=json.dumps(ema_series),
            atr_json=json.dumps(atr_data),
            pullbacks_json=json.dumps(pullbacks),
            evidence_json=json.dumps(evidence_map),
        )

        output_path.write_text(html, encoding="utf-8")
