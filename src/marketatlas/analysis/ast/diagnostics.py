"""Backlog 059: positioned diagnostics for the DSL and compiler.

The lexer (056) and parser (057) already raise positioned errors directly;
this module adds the downstream piece — source mapping for AST-level findings
and human-readable rendering. ``SourceMap`` records where named AST nodes live
in the source text; compiler passes attach those positions to ``Diagnostic``
objects (backlog 038) so ``CompilationError`` preserves locations "where
source-mapped". Rendering is split into a compact one-line form (tests, logs)
and a caret snippet (CLI).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from marketatlas.analysis.ast.lexer import SourcePosition
from marketatlas.analysis.ast.validation import Diagnostic

__all__ = [
    "SourceMap",
    "format_diagnostic",
    "format_errors",
    "render_snippet",
    "with_position",
]


@dataclass(frozen=True)
class SourceMap:
    """Source positions for named AST nodes, produced by the DSL parser.

    ``definitions`` maps a definition name to the position of its name token;
    ``parameters`` maps ``(definition, parameter)`` to the position of the
    parameter's name token; ``source`` is the original DSL text (used for
    snippet rendering). Passes look up positions by node name and attach them
    to diagnostics that lack one. ASTs that never came from text carry no map.
    """

    definitions: Mapping[str, SourcePosition] = field(default_factory=dict)
    parameters: Mapping[tuple[str, str], SourcePosition] = field(default_factory=dict)
    source: str = ""

    def position_for(
        self, node_type: str, node_name: str, *, parameter: str | None = None
    ) -> SourcePosition | None:
        if parameter is not None:
            return self.parameters.get((node_name, parameter))
        return self.definitions.get(node_name)


def with_position(diagnostic: Diagnostic, position: SourcePosition | None) -> Diagnostic:
    """Return ``diagnostic`` with ``position`` attached (existing position wins)."""
    if position is None or diagnostic.position is not None:
        return diagnostic
    return Diagnostic(
        message=diagnostic.message,
        severity=diagnostic.severity,
        node_name=diagnostic.node_name,
        node_type=diagnostic.node_type,
        position=position,
    )


def format_diagnostic(diagnostic: Diagnostic, source: str | None = None) -> str:
    """Compact one-line rendering: ``line:col: <severity>: <message>``.

    A positioned diagnostic with ``source`` additionally carries the offending
    line and caret (block form). Without a position the line:col prefix is
    omitted.
    """
    if diagnostic.position is None:
        text = f"{diagnostic.severity.value}: {diagnostic.message}"
    else:
        pos = diagnostic.position
        text = f"{pos.line}:{pos.col}: {diagnostic.severity.value}: {diagnostic.message}"
        if source is not None:
            text += "\n" + render_snippet(source, pos)
    return text


def format_errors(
    diagnostics: tuple[Diagnostic, ...] | list[Diagnostic],
    source: str | None = None,
) -> str:
    """Multi-error block: one compact line per diagnostic, plus a header."""
    if not diagnostics:
        return ""
    lines = [format_diagnostic(d, source) for d in diagnostics]
    noun = "error" if len(lines) == 1 else "errors"
    return f"{len(lines)} {noun}:\n" + "\n".join(lines)


def render_snippet(source: str, position: SourcePosition) -> str:
    """Offending source line plus a caret on the following line."""
    lines = source.splitlines() or [""]
    line = lines[position.line - 1] if 0 < position.line <= len(lines) else ""
    return f"  {line}\n  {' ' * (position.col - 1)}^"
