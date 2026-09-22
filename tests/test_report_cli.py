from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from marketatlas.cli.commands import report_command

pytestmark = pytest.mark.tier2


def _trade(ts: str, r: float) -> dict[str, object]:
    risk = 10.0
    return {
        "submit_ts": ts,
        "entry_ts": ts,
        "exit_ts": ts,
        "instrument": "TEST",
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


def _write_doc(path: Path, trades: list[dict[str, object]], n: int = 12) -> Path:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    rs = [2.0, -1.0, 1.5, -0.5, 0.8, -0.6, 1.0, -0.8, 1.2, -0.4, 2.5, -1.0]
    full = trades or [
        _trade((base + timedelta(days=14 * i)).isoformat(), r) for i, r in enumerate(rs[:n])
    ]
    doc = {
        "symbol": "TEST",
        "timeframe": "1d",
        "trades": full,
        "equity_curve": [{"t": "2024-01-01T00:00:00", "balance": 1000.0}],
    }
    path.write_text(json.dumps(doc))
    return path


def _args(**overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {
        "json": "",
        "costs": "",
        "format": "text",
        "output": "",
        "seed": 42,
        "sims": 100,
        "risk_fraction": 0.0,
        "target_cagr": 100.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class TestReportCommand:
    def test_text_dashboard_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_doc(tmp_path / "out.json", [])
        report_command(_args(json=str(src), sims=100))
        captured = capsys.readouterr()
        assert "METRICS REPORT" in captured.out
        assert "Trade-level (099" in captured.out
        assert "Robustness (102" in captured.out
        assert "the combination double" in captured.out

    def test_json_format_to_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_doc(tmp_path / "out.json", [])
        report_command(_args(json=str(src), format="json", sims=100))
        payload = json.loads(capsys.readouterr().out)
        assert "verdict" in payload and "robustness" in payload and "trades" in payload

    def test_net_layer_with_costs(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = _write_doc(tmp_path / "out.json", [])
        report_command(_args(json=str(src), costs='{"commission_flat": 5.0}', sims=100))
        captured = capsys.readouterr()
        assert "Net after costs (101" in captured.out

    def test_output_file_written(self, tmp_path: Path) -> None:
        src = _write_doc(tmp_path / "out.json", [])
        out = tmp_path / "report.json"
        report_command(_args(json=str(src), format="json", sims=100, output=str(out)))
        assert out.exists()
        payload = json.loads(out.read_text())
        assert "verdict" in payload

    def test_missing_json_exits(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            report_command(_args(json=str(tmp_path / "nope.json")))
        assert exc.value.code == 1
        assert "not found" in capsys.readouterr().err

    def test_no_trades_exits(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = _write_doc(tmp_path / "out.json", [])
        src.write_text('{"symbol": "TEST", "trades": []}')
        with pytest.raises(SystemExit) as exc:
            report_command(_args(json=str(src)))
        assert exc.value.code == 1
        assert "no trades" in capsys.readouterr().err

    def test_bad_cost_schedule_exits(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = _write_doc(tmp_path / "out.json", [])
        with pytest.raises(SystemExit) as exc:
            report_command(_args(json=str(src), costs="not-json-or-path"))
        assert exc.value.code == 1
        assert "cost schedule" in capsys.readouterr().err
