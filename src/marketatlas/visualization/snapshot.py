"""Static PNG snapshot renderer.

Draws a candlestick window around a point of interest (a trade) and overlays
the fact geometry visible at that cursor (no lookahead: each frame only carries
its own facts). SR levels, swing points / alternating zigzag, and pullback
markers are pulled from ``AnalysisFrame.facts``.

Two entry points share one render path over the same structured data:
``render_trade_snapshot`` accepts a typed ``AnalysisOutput``, while
``render_poi_snapshot`` accepts the JSON structured form produced by
``frames.jsoncodec`` (the single source of truth every consumer reads).

matplotlib is imported lazily so projects that never request PNG snapshots do
not require it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from marketatlas.frames.jsoncodec import decode_fact

# TradingView-ish palette
_BG = "#131722"
_TEXT = "#d1d4dc"
_MUTED = "#787b86"
_GRID = "#363a45"
_UP = "#26a69a"
_DOWN = "#ef5350"
_ENTRY = "#2962ff"
_SUPPORT = "#3b82f6"
_RESISTANCE = "#f59e0b"
_PULLBACK_BULL = "#22c55e"
_PULLBACK_BEAR = "#ef4444"

_DEFAULT_PRE = 45
_DEFAULT_POST = 25


def _ts_parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _norm_candles_from_input(source: Any, tf: str) -> list[dict[str, Any]]:
    """Return candle dicts ``{ts, o, h, l, c, v}`` from typed or schema input."""
    if isinstance(source, dict) and "candles" in source:
        raw = source["candles"].get(tf) or next(iter(source["candles"].values()))
        return [
            c if isinstance(c, dict) else {
                "ts": c.timestamp.isoformat(), "o": c.open, "h": c.high,
                "l": c.low, "c": c.close, "v": c.volume,
            }
            for c in raw
        ]
    candles = source.candles.get(tf) or tuple(source.candles.values())[0]
    return [
        c if isinstance(c, dict) else {
            "ts": c.timestamp.isoformat(), "o": c.open, "h": c.high,
            "l": c.low, "c": c.close, "v": c.volume,
        }
        for c in candles
    ]


def _facts_at(source: Any, poi: datetime) -> dict[str, Any] | None:
    """Return typed facts dict visible at ``poi`` (nearest frame <= poi)."""
    # Schema form: {'ts': iso, 'facts': {name: encoded_fact}}
    if isinstance(source, dict) and "facts_by_ts" in source:
        best: tuple[str, Any] | None = None
        for ts, facts in source["facts_by_ts"].items():
            if _ts_parse(ts) <= poi:
                best = (ts, facts)
            else:
                break
        if best is None:
            return None
        return {name: decode_fact(f) for name, f in best[1].items()}
    # Typed form: AnalysisFrame.facts
    best_frame: Any = None
    for frame in source.frames:
        if frame.timestamp <= poi:
            best_frame = frame
        else:
            break
    return best_frame.facts if best_frame is not None else None


def _symbol_from_input(source: Any) -> str:
    return source["symbol"] if isinstance(source, dict) else source.symbol


def _timeframe_from_input(source: Any) -> str:
    return source["timeframe"] if isinstance(source, dict) else source.timeframe


def _window(
    candles: list[dict[str, Any]], poi: datetime, pre: int, post: int
) -> tuple[list[dict[str, Any]], int, int]:
    idx = min(
        (i for i, c in enumerate(candles) if _ts_parse(c["ts"]) >= poi),
        default=len(candles) - 1,
    )
    start = max(0, idx - pre)
    end = min(len(candles), idx + post + 1)
    return candles[start:end], start, idx - start


def _overlay_sr(
    facts: dict[str, Any], price_range: tuple[float, float]
) -> list[dict[str, Any]]:
    """SR levels as translucent horizontal lines, each labelled on the line with
    value + strength, extending past the right edge of the visible window."""
    from marketatlas.facts.structural import SRFact

    shapes: list[dict[str, Any]] = []
    for fact in facts.values():
        if isinstance(fact, SRFact):
            for lv in fact.levels:
                color = _SUPPORT if lv.type == "support" else _RESISTANCE
                label = f"{lv.price:.4f}  s{lv.strength}"
                shapes.append(
                    {
                        "kind": "hline",
                        "y": lv.price,
                        "color": color,
                        "width": min(2.5, 0.7 + 0.5 * lv.strength),
                        "alpha": 0.6,
                    }
                )
                # label on the line itself, extending past the right edge of the
                # chart (x in axes-fraction via x_axes, y follows the line)
                shapes.append(
                    {
                        "kind": "text",
                        "x_axes": 1.005,
                        "y": lv.price,
                        "text": label,
                        "color": color,
                        "size": 7,
                        "ha": "left",
                        "va": "center",
                    }
                )
    return shapes


def _overlay_pullbacks(
    facts: dict[str, Any], start_index: int, end_index: int
) -> list[dict[str, Any]]:
    """Show the swing points that triggered each pullback, connected in order.

    Matches the pullback's ``swing_pattern`` price sequence to the swing
    points present in the frame (``SwingFact``/``SwingStructureFact``) and
    draws a polyline through them — the real pattern that fired, not a generic
    zigzag.
    """
    from marketatlas.facts.pattern import PullbackFact
    from marketatlas.facts.structural import SwingFact, SwingStructureFact, TrendDirection

    swings: list[Any] = []
    for fact in facts.values():
        if isinstance(fact, SwingFact):
            swings.extend(fact.swings)
        elif isinstance(fact, SwingStructureFact):
            swings.extend(fact.points)
    by_price: dict[float, Any] = {}
    for s in swings:
        by_price.setdefault(s.price, s)

    shapes: list[dict[str, Any]] = []
    for fact in facts.values():
        if isinstance(fact, PullbackFact) and fact.swing_pattern:
            is_bull = fact.direction == TrendDirection.BULLISH
            color = _PULLBACK_BULL if is_bull else _PULLBACK_BEAR
            pts: list[tuple[int, float]] = []
            for price in fact.swing_pattern:
                s = by_price.get(price)
                if s is not None:
                    x_pos = s.index - start_index
                    if 0 <= x_pos < (end_index - start_index):
                        pts.append((x_pos, price))
            pts.sort(key=lambda p: p[0])
            if len(pts) >= 2:
                shapes.append(
                    {
                        "kind": "polyline",
                        "x": [p[0] for p in pts],
                        "y": [p[1] for p in pts],
                        "color": color,
                        "width": 1.6,
                        "alpha": 0.9,
                        "label": "pullback",
                    }
                )
                shapes.append(
                    {
                        "kind": "scatter",
                        "x": [p[0] for p in pts],
                        "y": [p[1] for p in pts],
                        "color": color,
                        "size": 30,
                        "label": "pullback",
                    }
                )
    return shapes


def _trade_box_shapes(
    sub: list[dict[str, Any]],
    x0: int,
    x1: int,
    entry: float,
    stop: float,
    target: float,
    rr_ratio: float | None = None,
) -> list[dict[str, Any]]:
    """Two translucent panes: the stop side (red) and target side (green).

    Both span horizontally from the trade submission bar ``x0`` to ``x1``
    (cap at the last visible candle): entry->stop is red, entry->target is
    green. The full stop..target band is deliberately *not* filled — only the
    two half-sides around the entry. Entry/stop/target each get a label line
    past the right edge of the chart at their price level.
    """
    x1 = max(x0 + 1, min(x1, len(sub) - 1))
    stop_side = {
        "kind": "rect",
        "x0": x0, "x1": x1,
        "y0": min(entry, stop), "y1": max(entry, stop),
        "color": _DOWN, "alpha": 0.14,
    }
    target_side = {
        "kind": "rect",
        "x0": x0, "x1": x1,
        "y0": min(entry, target), "y1": max(entry, target),
        "color": _UP, "alpha": 0.14,
    }
    target_lbl = (
        f"R (x{rr_ratio:.2f}) {target:.4f}"
        if rr_ratio is not None else f"Target {target:.4f}"
    )
    def _hlabel(y: float, text: str, color: str) -> dict[str, Any]:
        return {"kind": "hline", "y": y, "color": color, "width": 1.0,
                "alpha": 0.9}
    return [
        stop_side,
        target_side,
        _hlabel(stop, f"Stop {stop:.4f}", _DOWN),
        _hlabel(target, target_lbl, _UP),
        {"kind": "hline", "y": entry, "color": _ENTRY, "width": 1.4, "alpha": 0.95},
        {"kind": "vline", "x": x0, "color": _ENTRY, "alpha": 0.4},
        {"kind": "text", "x_axes": 1.005, "y": entry,
         "text": f"Entry {entry:.4f}", "color": _ENTRY, "size": 7,
         "ha": "left", "va": "center"},
        {"kind": "text", "x_axes": 1.005, "y": stop,
         "text": f"Stop {stop:.4f}", "color": _DOWN, "size": 7,
         "ha": "left", "va": "center"},
        {"kind": "text", "x_axes": 1.005, "y": target,
         "text": target_lbl, "color": _UP, "size": 7,
         "ha": "left", "va": "center"},
    ]


def draw_shapes(ax: Any, shapes: list[dict[str, Any]]) -> None:
    """Draw a list of shape specs onto ``ax``.

    Kinds:
      ``hline``   horizontal line at ``y`` (width, color, alpha)
      ``vline``   vertical line at ``x``
      ``line``    segment ``(x0,y0)-(x1,y1)``
      ``rect``    translucent filled rect from ``x0..x1`` x ``y0..y1``
      ``polyline`` connected ``x``/``y`` point lists
      ``scatter`` markers at ``x``/``y`` point lists
      ``arrow``   arrow at ``x,y`` with vertical offset ``dy``
      ``text``    label at ``x,y`` (``text``, color, rotation optional)
    """
    import matplotlib.patches as mp

    for s in shapes:
        kind = s["kind"]
        color = s.get("color", _TEXT)
        alpha = s.get("alpha", 1.0)
        label = s.get("label")

        if kind == "hline":
            ax.axhline(
                s["y"], color=color, linestyle="--",
                linewidth=s.get("width", 1.0), alpha=alpha, label=label,
            )
        elif kind == "vline":
            ax.axvline(s["x"], color=color, alpha=alpha,
                       linewidth=s.get("width", 1.0), label=label)
        elif kind == "line":
            ax.plot([s["x0"], s["x1"]], [s["y0"], s["y1"]], color=color,
                    alpha=alpha, linewidth=s.get("width", 1.0), label=label)
        elif kind == "rect":
            r = mp.Rectangle(
                (s["x0"], s["y0"]), s["x1"] - s["x0"], s["y1"] - s["y0"],
                facecolor=color, edgecolor=color, alpha=alpha, zorder=1,
            )
            ax.add_patch(r)
            if label:
                ax.plot([], [], color=color, alpha=alpha, label=label)
        elif kind == "polyline":
            xs, ys = s["x"], s["y"]
            if len(xs) >= 2:
                ax.plot(xs, ys, color=color, linewidth=s.get("width", 0.8),
                        alpha=alpha, label=label, zorder=3)
        elif kind == "scatter":
            if s["x"]:
                ax.scatter(s["x"], s["y"], color=color, s=s.get("size", 16),
                           alpha=alpha, label=label, zorder=4)
        elif kind == "arrow":
            ax.annotate(
                "",
                xy=(s["x"], s["y"]),
                xytext=(s["x"], s["y"] + s["dy"]),
                arrowprops=dict(arrowstyle="->", color=color, alpha=alpha),
            )
            if label:
                ax.plot([], [], color=color, alpha=alpha, label=label)
        elif kind == "text":
            kwargs = {}
            if s.get("x_axes") is not None:
                # x in axes-fraction, y in data coords -> blended transform so
                # labels peek past the right edge and sit on their line.
                kwargs["transform"] = ax.get_yaxis_transform()
                tx = s["x_axes"]
            else:
                tx = s["x"]
            ax.text(
                tx, s["y"], s["text"], color=color,
                fontsize=s.get("size", 8),
                rotation=s.get("rotation", 0), ha=s.get("ha", "left"),
                va=s.get("va", "bottom"), **kwargs,
            )


def _draw_candles(ax: Any, sub: list[dict[str, Any]]) -> None:
    w = 0.7
    for i, c in enumerate(sub):
        up = c["c"] >= c["o"]
        color = _UP if up else _DOWN
        bot, top = sorted((c["o"], c["c"]))
        ax.add_patch(
            __import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
                (i - w / 2, bot), w, max(top - bot, 1e-6),
                facecolor=color, edgecolor=color,
            )
        )
        ax.plot([i, i], [c["l"], c["h"]], color=color, linewidth=0.8, zorder=0)


def overlay_series(
    source: Any, tf: str, overlays: tuple[str, ...]
) -> dict[str, tuple[list[int], list[float]]]:
    """Reconstruct plotable fact series (EMA, SMA, ATR) across the visible bars.

    Reads each frame's typed facts (schema ``facts_by_ts`` or typed frames) and
    returns ``{fact_name: (x_indices, values)}`` in bar-index space. Only facts
    whose concrete type matches the requested overlay name are collected.
    """
    import numpy as np

    from marketatlas.facts.primitive import ATRFact, EMAFact, SMAFact

    over_type: dict[str, type] = {}
    for name in overlays:
        for cls in (EMAFact, SMAFact, ATRFact):
            if cls.__name__.lower().startswith(name.lower()):
                over_type[name] = cls
                break

    result: dict[str, tuple[list[int], list[float]]] = {n: ([], []) for n in over_type}
    if not over_type:
        return result

    candles = _norm_candles_from_input(source, tf)
    ts_list = [_ts_parse(c["ts"]) for c in candles]

    # schema form: {'ts': iso, 'facts': {name: encoded_fact}}
    if isinstance(source, dict) and "facts_by_ts" in source:
        entries = source["facts_by_ts"]
    else:
        entries = {f.timestamp.isoformat(): f.facts for f in source.frames}

    for ts_iso, facts in entries.items():
        ts = _ts_parse(ts_iso)
        idx = min((i for i, t in enumerate(ts_list) if t >= ts), default=-1)
        if idx < 0:
            continue
        for name, cls in over_type.items():
            for f in facts.values():
                if isinstance(f, cls):
                    result[name][0].append(idx)
                    result[name][1].append(f.value)
                    break
    for name in result:
        if result[name][0]:
            order = np.argsort(result[name][0])
            result[name] = ([result[name][0][i] for i in order],
                            [result[name][1][i] for i in order])
    return result


def _draw_volume(ax: Any, sub: list[dict[str, Any]]) -> None:
    """Volume bars colored by candle direction on their own axis."""
    import matplotlib.patches as mp

    w = 0.7
    for i, c in enumerate(sub):
        up = c["c"] >= c["o"]
        color = _UP if up else _DOWN
        v = c.get("v", 0.0) or 0.0
        ax.add_patch(
            mp.Rectangle((i - w / 2, 0), w, v, facecolor=color,
                         edgecolor=color, alpha=0.8)
        )
    ax.set_ylim(bottom=0)
    ax.yaxis.tick_right()
    ax.tick_params(colors=_MUTED, labelsize=7)
    ax.set_facecolor(_BG)


def render_trade_snapshot(
    source: Any,
    poi: datetime,
    out_path: str | Path,
    *,
    entry: float | None = None,
    stop: float | None = None,
    target: float | None = None,
    rr_ratio: float | None = None,
    submit_ts: datetime | None = None,
    max_hold_days: int = 10,
    direction: str = "",
    result: str | None = None,
    pnl: float | None = None,
    note: str = "",
    timeframe: str | None = None,
    pre: int = _DEFAULT_PRE,
    post: int = _DEFAULT_POST,
    width: float = 11.0,
    height: float = 6.0,
    show_volume: bool = True,
    overlays: tuple[str, ...] = (),
) -> Path:
    """Render a candle PNG for one POI with fact annotations.

    ``source`` is either a typed ``AnalysisOutput`` or the per-instrument dict
    produced by ``frames.jsoncodec.encode_analysis_output``.

    ``overlays`` lists fact-series to plot on the price axis (e.g. ``("ema",)``),
    reconstructed from the per-frame facts across the visible window. Volume is
    drawn on its own subplot below the price axis unless ``show_volume`` is False.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tf = timeframe or _timeframe_from_input(source)
    candles = _norm_candles_from_input(source, tf)
    sub, start_index, x = _window(candles, poi, pre, post)
    if not sub:
        raise ValueError(f"no candles around {poi}")

    if show_volume:
        fig, (ax, ax_vol) = plt.subplots(
            2, 1, figsize=(width, height), facecolor=_BG,
            sharex=True, gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05},
        )
    else:
        fig, ax = plt.subplots(figsize=(width, height), facecolor=_BG)
        ax_vol = None
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    _draw_candles(ax, sub)

    shapes: list[dict[str, Any]] = []
    facts = _facts_at(source, poi)
    if facts:
        lows = [c["l"] for c in sub]
        highs = [c["h"] for c in sub]
        price_range = (min(lows), max(highs)) if lows else (0.0, 1.0)
        shapes += _overlay_sr(facts, price_range)
        shapes += _overlay_pullbacks(facts, start_index, start_index + len(sub))

    if entry is not None and stop is not None and target is not None:
        submit_dt = submit_ts if submit_ts is not None else poi
        x_submit = next(
            (i for i, c in enumerate(sub) if _ts_parse(c["ts"]) >= submit_dt),
            len(sub) - 1,
        )
        shapes += _trade_box_shapes(
            sub, x_submit, x_submit + max_hold_days, entry, stop, target, rr_ratio
        )
    elif entry is not None:
        shapes.append(
            {"kind": "hline", "y": entry, "color": _ENTRY, "width": 1.4,
             "alpha": 0.95}
        )
        shapes.append({"kind": "vline", "x": x, "color": _ENTRY, "alpha": 0.4})
        shapes.append(
            {"kind": "text", "x_axes": 1.005, "y": entry,
             "text": f"Entry {entry:.4f}", "color": _ENTRY, "size": 7,
             "ha": "left", "va": "center"}
        )

    draw_shapes(ax, shapes)

    if overlays:
        series = overlay_series(source, tf, overlays)
        for name, (xs, ys) in series.items():
            ax.plot(xs, ys, color=_ENTRY, linewidth=1.2, alpha=0.9,
                    label=name.upper())

    if ax_vol is not None:
        _draw_volume(ax_vol, sub)

    if note:
        ax.text(
            0.01, 0.98, note, color=_MUTED, fontsize=8,
            transform=ax.transAxes, ha="left", va="top",
        )

    title_parts = [_symbol_from_input(source), tf.upper()]
    if direction:
        title_parts.append(direction.upper())
    if result:
        title_parts.append(f"result={result}")
    if pnl is not None:
        title_parts.append(f"pnl={pnl:+.2f}")
    ax.set_title("  ".join(title_parts), color=_TEXT)

    dts = [_ts_parse(c["ts"]) for c in sub]
    ticks = list(range(0, len(sub), max(1, len(sub) // 12)))
    tick_ax = ax_vol if ax_vol is not None else ax
    tick_ax.set_xticks(ticks)
    tick_ax.set_xticklabels(
        [dts[i].strftime("%Y-%m-%d") for i in ticks],
        rotation=45, ha="right", color=_MUTED, fontsize=8,
    )
    tick_ax.tick_params(colors=_MUTED, labelsize=8)
    if ax_vol is not None:
        ax.tick_params(labelbottom=False, colors=_MUTED, labelsize=7)
    for sp in ax.spines.values():
        sp.set_color(_GRID)
    if ax_vol is not None:
        for sp in ax_vol.spines.values():
            sp.set_color(_GRID)
        ax_vol.set_ylim(0, max((c.get("v", 0.0) or 0.0) for c in sub) * 1.1 or 1.0)
        ax_vol.grid(alpha=0.15, color=_GRID, axis="y")
    ax.grid(alpha=0.15, color=_GRID)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out


def locate_pois(struct: Any, *, kinds: str | set[str] | None = None) -> list[dict[str, Any]]:
    """Locate points of interest across a portfolio structured doc.

    Returns POI records each tagged with a ``kind``:
      ``trade``     a traded outcome (entry/stop/target/result/pnl)
      ``rejection`` a signal-rejected cursor (reason in ``reason``)
      ``pattern``   a detected pattern fact at its cursor
      ``sr``        a support/resistance level
      ``swing``     a swing-structure geometry

    ``kinds`` filters to a subset (default: all). Accepts either a typed
    ``PortfolioOutput`` or the JSON form from ``frames.jsoncodec.encode_portfolio``.
    """
    from marketatlas.frames.jsoncodec import encode_analysis_output

    if isinstance(struct, dict) and "per_instrument" in struct:
        per: dict[str, Any] = struct["per_instrument"]
    else:
        per = {
            canonical: encode_analysis_output(out)
            for canonical, out in struct.outputs.items()
        }

    if kinds:
        want: set[str] = kinds if isinstance(kinds, set) else set([kinds])
    else:
        want = {"trade", "rejection", "pattern", "sr", "swing"}

    pois: list[dict[str, Any]] = []
    for canonical, pin in per.items():
        for tr in pin.get("trades", ()):
            if "trade" in want:
                pois.append(
                    {
                        "kind": "trade",
                        "symbol": canonical,
                        "tf": pin["timeframe"],
                        "ts": tr["entry_ts"],
                        "submit_ts": tr.get("submit_ts", tr["entry_ts"]),
                        "entry": tr["entry"],
                        "stop": tr["stop"],
                        "target": tr["target"],
                        "direction": tr["direction"],
                        "result": tr.get("result"),
                        "pnl": tr.get("pnl"),
                        "rr_ratio": tr.get("rr_ratio"),
                    }
                )
        for ts, rejs in (pin.get("rejections_by_ts") or {}).items():
            if "rejection" in want:
                for r in rejs:
                    pois.append(
                        {
                            "kind": "rejection",
                            "symbol": canonical,
                            "tf": pin["timeframe"],
                            "ts": ts,
                            "reason": r["text"],
                        }
                    )
        for ts, pats in (pin.get("patterns_by_ts") or {}).items():
            if "pattern" in want:
                for name, enc in pats.items():
                    pois.append(
                        {
                            "kind": "pattern",
                            "symbol": canonical,
                            "tf": pin["timeframe"],
                            "ts": ts,
                            "pattern": name,
                        }
                    )
    return pois


def snapshot_basename(poi: dict[str, Any]) -> str:
    """Descriptive filename for a POI snapshot, e.g. ``GBPUSD_2021-02-19_bull_win_pnl97.02.png``."""
    sym = poi["symbol"]
    date = _ts_parse(poi["ts"]).strftime("%Y-%m-%d")
    kind = poi.get("kind", "trade")
    parts = [sym, date, kind]
    if kind == "trade":
        direction = poi.get("direction", "")
        result = poi.get("result")
        pnl = poi.get("pnl")
        if direction:
            parts.append(direction)
        if result:
            parts.append(result)
        if pnl is not None:
            parts.append(f"pnl{pnl:+.1f}")
    elif kind == "rejection":
        parts.append(poi.get("reason", "rej").lower().replace(" ", "_"))
    elif kind == "pattern":
        parts.append(poi.get("pattern", "pattern"))
    return "_".join(p for p in parts if p) + ".png"


def _per_instrument(struct: Any) -> dict[str, Any]:
    """Normalize a portfolio doc (typed or schema) to ``{canonical: dict}``."""
    if isinstance(struct, dict) and "per_instrument" in struct:
        return struct["per_instrument"]
    from marketatlas.frames.jsoncodec import encode_analysis_output

    return {
        canonical: encode_analysis_output(out)
        for canonical, out in struct.outputs.items()
    }


def render_poi_snapshot(
    struct: Any,
    poi: dict[str, Any],
    out_dir: str | Path,
    *,
    timeframe: str | None = None,
    pre: int = _DEFAULT_PRE,
    post: int = _DEFAULT_POST,
    show_volume: bool = True,
    overlays: tuple[str, ...] = (),
    per: dict[str, Any] | None = None,
) -> Path:
    """Render one POI (from :func:`locate_pois`) into ``out_dir`` with a
    descriptive, triage-friendly filename."""
    pin = (per if per is not None else _per_instrument(struct))[poi["symbol"]]
    if poi.get("kind") == "rejection":
        note = poi.get("reason", "")
    elif poi.get("kind") == "pattern":
        note = poi["pattern"]
    else:
        note = ""
    return render_trade_snapshot(
        pin,
        _ts_parse(poi["ts"]),
        Path(out_dir) / snapshot_basename(poi),
        entry=poi.get("entry"),
        stop=poi.get("stop"),
        target=poi.get("target"),
        rr_ratio=poi.get("rr_ratio"),
        submit_ts=_ts_parse(poi.get("submit_ts", poi["ts"])),
        max_hold_days=pin.get("max_hold_days", 10),
        direction=poi.get("direction", ""),
        result=poi.get("result"),
        pnl=poi.get("pnl"),
        note=note,
        timeframe=timeframe,
        pre=pre,
        post=post,
        show_volume=show_volume,
        overlays=overlays,
    )


def render_poi_snapshots(
    struct: Any,
    out_dir: str | Path,
    *,
    timeframe: str | None = None,
    pre: int = _DEFAULT_PRE,
    post: int = _DEFAULT_POST,
    show_volume: bool = True,
    overlays: tuple[str, ...] = (),
    kinds: str | set[str] | None = None,
) -> list[Path]:
    """Render a PNG per POI across the whole (typed or JSON) output."""
    per = _per_instrument(struct)
    return [
        render_poi_snapshot(
            struct, poi, out_dir, timeframe=timeframe, pre=pre, post=post,
            show_volume=show_volume, overlays=overlays, per=per,
        )
        for poi in locate_pois(struct, kinds=kinds)
    ]
