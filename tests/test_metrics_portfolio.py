from __future__ import annotations

import math
from datetime import datetime

import pytest
from marketatlas.metrics import drawdown, portfolio, stats

pytestmark = pytest.mark.tier1


def _simple_curve(values: list[float]) -> list[dict[str, object]]:
    """Sparse chronological curve with clearly separated months."""
    days = 0
    out: list[dict[str, object]] = []
    base = datetime(2024, 1, 1)
    for b in values:
        out.append({"t": base.fromordinal(base.toordinal() + days).isoformat(), "balance": b})
        days += 30
    return out


def _trade(
    result: str,
    entry: str,
    exit_ts: str,
    risk: float = 10.0,
    instrument: str = "A",
    direction: str = "bullish",
) -> dict[str, object]:
    r = {"win": 2.0, "loss": -1.0, "breakeven": 0.0}.get(result, 0.0)
    return {
        "submit_ts": entry,
        "entry_ts": entry,
        "exit_ts": exit_ts,
        "instrument": instrument,
        "direction": direction,
        "result": result,
        "exit_reason": "target" if result == "win" else "stop",
        "pnl": r * risk,
        "risk_amount": risk,
        "r_multiple": r,
    }


class TestCagr:
    def test_growth(self) -> None:
        # 100 -> 200 in exactly 1 year => 100%/yr.
        assert stats.cagr(200.0, 100.0, 1.0) == pytest.approx(1.0)
        assert stats.cagr(200.0, 100.0, 2.0) == pytest.approx(math.sqrt(2) - 1)

    def test_invalid_inputs_none(self) -> None:
        assert stats.cagr(100.0, 0.0, 1.0) is None
        assert stats.cagr(100.0, 50.0, 0.0) is None


class TestLogReturns:
    def test_log_returns(self) -> None:
        lr = stats.log_returns([100.0, 110.0, 121.0])
        assert lr == pytest.approx([math.log(1.1), math.log(1.1)])

    def test_nonpositive_skipped(self) -> None:
        assert stats.log_returns([100.0, 0.0, 200.0]) == []
        assert stats.log_returns([-1.0, -2.0]) == []
        assert stats.log_returns([]) == []


class TestSharpeSortino:
    LOGS = [0.05, -0.02, 0.03, 0.01, -0.015, 0.02]

    def test_sharpe_matches_numpy(self) -> None:
        # Independent recomputation: (mean/std, ddof=1) * sqrt(ppr)
        import statistics

        mean = statistics.fmean(self.LOGS)
        std = statistics.stdev(self.LOGS)
        expected = mean / std * math.sqrt(12)
        assert stats.sharpe(self.LOGS, 12.0) == pytest.approx(expected)

    def test_sharpe_flat_returns_none(self) -> None:
        assert stats.sharpe([0.01, 0.01, 0.01], 12.0) is None

    def test_zero_downside_sortino_returns_none(self) -> None:
        # All periods positive => no downside => ratio unbounded => None.
        assert stats.sortino([0.02, 0.03, 0.01], 12.0) is None

    def test_sortino_denominator(self) -> None:
        # MAR = 0: downside = sqrt(mean(neg^2)) * sqrt(ppr).
        logs = [-0.05, 0.1, -0.01, 0.02]
        negs = [r for r in logs if r < 0]
        import statistics

        downside = math.sqrt(statistics.fmean([r**2 for r in negs])) * math.sqrt(12)
        annual = statistics.fmean(logs) * 12
        expected = annual / downside
        assert stats.sortino(logs, 12.0) == pytest.approx(expected)


class TestVolatility:
    def test_annualized(self) -> None:
        logs = [0.01, -0.01, 0.02, -0.02, 0.03]
        import statistics

        std = statistics.stdev(logs)
        assert stats.volatility(logs, 12.0) == pytest.approx(std * math.sqrt(12))

    def test_single_period_None(self) -> None:
        assert stats.volatility([0.01], 12.0) is None


class TestProductReturns:
    def test_compounds(self) -> None:
        assert stats.product_returns([0.1, 0.1]) == pytest.approx(0.21)  # 1.1*1.1-1
        assert stats.product_returns([]) is None


