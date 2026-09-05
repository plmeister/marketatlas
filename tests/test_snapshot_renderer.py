"""Tests for the static PNG snapshot renderer (matplotlib optional)."""

import pytest
from marketatlas.visualization import snapshot as snp

matplotlib = pytest.importorskip("matplotlib", reason="requires snapshots extra")


def _sample_output(poi):
    from datetime import UTC, datetime, timedelta

    from marketatlas.analysis.factkey import FactKey
    from marketatlas.data.types import Candle
    from marketatlas.facts.pattern import PullbackFact
    from marketatlas.facts.structural import (
        SRFact,
        SRLevel,
        SwingFact,
        SwingPoint,
        SwingStructureFact,
        SwingType,
        TrendDirection,
        TrendFact,
    )
    from marketatlas.frames.frame import AnalysisFrame
    from marketatlas.frames.output import AnalysisOutput

    start = datetime(2024, 1, 1, tzinfo=UTC)
    candles = []
    px = 100.0
    for i in range(160):
        ts = start + timedelta(days=i)
        px += 0.3 + (-0.6 if i % 7 == 3 else 0.3)
        candles.append(
            Candle(ts, px - 0.3, px + 1.2, px - 1.1, px, 1000.0)
        )

    frame = AnalysisFrame(
        timestamp=poi,
        candle=candles[120],
        facts={
            FactKey("sr"): SRFact(
                timestamp=poi, evidence=(),
                levels=(
                    SRLevel(97.0, 2, "support"),
                    SRLevel(103.0, 3, "resistance"),
                ),
            ),
            FactKey("swing"): SwingFact(
                timestamp=poi, evidence=(),
                swings=(
                    SwingPoint(97.0, 100, SwingType.LOW, start + timedelta(days=100)),
                    SwingPoint(102.0, 106, SwingType.HIGH, start + timedelta(days=106)),
                ),
            ),
            FactKey("structure"): SwingStructureFact(
                timestamp=poi, evidence=(),
                points=(
                    SwingPoint(97.0, 100, SwingType.LOW, start + timedelta(days=100)),
                    SwingPoint(102.0, 106, SwingType.HIGH, start + timedelta(days=106)),
                ),
            ),
            FactKey("pullback"): PullbackFact(
                timestamp=poi, evidence=(),
                direction=TrendDirection.BULLISH,
                swing_pattern=(97.0, 102.0, 99.5), strength=0.7,
            ),
            FactKey("trend"): TrendFact(
                timestamp=poi, evidence=(),
                direction=TrendDirection.BULLISH, strength=0.8,
            ),
        },
        evidence=(),
    )
    return AnalysisOutput(
        symbol="TEST",
        timeframe="d1",
        timeframes=("d1",),
        candles={"d1": tuple(candles)},
        frames=(frame,),
        trades=(),
        summary=None,  # type: ignore[arg-type]
        window_size=50,
        max_hold_days=20,
        title="TEST",
    )


