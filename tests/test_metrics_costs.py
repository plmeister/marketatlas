from __future__ import annotations

import json
import math
from typing import Any

import pytest
from marketatlas.metrics import costs
from marketatlas.metrics.costs import CostSchedule

pytestmark = pytest.mark.tier1


def _trade(
    result: str,
    r: float,
    entry: float = 100.0,
    stop: float = 97.0,
    risk: float = 30.0,
    reason: str = "target",
    direction: str = "bullish",
) -> dict[str, object]:
    return {
        "submit_ts": "2026-01-01T00:00:00",
        "entry_ts": "2026-01-01T00:00:00",
        "exit_ts": "2026-01-02T00:00:00",
        "entry": entry,
        "stop": stop,
        "target": entry + r * abs(entry - stop),
        "direction": direction,
        "result": result,
        "exit_reason": reason,
        "pnl": r * risk,
        "risk_amount": risk,
        "r_multiple": r,
    }


def _win() -> dict[str, object]:
    # size = 30/3 = 10 units; exit_price = 106.
    return _trade("win", 2.0, reason="target")


def _loss() -> dict[str, object]:
    # size = 10; exit_price = 97, stop exit.
    return _trade("loss", -1.0, reason="stop")


class TestScheduleParsing:
    def test_inline_json(self) -> None:
        s = CostSchedule.parse('{"commission_flat": 1.5, "commission-rate": 0.0005}')
        assert s.commission_flat == 1.5
        assert s.commission_rate == 0.0005  # '-' keys normalized

    def test_from_dict_rejects_unknown(self) -> None:
        with pytest.raises(ValueError, match="unknown cost-schedule field"):
            CostSchedule.from_dict({"slippage": 1.0})

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be >="):
            CostSchedule.from_dict({"commission_flat": -1.0})

    def test_rate_sane_bounds(self) -> None:
        with pytest.raises(ValueError, match="fraction"):
            CostSchedule.from_dict({"commission_rate": 2.0})

    def test_from_json_file(self, tmp_path) -> None:
        p = tmp_path / "costs.json"
        p.write_text(json.dumps({"entry_slippage_pct": 0.1}))
        s = CostSchedule.parse(str(p))
        assert s.entry_slippage_pct == 0.1
        assert s.source == str(p)

    def test_garbage_rejected(self) -> None:
        with pytest.raises(ValueError, match="inline JSON"):
            CostSchedule.parse("definitely-not-a-schedule")

    def test_default_zero_schedule(self) -> None:
        assert CostSchedule().to_dict() == {
            "commission_flat": 0.0,
            "commission_rate": 0.0,
            "entry_slippage_pct": 0.0,
            "exit_slippage_pct": 0.0,
            "stop_slippage_pct": 0.0,
            "size_step": 0.0,
        }


class TestApplyCosts:
    def test_exact_net_r_pnl_known_schedule(self) -> None:
        s = CostSchedule(
            commission_flat=5.0, entry_slippage_pct=0.1, exit_slippage_pct=0.1,
            stop_slippage_pct=0.2,
        )
        win, loss = costs.apply_cost_schedule([_win(), _loss()], s)

        # win trade: notional 10*100 + 10*106; spread 1.0+1.06; commission 5.
        assert win["pnl"] == pytest.approx(60.0 - 7.06)
        assert win["r_multiple"] == pytest.approx((60.0 - 7.06) / 30.0)
        assert win["cost_pnl"] == pytest.approx(7.06)
        assert win["cost_breakdown"]["spread"] == pytest.approx(2.06)
        assert win["cost_breakdown"]["commission"] == pytest.approx(5.0)
        assert win["cost_breakdown"]["stop_slippage"] == pytest.approx(0.0)

        # loss trade is a stop exit: adds stop gap-through slippage (0.2% of entry notional).
        assert loss["pnl"] == pytest.approx(-30.0 - 8.97)
        assert loss["r_multiple"] == pytest.approx((30.0 + 8.97) / 30.0 * -1.0)
        assert loss["cost_breakdown"]["stop_slippage"] == pytest.approx(2.0)
        assert loss["cost_breakdown"]["spread"] == pytest.approx(1.97)

    def test_zero_cost_net_equals_gross(self) -> None:
        trades = [_win(), _loss()]
        net = costs.apply_cost_schedule(trades, CostSchedule())
        for gross, n in zip(trades, net):
            assert n["pnl"] == pytest.approx(gross["pnl"])
            assert n["r_multiple"] == pytest.approx(gross["r_multiple"])
            assert n["cost_pnl"] == 0.0
            assert n["cost_applied"] is True  # pass ran, just charged nothing

    def test_slip_through_stop_beyond_stop_price(self) -> None:
        # gap-through: stop exit pays adverse fill beyond the submitted stop.
        s = CostSchedule(stop_slippage_pct=0.5)
        loss = costs.apply_cost_schedule([_loss()], s)[0]
        expect_stop_slip = 0.005 * 10.0 * 100.0  # 0.5% of 1000 entry notional
        assert loss["cost_breakdown"]["stop_slippage"] == pytest.approx(expect_stop_slip)
        # target exits never pay stop slippage.
        win = costs.apply_cost_schedule([_win()], CostSchedule(stop_slippage_pct=0.5))[0]
        assert win["cost_breakdown"]["stop_slippage"] == 0.0

    def test_commission_rate_scales_with_notional(self) -> None:
        s = CostSchedule(commission_rate=0.001)
        win = costs.apply_cost_schedule([_win()], s)[0]
        assert win["cost_breakdown"]["commission"] == pytest.approx(0.001 * (1000 + 1060))

    def test_cancelled_trades_pay_nothing(self) -> None:
        cancelled = _trade("cancelled", 0.0, reason="cancel")
        s = CostSchedule(commission_flat=10.0, entry_slippage_pct=10.0)
        out = costs.apply_cost_schedule([cancelled], s)[0]
        assert out["pnl"] == 0.0
        assert out["cost_pnl"] == 0.0
        assert out["size_factor"] == 1.0

    def test_rounding_floor_reduces_exposure_and_r(self) -> None:
        s = CostSchedule(
            commission_flat=5.0,
            entry_slippage_pct=0.1,
            exit_slippage_pct=0.1,
            size_step=4.0,
        )
        win = costs.apply_cost_schedule([_win()], s)[0]
        # size 10 → floor(10/4)*4 = 8; factor 0.8; risk 24; notional 800/848.
        assert win["size"] == pytest.approx(8.0)
        assert win["size_factor"] == pytest.approx(0.8)
        assert win["effective_risk"] == pytest.approx(24.0)
        assert win["gross_size"] == pytest.approx(10.0)
        cost = 5.0 + 0.001 * 800 + 0.001 * 848
        assert win["cost_pnl"] == pytest.approx(cost)
        assert win["pnl"] == pytest.approx(60.0 * 0.8 - cost)
        assert win["r_multiple"] == pytest.approx((60.0 * 0.8 - cost) / 24.0)

    def test_rounding_below_one_step_drops_trade(self) -> None:
        tiny = _trade("win", 2.0, entry=100.0, stop=98.0, risk=2.0)  # size 1
        out = costs.apply_cost_schedule([tiny], CostSchedule(size_step=10.0))[0]
        assert out["dropped"] is True
        assert out["pnl"] == 0.0
        assert out["effective_risk"] == 0.0
        assert out["r_multiple"] is None

    def test_inputs_not_mutated(self) -> None:
        gross = [_win(), _loss()]
        snapshot = [dict(t) for t in gross]
        costs.apply_cost_schedule(gross, CostSchedule(size_step=1.0))
        assert gross == snapshot