class TestDrawdownAnalysis:
    def _points(self, balances: list[float]) -> list[tuple[datetime, float]]:
        base = datetime(2024, 1, 1)
        return [(base.replace(day=1, month=(i % 12) + 1), b) for i, b in enumerate(balances)]

    def test_one_deep_drawdown_dates_and_duration(self) -> None:
        # 100, 120, 90, 80, 110, 130
        # Peak 120 (idx 1), trough 80 (idx 3); recovery on 130 (idx 5) — the
        # 110 bar undercuts the old peak so it does not count as recovery.
        dd = drawdown.drawdown_analysis(self._points([100.0, 120.0, 90.0, 80.0, 110.0, 130.0]))
        assert dd["max_drawdown_pct"] == pytest.approx((120.0 - 80.0) / 120.0 * 100)
        assert dd["max_drawdown_abs"] == pytest.approx(40.0)
        assert dd["duration_bars"] == 2  # idx 1 -> idx 3
        assert dd["recovery_bars"] == 2  # idx 3 -> idx 5
        assert dd["recovered"] is True
        assert dd["peak"]["balance"] == 120.0
        assert dd["trough"]["balance"] == 80.0
        assert dd["count"] == 1
        assert dd["avg_drawdown_pct"] == pytest.approx((120.0 - 80.0) / 120.0 * 100)
        assert dd["avg_duration_bars"] == pytest.approx(2.0)
        assert dd["max_recovery_bars"] == 2

    def test_open_drawdown_no_recovery(self) -> None:
        dd = drawdown.drawdown_analysis(self._points([100.0, 110.0, 90.0]))
        assert dd["max_drawdown_pct"] == pytest.approx((110.0 - 90.0) / 110.0 * 100)
        assert dd["recovered"] is False
        assert dd["recovery_bars"] is None
        assert dd["count"] == 1

    def test_two_episodes_and_average(self) -> None:
        # 100, 120, 95, 105, 130, 100, 70
        # Ep1: peak 120@1, trough 95@2, recover 130@4. Ep2: peak 130@4,
        # trough 70@6, still underwater at end.
        dd = drawdown.drawdown_analysis(
            self._points([100.0, 120.0, 95.0, 105.0, 130.0, 100.0, 70.0])
        )
        assert dd["count"] == 2
        depth1 = (120.0 - 95.0) / 120.0 * 100
        depth2 = (130.0 - 70.0) / 130.0 * 100
        assert dd["avg_drawdown_pct"] == pytest.approx((depth1 + depth2) / 2)
        assert dd["max_drawdown_pct"] == pytest.approx(depth2)
        assert dd["max_recovery_bars"] == 2  # trough 95@2 -> recover 130@4
        assert dd["episodes"][0]["recovered"] is True
        assert dd["episodes"][1]["recovered"] is False

    def test_flat_series_no_episodes(self) -> None:
        dd = drawdown.drawdown_analysis(self._points([100.0, 100.0, 100.0]))
        assert dd["count"] == 0
        assert dd["max_drawdown_pct"] == 0.0
        assert dd["max_recovery_bars"] is None

    def test_empty(self) -> None:
        dd = drawdown.drawdown_analysis([])
        assert dd["count"] == 0
        assert dd["max_drawdown_pct"] == 0.0

    def test_distribution(self) -> None:
        dd = drawdown.drawdown_analysis(self._points([1000.0, 1100.0, 700.0, 1000.0, 900.0]))
        dist = drawdown.drawdown_distribution(dd["episodes"])  # type: ignore[arg-type]
        depths = [float(e["depth_pct"]) for e in dd["episodes"] if isinstance(e, dict)]
        for t in (10.0, 20.0, 50.0):
            key = f"gt_{int(t):d}pct"
            expected = sum(1 for d in depths if d > t) / len(depths) if depths else 0.0
            assert dist[key] == pytest.approx(expected)


