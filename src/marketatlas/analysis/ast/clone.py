from __future__ import annotations

from copy import deepcopy
from typing import overload

from marketatlas.analysis.ast.expressions import (
    ChoiceExpression,
    Expression,
    LiteralExpression,
    ReferenceExpression,
)
from marketatlas.analysis.ast.models import (
    Analysis,
    Capability,
    Definition,
    Parameter,
    Provider,
)


def _clone_metadata(metadata: dict[str, str] | None) -> dict[str, str] | None:
    return dict(metadata) if metadata is not None else None


def clone_expression(expr: Expression) -> Expression:
    """Recursively clone an expression tree.

    ``LiteralExpression`` payloads are deep-copied so mutable values (lists,
    dicts) never share state between the original and its clone.
    ``ChoiceExpression`` members and ``ReferenceExpression`` names are cloned
    recursively.
    """
    if isinstance(expr, LiteralExpression):
        return LiteralExpression(deepcopy(expr.value))
    if isinstance(expr, ChoiceExpression):
        return ChoiceExpression(tuple(clone_expression(v) for v in expr.values))
    if isinstance(expr, ReferenceExpression):
        return ReferenceExpression(expr.name)
    raise TypeError(f"Cannot clone unsupported expression node: {type(expr).__name__}")


@overload
def clone(node: Analysis) -> Analysis: ...


@overload
def clone(node: Definition) -> Definition: ...


@overload
def clone(node: Parameter) -> Parameter: ...


@overload
def clone(node: Provider) -> Provider: ...


@overload
def clone(node: Capability) -> Capability: ...


@overload
def clone(node: Expression) -> Expression: ...


@overload
def clone(node: object) -> object: ...


def clone(node: object) -> object:
    """Return an equal, independent deep copy of an AST node.

    Every field of the returned node is freshly allocated: nested definitions,
    parameters, providers, and expression trees are cloned recursively, and
    ``metadata`` dicts are copied. Mutating a clone's payload (or replacing a
    field) never affects the original. ``id``/``metadata`` are preserved, so
    cloning a pure-literal AST is semantically a no-op.
    """
    if isinstance(node, Analysis):
        return Analysis(
            name=node.name,
            version=node.version,
            definitions=tuple(clone(d) for d in node.definitions),
            providers=tuple(clone(p) for p in node.providers),
            timeframes=node.timeframes,
            id=node.id,
            metadata=_clone_metadata(node.metadata),
        )
    if isinstance(node, Definition):
        return Definition(
            name=node.name,
            provider=node.provider,
            parameters=tuple(clone(p) for p in node.parameters),
            id=node.id,
            metadata=_clone_metadata(node.metadata),
        )
    if isinstance(node, Parameter):
        return Parameter(name=node.name, value=clone_expression(node.value))
    if isinstance(node, Provider):
        return Provider(
            name=node.name,
            capability=node.capability,
            category=node.category,
            impl=node.impl,
            default_params=tuple(clone(p) for p in node.default_params),
        )
    if isinstance(node, Capability):
        return Capability(
            id=node.id,
            description=node.description,
            required_params=node.required_params,
        )
    if isinstance(node, Expression):
        return clone_expression(node)
    raise TypeError(f"Cannot clone unsupported node type: {type(node).__name__}")
