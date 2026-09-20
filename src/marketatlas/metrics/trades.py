"""Trade-level statistics in R units (backlog 099).

Consumes the enriched trade dicts emitted by ``frames.jsoncodec`` (098: exit
reason, MFE/MAE in R, realized ``r_multiple``, risk amount, timestamps) and
reduces them to the trade-level metrics dashboard. Pure functions over plain
dicts — JSON-serializable, unit-testable, no I/O.

R is the canonical unit throughout: every outcome is ``pnl / risk_amount``.
Cancelled/breakeven trades realize R = 0 and are (deliberately) included in
the closed-trade denominator of win rate and expectancy, with the decided-trade
variants reported alongside so both counting conventions are visible.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from marketatlas.metrics import stats

# Results recorded by the tradebook (``TradeOutcome.result``). Count keys use
# the plural ``TradeBook.summary`` convention.
ALL_RESULTS = ("win", "loss", "breakeven", "cancelled")
FILLED_RESULTS = ("win", "loss", "breakeven")
DECIDED_RESULTS = ("win", "loss")
_RESULT_KEY = {"win": "wins", "loss": "losses", "breakeven": "breakevens", "cancelled": "cancelled"}

# Exit reasons (``ExitReason`` string values) surfaced for the breakdown.
KNOWN_REASONS = ("stop", "target", "timeout", "cancel", "reversal")

# MFE/exceeded-levels milestones used across reach + MFE analysis (R units).
R_LEVELS = (1, 2, 3, 4)

Trade = Mapping[str, Any]

_DAYS_PER_MONTH = 365.25 / 12.0


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        f = float(value)
        return f if math.isfinite(f) else None
    return None


def _ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _hours_between(start: str | None, end: str | None) -> float | None:
    a, b = _ts(start), _ts(end)
    if a is None or b is None:
        return None
    delta = (b - a).total_seconds() / 3600.0
    return max(0.0, delta)


def _counts(trades: Sequence[Trade]) -> dict[str, int]:
    counts: dict[str, int] = {key: 0 for key in _RESULT_KEY.values()}
    for trade in trades:
        result = trade.get("result")
        key = _RESULT_KEY.get(result) if isinstance(result, str) else None
        if key is not None:
            counts[key] += 1
    counts["total"] = len(trades)
    counts["filled"] = counts["wins"] + counts["losses"] + counts["breakevens"]
    counts["decided"] = counts["wins"] + counts["losses"]
    return counts


def _r(trade: Trade) -> float | None:
    return _float(trade.get("r_multiple"))


def _win_rate(counts: dict[str, int]) -> dict[str, object]:
    total = counts["total"]
    decided = counts["decided"]
    wins = counts["wins"]
    return {
        "decided": wins / decided if decided else 0.0,
        "all": wins / total if total else 0.0,
        # Counting convention flag: ``decided`` excludes breakevens/cancels
        # (R == 0) from the denominator; ``all`` counts them as non-wins.
        "decided_count": decided,
        "all_count": total,
        "denominator": "decided",
        "note": (
            "win_rate.decided = wins/(wins+losses); win_rate.all includes "
            "breakevens and cancels (R=0) as non-wins."
        ),
    }


def _r_averages(trades: Sequence[Trade]) -> dict[str, object]:
    wins = [r for t in trades if t.get("result") == "win" and (r := _r(t)) is not None]
    losses = [abs(r) for t in trades if t.get("result") == "loss" and (r := _r(t)) is not None]
    win_mean = stats.mean(wins)
    loss_mean = stats.mean(losses)
    return {
        "win_r_mean": win_mean,
        "win_r_median": stats.median(wins),
        "loss_r_mean": loss_mean,  # magnitude (positive) for payoff comparability
        "loss_r_median": stats.median(losses),
        "payoff_ratio_r": ((win_mean / loss_mean) if win_mean is not None and loss_mean else None),
    }


def _expectancy(trades: Sequence[Trade]) -> dict[str, object]:
    all_r = [r for t in trades if (r := _r(t)) is not None]
    decided_r = [
        r for t in trades if t.get("result") in DECIDED_RESULTS and (r := _r(t)) is not None
    ]
    return {
        "expectancy_r": stats.mean(all_r),
        "expectancy_decided_r": stats.mean(decided_r),
        "note": (
            "expectancy_r is the mean realized R over ALL closed trades "
            "(cancelled/breakeven with R=0 count); expectancy_decided_r is "
            "mean realized R over wins+losses only."
        ),
        "closed_with_r_count": len(all_r),
        "decided_with_r_count": len(decided_r),
    }


def _profit_factor(trades: Sequence[Trade]) -> dict[str, object]:
    gross_profit = 0.0
    gross_loss = 0.0
    for t in trades:
        r = _r(t)
        if r is None or r == 0.0:
            continue
        if r > 0:
            gross_profit += r
        else:
            gross_loss += abs(r)
    pf = gross_profit / gross_loss if gross_loss > 0 else None
    return {
        "profit_factor_r": pf,
        "gross_profit_r": gross_profit,
        "gross_loss_r": gross_loss,
    }


def _r_distribution(trades: Sequence[Trade], decided_count: int) -> dict[str, object]:
    decided = [r for t in trades if t.get("result") in DECIDED_RESULTS and (r := _r(t)) is not None]
    skew, kurt = None, None
    if decided:
        skew = stats.skewness(decided)
        kurt = stats.kurtosis(decided)
    wins = [r for r in decided if r > 0]
    losses = [r for r in decided if r < 0]
    return {
        "count": len(decided),
        "skipped_zero_risk": decided_count - len(decided),
        "min": stats.percentile(decided, 0.0),
        "max": stats.percentile(decided, 1.0),
        "percentiles": stats.percentiles(
            decided,
            {
                "p1": 0.01,
                "p5": 0.05,
                "p25": 0.25,
                "p50": 0.5,
                "p75": 0.75,
                "p95": 0.95,
                "p99": 0.99,
            },
        ),
        "skew": skew,
        "kurtosis": kurt,
        "histogram": stats.histogram(decided, n_bins=10),
        "max_win_r": max(wins) if wins else None,
        "max_loss_r": min(losses) if losses else None,
        "max_loss_magnitude_r": max(abs(v) for v in losses) if losses else None,
    }


def _duration(trades: Sequence[Trade]) -> dict[str, object]:
    per_trade: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        hours = _hours_between(t.get("entry_ts"), t.get("exit_ts"))
        if hours is None:
            continue
        per_trade[t.get("result", "unknown")].append(hours)
    all_hours = [h for group in per_trade.values() for h in group]
    by_outcome: dict[str, dict[str, object]] = {}
    for result in sorted(per_trade):
        group = per_trade[result]
        by_outcome[result] = {
            "count": len(group),
            "mean_hours": stats.mean(group),
            "median_hours": stats.median(group),
        }
    return {
        "mean_hours": stats.mean(all_hours),
        "median_hours": stats.median(all_hours),
        "by_outcome": by_outcome,
    }


def _mfe_exit_quality(trades: Sequence[Trade]) -> dict[str, object]:
    """ "Exits too early?" signal: winners that MFE'd past an R level but exited below it."""
    winners: list[tuple[Trade, float, float]] = []
    for t in trades:
        r = _r(t)
        mfe = _float(t.get("mfe_r"))
        if t.get("result") == "win" and r is not None and mfe is not None:
            winners.append((t, mfe, r))
    filled = sum(1 for t in trades if t.get("result") in FILLED_RESULTS)
    reached_but_exited_less: dict[str, dict[str, object]] = {}
    for level in R_LEVELS:
        matched = [w for w in winners if w[1] >= level and w[2] < level]
        reached_but_exited_less[str(level) + "r"] = {
            "count": len(matched),
            "pct_of_winners": len(matched) / len(winners) if winners else 0.0,
            "pct_of_filled": len(matched) / filled if filled else 0.0,
        }
    left_on_table = [float(mfe) - float(r) for _t, mfe, r in winners]
    return {
        "winners_with_mfe": len(winners),
        "mfe_exceeded_but_exited_less": reached_but_exited_less,
        "exit_below_mfe_mean_r": stats.mean(left_on_table),
        "exit_below_mfe_median_r": stats.median(left_on_table),
    }


