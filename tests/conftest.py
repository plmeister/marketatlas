from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Rewrite snapshot files with current output",
    )


SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def assert_snapshot(name: str, actual: str, request: pytest.FixtureRequest) -> None:
    path = SNAPSHOT_DIR / f"{name}.json"
    if request.config.getoption("--update-snapshots") or "UPDATE_SNAPSHOTS" in os.environ:
        path.write_text(actual)
        return

    if not path.exists():
        msg = f"Snapshot '{name}' not found at {path}. " "Run with --update-snapshots to create."
        raise AssertionError(msg)

    expected = path.read_text()
    actual_obj = json.loads(actual)
    expected_obj = json.loads(expected)
    assert actual_obj == expected_obj, f"Snapshot '{name}' mismatch"
