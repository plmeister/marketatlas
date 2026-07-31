from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


class Expression:
    """Base class for parameter value expressions.

    A parameter value is a tree node so it can be validated, cloned, expanded,
    and serialized structurally. ``LiteralExpression`` is a concrete value;
    ``ChoiceExpression`` is a template expansion point (backlog 048).
    """


@dataclass(frozen=True, eq=False)
class LiteralExpression(Expression):
    """A parameter value that is itself a concrete literal.

    ``LiteralExpression(v)`` compares equal to ``v`` itself, so existing code
    reading ``Parameter.value`` keeps working unchanged.
    """

    value: object

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LiteralExpression):
            return self.value == other.value
        if isinstance(other, Expression):
            return NotImplemented
        return self.value == other

    def __hash__(self) -> int:
        try:
            return hash(self.value)
        except TypeError:
            return hash(repr(self.value))

    def __repr__(self) -> str:
        return f"LiteralExpression({self.value!r})"


@dataclass(frozen=True, eq=True)
class ChoiceExpression(Expression):
    """One of a finite set of candidate values.

    A choice is the AST-level primitive for template expansion (backlog 050):
    ``period = Choice([50, 100])`` means the parameter may take either value.
    A raw ``list`` param value is a plain literal, never implicitly a choice.
    """

    values: tuple[Expression, ...]

    def __repr__(self) -> str:
        inner = ", ".join(repr(v) for v in self.values)
        return f"ChoiceExpression({inner})"


def Choice(values: Iterable[object]) -> ChoiceExpression:  # noqa: N802
    """Build a ``ChoiceExpression``, wrapping raw members as literals.

    ``Choice([50, 100])`` -> ``ChoiceExpression((LiteralExpression(50),
    LiteralExpression(100)))``. Expression members (including nested choices)
    pass through unchanged. A bare list is *not* a choice — call this
    explicitly.
    """
    return ChoiceExpression(tuple(wrap(v) for v in values))


def wrap(value: object) -> Expression:
    """Wrap a raw value as a ``LiteralExpression``; pass expressions through."""
    if isinstance(value, Expression):
        return value
    return LiteralExpression(value)


def unwrap(value: object) -> object:
    """Return the concrete Python value of an expression, or the value itself.

    Raises ``ValueError`` for non-literal expression nodes — real handling for
    those lands with choice/template expansion (backlogs 048/050).
    """
    if isinstance(value, LiteralExpression):
        return value.value
    if isinstance(value, Expression):
        raise ValueError(f"Cannot unwrap non-literal expression: {type(value).__name__}")
    return value
