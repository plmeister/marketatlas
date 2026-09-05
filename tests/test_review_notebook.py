"""Tests for the review notebook (ipynb) spike: write + feedback round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from marketatlas.review.notebook import (
    REVIEW_TAG,
    build_notebook,
    iter_review_cells,
    write_notebook,
)

pytestmark = pytest.mark.tier1

_PAT_POI = {
    "kind": "pattern",
    "symbol": "EURAUD",
    "ts": "2026-02-03T00:00:00+00:00",
    "pattern": "pullback",
}
_TRADE_POI = {
    "kind": "trade",
    "symbol": "AUDUSD",
    "ts": "2026-03-03T00:00:00+00:00",
    "entry": 1.5,
    "stop": 1.2,
    "target": 2.0,
    "result": "loss",
    "pnl": -1030.2,
}

_PAT_BASENAME = "EURAUD_2026-02-03_pattern_pullback_pattern.png"
_TRADE_BASENAME = "AUDUSD_2026-03-03_trade_bullish_loss.png"


@pytest.fixture
def snap_dir(tmp_path: Path) -> Path:
    d = tmp_path / "snaps"
    d.mkdir()
    (d / _PAT_BASENAME).write_bytes(b"\x89PNG-dummy")
    (d / _TRADE_BASENAME).write_bytes(b"\x89PNG-dummy")
    return d


@pytest.fixture
def notebook() -> dict:
    pngs = [Path("/tmp/" + b) for b in (_PAT_BASENAME, _TRADE_BASENAME)]
    # use real files so base64 embedding works
    for p in pngs:
        p.write_bytes(b"\x89PNG-dummy")
    try:
        return build_notebook([(_TRADE_POI, pngs[1]), (_PAT_POI, pngs[0])])
    finally:
        for p in pngs:
            p.unlink(missing_ok=True)


def test_notebook_schema(notebook: dict) -> None:
    assert notebook["nbformat"] == 4
    assert notebook["nbformat_minor"] >= 4
    cells = notebook["cells"]
    # intro + (header, image, review) x 2 = 7
    assert len(cells) == 7
    img = cells[2]
    assert img["cell_type"] == "code"
    assert img["outputs"][0]["output_type"] == "display_data"
    assert img["outputs"][0]["data"]["image/png"]


def test_review_cells_tagged_and_prefilled(notebook: dict) -> None:
    # cells[6] is the review cell for the 2nd entry (the pattern poi)
    review_cell = notebook["cells"][6].get("source", "")
    assert isinstance(review_cell, str)
    assert REVIEW_TAG in review_cell
    assert _PAT_BASENAME in review_cell


def test_roundtrip_no_feedback(notebook: dict) -> None:
    assert iter_review_cells(notebook) == {}


def test_roundtrip_with_feedback(notebook: dict) -> None:
    cells = notebook["cells"]
    cells[6]["source"] = (
        f"{REVIEW_TAG} {_PAT_BASENAME} -->\n"
        "This setup is fine but market structure is choppy."
    )
    got = iter_review_cells(notebook)
    assert set(got) == {_PAT_BASENAME}
    assert "choppy" in got[_PAT_BASENAME]


def test_intro_placeholder_not_matched(notebook: dict) -> None:
    # the intro cell mentions the tag syntax literally; angle-bracket placeholder
    # must not be extracted as a real note.
    assert iter_review_cells(notebook) == {}


def test_write_and_reread(notebook: dict, tmp_path: Path) -> None:
    out = write_notebook(notebook, tmp_path / "review.ipynb")
    assert out.exists()
    with open(out) as f:
        assert json.load(f)["nbformat"] == 4