class TestCostsSummary:
    def test_aggregates(self) -> None:
        s = CostSchedule(commission_flat=2.0, exit_slippage_pct=0.1)
        net = costs.apply_cost_schedule([_win(), _loss()], s)
        summary = costs.costs_summary([_win(), _loss()], net, s)
        assert summary["filled_count"] == 2
        assert summary["costed_count"] == 2
        assert summary["dropped_count"] == 0
        assert summary["total_cost"] == pytest.approx(
            (2.0 + 0.001 * 1060) + (2.0 + 0.001 * 970)
        )

    def test_dropped_counted(self) -> None:
        s = CostSchedule(size_step=10.0)
        tiny = _trade("win", 2.0, entry=100.0, stop=98.0, risk=2.0)
        net = costs.apply_cost_schedule([tiny], s)
        assert costs.costs_summary([tiny], net, s)["dropped_count"] == 1


class TestNetMetrics:
    def test_zero_schedule_net_matches_gross_dashboard(self) -> None:
        trades = [_win(), _loss(), _trade("breakeven", 0.0, reason="timeout")]
        m: Any = costs.net_metrics(trades)
        assert m["drags"]["return_drag_pct"] == pytest.approx(0.0)
        assert m["drags"]["expectancy_drag_r"] == pytest.approx(0.0)
        assert m["sign_flips"] == []

    def test_costs_consume_return(self) -> None:
        trades = [_win(), _win(), _loss()]
        m: Any = costs.net_metrics(trades, CostSchedule(commission_flat=5.0, exit_slippage_pct=0.1))
        assert m["costs"]["total_cost"] > 0
        assert m["drags"]["return_drag_pct"] is not None and m["drags"]["return_drag_pct"] > 0.0

    def test_sign_flip_when_edge_destroyed(self) -> None:
        # Thin edge (+0.2R gross) that a $6.5 flat commission flips negative.
        trades = [_trade("win", 1.4), _trade("loss", -1.0, stop=97.0)]
        m: Any = costs.net_metrics(trades, CostSchedule(commission_flat=6.5))
        signals = [f["signal"] for f in m["sign_flips"]]
        assert any("expectancy" in s for s in signals)
        assert m["net"]["trades"]["expectancy"]["expectancy_r"] <= 0.0

    def test_break_even_win_rate_symmetric(self) -> None:
        # avg win R == avg loss R == 1 → break-even 50%.
        m: Any = costs.net_metrics([_trade("win", 1.0), _trade("loss", -1.0, stop=97.0)])
        assert m["break_even_win_rate"]["gross"] == pytest.approx(0.5)
        assert m["break_even_win_rate"]["net"] == pytest.approx(0.5)

    def test_net_portfolio_uses_net_pnl(self) -> None:
        trades = [_win(), _loss()]
        m: Any = costs.net_metrics(trades, CostSchedule(commission_flat=5.0), initial_balance=100.0)
        gross_pnl = 60.0 + -30.0
        net_pnl = m["net"]["portfolio"]["summary"]["total_pnl"]
        assert isinstance(net_pnl, float)
        cost = m["costs"]["total_cost"]
        assert isinstance(cost, float)
        assert net_pnl == pytest.approx(gross_pnl - cost)

    def test_break_even_lift_when_costs_bite(self) -> None:
        trades = [_win(), _win(), _loss()]
        m: Any = costs.net_metrics(trades, CostSchedule(commission_flat=5.0))
        be = m["break_even_win_rate"]
        assert be["required_lift_pp"] is not None and math.isfinite(be["required_lift_pp"])
        assert be["net"] > be["gross"]  # costs make symmetry worse than gross
