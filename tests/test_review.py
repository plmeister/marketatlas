"""Tests for the review agent (097): notes -> context bundles -> suggestions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from marketatlas.frames.jsoncodec import encode_fact
from marketatlas.review import NullProvider, iter_review, make_provider
from marketatlas.review.prompt import build_prompt

pytestmark = pytest.mark.tier2


def _mk_struct() -> dict:
    """A minimal per-instrument JSON doc exercising all three POI kinds."""
    from marketatlas.facts.structural import TrendDirection, TrendFact

    ts_trade = datetime(2024, 1, 19, tzinfo=UTC).isoformat()
    ts_rej = datetime(2024, 1, 20, tzinfo=UTC).isoformat()
    ts_pat = datetime(2024, 1, 21, tzinfo=UTC).isoformat()
    trend = encode_fact(
        TrendFact(
            timestamp=datetime(2024, 1, 19, tzinfo=UTC),
            evidence=(),
            direction=TrendDirection.BULLISH,
            strength=0.8,
        )
    )
    return {
        "per_instrument": {
            "GBPUSD": {
                "symbol": "GBPUSD",
                "timeframe": "d1",
                "timeframes": ["d1"],
                "max_hold_days": 10,
                "candles": {},
                "facts_by_ts": {ts_trade: {"trend": trend}},
                "patterns_by_ts": {
                    ts_pat: {"pullback": {"__cls": "marketatlas.facts.pattern.PullbackFact"}}
                },
                "rejections_by_ts": {
                    ts_rej: [{"text": "Signal blocked by resistance", "level": "WARNING"}]
                },
                "trades": [
                    {
                        "submit_ts": ts_trade,
                        "entry_ts": ts_trade,
                        "entry": 105.0,
                        "stop": 100.0,
                        "target": 115.0,
                        "direction": "bullish",
                        "result": "win",
                        "pnl": 50.0,
                        "rr_ratio": 2.0,
                    }
                ],
            }
        }
    }


def _write_png(dir: Path, name: str):
    p = dir / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    return p


def _write_note(dir: Path, png_name: str, text: str):
    png = _write_png(dir, png_name)
    note = png.with_suffix(".txt")
    note.write_text(text, encoding="utf-8")
    return png


TRADE_PNG = "GBPUSD_2024-01-19_trade_bullish_win_pnl+50.0.png"
REJ_PNG = "GBPUSD_2024-01-20_rejection_signal_blocked_by_resistance.png"
PAT_PNG = "GBPUSD_2024-01-21_pattern_pullback.png"


class TestJoin:
    def test_notes_join_pois(self, tmp_path: Path):
        _write_note(tmp_path, TRADE_PNG, "Stop too tight, stopped before target.")
        _write_note(tmp_path, REJ_PNG, "")
        _write_note(tmp_path, PAT_PNG, "False pattern here.")
        res = iter_review(tmp_path, _mk_struct())

        # trade + pattern notes are substantive; empty rejection note = reviewed, no action
        assert len(res.bundles) == 2
        kinds = {b.poi["kind"] for b in res.bundles}
        assert kinds == {"trade", "pattern"}

    def test_empty_note_is_reviewed_no_action(self, tmp_path: Path):
        _write_note(tmp_path, TRADE_PNG, "ok")
        _write_note(tmp_path, REJ_PNG, "")
        res = iter_review(tmp_path, _mk_struct())
        assert len(res.bundles) == 1
        assert res.bundles[0].poi["kind"] == "trade"

    def test_orphan_and_unreviewed_reported(self, tmp_path: Path):
        _write_note(tmp_path, TRADE_PNG, "reviewed")
        _write_png(tmp_path, "STRAY_png_totally_unmatched.png")
        _write_note(tmp_path, "STRAY_png_totally_unmatched.png", "orphan note")
        res = iter_review(tmp_path, _mk_struct())
        assert len(res.orphans) == 1
        assert res.orphans[0].name == "STRAY_png_totally_unmatched.png"
        # rejection + pattern have no note => unreviewed
        assert {poi["kind"] for poi in res.unreviewed} == {"rejection", "pattern"}

    def test_context_bundle_facts_trimmed(self, tmp_path: Path):
        _write_note(tmp_path, TRADE_PNG, "Stop too tight")
        res = iter_review(tmp_path, _mk_struct())
        bundle = res.bundles[0]
        assert bundle.poi["kind"] == "trade"
        assert bundle.poi["entry"] == 105.0
        assert bundle.poi["stop"] == 100.0
        # fact context decoded from JSON
        assert any("direction" in f for f in bundle.facts)


class TestPrompt:
    def test_golden_prompt_snippet(self):
        from marketatlas.review import ContextBundle

        bundle = ContextBundle(
            basename=TRADE_PNG,
            png_path=Path(TRADE_PNG),
            note_text="Stop too tight",
            poi={
                "kind": "trade",
                "symbol": "GBPUSD",
                "tf": "d1",
                "ts": datetime(2024, 1, 19, tzinfo=UTC).isoformat(),
                "entry": 105.0,
                "stop": 100.0,
                "target": 115.0,
                "direction": "bullish",
                "result": "win",
                "pnl": 50.0,
                "rr_ratio": 2.0,
            },
            facts=[{"name": "trend", "direction": "BULLISH", "strength": 0.8}],
        )
        prompt = build_prompt(
            {
                "basename": bundle.basename,
                "note_text": bundle.note_text,
                "poi": bundle.poi,
                "facts": bundle.facts,
            },
            strategy_source="pullback := detect_pullback { min_strength: 0.5 }",
        )
        assert bundle.basename in prompt
        assert "Stop too tight" in prompt
        assert "min_strength" in prompt


class TestProvider:
    def test_null_provider_no_suggestions(self):
        p = NullProvider()
        assert p.suggest([], None) == []

    def test_make_provider_defaults_to_null(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("MARKETATLAS_REVIEW_PROVIDER", raising=False)
        assert isinstance(make_provider(), NullProvider)


class TestCli:
    def _run_main(self, *args: str):
        from unittest.mock import patch

        with patch("sys.argv", ["marketatlas", *args]):
            from marketatlas.cli import main

            main()

    def _setup(self, tmp_path: Path) -> tuple[Path, Path]:
        snap = tmp_path / "snapshots"
        snap.mkdir()
        _write_note(snap, TRADE_PNG, "Stop too tight, probe min_strength.")
        _write_note(snap, REJ_PNG, "")
        jpath = tmp_path / "out.json"
        jpath.write_text(json.dumps(_mk_struct()))
        return snap, jpath

    def test_review_smoke(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        snap, jpath = self._setup(tmp_path)
        self._run_main("review", "--snapshots", str(snap), "--output-json", str(jpath))
        out = capsys.readouterr().out
        assert TRADE_PNG in out
        assert "no provider configured" in out

    def test_review_auto_find_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        snap, _ = self._setup(tmp_path)
        # drop explicit flag; JSON sits beside snapshots dir
        self._run_main("review", "--snapshots", str(snap))
        out = capsys.readouterr().out
        assert TRADE_PNG in out
        assert "no provider configured" in out

    def test_review_json_out(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        snap, jpath = self._setup(tmp_path)
        report = tmp_path / "report.json"
        self._run_main(
            "review", "--snapshots", str(snap), "--output-json", str(jpath), "--json", str(report)
        )
        capsys.readouterr()
        payload = json.loads(report.read_text())
        assert payload["bundles"][0]["basename"] == TRADE_PNG
        assert payload["provider_configured"] is False

    def test_review_no_notes_exits_clean(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        snap = tmp_path / "snapshots"
        snap.mkdir()
        _write_png(snap, TRADE_PNG)  # PNG but no sidecar
        jpath = tmp_path / "out.json"
        jpath.write_text(json.dumps(_mk_struct()))
        self._run_main("review", "--snapshots", str(snap), "--output-json", str(jpath))
        out = capsys.readouterr().out
        assert "No notes found to review" in out

    def test_review_missing_snapshots_dir_exits(self, tmp_path: Path):
        with pytest.raises(SystemExit) as exc:
            self._run_main("review", "--snapshots", str(tmp_path / "nope"))
        assert exc.value.code == 1
