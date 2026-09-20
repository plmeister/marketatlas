from __future__ import annotations

import statistics
from datetime import datetime

import pytest
from marketatlas.frames import jsoncodec
from marketatlas.metrics import stats
from marketatlas.metrics.trades import trade_metrics

pytestmark = pytest.mark.tier1


def _trade(
    result: str,
    r: float,
    mfe_r: float | None = None,
    mae_r: float | None = None,
    reason: str = "target",
    direction: str = "bullish",
    entry: str = "2026-01-01T00:00:00",
    exit: str = "2026-01-02T00:00:00",
    submit: str | None = None,
    pnl: float | None = None,
    risk: float = 20.0,
) -> dict[str, object]:
    return {
        "submit_ts": submit or entry,
        "entry_ts": entry,
        "exit_ts": exit,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "direction": direction,
        "result": result,
        "exit_reason": reason,
        "pnl": pnl if pnl is not None else r * risk,
        "risk_amount": risk,
        "r_multiple": r,
    }


def _fixture() -> list[dict[str, object]]:
    return [
        _trade("win", 2.0, mfe_r=4.0, mae_r=0.8, reason="target",
               entry="2026-01-01T00:00:00", exit="2026-01-02T00:00:00"),
        _trade("loss", -1.0, mfe_r=0.5, mae_r=1.0, reason="stop",
               entry="2026-01-02T00:00:00", exit="2026-01-04T00:00:00"),
        _trade("win", 1.0, mfe_r=2.0, mae_r=0.5, reason="target", direction="bearish",
               entry="2026-01-03T00:00:00", exit="2026-01-03T12:00:00", risk=10.0),
        _trade("breakeven", 0.0, mfe_r=1.2, mae_r=1.0, reason="timeout",
               entry="2026-01-04T00:00:00", exit="2026-01-05T00:00:00"),
        _trade("cancelled", 0.0, reason="cancel",
               entry="2026-01-05T00:00:00", exit="2026-01-06T00:00:00",
               submit="2026-01-05T00:00:00"),
    ]


class TestCountsAndRates:
    def test_counts(self) -> None:
        m = trade_metrics(_fixture())
        c = m["counts"]
        assert c["total"] == 5
        assert c["wins"] == 2
        assert c["losses"] == 1
        assert c["breakevens"] == 1
        assert c["cancelled"] == 1
        assert c["filled"] == 4
        assert c["decided"] == 3

    def test_win_rate_both_denominators(self) -> None:
        wr = trade_metrics(_fixture())["win_rate"]
        assert wr["decided"] == pytest.approx(2 / 3)
        assert wr["all"] == pytest.approx(0.4)

    def test_empty(self) -> None:
        m = trade_metrics([])
        assert m["counts"] == {"wins": 0, "losses": 0, "breakevens": 0,
                               "cancelled": 0, "total": 0, "filled": 0, "decided": 0}
        assert m["win_rate"]["decided"] == 0.0
        assert m["expectancy"]["expectancy_r"] is None
        assert m["profit_factor"]["profit_factor_r"] is None


class TestRAveragesAndExpectancy:
    def test_avg_r(self) -> None:
        avg = trade_metrics(_fixture())["avg_r"]
        assert avg["win_r_mean"] == pytest.approx(1.5)
        assert avg["win_r_median"] == pytest.approx(1.5)
        assert avg["loss_r_mean"] == pytest.approx(1.0)
        assert avg["loss_r_median"] == pytest.approx(1.0)
        assert avg["payoff_ratio_r"] == pytest.approx(1.5)

    def test_expectancy(self) -> None:
        e = trade_metrics(_fixture())["expectancy"]
        assert e["expectancy_r"] == pytest.approx(0.4)  # cancels R=0 count
        assert e["expectancy_decided_r"] == pytest.approx(2 / 3)

    def test_profit_factor(self) -> None:
        pf = trade_metrics(_fixture())["profit_factor"]
        assert pf["gross_profit_r"] == pytest.approx(3.0)
        assert pf["gross_loss_r"] == pytest.approx(1.0)
        assert pf["profit_factor_r"] == pytest.approx(3.0)

    def test_zero_gross_loss_pf_is_none(self) -> None:
        trades = [_trade("win", 2.0), _trade("win", 1.0)]
        pf = trade_metrics(trades)["profit_factor"]
        assert pf["gross_loss_r"] == 0.0
        assert pf["profit_factor_r"] is None


