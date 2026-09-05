"""Tests for manual annotation sidecar notes (backlog 096)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from marketatlas.frames.jsoncodec import encode_analysis_output
from marketatlas.visualization import notes
from marketatlas.visualization import snapshot as snp


class TestNotes:
    def test_note_path_swaps_extension(self) -> None:
        p = notes.note_path("output/snapshots/EURUSD_2026-03-27.png")
        assert p == Path("output/snapshots/EURUSD_2026-03-27.txt")

    def test_read_note_missing_is_none(self, tmp_path: Path) -> None:
        png = tmp_path / "a.png"
        png.write_bytes(b"x")
        assert notes.read_note(png) is None

    def test_read_note_empty_vs_content(self, tmp_path: Path) -> None:
        png = tmp_path / "a.png"
        png.write_bytes(b"x")
        notes.write_note(png, "")
        assert notes.read_note(png) == ""

        png2 = tmp_path / "b.png"
        png2.write_bytes(b"x")
        notes.write_note(png2, "reviewed")
        assert notes.read_note(png2) == "reviewed"

    def test_iter_notes_missing_and_empty_discriminated(self, tmp_path: Path) -> None:
        (tmp_path / "no_sidecar.png").write_bytes(b"x")
        (tmp_path / "empty.png").write_bytes(b"x")
        notes.write_note(tmp_path / "empty.png", "")
        (tmp_path / "full.png").write_bytes(b"x")
        notes.write_note(tmp_path / "full.png", "some verdict")

        result = dict(notes.iter_notes(tmp_path))
        # only PNGs present, deterministic alphabetical ordering
        assert list(result.keys()) == [
            tmp_path / "empty.png",
            tmp_path / "full.png",
            tmp_path / "no_sidecar.png",
        ]
        assert result[tmp_path / "empty.png"] == ""  # reviewed, no action
        assert result[tmp_path / "full.png"] == "some verdict"
        assert result[tmp_path / "no_sidecar.png"] is None  # not yet reviewed

    def test_iter_notes_empty_dir_yields_nothing(self, tmp_path: Path) -> None:
        assert list(notes.iter_notes(tmp_path / "nope")) == []

    def test_write_note_idempotent_and_preserves_wording(self, tmp_path: Path) -> None:
        png = tmp_path / "x.png"
        png.write_bytes(b"x")
        assert notes.write_note(png, "") == notes.write_note(png, "")
        assert notes.read_note(png) == ""
        notes.write_note(png, "stop too tight, widen to 2ATR")
        assert notes.read_note(png) == "stop too tight, widen to 2ATR"


class TestNotesRender:
    def _poi(self) -> datetime:
        return datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=120)

    def _struct(self) -> dict:
        pytest.importorskip("matplotlib", reason="requires snapshots extra")

        from marketatlas.data.types import Candle
        from marketatlas.facts.structural import TrendDirection
        from marketatlas.frames.frame import AnalysisFrame
        from marketatlas.frames.output import AnalysisOutput
        from marketatlas.strategy.signals import TradeSignal
        from marketatlas.strategy.trade import TradeCandidate
        from marketatlas.strategy.tradebook import TradeOutcome

        poi = self._poi()
        start = datetime(2024, 1, 1, tzinfo=UTC)
        candles = tuple(
            Candle(start + timedelta(days=i), 99.0, 101.0, 98.0, 100.0, 1000.0)
            for i in range(160)
        )
        frame = AnalysisFrame(
            timestamp=poi, candle=candles[120], facts={}, evidence=(),
        )
        cand = TradeCandidate(
            direction=TrendDirection.BULLISH, entry=100.0, stop=96.0,
            target=104.0, size=2.0, risk_amount=10.0, reward_amount=20.0,
            rr_ratio=2.0, slippage_pct=0.0, source="test", evidence=(),
        )
        signal = TradeSignal(
            direction=TrendDirection.BULLISH, entry_zone=(99.5, 100.5),
            confidence=0.8, source="test", evidence=(),
        )
        outcome = TradeOutcome(
            submit_time=poi, entry_timestamp=poi,
            exit_timestamp=poi + timedelta(days=3), candidate=cand,
            signal=signal, source_strategy="swing", instrument="TEST",
            pnl=123.4, result="win",
        )
        out = AnalysisOutput(
            symbol="TEST", timeframe="d1", timeframes=("d1",),
            candles={"d1": candles}, frames=(frame,), trades=(outcome,),
            summary=None,  # type: ignore[arg-type]
            window_size=50, max_hold_days=20, title="TEST",
        )
        doc = json.loads(json.dumps(encode_analysis_output(out)))
        return {"per_instrument": {"TEST": doc}, "instruments": ["TEST"]}

    def test_render_without_notes_no_txt_files(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "shots"
        pngs = snp.render_poi_snapshots(self._struct(), out_dir,
                                        kinds="trade", write_notes=False)
        assert pngs and all(p.suffix == ".png" for p in pngs)
        assert not list(out_dir.glob("*.txt"))

    def test_render_with_notes_drops_txt_templates(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "shots"
        pngs = snp.render_poi_snapshots(self._struct(), out_dir,
                                        kinds="trade", write_notes=True)
        assert pngs
        for png in pngs:
            assert notes.note_path(png).exists()
            assert notes.read_note(png) == ""