def _mae_distribution(trades: Sequence[Trade]) -> dict[str, object]:
    """MAE (R) over filled trades — stop-distance sanity check."""
    all_mae = [
        v
        for t in trades
        if t.get("result") in FILLED_RESULTS and (v := _float(t.get("mae_r"))) is not None
    ]
    loss_mae = [
        v for t in trades if t.get("result") == "loss" and (v := _float(t.get("mae_r"))) is not None
    ]
    return {
        "over_filled_count": len(all_mae),
        "mean_r": stats.mean(all_mae),
        "median_r": stats.median(all_mae),
        "p95_r": stats.percentile(all_mae, 0.95),
        "median_loss_r": stats.median(loss_mae),
    }


def _exit_breakdown(trades: Sequence[Trade], total: int) -> dict[str, dict[str, object]]:
    by_reason: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        reason = t.get("exit_reason")
        if reason in KNOWN_REASONS:
            by_reason[reason].append(t)
    out: dict[str, dict[str, object]] = {}
    for reason in KNOWN_REASONS:
        group = by_reason.get(reason, [])
        if not group:
            continue
        wins = sum(1 for t in group if t.get("result") == "win")
        decided = sum(1 for t in group if t.get("result") in DECIDED_RESULTS)
        rs = [r for t in group if (r := _r(t)) is not None]
        out[reason] = {
            "count": len(group),
            "share_pct": len(group) / total * 100 if total else 0.0,
            "win_rate": wins / decided if decided else 0.0,
            "avg_r": stats.mean(rs),
        }
    return out