class TestRDistribution:
    def test_distribution_metrics(self) -> None:
        d = trade_metrics(_fixture())["r_distribution"]
        assert d["count"] == 3
        assert d["min"] == pytest.approx(-1.0)
        assert d["max"] == pytest.approx(2.0)
        p = d["percentiles"]
        assert p["p50"] == pytest.approx(1.0)
        assert p["p25"] == pytest.approx(0.0)
        assert p["p75"] == pytest.approx(1.5)
        assert p["p1"] == pytest.approx(-0.96)
        assert d["max_win_r"] == pytest.approx(2.0)
        assert d["max_loss_r"] == pytest.approx(-1.0)
        assert d["max_loss_magnitude_r"] == pytest.approx(1.0)
        # hand-computed population skew/kurtosis on [-1, 1, 2]
        assert d["skew"] == pytest.approx(-10 / (7 * 14**0.5), abs=1e-9)
        assert d["kurtosis"] == pytest.approx(-1.5)
        hist = d["histogram"]
        assert sum(hist["counts"]) == 3
        assert hist["edges"][-1] == pytest.approx(2.0)

    def test_single_trade(self) -> None:
        d = trade_metrics([_trade("win", 2.0)])["r_distribution"]
        assert d["min"] == d["max"] == pytest.approx(2.0)
        assert d["skew"] is None
        assert d["kurtosis"] is None

    def test_all_breakeven(self) -> None:
        m = trade_metrics([_trade("breakeven", 0.0), _trade("breakeven", 0.0)])
        d = m["r_distribution"]
        assert d["skew"] is None
        assert d["kurtosis"] is None
        assert d["percentiles"]["p50"] is None
        assert m["counts"] == {"wins": 0, "losses": 0, "breakevens": 2, "cancelled": 0,
                               "total": 2, "filled": 2, "decided": 0}


class TestDuration:
    def test_duration(self) -> None:
        dur = trade_metrics(_fixture())["duration"]
        assert dur["mean_hours"] == pytest.approx((24 + 48 + 12 + 24 + 24) / 5)
        assert dur["median_hours"] == pytest.approx(24.0)
        win = dur["by_outcome"]["win"]
        assert win["mean_hours"] == pytest.approx(18.0)
        assert dur["by_outcome"]["loss"]["mean_hours"] == pytest.approx(48.0)
        assert dur["by_outcome"]["breakeven"]["mean_hours"] == pytest.approx(24.0)
        assert dur["by_outcome"]["cancelled"]["mean_hours"] == pytest.approx(24.0)

    def test_missing_timestamps_skipped(self) -> None:
        t = _trade("win", 1.0)
        t["exit_ts"] = None
        m = trade_metrics([t])
        assert m["duration"]["mean_hours"] is None


class TestMfeExitQuality:
    def test_left_on_table(self) -> None:
        m = trade_metrics(_fixture())["mfe_exit_quality"]
        assert m["winners_with_mfe"] == 2
        reached = m["mfe_exceeded_but_exited_less"]
        # T1 MFE'd 4R, exited at 2R; T3 MFE'd 2R, exited at 1R.
        assert reached["1r"]["count"] == 0  # both realized beyond 1R
        assert reached["2r"]["count"] == 1  # T3 (exited at exactly 1R < 2R)
        assert reached["3r"]["count"] == 1  # T1
        assert reached["4r"]["count"] == 1  # T1
        assert reached["4r"]["pct_of_winners"] == pytest.approx(0.5)
        assert m["exit_below_mfe_mean_r"] == pytest.approx(1.5)
        assert m["exit_below_mfe_median_r"] == pytest.approx(1.5)

    def test_hand_built_mfe3_close1r(self) -> None:
        # Trade that MFE'd 3R then realized 1R must be flagged as 3R/4R left.
        t = _trade("win", 1.0, mfe_r=3.0)
        reached = trade_metrics([t])["mfe_exit_quality"]["mfe_exceeded_but_exited_less"]
        assert reached["3r"]["count"] == 1
        assert reached["2r"]["count"] == 1
        assert reached["1r"]["count"] == 0
        assert reached["3r"]["pct_of_winners"] == 1.0


class TestMae:
    def test_mae_distribution(self) -> None:
        mae = trade_metrics(_fixture())["mae"]
        assert mae["over_filled_count"] == 4
        assert mae["mean_r"] == pytest.approx((0.8 + 1.0 + 0.5 + 1.0) / 4)
        assert mae["median_r"] == pytest.approx(0.9)
        assert mae["p95_r"] == pytest.approx(1.0)
        assert mae["median_loss_r"] == pytest.approx(1.0)


class TestExitBreakdown:
    def test_breakdown_shares_and_win_rate(self) -> None:
        bd = trade_metrics(_fixture())["exit_breakdown"]
        stop = bd["stop"]
        assert stop["count"] == 1
        assert stop["share_pct"] == pytest.approx(20.0)
        assert stop["win_rate"] == 0.0
        assert stop["avg_r"] == pytest.approx(-1.0)
        target = bd["target"]
        assert target["count"] == 2
        assert target["share_pct"] == pytest.approx(40.0)
        assert target["win_rate"] == 1.0
        assert target["avg_r"] == pytest.approx(1.5)
        assert bd["timeout"]["count"] == 1
        assert bd["cancel"]["count"] == 1
        assert "reversal" not in bd


class TestFrequency:
    def test_frequency(self) -> None:
        f = trade_metrics(_fixture())["frequency"]
        assert f["elapsed_days"] == pytest.approx(5.0)
        assert f["trades_per_day"] == pytest.approx(1.0)
        assert f["trades_per_week"] == pytest.approx(7.0)
        assert f["trades_per_month"] == pytest.approx(365.25 / 12.0)


