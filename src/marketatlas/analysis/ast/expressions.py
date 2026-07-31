from __future__ import annotations

from dataclasses import dataclass


class Expression:
    """Base class for parameter value expressions.

    A parameter value is a tree node so it can be validated, cloned, expanded,
    and serialized structurally. ``LiteralExpression`` is the only concrete
    node type until choice/template nodes land (backlog 048).
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