class TestSnapshotRenderer:
    def test_render_trade_snapshot_writes_png(self, tmp_path):
        from datetime import UTC, datetime, timedelta

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        out = snp.render_trade_snapshot(
            _sample_output(poi), poi,
            tmp_path / "poi.png",
            entry=100.5, stop=96.0, target=104.0,
            direction="bullish", result="win", pnl=123.4,
        )
        assert out.exists()
        assert out.stat().st_size > 0
        assert out.suffix == ".png"

    def test_overlay_sr_adds_labels_with_price_and_strength(self):
        from datetime import UTC, datetime, timedelta

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        output = _sample_output(poi)
        facts = snp._facts_at(output, poi)
        assert facts is not None
        shapes = snp._overlay_sr(facts, (90.0, 110.0))
        hlines = [s for s in shapes if s["kind"] == "hline"]
        texts = [s for s in shapes if s["kind"] == "text"]
        assert len(hlines) >= 2
        # labels carry both price and strength on the line itself
        assert any("s2" in t["text"] for t in texts)
        assert any("97" in t["text"] for t in texts)
        # labels extend past the right edge (axes-fraction x) at the line's y
        assert all(t["x_axes"] > 1.0 and not t.get("x") for t in texts)
        assert all("y" in t and t["y"] > 0 for t in texts)

    def test_overlay_pullback_draws_swing_connectors(self):
        from datetime import UTC, datetime, timedelta

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        facts = snp._facts_at(_sample_output(poi), poi)
        assert facts is not None
        shapes = snp._overlay_pullbacks(facts, 0, 160)
        kinds = {s["kind"] for s in shapes}
        # pullback pattern now renders as swing-point connector polyline, not noise arrows
        assert "polyline" in kinds and "scatter" in kinds
        poly = next(s for s in shapes if s["kind"] == "polyline")
        assert len(poly["x"]) >= 2

    def test_facts_at_no_lookahead(self):
        from datetime import UTC, datetime, timedelta

        start = datetime(2024, 1, 1, tzinfo=UTC)
        # poi after last candle -> nearest <= poi is last frame
        last = start + timedelta(days=160)
        output = _sample_output(start + timedelta(days=120))
        facts = snp._facts_at(output, last)
        assert facts is not None

    def test_snapshot_basename(self):
        poi = {
            "symbol": "GBPUSD",
            "ts": "2021-02-19T00:00:00+00:00",
            "kind": "trade",
            "direction": "bullish",
            "result": "win",
            "pnl": 97.0,
        }
        assert snp.snapshot_basename(poi) == "GBPUSD_2021-02-19_trade_bullish_win_pnl+97.0.png"

    def test_locate_pois_from_typed_output(self):
        from datetime import UTC, datetime, timedelta

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        po = _portfolio_with(_with_trades(_sample_output(poi), _mk_trade(poi)))
        pois = snp.locate_pois(po, kinds="trade")
        assert len(pois) == 1
        assert pois[0]["symbol"] == "TEST"
        assert pois[0]["pnl"] == 123.4
        assert pois[0]["direction"] == "bullish"

    def test_render_poi_snapshots_from_schema(self, tmp_path):
        import json
        from datetime import UTC, datetime, timedelta

        from marketatlas.frames.jsoncodec import encode_analysis_output

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        output = _with_trades(_sample_output(poi), _mk_trade(poi))
        schema = encode_analysis_output(output)
        # round-trip through JSON to prove schema is the render source
        doc = json.loads(json.dumps({"_": schema}))["_"]

        out_dir = tmp_path / "shots"
        paths = snp.render_poi_snapshots(_schema_wrap(doc), out_dir)
        assert paths
        assert all(p.exists() for p in paths)

    def test_encode_portfolio_roundtrip_locates(self):
        from datetime import UTC, datetime, timedelta

        from marketatlas.frames.jsoncodec import encode_portfolio

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        output = _with_trades(_sample_output(poi), _mk_trade(poi))
        po = _portfolio_with(output)
        doc = encode_portfolio(po)
        assert "per_instrument" in doc
        pois = snp.locate_pois(doc, kinds="trade")
        assert len(pois) == 1
        assert pois[0]["symbol"] == "TEST"

    def test_locate_pois_finds_pattern_and_rejection(self):
        from datetime import UTC, datetime, timedelta

        from marketatlas.evidence.model import EvidenceEntry, EvidenceLevel
        from marketatlas.frames.jsoncodec import encode_analysis_output
        from marketatlas.frames.output import AnalysisOutput

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        base = _sample_output(poi)
        frame = base.frames[0]
        from marketatlas.frames.frame import AnalysisFrame

        frame = AnalysisFrame(
            timestamp=frame.timestamp, candle=frame.candle, facts=frame.facts,
            evidence=frame.evidence, signal_rejections=(
                EvidenceEntry(text="Trend too weak", level=EvidenceLevel.WARNING, source="trend"),
            ),
        )
        out = AnalysisOutput(
            symbol=base.symbol, timeframe=base.timeframe, timeframes=base.timeframes,
            candles=base.candles, frames=(frame,), trades=base.trades,
            summary=base.summary, window_size=base.window_size,
            max_hold_days=base.max_hold_days, title=base.title,
        )
        doc = encode_analysis_output(out)
        pois = snp.locate_pois(_schema_wrap(doc))
        kinds = {p["kind"] for p in pois}
        assert "rejection" in kinds
        assert "pattern" in kinds
        rej = next(p for p in pois if p["kind"] == "rejection")
        assert "trend too weak" in rej["reason"].lower()

    def test_locate_pois_kinds_filter_include_exclude(self):
        from datetime import UTC, datetime, timedelta

        from marketatlas.frames.jsoncodec import encode_analysis_output

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        out = _with_trades(_sample_output(poi), _mk_trade(poi))
        doc = encode_analysis_output(out)
        struct = _schema_wrap(doc)

        all_pois = snp.locate_pois(struct)
        all_kinds = {p["kind"] for p in all_pois}
        assert all_kinds == {"trade", "pattern"}

        trades = snp.locate_pois(struct, kinds="trade")
        assert {p["kind"] for p in trades} == {"trade"}

        patterns = snp.locate_pois(struct, kinds={"pattern"})
        assert {p["kind"] for p in patterns} == {"pattern"}

        no_pattern = snp.locate_pois(struct, kinds="trade,!pattern")
        assert {p["kind"] for p in no_pattern} == {"trade"}

        excl = snp.locate_pois(struct, kinds="trade", exclude_kinds="pattern")
        assert {p["kind"] for p in excl} == {"trade"}

    def test_draw_shapes_renders_all_kinds(self):
        from datetime import UTC, datetime, timedelta

        import matplotlib.pyplot as pl

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        output = _sample_output(poi)
        facts = snp._facts_at(output, poi)
        assert facts is not None
        fig, ax = pl.subplots()
        shapes = snp._overlay_sr(facts, (90.0, 110.0))
        shapes += snp._overlay_pullbacks(facts, 0, 160)
        shapes += snp._trade_box_shapes([{"c": 100.0}, {"c": 100.0}], 0, 10, 98.0, 96.0, 104.0)
        snp.draw_shapes(ax, shapes)
        # rectangle patch + lines/scatter drawn
        assert any(isinstance(pat, pl.Rectangle) for pat in ax.patches)
        assert len(ax.lines) >= 1
        pl.close(fig)

    def test_trade_box_two_sides_translucent(self):
        from datetime import UTC, datetime, timedelta

        import matplotlib.pyplot as pl

        poi = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)
        output = _sample_output(poi)
        facts = snp._facts_at(output, poi)
        assert facts is not None
        fig, ax = pl.subplots()
        box = snp._trade_box_shapes([{"c": 100.0}, {"c": 100.0}], 0, 10, 98.0, 96.0, 104.0)
        snp.draw_shapes(ax, box)
        rects = [p for p in ax.patches if isinstance(p, pl.Rectangle)]
        # stop side (red) + target side (green)
        assert len(rects) == 2
        assert all(0 < r.get_alpha() < 1.0 for r in rects)
        colors = {r.get_facecolor() for r in rects}
        assert len(colors) == 2
        pl.close(fig)