def _frequency(trades: Sequence[Trade]) -> dict[str, object]:
    stamps: list[datetime] = []
    for t in trades:
        for key in ("submit_ts", "entry_ts", "exit_ts"):
            ts = _ts(t.get(key))
            if ts is not None:
                stamps.append(ts)
    if not stamps:
        return {
            "elapsed_days": 0.0,
            "trades_per_day": 0.0,
            "trades_per_week": 0.0,
            "trades_per_month": 0.0,
        }
    naive = [s if s.tzinfo else s.replace(tzinfo=UTC) for s in stamps]
    elapsed_days = max(0.0, (max(naive) - min(naive)).total_seconds() / 86400.0)
    total = len(trades)
    if elapsed_days == 0.0:
        return {
            "elapsed_days": elapsed_days,
            "trades_per_day": float(total),
            "trades_per_week": float(total) * 7,
            "trades_per_month": float(total) * _DAYS_PER_MONTH,
        }
    return {
        "elapsed_days": elapsed_days,
        "trades_per_day": total / elapsed_days,
        "trades_per_week": total / (elapsed_days / 7.0),
        "trades_per_month": total / (elapsed_days / _DAYS_PER_MONTH),
    }


def _reach(
    trades: Sequence[Trade],
) -> dict[str, object]:
    """% of filled trades reaching each R level, by realized R and by MFE."""
    filled = [t for t in trades if t.get("result") in FILLED_RESULTS]
    realized: dict[str, dict[str, object]] = {}
    by_mfe: dict[str, dict[str, object]] = {}
    for level in R_LEVELS:
        real_count = sum(1 for t in filled if (r := _r(t)) is not None and r >= level)
        mfe_count = sum(
            1 for t in filled if (m := _float(t.get("mfe_r"))) is not None and m >= level
        )
        realized[str(level) + "r"] = {
            "pct": real_count / len(filled) if filled else 0.0,
            "count": real_count,
        }
        by_mfe[str(level) + "r"] = {
            "pct": mfe_count / len(filled) if filled else 0.0,
            "count": mfe_count,
        }
    directions: dict[str, dict[str, object]] = {}
    for direction in ("bullish", "bearish"):
        subset = [t for t in filled if t.get("direction") == direction]
        per_real: dict[str, dict[str, object]] = {}
        per_mfe: dict[str, dict[str, object]] = {}
        for level in R_LEVELS:
            rc = sum(1 for t in subset if (r := _r(t)) is not None and r >= level)
            mc = sum(1 for t in subset if (m := _float(t.get("mfe_r"))) is not None and m >= level)
            per_real[str(level) + "r"] = {
                "pct": rc / len(subset) if subset else 0.0,
                "count": rc,
            }
            per_mfe[str(level) + "r"] = {
                "pct": mc / len(subset) if subset else 0.0,
                "count": mc,
            }
        directions[direction] = {
            "trades": len(subset),
            "by_realized": per_real,
            "by_mfe": per_mfe,
        }
    return {"by_realized": realized, "by_mfe": by_mfe, "by_direction": directions}


def trade_metrics(trades: Sequence[Trade]) -> dict[str, object]:
    """Reduce enriched trade dicts (098) to the trade-level metrics dashboard.

    All values are in R units unless noted. Pure and JSON-serializable; the
    full schema is documented in ``backlog/099-trade-level-statistics.md``.
    """
    counts = _counts(trades)
    return {
        "counts": counts,
        "win_rate": _win_rate(counts),
        "avg_r": _r_averages(trades),
        "expectancy": _expectancy(trades),
        "profit_factor": _profit_factor(trades),
        "r_distribution": _r_distribution(trades, counts["decided"]),
        "duration": _duration(trades),
        "mfe_exit_quality": _mfe_exit_quality(trades),
        "mae": _mae_distribution(trades),
        "exit_breakdown": _exit_breakdown(trades, counts["total"]),
        "frequency": _frequency(trades),
        "reach": _reach(trades),
    }