class TestPortfolioMetrics:
    def test_hand_built_curve_cagr_and_dd(self) -> None:
        # 100 -> 121 over 2 years ⇒ CAGR = 10%. One DD 121->100 (17.4%).
        curve = _simple_curve([110.0, 121.0, 100.0, 121.0])
        trades = []
        m = portfolio.portfolio_metrics(trades, curve, initial_balance=100.0)
        assert m["summary"]["total_return_pct"] == pytest.approx(21.0)
        assert m["returns"]["cagr_pct"] is not None
        # elapsed span = last ts - first ts; curve starts 2024-01-01 ends ~90 days gap + 3*30 = end 2024-12-30ish
        dc = m["drawdown"]
        assert dc["max_drawdown_pct"] == pytest.approx((121.0 - 100.0) / 121.0 * 100)
        assert dc["trough"]["balance"] == 100.0
        assert dc["recovered"] is True
        assert m["risk"]["volatility_pct_annual"] is not None
        assert m["risk"]["sharpe"] is not None
        assert m["risk"]["sortino"] is not None  # deep DD = real downside
        assert m["equity_behavior"]["equity_curve"][0]["index"] == pytest.approx(100.0)

    def test_zero_downside_curve_sortino_none(self) -> None:
        curve = _simple_curve([110.0, 121.0, 133.0, 146.4])
        m = portfolio.portfolio_metrics([], curve, initial_balance=100.0)
        assert m["risk"]["sortino"] is None

    def test_consecutive_streaks(self) -> None:
        trades = [
            _trade("win", "2024-01-01", "2024-01-02"),
            _trade("win", "2024-01-03", "2024-01-04"),
            _trade("loss", "2024-01-05", "2024-01-06"),
            _trade("breakeven", "2024-01-07", "2024-01-08"),
            _trade("loss", "2024-01-09", "2024-01-10"),
            _trade("loss", "2024-01-11", "2024-01-12"),
        ]
        m = portfolio.portfolio_metrics(trades)
        assert m["equity_behavior"]["max_consecutive_wins"] == 2
        assert m["equity_behavior"]["max_consecutive_losses"] == 2

    def test_exposure_overlapping_trades(self) -> None:
        trades = [
            _trade("win", "2024-01-01", "2024-01-10", risk=10.0),
            _trade("loss", "2024-01-05", "2024-01-15", risk=10.0),
            _trade("win", "2024-01-12", "2024-01-20", risk=20.0),
        ]
        m = portfolio.portfolio_metrics(trades, initial_balance=1000.0)
        ex = m["exposure"]
        # overlaps: [01-05,01-10] two open (risk 20); [01-12,01-15] two open (30).
        assert ex["max_simultaneous_trades"] == 2
        assert ex["max_simultaneous_risk"] == pytest.approx(30.0)
        assert ex["max_simultaneous_risk_pct"] == pytest.approx(3.0)
        assert ex["risk_per_trade_pct"]["mean_pct"] == pytest.approx(40.0 / 3 / 1000 * 100)
        assert ex["risk_per_trade_pct"]["max_pct"] == pytest.approx(2.0)

    def test_exposure_by_instrument(self) -> None:
        trades = [
            _trade("win", "2024-01-01", "2024-01-10", risk=10.0, instrument="A"),
            _trade("loss", "2024-01-05", "2024-01-12", risk=20.0, instrument="B"),
        ]
        m = portfolio.portfolio_metrics(trades, initial_balance=1000.0)
        bi = m["exposure"]["by_instrument"]
        assert bi["A"]["win_rate"] == 1.0
        assert bi["B"]["losses"] == 1
        assert m["exposure"]["multi_instrument_share_pct"] > 0.0
        assert m["exposure"]["avg_simultaneous_instruments"] > 1.0

    def test_monthly_annual_returns(self) -> None:
        # 3 trades across 3 distinct months; monthly compounded vs simple.
        trades = [
            _trade("win", "2024-01-01", "2024-01-05", risk=10.0),
            _trade("win", "2024-02-01", "2024-02-05", risk=10.0),
            _trade("win", "2024-03-01", "2024-03-05", risk=10.0),
        ]
        m = portfolio.portfolio_metrics(trades, initial_balance=100.0)
        monthly = m["returns"]["monthly"]
        assert [r["period"] for r in monthly] == ["2024-01", "2024-02", "2024-03"]
        returns = [r["return"] for r in monthly]
        assert m["returns"]["simple_sum_return_pct"] == pytest.approx(sum(returns) * 100)
        prod = 1.0
        for r in returns:
            prod *= 1.0 + r
        assert m["returns"]["compounded_return_pct"] == pytest.approx((prod - 1) * 100)
        assert m["returns"]["annual"][-1]["period"] == "2024"
        assert m["returns"]["compounding_signal"] == "compounded >= simple"

    def test_compounded_less_than_simple(self) -> None:
        curve = _simple_curve([150.0, 80.0, 160.0])
        m = portfolio.portfolio_metrics([], curve, initial_balance=100.0)
        mo = m["returns"]
        # Jan bucket ends at 80 (both 150 and 80 land in Jan): -20%; Mar: +100%.
        assert mo["simple_sum_return_pct"] == pytest.approx((-0.2 + 1.0) * 100)
        assert mo["compounded_return_pct"] == pytest.approx((0.8 * 2.0 - 1.0) * 100)
        assert mo["compounding_signal"] == "compounded < simple (volatility drag)"
        assert mo["compounded_vs_simple_drag_pct"] == pytest.approx(20.0)

    def test_timeframe_basis_and_explicit_ppr(self) -> None:
        curve = _simple_curve([110.0, 121.0, 100.0, 121.0])
        tf = portfolio.portfolio_metrics([], curve, initial_balance=100.0, timeframe="D1")
        exp = portfolio.portfolio_metrics([], curve, initial_balance=100.0, periods_per_year=12.0)
        assert tf["risk"]["periods_per_year"] == 252
        assert exp["risk"]["periods_per_year"] == 12.0
        assert tf["risk"]["annualization_basis"] == "timeframe_bars_per_year"

    def test_empty_inputs(self) -> None:
        m = portfolio.portfolio_metrics([])
        assert m["summary"]["total_pnl"] == 0.0
        assert m["returns"]["total_return_pct"] == 0.0
        assert m["drawdown"]["count"] == 0
        assert m["risk"]["calmar"] is None
        assert m["exposure"]["max_simultaneous_trades"] == 0
        assert m["equity_behavior"]["max_consecutive_wins"] == 0

    def test_initial_derived_from_final_minus_pnl(self) -> None:
        trades = [_trade("win", "2024-01-01", "2024-01-02", risk=10.0)]
        curve = [{"t": "2024-01-02T00:00:00", "balance": 120.0}]
        m = portfolio.portfolio_metrics(trades, curve)
        assert m["summary"]["initial_balance"] == pytest.approx(100.0)
        assert m["summary"]["total_return_pct"] == pytest.approx(20.0)