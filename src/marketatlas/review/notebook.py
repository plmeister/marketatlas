"""Review notebook (ipynb) generation and feedback extraction.

Spike for backlog "ipynb review document": produces a single, self-contained
Jupyter notebook that embeds every snapshot PNG (base64, no external file
dependency) alongside a tagged markdown cell where a human types feedback.
The same module reads those tagged cells back so the review agent can consume
feedback items deterministically.

Cell contract
-------------
Each POI section is::

    [markdown] header  -- basename, kind, symbol, ts, outcome
    [output ]   chart  -- embedded image/png (base64)
    [markdown] review  -- a line starting with:  <!-- REVIEW: <basename> -->

The ``<!-- REVIEW: <basename> -->`` marker maps the cell's body back to a POI
via :func:`snapshot_basename`, preserving the same-basename join guarantee the
``.txt`` sidecar convention (backlog 096) already provides.

Notebooks are plain JSON (nbformat v4) so no third-party ``nbformat``
dependency is required to write or read them.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

REVIEW_TAG = "<!-- REVIEW:"
_TAG_RE = re.compile(r"<!--\s*REVIEW:\s*([^<>\s]+)\s*-->")


def _markdown_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source,
    }


def _image_cell(png_path: Path, *, mime: str = "image/png") -> dict[str, Any]:
    """A cell whose single output embeds ``png_path`` as base64 bytes."""
    data = base64.b64encode(png_path.read_bytes()).decode("ascii")
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [
            {
                "output_type": "display_data",
                "data": {mime: data},
                "metadata": {},
            }
        ],
        "source": "# chart",
    }


def build_notebook(
    entries: list[tuple[dict[str, Any], Path]],
    *,
    title: str = "MarketAtlas review",
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a review notebook from ``(poi, png_path)`` entries.

    ``notes`` maps a snapshot basename to pre-existing feedback text (e.g. from
    current ``.txt`` sidecars) so the notebook carries existing verdicts into
    its review cells.
    """
    notes = notes or {}
    cells: list[dict[str, Any]] = [
        _markdown_cell(
            "# " + title + "\n\n"
            "Review each annotated setup below. Below each chart is a markdown "
            "cell pre-tagged with ``<!-- REVIEW: <basename> -->``; type your "
            "verdict there. Keep the tag line intact so an agent can map your "
            "feedback back to the trade."
        )
    ]

    for poi, png_path in entries:
        basename = png_path.name
        kind = poi.get("kind", "?")
        head = f"## {basename}\n\n"
        head += f"- **kind:** {kind}\n"
        head += f"- **symbol:** {poi.get('symbol', '')}\n"
        head += f"- **ts:** {poi.get('ts', '')}\n"
        if kind == "trade":
            head += (
                f"- **entry:** {poi.get('entry')}  "
                f"**stop:** {poi.get('stop')}  "
                f"**target:** {poi.get('target')}\n"
            )
            head += f"- **result:** {poi.get('result')}  **pnl:** {poi.get('pnl')}\n"
        elif kind == "rejection":
            head += f"- **reason:** {poi.get('reason', '')}\n"

        cells.append(_markdown_cell(head))
        cells.append(_image_cell(png_path))
        body = notes.get(basename)
        cells.append(
            _markdown_cell(
                f"{REVIEW_TAG} {basename} -->\n"
                + (body if body else "*mark reviewed / no action, or type your feedback here*")
            )
        )

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def write_notebook(
    notebook: dict[str, Any],
    path: str | Path,
    *,
    indent: int = 1,
) -> Path:
    """Serialize a notebook dict to ``path`` as ipynb JSON."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(notebook, indent=indent) + "\n", encoding="utf-8")
    return out


def iter_review_cells(
    notebook: str | Path | dict[str, Any],
) -> dict[str, str]:
    """Extract feedback from a notebook's tagged markdown cells.

    Returns ``{basename: feedback_text}`` for every cell tagged with
    ``<!-- REVIEW: <basename> -->`` whose body is non-empty (cells left at the
    default "reviewed, no action" placeholder are treated as empty).
    """
    if isinstance(notebook, str | Path):
        with open(notebook) as f:
            doc = json.load(f)
    else:
        doc = notebook

    out: dict[str, str] = {}
    placeholder = "type your feedback here"
    for cell in doc.get("cells", []):
        if cell.get("cell_type") != "markdown":
            continue
        src = cell.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        m = _TAG_RE.search(src)
        if not m:
            continue
        basename = m.group(1)
        body = src[m.end():].strip()
        if body and placeholder not in body:
            out[basename] = body
    return out