def _mk_trade(entry_timestamp):
    from datetime import timedelta

    from marketatlas.facts.structural import TrendDirection
    from marketatlas.strategy.signals import TradeSignal
    from marketatlas.strategy.trade import TradeCandidate
    from marketatlas.strategy.tradebook import TradeOutcome

    cand = TradeCandidate(
        direction=TrendDirection.BULLISH, entry=100.0, stop=96.0, target=104.0,
        size=2.0, risk_amount=10.0, reward_amount=20.0, rr_ratio=2.0,
        slippage_pct=0.0, source="test", evidence=(),
    )
    signal = TradeSignal(
        direction=TrendDirection.BULLISH, entry_zone=(99.5, 100.5),
        confidence=0.8, source="test", evidence=(),
    )
    return TradeOutcome(
        submit_time=entry_timestamp, entry_timestamp=entry_timestamp,
        exit_timestamp=entry_timestamp + timedelta(days=3), candidate=cand,
        signal=signal, source_strategy="swing", instrument="TEST", pnl=123.4,
        result="win",
    )


def _with_trades(output, trade):
    from marketatlas.frames.output import AnalysisOutput

    return AnalysisOutput(
        symbol=output.symbol, timeframe=output.timeframe, timeframes=output.timeframes,
        candles=output.candles, frames=output.frames, trades=(trade,),
        summary=output.summary, window_size=output.window_size,
        max_hold_days=output.max_hold_days, title=output.title,
    )


def _empty_summary():
    from marketatlas.frames.output import AnalysisSummary

    return AnalysisSummary(
        initial_balance=1000.0, final_balance=1123.4, total_pnl=123.4,
        total_return_pct=12.34, total_trades=1, wins=1, losses=0, breakevens=0,
        win_rate=1.0, peak_balance=1123.4, max_drawdown=0.0, gross_profit=123.4,
        gross_loss=0.0, profit_factor=1.0, avg_win=123.4, avg_loss=0.0,
        expectancy=123.4, by_strategy={}, by_instrument={},
    )


def _portfolio_with(output):
    from marketatlas.frames.output import PortfolioOutput

    return PortfolioOutput(
        summary=_empty_summary(), by_instrument={}, outputs={"TEST": output},
        monthly={}, instruments=("TEST",), window_size=50,
        max_hold_days=20, title="TEST",
    )


def _schema_wrap(schema):
    return {
        "per_instrument": {"TEST": schema},
        "instruments": ["TEST"],
        "summary": {},
        "monthly": {},
    }
