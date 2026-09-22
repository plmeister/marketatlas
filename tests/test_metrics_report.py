from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.metrics import report
from marketatlas.metrics.costs import CostSchedule

pytestmark = pytest.mark.tier1


def _trade(ts: str, r: float, instrument: str = "A") -> dict[str, object]:
    risk = 10.0
    return {
        "submit_ts": ts,
        "entry_ts": ts,
        "exit_ts": ts,
        "instrument": instrument,
        "direction": "bullish",
        "result": "win" if r > 0 else "loss",
        "exit_reason": "target" if r > 0 else "stop",
        "pnl": r * risk,
        "risk_amount": risk,
        "r_multiple": r,
        "entry": 100.0,
        "stop": 97.0,
        "target": 106.0,
    }


def _series(rs: list[float]) -> list[dict[str, object]]:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return [_trade((base + timedelta(days=14 * i)).isoformat(), r) for i, r in enumerate(rs)]


_RS = [2.0, -1.0, 1.5, -0.5, 0.8, -0.6, 1.0, -0.8, 1.2, -0.4, 2.5, -1.0, 0.9, -0.3, 1.4, -0.9]


class TestBuildReport:
    def test_all_layers_populated(self) -> None:
        trades = _series(_RS)
        rep = report.build_report(
            trades,
            initial_balance=1000.0,
            timeframe="1d",
            n_sims=200,
            seed=1,
            trades_by_instrument={"A": trades},
        )
        assert set(rep) >= {"source", "verdict", "trades", "portfolio", "robustness"}
        src = rep["source"]
        assert isinstance(src, dict)
        assert src["trades"] == len(_RS)
        assert src["instruments"] == ["A"]
        verdict = rep["verdict"]
        assert isinstance(verdict, dict)
        assert isinstance(verdict["line"], str)
        assert "CAGR" in verdict["line"]
        rob = rep["robustness"]
        assert isinstance(rob, dict)
        assert set(rob) >= {"monte_carlo", "shuffle_order", "out_of_sample", "walk_forward"}
        assert rob["parameter_sensitivity"]["rows"]  # type: ignore[index]
        per_period = rob["per_period"]
        assert isinstance(per_period, dict)
        assert "annual" in per_period
        per_inst = rob["per_instrument"]
        assert isinstance(per_inst, dict)
        assert per_inst["by_instrument"]["A"]["count"] == len(_RS)  # type: ignore[index]

    def test_verdict_reliable_when_p5_positive(self) -> None:
        # Strong edge: all trades win -> MC p5 clearly positive.
        trades = _series([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        rep = report.build_report(trades, initial_balance=1000.0, n_sims=200, seed=2)
        verdict = rep["verdict"]
        assert isinstance(verdict, dict)
        mc = verdict["mc_cagr_p5_pct"]
        assert mc is not None and mc > 0.0
        assert verdict["reliable"] is True

    def test_net_layer_present_only_with_schedule(self) -> None:
        trades = _series(_RS)
        without = report.build_report(trades, initial_balance=1000.0, n_sims=50, seed=1)
        assert "net" not in without
        sched = CostSchedule(commission_flat=5.0)
        with_costs = report.build_report(
            trades, initial_balance=1000.0, n_sims=50, seed=1, cost_schedule=sched
        )
        net = with_costs.get("net")
        assert isinstance(net, dict)
        assert net["costs"]["total_cost"] > 0
        assert "net" in net and "portfolio" in net["net"] and "trades" in net["net"]

    def test_empty_trades_handled(self) -> None:
        rep = report.build_report([], n_sims=10, seed=1)
        verdict = rep["verdict"]
        assert isinstance(verdict, dict)
        assert "no CAGR" in verdict["line"]
        assert rep["source"]["trades"] == 0  # type: ignore[index]

    def test_json_serializable(self) -> None:
        trades = _series(_RS)
        rep = report.build_report(trades, initial_balance=1000.0, n_sims=100, seed=3)
        json.dumps(rep)


class TestTextFormat:
    def test_section_headers_present(self) -> None:
        trades = _series(_RS)
        rep = report.build_report(trades, initial_balance=1000.0, n_sims=100, seed=4)
        text = report.format_report_text(rep)
        assert "METRICS REPORT" in text
        assert "Trade-level (099" in text
        assert "Portfolio / equity (100" in text
        assert "Robustness (102" in text
        assert "Expectancy" in text
        assert "CAGR" in text

    def test_empty_trades_text(self) -> None:
        rep = report.build_report([], n_sims=10, seed=1)
        assert "no CAGR" in report.format_report_text(rep)


class TestSourceFromJson:
    def _single_doc(self) -> dict[str, object]:
        return {
            "symbol": "TEST",
            "timeframe": "1d",
            "trades": _series(_RS),
            "equity_curve": [{"t": "2024-01-01T00:00:00", "balance": 1000.0}],
        }

    def _portfolio_doc(self) -> dict[str, object]:
        return {
            "summary": {},
            "instruments": ["A", "B"],
            "per_instrument": {
                "A": {"timeframe": "1d", "trades": _series([1.0, -1.0])},
                "B": {"timeframe": "1d", "trades": _series([0.5, -0.5])},
            },
            "equity_curve": [{"t": "2024-01-01T00:00:00", "balance": 1000.0}],
        }

    def test_single_doc(self) -> None:
        trades, curve, instruments, tf = report.report_source_from_json(self._single_doc())
        assert len(trades) == len(_RS)
        assert instruments == ["TEST"]
        assert tf == "1d"
        assert curve[0]["balance"] == 1000.0

    def test_portfolio_doc_flattens_in_instrument_order(self) -> None:
        trades, curve, instruments, tf = report.report_source_from_json(self._portfolio_doc())
        assert len(trades) == 4
        assert instruments == ["A", "B"]
        assert tf == "1d"
        assert len(curve) == 1

    def test_no_trades(self) -> None:
        trades, curve, _inst, _tf = report.report_source_from_json({"symbol": "X"})
        assert trades == []
        assert curve == []

    def test_bad_trades_skipped(self) -> None:
        doc = {"symbol": "X", "trades": [{"not": "a trade"}, 42, "nope"]}
        trades, *_ = report.report_source_from_json(doc)
        assert len(trades) == 1  # dict entries kept; ints/strings filtered
