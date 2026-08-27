from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

from marketatlas.backtesting.backtester import BacktestResult
from marketatlas.facts.pattern import PullbackFact
from marketatlas.facts.primitive import ATRFact, EMAFact
from marketatlas.facts.structural import (
    SRFact,
    SwingFact,
    SwingStructureFact,
    TrendDirection,
    TrendFact,
)
from marketatlas.frames.frame import AnalysisFrame
from marketatlas.strategy.tradebook import TradeBook
from marketatlas.visualization.context import RenderContext
from marketatlas.visualization.html_renderer import _candle_to_dict, _ts_to_time


def _extract_frames_json(frames: list[AnalysisFrame]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        evidence = [
            {"text": e.text, "level": e.level.value, "source": e.source} for e in frame.evidence
        ]
        risk_evidence = [
            {"text": e.text, "level": e.level.value, "source": e.source}
            for e in frame.risk_evidence
        ]
        signals = [
            {
                "direction": s.direction.value,
                "confidence": s.confidence,
                "source": s.source,
                "entry_zone": list(s.entry_zone),
            }
            for s in frame.signals
        ]
        signal_rejections = [
            {"text": e.text, "level": e.level.value, "source": e.source}
            for e in frame.signal_rejections
        ]
        result.append(
            {
                "time": _ts_to_time(frame.timestamp.timestamp()),
                "evidence": evidence,
                "risk_evidence": risk_evidence,
                "signals": signals,
                "signal_rejections": signal_rejections,
            }
        )
    return result


def _extract_ema_per_frame(
    frames: list[AnalysisFrame],
) -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = {}
    for frame in frames:
        for fact_type_key, fact in frame.facts.items():
            if isinstance(fact, EMAFact):
                name = f"EMA{fact.period}"
                if name not in series:
                    series[name] = []
                series[name].append(
                    {
                        "time": _ts_to_time(frame.timestamp.timestamp()),
                        "value": fact.value,
                    }
                )
    return series


def _extract_atr_per_frame(frames: list[AnalysisFrame]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        for fact in frame.facts.values():
            if isinstance(fact, ATRFact):
                result.append(
                    {
                        "time": _ts_to_time(frame.timestamp.timestamp()),
                        "value": fact.value,
                    }
                )
                break
    return result


def _extract_sr_per_frame(frames: list[AnalysisFrame]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        levels = []
        for fact in frame.facts.values():
            if isinstance(fact, SRFact):
                for lv in fact.levels:
                    levels.append(
                        {
                            "price": lv.price,
                            "strength": lv.strength,
                            "type": lv.type,
                        }
                    )
        result.append(
            {
                "time": _ts_to_time(frame.timestamp.timestamp()),
                "levels": levels,
            }
        )
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
        if pb is not None and pb.direction != TrendDirection.NEUTRAL:
            is_bull = pb.direction == TrendDirection.BULLISH
            result.append(
                {
                    "time": _ts_to_time(frame.timestamp.timestamp()),
                    "position": "belowBar" if is_bull else "aboveBar",
                    "color": "#22c55e" if is_bull else "#ef4444",
                    "shape": "arrowUp" if is_bull else "arrowDown",
                }
            )
        else:
            result.append(None)
    return result


def _extract_facts_per_frame(
    frames: list[AnalysisFrame],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Serialize per-frame facts with swing data deduplicated.

    Swing facts (``SwingFact``) carry the full accumulated pivot list on every
    frame, which is largely static between adjacent frames. To avoid emitting
    the same pivot dict hundreds of times, each unique pivot is stored once in
    a returned global ``swing_points`` map keyed by timeframe, and the per-frame
    swing fact stores only the list of pivot *times*. The JS hydrates the facts
    back to full pivot objects via :data:`SWING_POINTS`.
    """
    result: list[dict[str, Any]] = []
    swing_points: dict[str, dict[str, Any]] = {}
    for frame in frames:
        facts: dict[str, Any] = {}
        for fact_type_key, fact in frame.facts.items():
            label = fact_type_key.name
            if label in facts:
                label = (
                    f"{label}_{fact_type_key.timeframe.value}"
                    if fact_type_key.timeframe is not None
                    else f"{label}_{len(facts)}"
                )
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
                    "direction": fact.direction.value,
                    "swing_pattern": list(fact.swing_pattern),
                    "strength": fact.strength,
                }
            elif isinstance(fact, SwingStructureFact):
                # Match swing_pattern prices to SwingFact swings for indices/times
                facts[label] = {
                    "type": "swingstructure",
                    "points": [
                        {
                            "price": s.price,
                            "index": s.index,
                            "type": s.type.value,
                            "time": s.timestamp.strftime("%Y-%m-%d"),
                        }
                        for s in fact.points
                    ],
                }
            elif isinstance(fact, SRFact):
                levels = [
                    {"price": lv.price, "strength": lv.strength, "type": lv.type}
                    for lv in fact.levels
                ]
                facts[label] = {"type": "sr", "levels": levels}
            elif isinstance(fact, SwingFact):
                tf = (
                    fact_type_key.timeframe.value
                    if fact_type_key.timeframe is not None
                    else None
                )
                store = swing_points.setdefault(tf if tf is not None else "", {})
                times: list[str] = []
                for s in fact.swings:
                    key = s.timestamp.strftime("%Y-%m-%d")
                    store[key] = {
                        "price": s.price,
                        "index": s.index,
                        "type": s.type.value,
                        "time": key,
                    }
                    times.append(key)
                facts[label] = {"type": "swing", "swings": times, "timeframe": tf}
        result.append(facts)
    return result, swing_points


def _extract_trades_json(tradebook: TradeBook) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for trade in tradebook.trades:
        c = trade.candidate
        result.append(
            {
                "entry_time": trade.entry_timestamp.strftime("%Y-%m-%d"),
                "exit_time": (
                    trade.exit_timestamp.strftime("%Y-%m-%d")
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
                "instrument": trade.instrument,
                "size": c.size,
                "risk_amount": c.risk_amount,
                "rr_ratio": c.rr_ratio,
            }
        )
    return result


_JS_TEMPLATE_PATH = Path(__file__).parent / "interactive.js"
_JS_BASE_DIR = Path(__file__).parent / "base"
_BASE_MODULE_NAMES = [
    "models.js",
    "views/markers.js",
    "views/overlays.js",
    "views/trades.js",
    "views/crosshair.js",
    "views/chart.js",
    "views.js",
    "controllers.js",
]

_JS_PLACEHOLDERS = [
    "CANDLES_BY_TF",
    "AVAILABLE_TFS",
    "FRAMES",
    "EMA_SERIES",
    "ATR_DATA",
    "SR_DATA",
    "TRADES",
    "PULLBACKS",
    "FACTS_DATA",
    "SWING_POINTS",
    "SUMMARY",
    "INITIAL_BALANCE",
    "MIN_TOUCHES",
    "MAX_HOLD_DAYS",
]

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
  #volume-container {{ width: 100%; height: 80px; border-top: 1px solid #0f3460; }}
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
  <span class="stat">BE: <b id="s-breakevens">0</b></span>
  <span class="stat">W/L: <b id="s-winrate">0.0%</b></span>
  <span class="stat">PF: <b id="s-pf">0.0</b></span>
  <span class="stat">Avg W: <b id="s-avgwin">0.00</b></span>
  <span class="stat">Avg L: <b id="s-avgloss">0.00</b></span>
  <span class="stat">Expectancy: <b id="s-expectancy">$0.00</b></span>
  <span class="stat">Drawdown: <b id="s-drawdown">0.0%</b></span>
</div>
<div id="frame-controls">
  <button id="btn-first" title="First frame (Home)">&#9654;&#9664; First</button>
  <button id="btn-event-prev" title="Previous significant event (P)">&#9664; Event</button>
  <button id="btn-prev" title="Previous frame (Left arrow)">&#9664; Prev</button>
  <span class="frame-label">Frame
    <span id="frame-num">0</span> / <span id="frame-total">0</span></span>
  <button id="btn-next" title="Next frame (Right arrow)">Next &#9654;</button>
  <button id="btn-event-next" title="Next significant event (N)">Event &#9654;</button>
  <button id="btn-last" title="Last frame (End)">Last &#9654;&#9664;</button>
  <button id="btn-play" title="Play/Pause (Space)">&#9654; Play</button>
  <select id="speed-select" title="Playback speed">
    <option value="1000">1 fps</option>
    <option value="500" selected>2 fps</option>
    <option value="200">5 fps</option>
    <option value="100">10 fps</option>
  </select>
  <select id="tf-select" title="Resolution">
    {tf_options}
  </select>
  <button id="btn-visibility" title="Toggle future candle visibility (V)">&#128065; Hide</button>
  <button id="btn-autoscroll" class="active"
    title="Toggle auto-scroll (A)">&#128268; Scroll</button>
</div>
<div id="main-area">
  <div id="chart-col">
    <div id="chart-container"></div>
    <div id="volume-container"></div>
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
{js_content}
</body>
</html>
"""


class InteractiveRenderer:
    def __init__(self, context: RenderContext) -> None:
        self._context = context

    def render(self, output_path: Path) -> None:
        ctx = self._context
        frames = list(ctx.frames)

        frames_json = _extract_frames_json(frames)
        ema_json = _extract_ema_per_frame(frames)
        atr_json = _extract_atr_per_frame(frames)
        sr_json = _extract_sr_per_frame(frames)
        pullbacks_json = _extract_pullbacks_per_frame(frames)
        facts_json, swing_points = _extract_facts_per_frame(frames)
        trades_json = _extract_trades_json(ctx.tradebook)

        candles_by_tf: dict[str, list[dict[str, Any]]] = {}
        for tf in ctx.store.available_timeframes:
            tf_candles = ctx.store.get_candles(tf)
            if tf_candles:
                candles_by_tf[tf.value] = [_candle_to_dict(c) for c in tf_candles]

        available_tfs = [tf.value for tf in ctx.store.available_timeframes]
        primary_candle_count = len(candles_by_tf.get(available_tfs[0], [])) if available_tfs else 0

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
            "expectancy": summary["expectancy"],
        }

        title = ctx.title or f"{ctx.store.symbol.name} — {ctx.store.timeframe.value}"
        meta = (
            f"{primary_candle_count} candles | {len(frames)} frames | "
            f"{len(ctx.tradebook.trades)} trades"
        )

        js_modules = "".join(
            (_JS_BASE_DIR / m).read_text(encoding="utf-8") + "\n" for m in _BASE_MODULE_NAMES
        )
        js_entry = _JS_TEMPLATE_PATH.read_text(encoding="utf-8")
        js_template = js_modules + js_entry
        primary_tf = ctx.store.timeframe.value
        tf_options = "".join(
            f'<option value="{tf}"{" selected" if tf == primary_tf else ""}>{tf}</option>'
            for tf in available_tfs
        )
        data_map = {
            "CANDLES_BY_TF": json.dumps(candles_by_tf),
            "AVAILABLE_TFS": json.dumps(available_tfs),
            "FRAMES": json.dumps(frames_json),
            "EMA_SERIES": json.dumps(ema_json),
            "ATR_DATA": json.dumps(atr_json),
            "SR_DATA": json.dumps(sr_json),
            "TRADES": json.dumps(trades_json),
            "PULLBACKS": json.dumps(pullbacks_json),
            "FACTS_DATA": json.dumps(facts_json),
            "SWING_POINTS": json.dumps(swing_points),
            "SUMMARY": json.dumps(summary_json),
            "INITIAL_BALANCE": json.dumps(ctx.tradebook.initial_balance),
            "MIN_TOUCHES": json.dumps(ctx.min_touches),
            "MAX_HOLD_DAYS": json.dumps(ctx.max_hold_days),
        }
        for name in sorted(_JS_PLACEHOLDERS, key=len, reverse=True):
            js_template = js_template.replace(f"null; // @data:{name}", data_map[name] + ";")

        html = _INTERACTIVE_TEMPLATE.format(
            title=title,
            meta=meta,
            initial_balance=ctx.tradebook.initial_balance,
            tf_options=tf_options,
            js_content="<script>\n" + js_template + "\n</script>",
        )

        output_path.write_text(html, encoding="utf-8")

        debug_path = output_path.with_suffix(".pkl")
        result = BacktestResult(
            store=ctx.store,
            frames=ctx.frames,
            tradebook=ctx.tradebook,
            window_size=ctx.window_size,
            max_hold_days=ctx.max_hold_days,
        )
        debug_path.write_bytes(pickle.dumps(result))
