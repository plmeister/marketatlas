"""Prompt assembly for the review agent (backlog 097).

Assembles a self-contained LLM prompt from a review context bundle so an
external tuning advisor can emit structured suggestions without re-reading the
raw JSON. The bundle is already trimmed and matched in :mod:`marketatlas.review`;
this module only renders it into the prompt text plus the expected suggestion
schema.
"""

from __future__ import annotations

from typing import Any

_SUGGESTION_SCHEMA = """\
For each noted problem, emit a suggestion in this exact shape:
  file: <strategy/DSL file or rule to change>
  rule:  <specific rule/threshold/param name, e.g. risk.max_stop_atr,
          generate_signal.min_strength, atr.period>
  change: <from value -> to value>
  rationale: <why, quoting the note evidence>
  expected_effect: <predicted effect on win rate / drawdown / trades>
"""


def _facts_block(facts: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for fact in facts:
        name = fact.get("__cls", "fact")
        lines.append(f"  - {name}: {fact}")
    return "\n".join(lines) if lines else "  (no fact context for this snapshot)"


def build_prompt(bundle: dict[str, Any], strategy_source: str | None = None) -> str:
    """Render one noted snapshot into a complete tuning-advisor prompt."""
    poi = bundle["poi"]
    lines: list[str] = [
        "You are a systematic-strategy tuning advisor. Read the human review "
        "note below and the analysis output around that point, then recommend "
        "concrete algorithm changes.",
        "",
        f"Snapshot: {bundle['basename']}",
        f"Note: {bundle['note_text']!r}",
        f"POI kind: {poi.get('kind')}",
        f"Symbol: {poi.get('symbol')}  Timeframe: {poi.get('tf')}  Date: {poi.get('ts')}",
    ]
    if poi.get("kind") == "trade":
        lines += [
            f"Direction: {poi.get('direction')}",
            f"Entry: {poi.get('entry')}  Stop: {poi.get('stop')}  "
            f"Target: {poi.get('target')}  R:R: {poi.get('rr_ratio')}",
            f"Result: {poi.get('result')}  PnL: {poi.get('pnl')}",
        ]
    elif poi.get("kind") == "rejection":
        lines.append(f"Rejection reason: {poi.get('reason')}")
    elif poi.get("kind") == "pattern":
        lines.append(f"Pattern: {poi.get('pattern')}")

    lines += [
        "",
        "Facts visible at this cursor (no lookahead):",
        _facts_block(bundle["facts"]),
    ]
    if strategy_source:
        lines += ["", "Current strategy / DSL source:", strategy_source]
    lines += ["", _SUGGESTION_SCHEMA]
    return "\n".join(lines)


def build_prompt_set(
    bundles: list[dict[str, Any]],
    strategy_source: str | None = None,
) -> list[tuple[str, str]]:
    """Return ``(basename, prompt)`` for every noted snapshot."""
    return [(b["basename"], build_prompt(b, strategy_source)) for b in bundles]
