"""Costs & realism — net-performance layer (backlog 101).

Metrics 099/100 judge a backtest gross: they ignore the frictions a live
account pays. This module layers an explicit, run-configurable cost schedule
over the enriched trade dicts (098) and reports NET performance alongside the
gross dashboard — so the real "edge survives?" question is answered, not just
the idealised one.

The schedule covers the costs that dominate live results:

* **commission** — flat per round-trip trade and/or a rate on round-trip
  notional (entry leg + exit leg, sized on the actual position).
* **spread / slippage** — a % of the notional friction on entry and on exit
  (the candidate already carries an entry-only ``slippage_pct`` from risk
  sizing; here both legs are formalised on the recorded trade geography).
* **stop-loss slippage** — an extra adverse fill (gap-through) when a stop is
  hit: only stop exits pay it.
* **position-size rounding** — lot/contract steps: real accounts can't hold
  arbitrary fractional sizes. Rounding scales the deployed exposure (and the
  cost base) while leaving the R unit — one unit of *intended* risk — intact.

Delayed/missed fills are deliberately out of scope here: the probabilistic
variant belongs to the Monte-Carlo layer (backlog 102). This module is the
deterministic cost pass.

Everything is a pure function over plain dicts (JSON-serializable, no I/O).
Costs never mutate the input trades — ``apply_cost_schedule`` returns net-
adjusted *copies* so gross metrics stay intact and net is purely additive.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from marketatlas.metrics.portfolio import portfolio_metrics
from marketatlas.metrics.trades import trade_metrics

Trade = Mapping[str, Any]

FILLED_RESULTS = ("win", "loss", "breakeven")
_STOP_REASON = "stop"

# Cost field keys added to every net-adjusted trade dict. Consumers (net
# dashboard, report) read these; ``pnl``/``r_multiple`` are overridden to the
# net values so 099/100 reductions run unchanged over the same schemas.
COST_KEYS = (
    "gross_pnl",
    "gross_r_multiple",
    "cost_pnl",
    "cost_r",
    "effective_risk",
    "size",
    "gross_size",
    "size_factor",
    "entry_notional",
    "exit_notional",
    "cost_breakdown",
    "cost_applied",
    "dropped",
)


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        f = float(value)
        return f if math.isfinite(f) else None
    return None


@dataclass(frozen=True)
class CostSchedule:
    """Run-configurable frictions applied to every filled trade.

    All fields zero by default → net == gross (back-compat guard: enabling
    costs is opt-in). Costs are denominated either in account currency
    (``commission_flat``) or as fractions/pct of position notional.
    """

    commission_flat: float = 0.0  # per round-trip filled trade, account currency
    commission_rate: float = 0.0  # fraction of round-trip notional (entry+exit legs)
    entry_slippage_pct: float = 0.0  # % of entry notional paid on entry fills
    exit_slippage_pct: float = 0.0  # % of exit notional paid on exit fills
    stop_slippage_pct: float = 0.0  # % of entry notional adverse gap fill when a stop is hit
    size_step: float = 0.0  # lot/contract size rounding increment; 0 = no rounding
    source: str = field(default="default", compare=False, kw_only=True)

    _KEYS = (
        "commission_flat",
        "commission_rate",
        "entry_slippage_pct",
        "exit_slippage_pct",
        "stop_slippage_pct",
        "size_step",
    )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CostSchedule:
        """Build from a plain dict, normalizing ``-`` keys and rejecting unknown ones."""
        normalized: dict[str, Any] = {}
        for raw_key, value in data.items():
            key = str(raw_key).replace("-", "_")
            if key not in cls._KEYS:
                raise ValueError(
                    f"unknown cost-schedule field '{raw_key}'; "
                    f"valid: {', '.join(cls._KEYS)}"
                )
            normalized[key] = value
        kwargs = {key: _float(normalized.get(key, 0.0)) or 0.0 for key in cls._KEYS}
        schedule = cls(**kwargs)  # type: ignore[arg-type]
        schedule.validate()
        return schedule

    @classmethod
    def parse(cls, raw: str) -> CostSchedule:
        """Parse a ``--costs`` value: inline JSON or a path to a JSON file."""
        text = raw.strip()
        if not text:
            raise ValueError("empty cost schedule")
        data: Any = None
        source: str = text
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            path = Path(text)
            if not path.is_file():
                raise ValueError(
                    "cost schedule must be inline JSON "
                    "(e.g. '{\"commission_flat\": 1.5}') or a path to a JSON file"
                ) from None
            source = str(path)
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError(f"cost schedule file '{path}' is not valid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("cost schedule JSON must be an object")
        schedule = cls.from_dict(data)
        return CostSchedule(**schedule.to_dict(), source=source)

    def to_dict(self) -> dict[str, float]:
        return {key: float(getattr(self, key)) for key in self._KEYS}

    def validate(self) -> None:
        for key in self._KEYS:
            value = float(getattr(self, key))
            if value < 0:
                raise ValueError(f"cost-schedule field '{key}' must be >= 0, got {value}")
        if self.commission_rate > 1.0:
            raise ValueError(
                f"commission_rate must be a fraction in [0, 1], got {self.commission_rate}"
            )


def _notional(
    trade: Trade, schedule: CostSchedule
) -> tuple[float | None, float | None, float | None]:
    """(size, entry_notional, exit_notional) on the MAYBE-rounded position.

    Size is derived from the recorded risk geometry (``risk / stop_distance``,
    matching ``RiskEngine`` sizing); exit price is backed out of the realized
    per-unit P&L so spread friction uses the actual exit level (stop/target/
    timeout close) rather than an assumed one. ``None`` sizing when the trade
    cannot be costed (missing geometry/risk).
    """
    entry = _float(trade.get("entry"))
    stop = _float(trade.get("stop"))
    risk = _float(trade.get("risk_amount"))
    pnl = _float(trade.get("pnl"))
    if entry is None or stop is None or risk is None or risk <= 0 or pnl is None:
        return None, None, None
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        return None, None, None
    size = risk / stop_distance
    step = _float(schedule.size_step) or 0.0
    if step > 0:
        size = math.floor(size / step + 1e-9) * step
    per_unit = pnl / (risk / stop_distance)
    if trade.get("direction") == "bullish":
        exit_price = entry + per_unit
    else:
        exit_price = entry - per_unit
    return size, size * entry, size * exit_price


def _apply_cost(trade: Trade, schedule: CostSchedule) -> dict[str, Any]:
    """Net-adjust one trade dict; returns a NEW dict (gross untouched)."""
    out: dict[str, Any] = dict(trade)
    out["gross_pnl"] = _float(trade.get("pnl"))
    out["gross_r_multiple"] = _float(trade.get("r_multiple"))
    if trade.get("result") not in FILLED_RESULTS:
        # Never-filled (cancelled) trades pay nothing; net == gross (R = 0).
        out.update(
            {
                "cost_pnl": 0.0,
                "cost_r": 0.0,
                "effective_risk": _float(trade.get("risk_amount")),
                "size": 0.0,
                "gross_size": _float(trade.get("risk_amount")),
                "size_factor": 1.0,
                "entry_notional": 0.0,
                "exit_notional": 0.0,
                "cost_breakdown": {"commission": 0.0, "spread": 0.0, "stop_slippage": 0.0},
                "cost_applied": False,
                "dropped": False,
            }
        )
        return out

    size, entry_notional, exit_notional = _notional(trade, schedule)
    if size is None or entry_notional is None or exit_notional is None:
        # Un-costable (no geometry/risk recorded) — leave the trade gross.
        out.update(
            {
                "cost_pnl": 0.0,
                "cost_r": 0.0,
                "effective_risk": _float(trade.get("risk_amount")),
                "size": None,
                "gross_size": None,
                "size_factor": 1.0,
                "entry_notional": None,
                "exit_notional": None,
                "cost_breakdown": {"commission": 0.0, "spread": 0.0, "stop_slippage": 0.0},
                "cost_applied": False,
                "dropped": False,
            }
        )
        return out

    gross_risk = _float(trade.get("risk_amount")) or 0.0
    stop_dist = abs((_float(trade.get("entry")) or 0.0) - (_float(trade.get("stop")) or 0.0))
    gross_size = gross_risk / (stop_dist or 1.0) if stop_dist else 1.0
    gross_size = max(gross_size, 0.0)
    if gross_size <= 0:
        gross_size = 1.0
    size_factor = size / gross_size
    if size_factor < 1e-12 or size <= 0:
        # Lot rounding floors the position: sizing below one tradable step
        # means the setup cannot be put on. Recorded as a missed trade.
        net_pnl, effective_risk, cost = 0.0, 0.0, 0.0
        dropped, costs = True, {"commission": 0.0, "spread": 0.0, "stop_slippage": 0.0}
    else:
        commission = schedule.commission_flat + schedule.commission_rate * (
            entry_notional + exit_notional
        )
        spread = (
            schedule.entry_slippage_pct / 100.0 * entry_notional
            + schedule.exit_slippage_pct / 100.0 * exit_notional
        )
        stop_slip = (
            schedule.stop_slippage_pct / 100.0 * entry_notional
            if trade.get("exit_reason") == _STOP_REASON
            else 0.0
        )
        cost = commission + spread + stop_slip
        costs = {"commission": commission, "spread": spread, "stop_slippage": stop_slip}
        net_pnl = (_float(trade.get("pnl")) or 0.0) * size_factor - cost
        effective_risk = gross_risk * size_factor
        dropped = False

    if effective_risk > 0:
        net_r = net_pnl / effective_risk
        cost_r = cost / effective_risk
    else:
        net_r, cost_r = None, None

    out.update(
        {
            "pnl": net_pnl,
            "r_multiple": net_r,
            "cost_pnl": cost,
            "cost_r": cost_r,
            "effective_risk": effective_risk,
            "size": size,
            "gross_size": gross_size,
            "size_factor": size_factor,
            "entry_notional": entry_notional,
            "exit_notional": exit_notional,
            "cost_breakdown": costs,
            "cost_applied": not dropped,
            "dropped": dropped,
        }
    )
    return out


def apply_cost_schedule(
    trades: Sequence[Trade], schedule: CostSchedule
) -> list[dict[str, Any]]:
    """Net-adjust every trade under ``schedule`` (copies; gross inputs intact).

    Each output dict carries the original keys with ``pnl``/``r_multiple``
    overridden to net values plus the ``COST_KEYS`` provenance block
    (gross P&L, cost in currency/R, rounded size & factor, notional legs —
    see ``_apply_cost``). Order and membership are preserved.
    """
    return [_apply_cost(t, schedule) for t in trades]


def costs_summary(
    trades: Sequence[Trade], net: Sequence[Trade], schedule: CostSchedule
) -> dict[str, object]:
    """Aggregate the frictions actually charged over the filled trades.

    Includes per-trade average cost in currency and in R units of the deployed
    risk (the real cost drag per trade), plus round-trip notional turnover and
    how many setups lot-rounding dropped entirely. Empty books zero-fill.
    """
    filled = [n for n, g in zip(net, trades) if g.get("result") in FILLED_RESULTS]
    costed = [n for n in filled if n.get("cost_applied")]
    dropped = [n for n in filled if n.get("dropped")]
    total_cost = sum(_float(n.get("cost_pnl")) or 0.0 for n in costed)
    total_commission = sum(
        _float(n.get("cost_breakdown", {}).get("commission")) or 0.0 for n in costed
        if isinstance(n.get("cost_breakdown"), Mapping)
    )
    total_spread = sum(
        _float(n.get("cost_breakdown", {}).get("spread")) or 0.0 for n in costed
        if isinstance(n.get("cost_breakdown"), Mapping)
    )
    total_stop_slip = sum(
        _float(n.get("cost_breakdown", {}).get("stop_slippage")) or 0.0 for n in costed
        if isinstance(n.get("cost_breakdown"), Mapping)
    )
    notional = sum(
        (_float(n.get("entry_notional")) or 0.0) + (_float(n.get("exit_notional")) or 0.0)
        for n in costed
    )
    cost_rs = [r for n in costed if (r := _float(n.get("cost_r"))) is not None]
    avg_cost_r = sum(cost_rs) / len(cost_rs) if cost_rs else None
    avg_commission = total_cost / len(costed) if costed else 0.0
    win_notional_share: float | None = None
    gross_wins = [g for g in trades if g.get("result") == "win"]
    if gross_wins and total_cost:
        win_pnls = [p for g in gross_wins if (p := _float(g.get("pnl"))) is not None and p > 0]
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else None
        avg_cost_filled = total_cost / len(costed) if costed else 0.0
        win_notional_share = (
            avg_cost_filled / avg_win * 100 if avg_win is not None and avg_win > 0 else None
        )
    return {
        "filled_count": len(filled),
        "costed_count": len(costed),
        "dropped_count": len(dropped),
        "total_cost": total_cost,
        "commission": total_commission,
        "spread": total_spread,
        "stop_slippage": total_stop_slip,
        "round_trip_notional": notional,
        "avg_cost_per_filled": avg_commission,
        "avg_cost_r": avg_cost_r,
        "cost_share_of_avg_win_pct": win_notional_share,
        "note": (
            "costs apply only to filled trades; cancelled trades fill no "
            "orders and pay nothing. avg_cost_r is cost / effective (rounded) risk."
        ),
    }


def _num(obj: Mapping[str, Any], *path: str) -> float | None:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(key)
    return _float(cur)


def break_even_win_rate(win_r_mean: float | None, loss_r_mean: float | None) -> float | None:
    """Win rate at which expectancy = 0 given avg win/loss R: ``L/(W+L)``."""
    if win_r_mean is None or loss_r_mean is None:
        return None
    if (win_r_mean + loss_r_mean) <= 0:
        return None
    return loss_r_mean / (win_r_mean + loss_r_mean)


def net_metrics(
    trades: Sequence[Trade],
    schedule: CostSchedule | None = None,
    *,
    initial_balance: float | None = None,
    timeframe: str | None = None,
    periods_per_year: float | None = None,
) -> dict[str, object]:
    """Gross-vs-net dashboard: what frictions do to the 099/100 numbers.

    Combines the trade-level (099) and portfolio-level (100) reductions over
    the gross trades and over their net-adjusted copies, then reports the gap
    terms — return/CAGR/expectancy/PF/win-rate drag — a sign-flip warning list
    (edge destroyed after costs), and the break-even win rate at the current
    schedule. ``schedule=None`` yields zero drags and a no-op cost summary
    (net == gross outright).

    Pure + JSON-serializable; the schema is documented in
    ``backlog/101-costs-realism.md``.
    """
    schedule = schedule or CostSchedule()
    net = apply_cost_schedule(trades, schedule)
    gross_tm = trade_metrics(trades)
    net_tm = trade_metrics(net)
    gross_pm = portfolio_metrics(trades, None, initial_balance, timeframe, periods_per_year)
    net_pm = portfolio_metrics(net, None, initial_balance, timeframe, periods_per_year)

    g_ret = _num(gross_pm, "summary", "total_return_pct")
    n_ret = _num(net_pm, "summary", "total_return_pct")
    g_cagr = _num(gross_pm, "returns", "cagr_pct")
    n_cagr = _num(net_pm, "returns", "cagr_pct")
    g_exp = _num(gross_tm, "expectancy", "expectancy_r")
    n_exp = _num(net_tm, "expectancy", "expectancy_r")
    g_pf = _num(gross_tm, "profit_factor", "profit_factor_r")
    n_pf = _num(net_tm, "profit_factor", "profit_factor_r")
    g_wr = _num(gross_tm, "win_rate", "decided")
    n_wr = _num(net_tm, "win_rate", "decided")

    g_win_r = _num(gross_tm, "avg_r", "win_r_mean")
    g_loss_r = _num(gross_tm, "avg_r", "loss_r_mean")
    be_gross = break_even_win_rate(g_win_r, g_loss_r)
    n_win_r = _num(net_tm, "avg_r", "win_r_mean")
    n_loss_r = _num(net_tm, "avg_r", "loss_r_mean")
    be_net = break_even_win_rate(n_win_r, n_loss_r)

    diffs: dict[str, float | None] = {
        "return_drag_pct": (g_ret - n_ret) if g_ret is not None and n_ret is not None else None,
        "cagr_drag_pct": (
            g_cagr - n_cagr if g_cagr is not None and n_cagr is not None else None
        ),
        "expectancy_drag_r": (
            g_exp - n_exp if g_exp is not None and n_exp is not None else None
        ),
        "profit_factor_drag": (
            g_pf - n_pf if g_pf is not None and n_pf is not None else None
        ),
        "win_rate_drag_pp": (
            (g_wr - n_wr) * 100 if g_wr is not None and n_wr is not None else None
        ),
    }

    flips: list[dict[str, object]] = []
    if g_ret is not None and n_ret is not None and g_ret > 0 and n_ret <= 0:
        flips.append(
            {
                "signal": "positive gross return flips net negative",
                "metric": "total_return_pct",
                "gross": g_ret,
                "net": n_ret,
            }
        )
    if g_cagr is not None and n_cagr is not None and g_cagr > 0 and n_cagr < 0:
        flips.append(
            {
                "signal": "positive gross CAGR flips net negative",
                "metric": "cagr_pct",
                "gross": g_cagr,
                "net": n_cagr,
            }
        )
    if g_exp is not None and n_exp is not None and g_exp > 0 and n_exp <= 0:
        flips.append(
            {
                "signal": "positive gross expectancy wiped by costs",
                "metric": "expectancy_r",
                "gross": g_exp,
                "net": n_exp,
            }
        )
    if g_pf is not None and n_pf is not None and g_pf >= 1.0 and n_pf < 1.0:
        flips.append(
            {
                "signal": "profit factor falls below 1.0 after costs",
                "metric": "profit_factor_r",
                "gross": g_pf,
                "net": n_pf,
            }
        )

    be_lift = (be_net - (g_wr or 0.0)) if be_net is not None and g_wr is not None else None
    return {
        "cost_schedule": schedule.to_dict(),
        "costs": costs_summary(trades, net, schedule),
        "net": {
            "trades": net_tm,
            "portfolio": net_pm,
        },
        "drags": diffs,
        "sign_flips": flips,
        "break_even_win_rate": {
            "gross": be_gross,
            "net": be_net,
            "required_lift_pp": (be_lift * 100) if be_lift is not None else None,
            "note": (
                "win rate that zeroes expectancy = avg_loss_r/(avg_win_r+avg_loss_r); "
                "required_lift_pp = break-even net win rate minus realized gross win rate"
            ),
        },
        "note": (
            "gross metrics unchanged; net.trades/portfolio recompute 099/100 over "
            "cost-adjusted copies, so every headline number is directly comparable"
        ),
    }
