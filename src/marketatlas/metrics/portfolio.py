"""Portfolio / equity performance metrics (backlog 100).

Consumes the enriched trade dicts (098) plus the time-indexed equity curve the
tradebook emits (``[{t, balance}]``) and reduces them to the portfolio-level
dashboard: compounding returns, risk-adjusted ratios, drawdown episodes and
exposure. Complements ``trades.trade_metrics`` (099) which judges individual
trades in R units — this module asks whether the book compounded and survived.

Pure functions over plain dicts — JSON-serializable, unit-testable, no I/O.
The rest of the metrics layer (101 costs, 102 robustness/report) builds on this
module and the ``stats``/``drawdown`` helpers.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from marketatlas.metrics import drawdown, stats

Trade = Mapping[str, Any]
CurvePoint = Mapping[str, Any]

# Annualization basis: bars per (trading) year derived from a timeframe token.
# 252 trading days/year, 24-hour forex-style sessions. Matches both the DSL
# casing ("D1", "H4", "M15") and the ``Timeframe`` value casing ("1d", "4h").
_BARS_PER_YEAR = {
    "1w": 52,
    "W1": 52,
    "1d": 252,
    "D1": 252,
    "4h": 252 * 6,
    "H4": 252 * 6,
    "1h": 252 * 24,
    "H1": 252 * 24,
    "30m": 252 * 48,
    "M30": 252 * 48,
    "15m": 252 * 96,
    "M15": 252 * 96,
    "5m": 252 * 288,
    "M5": 252 * 288,
    "1m": 252 * 1440,
    "M1": 252 * 1440,
}

_FILLED = ("win", "loss", "breakeven")


def bars_per_year(timeframe: str | None) -> int | None:
    """Bars per trading year for a timeframe token; ``None`` when unknown."""
    if timeframe is None:
        return None
    return _BARS_PER_YEAR.get(timeframe)


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(float(value)) else None
    return None


def _ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _naive(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_curve(
    equity_curve: Sequence[CurvePoint] | None,
) -> list[tuple[datetime, float]]:
    """``[{t, balance}]`` → ordered ``(datetime, float)`` pairs, naive-normalized."""
    out: list[tuple[datetime, float]] = []
    for point in equity_curve or ():
        ts = _ts(point.get("t"))
        bal = _float(point.get("balance"))
        if ts is not None and bal is not None:
            out.append((_naive(ts), bal))
    out.sort(key=lambda p: p[0])
    return out


def _resolve_initial(
    trades: Sequence[Trade],
    curve_balance_final: float | None,
    initial_balance: float | None,
) -> tuple[float, str]:
    """Resolve the running balance at the start of the series.

    Preference: explicit ``initial_balance`` → back-out of the final curve
    balance minus realized P&L (every fully-closed trade lands on the curve, so
    ``initial = final - sum(pnl)``) → fixed index ``100.0`` when neither curve
    nor explicit balance exists.
    """
    if initial_balance is not None:
        return float(initial_balance), "explicit"
    pnl_sum = 0.0
    for t in trades:
        pnl = _float(t.get("pnl"))
        if pnl is not None:
            pnl_sum += pnl
    if curve_balance_final is not None:
        return float(curve_balance_final) - pnl_sum, "derived_final_minus_pnl"
    return 100.0, "default_index"


def _elapsed_years(
    curve_points: list[tuple[datetime, float]], trades: Sequence[Trade]
) -> float | None:
    """Calendar span in years across the series and the trade timeline."""
    stamps = [ts for ts, _bal in curve_points] if len(curve_points) >= 2 else []
    if not stamps:
        for key in ("submit_ts", "entry_ts", "exit_ts"):
            for t in trades:
                ts = _ts(t.get(key))
                if ts is not None:
                    stamps.append(_naive(ts))
    if len(stamps) < 2:
        return None
    days = max(0.0, (max(stamps) - min(stamps)).total_seconds() / 86400.0)
    return days / 365.25


def _resolve_periods_per_year(
    years: float | None, periods: int, timeframe: str | None, explicit: float | None
) -> tuple[float, str]:
    if explicit is not None:
        return float(explicit), "explicit"
    bpy = bars_per_year(timeframe) if timeframe else None
    if bpy is not None:
        return float(bpy), "timeframe_bars_per_year"
    if years and years > 0 and periods > 0:
        return max(1.0, periods / years), "observed_closes_per_year"
    return 252.0, "default_252"


def _bucketized_returns(
    curve_points: list[tuple[datetime, float]], fmt: str
) -> list[dict[str, object]]:
    """Compounded returns per calendar bucket (``%Y-%m`` / ``%Y``).

    The last balance seen within each bucket is taken as the bucket's end;
    empty buckets are skipped (no data → no fabricated return). The first
    bucket compares against the series start (the initial point prepended to
    the curve), later buckets against the previous bucket's end.
    """
    last_by_bucket: dict[str, float] = {}
    for ts, bal in curve_points:
        last_by_bucket[ts.strftime(fmt)] = bal
    keys = sorted(last_by_bucket)
    if not keys:
        return []
    start_balance = curve_points[0][1]
    out: list[dict[str, object]] = []
    prev_last: float | None = None
    for key in keys:
        cur = last_by_bucket[key]
        base = prev_last if prev_last is not None else start_balance
        r = (cur / base - 1.0) if base > 0 else None
        out.append(
            {
                "period": key,
                "return": r,
                "return_pct": r * 100 if r is not None else None,
                "balance": cur,
            }
        )
        prev_last = cur
    return out


def _streaks(trades: Sequence[Trade]) -> dict[str, object]:
    streaking: dict[str, int] = {"wins": 0, "losses": 0}
    max_wins = 0
    max_losses = 0
    for t in trades:
        result = str(t.get("result") or "")
        if result == "win":
            streaking["wins"] += 1
            streaking["losses"] = 0
            max_wins = max(max_wins, streaking["wins"])
        elif result == "loss":
            streaking["losses"] += 1
            streaking["wins"] = 0
            max_losses = max(max_losses, streaking["losses"])
        else:
            streaking["wins"] = 0
            streaking["losses"] = 0
    return {
        "max_consecutive_wins": max_wins,
        "max_consecutive_losses": max_losses,
        "note": "breakeven/cancelled trades break both streaks",
    }


def _filled_trades(trades: Sequence[Trade]) -> list[Trade]:
    return [
        t
        for t in trades
        if t.get("result") in _FILLED
        and _ts(t.get("entry_ts")) is not None
        and _ts(t.get("exit_ts")) is not None
    ]


def _num(obj: Mapping[str, object], key: str) -> float | None:
    v = obj.get(key)
    if isinstance(v, bool):
        return None
    return float(v) if isinstance(v, int | float) else None


def _dd_episodes(dd: Mapping[str, object]) -> list[dict[str, object]]:
    ep = dd.get("episodes")
    if isinstance(ep, list):
        return [e for e in ep if isinstance(e, dict)]
    return []


def _exposure(
    trades: Sequence[Trade], initial: float
) -> dict[str, object]:
    """Simultaneous-open-position exposure over filled trades' [entry, exit).

    Events sweep: entries add risk, exits remove it. Max simultaneous count,
    max simultaneous risk, time-weighted average exposure, and (per the
    lighter "correlation of simultaneous positions" reduction) the average
    number of instruments open and the share of span with multiple instruments.
    """
    filled = _filled_trades(trades)
    events: list[tuple[datetime, float, float, str]] = []  # (ts, d_risk, d_count, instrument)
    for t in filled:
        entry = _ts(t.get("entry_ts"))
        exit_ts = _ts(t.get("exit_ts"))
        risk = _float(t.get("risk_amount")) or 0.0
        instrument = str(t.get("instrument") or "-")
        if entry is None or exit_ts is None:
            continue
        if entry > exit_ts:
            entry, exit_ts = exit_ts, entry
        events.append((_naive(entry), +risk, +1.0, instrument))
        events.append((_naive(exit_ts), -risk, -1.0, instrument))
    events.sort(key=lambda e: e[0])
    if not events:
        return {
            "filled_for_exposure": 0,
            "max_simultaneous_trades": 0,
            "max_simultaneous_risk": 0.0,
            "max_simultaneous_risk_pct": 0.0,
            "avg_exposure_pct": 0.0,
            "avg_simultaneous_instruments": 0.0,
            "multi_instrument_share_pct": 0.0,
            "by_instrument": {},
        }

    open_risk = 0.0
    open_count = 0
    open_instruments: set[str] = set()
    max_risk = 0.0
    max_count = 0
    max_instruments = 0
    risk_area = 0.0
    inst_area = 0.0
    multi_area = 0.0
    prev_ts = events[0][0]
    span = (events[-1][0] - prev_ts).total_seconds()
    for ts, d_risk, d_count, instrument in events:
        elapsed = max(0.0, (ts - prev_ts).total_seconds())
        risk_area += open_risk * elapsed
        inst_area += len(open_instruments) * elapsed
        if len(open_instruments) > 1:
            multi_area += elapsed
        open_risk += d_risk
        open_count += int(d_count)
        if d_count > 0:
            open_instruments.add(instrument)
        else:
            open_instruments.discard(instrument)
        max_risk = max(max_risk, open_risk)
        max_count = max(max_count, open_count)
        max_instruments = max(max_instruments, len(open_instruments))
        prev_ts = ts

    per_instrument: dict[str, dict[str, object]] = {}
    by_inst: dict[str, list[Trade]] = defaultdict(list)
    for t in filled:
        by_inst[str(t.get("instrument") or "-")].append(t)
    for instrument, group in sorted(by_inst.items()):
        wins = sum(1 for t in group if t.get("result") == "win")
        decided = sum(1 for t in group if t.get("result") in _FILLED)
        risks = [r for t in group if (r := _float(t.get("risk_amount"))) is not None]
        per_instrument[instrument] = {
            "trades": len(group),
            "wins": wins,
            "losses": sum(1 for t in group if t.get("result") == "loss"),
            "win_rate": wins / decided if decided else 0.0,
            "total_risk": sum(risks),
            "mean_risk_pct": (
                sum(risks) / len(risks) / initial * 100 if risks and initial else 0.0
            ),
        }

    risk_pcts = [r for t in trades if (r := _float(t.get("risk_amount"))) is not None and r > 0]
    per_period = (
        {
            "count": len(risk_pcts),
            "mean_pct": sum(risk_pcts) / len(risk_pcts) / initial * 100 if initial else 0.0,
            "max_pct": max(risk_pcts) / initial * 100 if initial else 0.0,
            "note": "risk_amount / initial_balance, 1R symmetrical basis",
        }
        if risk_pcts
        else {"count": 0, "mean_pct": 0.0, "max_pct": 0.0, "note": "no trades with risk set"}
    )

    share = (multi_area / span * 100) if span > 0 else 0.0
    return {
        "risk_per_trade_pct": per_period,
        "filled_for_exposure": len(filled),
        "max_simultaneous_trades": max_count,
        "max_simultaneous_risk": max_risk,
        "max_simultaneous_risk_pct": (max_risk / initial * 100) if initial else 0.0,
        "avg_exposure_pct": (risk_area / span / initial * 100) if span and initial else 0.0,
        "avg_simultaneous_instruments": (inst_area / span) if span else 0.0,
        "multi_instrument_share_pct": share,
        "by_instrument": per_instrument,
        "note": "avg_exposure_pct is time-weighted open risk / initial_balance",
    }


def portfolio_metrics(
    trades: Sequence[Trade],
    equity_curve: Sequence[CurvePoint] | None = None,
    initial_balance: float | None = None,
    timeframe: str | None = None,
    periods_per_year: float | None = None,
    risk_free: float = 0.0,
    target: float = 0.0,
) -> dict[str, object]:
    """Reduce (enriched trades, equity curve) to the portfolio dashboard (100).

    Parameters decide the annualization basis (documented convention):
      * ``initial_balance`` — explicit, else back-derived from
        ``final_curve_balance - sum(pnl)``, else a fixed 100.0 index.
      * ``timeframe`` token / ``periods_per_year`` — bars-per-year factor for
        vol/Sharpe/Sortino annualization; default ``None`` falls back to the
        observed closes-per-year, then 252.
      * ``risk_free`` (annual, default 0) — Sharpe excess-return reference,
        chosen so backtests compare on pure strategy edge.
      * ``target`` (annual, default 0) — Sortino minimum-acceptable return.

    Pure and JSON-serializable; the schema is documented in
    ``backlog/100-portfolio-performance-metrics.md``.
    """
    resolved_initial = initial_balance or _resolved_initial(trades, equity_curve, initial_balance)
    rendered: dict[str, object] = {
        "summary": _summary(trades, equity_curve, initial_balance),
        "returns": _returns(trades, equity_curve, initial_balance, timeframe, periods_per_year),
        "drawdown": drawdown.drawdown_analysis(_full_curve(trades, equity_curve, initial_balance)),
        "risk": _risk(
            trades, equity_curve, initial_balance, timeframe, periods_per_year, risk_free, target
        ),
        "equity_behavior": _equity_behavior(trades, equity_curve, initial_balance),
        "exposure": _exposure(trades, resolved_initial),
    }
    return rendered


def _resolved_initial(
    trades: Sequence[Trade],
    equity_curve: Sequence[CurvePoint] | None,
    initial_balance: float | None,
) -> float:
    points = parse_curve(equity_curve)
    final = points[-1][1] if points else None
    initial, _basis = _resolve_initial(trades, final, initial_balance)
    return initial


def _full_curve(
    trades: Sequence[Trade],
    equity_curve: Sequence[CurvePoint] | None,
    initial_balance: float | None,
) -> list[tuple[datetime, float]]:
    """Resolved curve with the initial balance prepended as the start point."""
    points = parse_curve(equity_curve)
    initial, basis = _resolve_initial(trades, points[-1][1] if points else None, initial_balance)
    if not points:
        # Reconstruct per-trade close series from realized P&L (cancel: 0).
        acc = initial
        close_series: list[tuple[datetime, float]] = []
        for t in trades:
            exit_ts = _ts(t.get("exit_ts"))
            pnl = _float(t.get("pnl"))
            if exit_ts is None:
                continue
            acc += pnl or 0.0
            close_series.append((_naive(exit_ts), acc))
        close_series.sort(key=lambda p: p[0])
        points = close_series
    start_ts = points[0][0] if points else datetime(1970, 1, 1)
    return [(start_ts, initial), *points]


def _summary(
    trades: Sequence[Trade],
    equity_curve: Sequence[CurvePoint] | None,
    initial_balance: float | None,
) -> dict[str, object]:
    points = parse_curve(equity_curve)
    initial, _basis = _resolve_initial(trades, points[-1][1] if points else None, initial_balance)
    pnl_sum = sum(_float(t.get("pnl")) or 0.0 for t in trades)
    final = points[-1][1] if points else initial + pnl_sum
    total_return = (final / initial - 1) if initial > 0 else None
    return {
        "initial_balance": initial,
        "final_balance": final,
        "total_pnl": final - initial,
        "total_return_pct": total_return * 100 if total_return is not None else None,
        "note": "total_return_pct = final/initial - 1 (compounded over the series)",
    }


def _returns(
    trades: Sequence[Trade],
    equity_curve: Sequence[CurvePoint] | None,
    initial_balance: float | None,
    timeframe: str | None,
    periods_per_year: float | None,
) -> dict[str, object]:
    points = parse_curve(equity_curve)
    initial, _basis = _resolve_initial(trades, points[-1][1] if points else None, initial_balance)
    full = _full_curve(trades, equity_curve, initial_balance)
    periods = max(0, len(full) - 1)
    years = _elapsed_years(full, trades)
    ppr, basis = _resolve_periods_per_year(years, periods, timeframe, periods_per_year)
    observed = (max(1.0, periods / years) if years and periods else None) if years else periods
    monthly = _bucketized_returns(full, "%Y-%m")
    annual = _bucketized_returns(full, "%Y")
    monthly_returns = [r for m in monthly if (r := _num(m, "return")) is not None]
    simple_sum = sum(monthly_returns) if monthly_returns else None
    compounded = stats.product_returns(monthly_returns) if monthly_returns else None
    final = full[-1][1]
    cagr = stats.cagr(final, initial, years) if years else None
    if cagr is None and periods:
        cagr = stats.annualized_geometric_return(stats.log_returns([b for _t, b in full]), ppr)
    monthly_pcts = [p for m in monthly if (p := _num(m, "return_pct")) is not None]
    best = max(monthly_pcts) if monthly_pcts else None
    worst = min(monthly_pcts) if monthly_pcts else None
    return {
        "years": years,
        "periods": periods,
        "periods_per_year": ppr,
        "observed_periods_per_year": observed,
        "annualization_basis": basis,
        "total_return_pct": ((final / initial - 1) * 100) if initial > 0 else None,
        "simple_sum_return_pct": simple_sum * 100 if simple_sum is not None else None,
        "compounded_return_pct": compounded * 100 if compounded is not None else None,
        "compounded_vs_simple_drag_pct": (
            (simple_sum - compounded) * 100
            if simple_sum is not None and compounded is not None
            else None
        ),
        "compounding_signal": (
            "compounded < simple (volatility drag)"
            if simple_sum is not None and compounded is not None and compounded < simple_sum
            else "compounded >= simple"
        ),
        "cagr_pct": cagr * 100 if cagr is not None else None,
        "monthly": monthly,
        "annual": annual,
        "best_month_pct": best,
        "worst_month_pct": worst,
    }


def _risk(
    trades: Sequence[Trade],
    equity_curve: Sequence[CurvePoint] | None,
    initial_balance: float | None,
    timeframe: str | None,
    periods_per_year: float | None,
    risk_free: float,
    target: float,
) -> dict[str, object]:
    full = _full_curve(trades, equity_curve, initial_balance)
    balances = [b for _t, b in full]
    lr = stats.log_returns(balances)
    years = _elapsed_years(full, trades)
    ppr, basis = _resolve_periods_per_year(
        years, max(0, len(full) - 1), timeframe, periods_per_year
    )
    vol = stats.volatility(lr, ppr)
    sh = stats.sharpe(lr, ppr, risk_free)
    so = stats.sortino(lr, ppr, target)
    dd = drawdown.drawdown_analysis(full)
    max_dd_pct = _num(dd, "max_drawdown_pct") or 0.0
    years2 = years or (len(lr) / ppr if ppr else None)
    cagr = stats.cagr(full[-1][1], full[0][1], years2) if years2 else None
    calmar = (cagr / (max_dd_pct / 100.0)) if cagr is not None and max_dd_pct > 0 else None
    episodes = _dd_episodes(dd)
    return {
        "volatility_pct_annual": vol * 100 if vol is not None else None,
        "sharpe": sh,
        "sortino": so,
        "calmar": calmar,
        "risk_free": risk_free,
        "target": target,
        "risk_of_ruin": drawdown.drawdown_distribution(episodes),
        "risk_of_ruin_note": (
            "heuristic: empirical share of recorded drawdown episodes deeper "
            "than each threshold; Monte-Carlo variant in backlog 102"
        ),
        "annualization_basis": basis,
        "periods_per_year": ppr,
    }


def _equity_behavior(
    trades: Sequence[Trade],
    equity_curve: Sequence[CurvePoint] | None,
    initial_balance: float | None,
) -> dict[str, object]:
    full = _full_curve(trades, equity_curve, initial_balance)
    initial = _resolved_initial(trades, equity_curve, initial_balance)
    dd = drawdown.drawdown_analysis(full)
    series = [
        {
            "t": ts.isoformat(),
            "balance": bal,
            "index": (bal / initial * 100) if initial else None,
        }
        for ts, bal in full
    ]
    return {
        "max_consecutive_wins": _streaks(trades)["max_consecutive_wins"],
        "max_consecutive_losses": _streaks(trades)["max_consecutive_losses"],
        "streak_note": _streaks(trades)["note"],
        "largest_peak_to_trough_loss": dd["max_drawdown_abs"],
        "equity_curve": series,
    }
