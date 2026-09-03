"""CLI tests for the snapshot POI-kind filter (backlog 095)."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from marketatlas.cli.commands import (
    VALID_SNAPSHOT_KINDS,
    _emit_json_and_snapshots,
    parse_kinds,
    snapshot_command,
)

pytestmark = pytest.mark.tier2


class TestParseKinds:
    def test_default_empty(self) -> None:
        assert parse_kinds("") == (set(), set())

    def test_include_only(self) -> None:
        assert parse_kinds("trade,rejection") == ({"trade", "rejection"}, set())

    def test_exclude_form(self) -> None:
        assert parse_kinds("!pattern") == (set(), {"pattern"})

    def test_mixed_include_exclude(self) -> None:
        assert parse_kinds("trade,!pattern") == ({"trade"}, {"pattern"})

    @pytest.mark.parametrize("bad", ["bogus", "!bogus", "trade,bogus", "!sr,zzz"])
    def test_invalid_kind_errors(self, bad: str, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            parse_kinds(bad)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        for valid in VALID_SNAPSHOT_KINDS:
            assert valid in err


def _args(**kw) -> argparse.Namespace:
    defaults: dict = {
        "output_json": "",
        "snapshots": "",
        "kinds": "",
        "outdir": ".",
        "timeframe": None,
        "overlays": "",
        "no_volume": False,
    }
    defaults.update(kw)
    return argparse.Namespace(**defaults)


class TestEmitJsonAndSnapshots:
    @patch("marketatlas.visualization.snapshot.render_poi_snapshots")
    def test_kinds_parsed_and_passed(self, mock_render: MagicMock) -> None:
        mock_render.return_value = []
        args = _args(snapshots="out", kinds="trade,!pattern")
        _emit_json_and_snapshots(MagicMock(), args)
        mock_render.assert_called_once()
        _, kwargs = mock_render.call_args
        assert kwargs["kinds"] == {"trade"}
        assert kwargs["exclude_kinds"] == {"pattern"}

    @patch("marketatlas.visualization.snapshot.render_poi_snapshots")
    def test_no_kinds_passes_none(self, mock_render: MagicMock) -> None:
        mock_render.return_value = []
        args = _args(snapshots="out", kinds="")
        _emit_json_and_snapshots(MagicMock(), args)
        _, kwargs = mock_render.call_args
        assert kwargs["kinds"] is None
        assert kwargs["exclude_kinds"] is None


class TestSnapshotCommand:
    @patch("marketatlas.visualization.snapshot.render_poi_snapshots")
    def test_kinds_threaded(self, mock_render: MagicMock, tmp_path: Path) -> None:
        mock_render.return_value = []
        src = tmp_path / "out.json"
        src.write_text(
            '{"per_instrument": {"TEST": {"timeframe": "d1", "trades": [], '
            '"rejections_by_ts": {}, "patterns_by_ts": {}}}, "instruments": ["TEST"]}'
        )
        args = _args(
            output_json=str(src), outdir=str(tmp_path / "shots"),
            kinds="rejection,!pattern",
        )
        snapshot_command(args)
        mock_render.assert_called_once()
        _, kwargs = mock_render.call_args
        assert kwargs["kinds"] == {"rejection"}
        assert kwargs["exclude_kinds"] == {"pattern"}

    def test_missing_json_exits(self, tmp_path: Path, capsys) -> None:
        args = _args(output_json=str(tmp_path / "nope.json"), kinds="trade")
        with pytest.raises(SystemExit) as exc:
            snapshot_command(args)
        assert exc.value.code == 1