class TestReach:
    def test_reach_by_realized_and_mfe(self) -> None:
        r = trade_metrics(_fixture())["reach"]
        assert r["by_realized"]["1r"]["pct"] == pytest.approx(0.5)  # 2/4 filled
        assert r["by_realized"]["1r"]["count"] == 2
        assert r["by_realized"]["2r"]["pct"] == pytest.approx(0.25)
        assert r["by_realized"]["3r"]["pct"] == 0.0
        assert r["by_realized"]["4r"]["pct"] == 0.0
        assert r["by_mfe"]["1r"]["pct"] == pytest.approx(0.75)
        assert r["by_mfe"]["2r"]["pct"] == pytest.approx(0.5)
        assert r["by_mfe"]["3r"]["pct"] == pytest.approx(0.25)
        assert r["by_mfe"]["4r"]["pct"] == pytest.approx(0.25)

    def test_reach_by_direction(self) -> None:
        d = trade_metrics(_fixture())["reach"]["by_direction"]
        assert d["bullish"]["trades"] == 3
        assert d["bullish"]["by_realized"]["1r"]["pct"] == pytest.approx(1 / 3)
        assert d["bullish"]["by_mfe"]["1r"]["pct"] == pytest.approx(2 / 3)
        assert d["bearish"]["trades"] == 1
        assert d["bearish"]["by_realized"]["1r"]["pct"] == 1.0
        assert d["bearish"]["by_mfe"]["2r"]["pct"] == 1.0


class TestStatsHelpers:
    def test_percentile_linear_interp(self) -> None:
        values = [-1.0, 1.0, 2.0]
        assert stats.percentile(values, 0.0) == -1.0
        assert stats.percentile(values, 1.0) == 2.0
        assert stats.percentile(values, 0.5) == pytest.approx(1.0)
        assert stats.percentile(values, 0.25) == pytest.approx(0.0)
        assert stats.percentile([], 0.5) is None

    def test_median_matches_statistics(self) -> None:
        values = [3.0, 1.0, 4.0, 1.5, 2.0]
        assert stats.median(values) == pytest.approx(statistics.median(values))
        assert stats.median(values) == pytest.approx(stats.percentile(values, 0.5))

    def test_histogram_edges(self) -> None:
        h = stats.histogram([1.0, 2.0, 3.0, 4.0], n_bins=3)
        edges = h["edges"]
        counts = h["counts"]
        assert len(edges) == 4
        assert edges[-1] == 4.0
        assert sum(counts) == 4  # type: ignore[arg-type]

    def test_histogram_degenerate(self) -> None:
        assert stats.histogram([]) == {"edges": [], "counts": []}
        h = stats.histogram([2.0, 2.0])
        assert h["counts"] == [2]  # type: ignore[arg-type]

    def test_skew_kurtosis_when_undefined(self) -> None:
        assert stats.skewness([1.0, 2.0]) is None
        assert stats.kurtosis([1.0, 2.0]) is None
        assert stats.skewness([1.0, 1.0, 1.0]) is None
        assert stats.kurtosis([1.0, 1.0, 1.0]) is None


class TestJsoncodecAlignment:
    def test_consumes_enriched_json(self) -> None:
        """trade_metrics must ingest the dicts jsoncodec._trade_to_dict emits."""
        tb = _build_book()
        encoded = jsoncodec._trade_to_dict(tb.trades[0])
        for key in ("submit_ts", "entry_ts", "exit_ts", "mfe_r", "mae_r", "direction",
                    "result", "exit_reason", "pnl", "risk_amount", "r_multiple"):
            assert key in encoded
        m = trade_metrics([encoded])
        assert m["counts"]["total"] == 1
        assert m["counts"]["wins"] == 1
        assert m["win_rate"]["decided"] == 1.0
        assert m["expectancy"]["expectancy_r"] == pytest.approx(encoded["r_multiple"])


def _build_book():
    from marketatlas.data.types import Candle
    from marketatlas.facts.structural import TrendDirection
    from marketatlas.strategy.signals import TradeSignal
    from marketatlas.strategy.trade import ExitReason, TradeCandidate
    from marketatlas.strategy.tradebook import TradeBook

    signal = TradeSignal(
        direction=TrendDirection.BULLISH,
        entry_zone=(99.0, 101.0),
        confidence=0.8,
        source="test",
        evidence=(),
    )
    candidate = TradeCandidate(
        direction=TrendDirection.BULLISH,
        entry=100.0,
        stop=95.0,
        target=115.0,
        size=0.2,
        risk_amount=1.0,
        reward_amount=3.0,
        rr_ratio=3.0,
        slippage_pct=0.0,
        source="test",
        evidence=(),
    )
    book = TradeBook(initial_balance=1000.0)
    ts = datetime(2026, 1, 1)
    book.submit_order(candidate, signal, "t", ts, instrument="")
    book.fill_order(Candle(timestamp=ts, open=100.0, high=103.0, low=99.0, close=102.0, volume=1000.0))
    book.close_trade(115.0, ts, "", reason=ExitReason.TARGET)
    return book