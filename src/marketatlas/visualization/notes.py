"""Manual annotation sidecar notes (backlog 096).

Pairs each snapshot PNG with a same-name ``.txt`` sidecar (basename shared,
extension swapped). Notes are free-form Markdown, authored by hand by a human
reviewer — the system only creates / reads them, never rewrites a human's
wording.

Contract:
  - Note filename = PNG filename with ``.png`` -> ``.txt``.
  - A missing note file means "not yet reviewed"; an **empty** note means
    "reviewed, no action".
  - ``write_note`` is for tests / scaffolding only (also used by the optional
    ``--notes`` template flag on snapshot rendering).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

NOTE_SUFFIX = ".txt"


def note_path(png_path: str | Path) -> Path:
    """Return the same-name ``.txt`` sidecar path for a snapshot PNG."""
    p = Path(png_path)
    return p.with_suffix(NOTE_SUFFIX)


def read_note(png_path: str | Path) -> str | None:
    """Return the note text for ``png_path``, or None if no sidecar exists."""
    path = note_path(png_path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def iter_notes(snapshots_dir: str | Path) -> Iterator[tuple[Path, str | None]]:
    """Yield ``(png_path, note_text)`` pairs for every PNG in ``snapshots_dir``.

    Yields in deterministic filename order. ``note_text`` is None when the PNG
    has no sidecar (not yet reviewed), else the file contents (possibly empty
    = reviewed, no action).
    """
    d = Path(snapshots_dir)
    if not d.is_dir():
        return
    for png in sorted(d.glob("*.png")):
        yield png, read_note(png)


def write_note(png_path: str | Path, text: str) -> Path:
    """Write ``text`` to the sidecar for ``png_path`` (tests / scaffolding only).

    Creates an empty template when ``text`` is empty, so a first render can
    drop a ``.txt`` per PNG that marks the review-ready state.
    """
    path = note_path(png_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
