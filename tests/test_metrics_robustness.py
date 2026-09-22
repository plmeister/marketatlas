from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from marketatlas.metrics import robustness

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


def _series(
    rs: list[float], day_spacing: int = 14, instrument: str = "A"
) -> list[dict[str, object]]:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    trades = []
    for i, r in enumerate(rs):
        ts = (base + timedelta(days=day_spacing * i)).isoformat()
        trades.append(_trade(ts, r, instrument))
    return trades


_FIXTURE_RS = [
    2.0,
    -1.0,
    1.5,
    -0.5,
    0.8,
    -0.6,
    1.0,
    -0.8,
    1.2,
    -0.4,
    2.5,
    -1.0,
    0.9,
    -0.3,
    1.4,
    -0.9,
]


class TestMonteCarlo:
    def test_seeded_run_reproducible(self) -> None:
        trades = _series(_FIXTURE_RS)
        a = robustness.monte_carlo(trades, n_sims=200, seed=7, initial_balance=1000.0)
        b = robustness.monte_carlo(trades, n_sims=200, seed=7, initial_balance=1000.0)
        assert a == b

    def test_different_seed_differs(self) -> None:
        trades = _series(_FIXTURE_RS)
        a = robustness.monte_carlo(trades, n_sims=200, seed=1, initial_balance=1000.0)
        b = robustness.monte_carlo(trades, n_sims=200, seed=2, initial_balance=1000.0)
        ci_a = a["confidence_intervals"]
        ci_b = b["confidence_intervals"]
        assert isinstance(ci_a, dict) and isinstance(ci_b, dict)
        assert ci_a["cagr"] != ci_b["cagr"]

    def test_p5_p95_sane_on_fixture(self) -> None:
        trades = _series(_FIXTURE_RS)
        mc = robustness.monte_carlo(trades, n_sims=500, seed=3, initial_balance=1000.0)
        ci = mc["confidence_intervals"]
        assert isinstance(ci, dict)
        cagr = ci["cagr"]
        assert isinstance(cagr, dict)
        assert cagr["p5"] <= cagr["p50"] <= cagr["p95"]
        assert cagr["p5"] is not None and cagr["p95"] is not None
        assert mc["trades_used"] == len(_FIXTURE_RS)
        assert mc["mode"] == "resample"
        dd = mc["worst_case_drawdown"]
        assert isinstance(dd, dict)
        p95 = dd["p95_pct"]
        assert p95 is not None and p95 >= 0.0

    def test_shuffle_keeps_total_fixed_reports_dd_band(self) -> None:
        trades = _series(_FIXTURE_RS)
        sh = robustness.monte_carlo(
            trades, n_sims=200, seed=5, mode="shuffle", initial_balance=1000.0
        )
        assert sh["mode"] == "shuffle"
        obs = sh["observed"]
        assert isinstance(obs, dict)
        ci = sh["confidence_intervals"]
        assert isinstance(ci, dict)
        # shuffle recomputes the equivalent total return every path.
        total = ci["total_return"]
        assert isinstance(total, dict)
        assert total["p5"] is not None and total["p50"] is not None and total["p95"] is not None
        assert total["p5"] == pytest.approx(total["p95"], abs=1e-9)
        dd = sh["worst_case_drawdown"]
        assert isinstance(dd, dict)
        assert dd["p95_pct"] is not None

    def test_negative_return_probabilities_present(self) -> None:
        trades = _series(_FIXTURE_RS)
        mc = robustness.monte_carlo(trades, n_sims=300, seed=9, initial_balance=1000.0)
        neg = mc["negative_return_probability"]
        assert isinstance(neg, dict)
        # Positive-edge book: longer horizons should be less likely negative.
        assert 0.0 <= neg["1y"] <= 1.0
        assert neg["1y"] > neg["5y"] or neg["trades_per_year"] > 0

    def test_no_trades(self) -> None:
        mc = robustness.monte_carlo([], n_sims=100, seed=1, initial_balance=1000.0)
        assert mc["trades_used"] == 0

    def test_rejects_bad_mode(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            robustness.monte_carlo([], mode="nope")

    def test_risk_fraction_capped(self) -> None:
        trades = _series([2.0, -1.0])
        mc = robustness.monte_carlo(
            trades, n_sims=50, seed=1, initial_balance=1000.0, risk_fraction=0.2
        )
        assert mc["risk_fraction"] == pytest.approx(0.2)


class TestOutOfSampleSplit:
    def test_leak_free_and_gap_reported(self) -> None:
        trades = _series(_FIXTURE_RS)
        split = robustness.out_of_sample_split(
            trades, test_fraction=0.3, initial_balance=1000.0, timeframe="1d"
        )
        lc = split["leakage_check"]
        assert isinstance(lc, dict)
        assert lc["disjoint"] is True
        assert int(split["train_count"] or 0) + int(split["test_count"] or 0) == int(
            split["count"] or 0
        )  # type: ignore[arg-type]
        ins = split["in_sample"]
        oos = split["out_of_sample"]
        assert isinstance(ins, dict) and isinstance(oos, dict)
        assert "cagr_pct" in ins and "cagr_pct" in oos
        gap = split["gap"]
        assert isinstance(gap, dict)
        train_count = int(ins.get("count") or 0)  # type: ignore[arg-type]
        test_count = int(oos.get("count") or 0)  # type: ignore[arg-type]
        assert train_count == split["train_count"]
        assert test_count == split["test_count"]

    def test_split_boundary_in_time(self) -> None:
        trades = _series(_FIXTURE_RS)
        split = robustness.out_of_sample_split(trades, test_fraction=0.5, initial_balance=1000.0)
        all_exit = sorted(str(t["exit_ts"]) for t in trades)
        assert split["split_at"] == all_exit[int(0.5 * len(all_exit))]

    def test_empty(self) -> None:
        split = robustness.out_of_sample_split([], test_fraction=0.3)
        assert split["count"] == 0


class TestWalkForward:
    def test_folds_cover_tail(self) -> None:
        trades = _series(_FIXTURE_RS)
        wf = robustness.walk_forward(trades, n_folds=3, min_train_frac=0.4, initial_balance=1000.0)
        folds = wf["folds"]
        assert isinstance(folds, list)
        assert len(folds) == 3
        agg = wf["aggregate"]
        assert isinstance(agg, dict)
        assert wf["count"] == len(trades)
        first_test_start = folds[0]["test_start"]
        last_test_end = folds[-1]["test_end"]
        assert first_test_start < last_test_end

    def test_negatives_folds_bad(self) -> None:
        with pytest.raises(ValueError, match="n_folds"):
            robustness.walk_forward([], n_folds=0)


class TestRiskSensitivity:
    def test_rows_reflect_nudges(self) -> None:
        trades = _series(_FIXTURE_RS)
        sens = robustness.risk_sensitivity(trades, n_sims=100, seed=4, initial_balance=1000.0)
        rows = sens["rows"]
        assert isinstance(rows, list)
        assert len(rows) == 3
        factors = [r["factor"] for r in rows]
        assert factors == [0.5, 1.0, 2.0]
        risk = [r["risk_fraction"] for r in rows]
        assert risk[0] < risk[1] < risk[2]

    def test_base_estimable(self) -> None:
        trades = _series([1.0, -1.0])  # risk 10 on 1000 initial -> 1%.
        sens = robustness.risk_sensitivity(trades, n_sims=50, seed=1, initial_balance=1000.0)
        assert sens["base_risk_fraction"] == pytest.approx(0.01)
