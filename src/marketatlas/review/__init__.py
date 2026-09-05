"""Review agent: notes -> algorithm-tuning suggestions (backlog 097).

Closes the human-review loop: reads the free-text ``.txt`` note sidecars (096)
beside snapshot PNGs, correlates each to its POI record in the structured JSON
(``run --output-json``), pulls the fact context visible at that cursor, and
assembles a context bundle an LLM tuning advisor can consume to suggest
algorithm changes.

This module owns gathering, matching, and formatting. The actual tuning
recommendation is the agentic output: ``Provider`` is the extension point, and
when no provider is configured the CLI degrades to printing the assembled
bundle plus a "no provider" marker (deterministic, non-failing).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from marketatlas.visualization.notes import iter_notes, note_path
from marketatlas.visualization.snapshot import locate_pois, snapshot_basename


@dataclass
class ContextBundle:
    """One noted snapshot joined to its POI + trimmed fact context."""

    basename: str
    png_path: Path
    note_text: str
    poi: dict[str, Any]
    facts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReviewResult:
    """Result of joining every note in a snapshots dir to the run's POIs.

    ``bundles``     noted snapshots with a matching POI (one entry per note).
    ``orphans``     note sidecars with no matching POI (note not dropped).
    ``unreviewed``  POIs with no note sidecar (review gap, not dropped).
    """

    bundles: list[ContextBundle]
    orphans: list[Path]
    unreviewed: list[dict[str, Any]]

    @property
    def total_notes(self) -> int:
        return len(self.bundles) + len(self.orphans)

    @property
    def has_notes(self) -> bool:
        return self.total_notes > 0


class Provider(Protocol):
    """An external tuning advisor that turns bundles into suggestions."""

    def suggest(
        self, bundles: list[ContextBundle], strategy_source: str | None
    ) -> list[dict[str, str]]:
        """Return structured suggestions ``{file, rule, change, rationale,
        expected_effect}`` for the given noted bundles."""
        ...


class NullProvider:
    """No-op provider used when no tuning advisor is configured."""

    def suggest(
        self, bundles: list[ContextBundle], strategy_source: str | None
    ) -> list[dict[str, str]]:
        return []


def _fact_context(
    struct: dict[str, Any], poi: dict[str, Any], limit: int = 12
) -> list[dict[str, Any]]:
    """Trim the facts visible at ``poi``'s cursor to a small JSON-safe list."""
    pin = struct.get("per_instrument", {}).get(poi["symbol"]) or struct
    facts_by_ts = pin.get("facts_by_ts") or {}
    enc = facts_by_ts.get(poi.get("ts"))
    if not enc:
        return []
    out: list[dict[str, Any]] = []
    for name, data in list(enc.items())[:limit]:
        fact: dict[str, Any] = {"name": name}
        fact.update(data)
        out.append(fact)
    return out


def iter_review(
    snapshots_dir: str | Path,
    struct: dict[str, Any],
    extra_notes: dict[str, str] | None = None,
) -> ReviewResult:
    """Join note feedback (``.txt`` sidecars, plus optional ``extra_notes``)
    to the run's POIs.

    ``extra_notes`` maps a snapshot basename to feedback text (e.g. the tagged
    feedback cells extracted from a review notebook). When both a ``.txt``
    sidecar and an ``extra_notes`` entry exist for the same basename, the
    ``extra_notes`` text wins (the notebook is the fresher review surface).
    """
    pois = locate_pois(struct)
    by_basename: dict[str, dict[str, Any]] = {}
    for poi in pois:
        by_basename[snapshot_basename(poi)] = poi

    extra_notes = extra_notes or {}
    bundles: list[ContextBundle] = []
    orphans: list[Path] = []
    reviewed_names: set[str] = set()
    for png, text in iter_notes(snapshots_dir):
        reviewed_names.add(png.name)
        poi_match = by_basename.get(png.name)
        if poi_match is None:
            orphans.append(png)
            continue
        nb_text = extra_notes.get(png.name)
        if nb_text:
            text = nb_text
        if text is None or text == "":
            continue
        bundles.append(
            ContextBundle(
                basename=png.name,
                png_path=png,
                note_text=text,
                poi=poi_match,
                facts=_fact_context(struct, poi_match),
            )
        )

    for name, text in extra_notes.items():
        if name in reviewed_names:
            continue
        orphans.append(note_path(name))

    unreviewed = [
        poi for name, poi in by_basename.items() if name not in reviewed_names
    ]
    return ReviewResult(bundles=bundles, orphans=orphans, unreviewed=unreviewed)


def make_provider() -> Provider:
    """Build the configured tuning-advisor provider, else a :class:`NullProvider`.

    A non-empty ``MARKETATLAS_REVIEW_PROVIDER`` env selects a provider module
    whose ``suggest`` is called with the bundles; falling back to
    :class:`NullProvider` is deterministic and never fails the run.
    """
    name = os.environ.get("MARKETATLAS_REVIEW_PROVIDER", "").strip()
    if not name:
        return NullProvider()
    import importlib
    from typing import cast

    mod = importlib.import_module(name)
    return cast(Provider, mod.make_provider())


def format_bundle(bundle: ContextBundle) -> str:
    """Render one bundle for human / no-provider output."""
    poi = bundle.poi
    lines = [
        f"--- {bundle.basename} ---",
        f"note: {bundle.note_text!r}",
        f"kind: {poi.get('kind')}  symbol: {poi.get('symbol')}  "
        f"tf: {poi.get('tf')}  ts: {poi.get('ts')}",
    ]
    if poi.get("kind") == "trade":
        lines.append(
            f"  entry: {poi.get('entry')}  stop: {poi.get('stop')}  "
            f"target: {poi.get('target')}  rr: {poi.get('rr_ratio')}"
        )
        lines.append(f"  result: {poi.get('result')}  pnl: {poi.get('pnl')}")
    elif poi.get("kind") == "rejection":
        lines.append(f"  reason: {poi.get('reason')}")
    elif poi.get("kind") == "pattern":
        lines.append(f"  pattern: {poi.get('pattern')}")
    if bundle.facts:
        lines.append("  facts:")
        for fact in bundle.facts:
            lines.append(f"    - {fact.get('name')}: {fact}")
    return "\n".join(lines)


def format_review(result: ReviewResult, suggestions: list[dict[str, str]] | None = None) -> str:
    """Render the full review report (bundles, gaps, optional suggestions)."""
    lines: list[str] = []
    for bundle in result.bundles:
        lines.append(format_bundle(bundle))
    if result.orphans:
        lines.append("\nOrphan notes (no matching snapshot):")
        for p in result.orphans:
            lines.append(f"  {p}")
    if result.unreviewed:
        lines.append("\nUnreviewed snapshots (no note):")
        for poi in result.unreviewed:
            lines.append(
                f"  {snapshot_basename(poi)} ({poi.get('kind')})"
            )
    if suggestions:
        lines.append("\nSuggestions:")
        for s in suggestions:
            lines.append(
                f"  file: {s.get('file')}  rule: {s.get('rule')}\n"
                f"    change: {s.get('change')}\n"
                f"    rationale: {s.get('rationale')}\n"
                f"    effect: {s.get('expected_effect')}"
            )
    return "\n".join(lines)
