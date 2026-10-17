#!/usr/bin/env python3
"""Notify a Matrix room (E2EE) about new paper/live trade events.

Reads the append-only events.jsonl for a paper tag, sends an alert for each
event beyond a persisted byte cursor, then advances the cursor. Heartbeats
are skipped. Entry alerts include a rendered chart image.

Config: see study/matrix_transport.py (defaults to ~/.config/marketatlas/notify.env).

Usage:
  PAPER_TAG=paper-test-v1-causal-2 poetry run python notify_new_events.py
  ... --dry-run        print messages, do not send
  ... --self-test      send a hello message
  ... --all            ignore the cursor and replay every event
  ... --init           set the cursor to EOF (skip existing history)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "study"))

from matrix_transport import MatrixTransport, load_config
from notify import format_entry, format_exit, render_entry_chart

STATE_BASE = os.path.expanduser("~/.local/share/marketatlas/paper-logs")


def read_new_events(path: str, offset: int) -> tuple[list[dict], int]:
    events: list[dict] = []
    with open(path, "rb") as fh:
        fh.seek(offset)
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events, fh.tell()


def build_items(events: list[dict], tmp: str) -> list[tuple[Any, ...]]:
    items: list[tuple[Any, ...]] = []
    for event in events:
        if event["type"] == "entry":
            items.append(("text", format_entry(event)))
            png_path = Path(tmp) / f"{event['sym']}-{event['date']}.png"
            try:
                render_entry_chart(str(event["sym"]), event, png_path)
            except Exception as exc:
                print(f"chart render failed for {event['sym']}: {exc}", file=sys.stderr)
                continue
            items.append(("image", str(png_path), f"{event['sym']} {event['date']}"))
        elif event["type"] == "exit":
            items.append(("text", format_exit(event)))
    return items


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    replay_all = "--all" in argv

    if "--self-test" in argv:
        msg = "marketatlas notifier self-test: Matrix E2EE transport OK."
        print(msg)
        if not dry_run:
            MatrixTransport(load_config()).self_test()
            print("self-test sent")
        return 0

    tag = os.environ.get("PAPER_TAG", "paper-test-v1-causal")
    state_dir = os.path.join(os.path.expanduser("~/.local/share/marketatlas/paper-logs"), tag)
    events_path = os.path.join(state_dir, "events.jsonl")
    cursor_path = os.path.join(state_dir, ".notified_offset")
    if "--init" in argv:
        size = os.path.getsize(events_path) if os.path.exists(events_path) else 0
        Path(state_dir).mkdir(parents=True, exist_ok=True)
        with open(cursor_path, "w") as fh:
            fh.write(str(size))
        print(f"cursor initialised -> {size}")
        return 0

    if not os.path.exists(events_path):
        print(f"no events file at {events_path}", file=sys.stderr)
        return 0

    if replay_all:
        offset = 0
    elif os.path.exists(cursor_path):
        with open(cursor_path) as fh:
            offset = int(fh.read().strip() or "0")
    else:
        offset = os.path.getsize(events_path)

    events, new_offset = read_new_events(events_path, offset)

    def _persist() -> None:
        if not dry_run:
            os.makedirs(state_dir, exist_ok=True)
            with open(cursor_path, "w") as fh:
                fh.write(str(new_offset))

    actionable = [e for e in events if e.get("type") in ("entry", "exit")]
    if not actionable:
        _persist()
        print(f"no new actionable events ({len(events)} new line(s), cursor -> {new_offset})")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        items = build_items(actionable, tmp)
        if dry_run:
            for item in items:
                if item[0] == "text":
                    print(item[1])
                else:
                    print(f"[image] {item[2]} -> {item[1]}")
        else:
            MatrixTransport(load_config()).notify(items)

    _persist()
    print(f"notified {len(actionable)} event(s), cursor -> {new_offset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
