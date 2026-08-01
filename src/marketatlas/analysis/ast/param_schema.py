from __future__ import annotations

import inspect
import sys
import types
import typing
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParamSpec:
    """Parameter contract for a provider: name, required, expected type.

    ``expected_type`` is a Python type, a union of types, or ``None`` when the
    constructor is unannotated (accept-all). Backlog 052.
    """

    name: str
    required: bool
    expected_type: object = None


def derive_param_schema(cls: type) -> tuple[ParamSpec, ...]:
    """Introspect a constructor's ``__init__`` signature into ``ParamSpec``s.

    ``self`` and variadic ``*args``/``**kwargs`` are excluded. Annotated
    parameters keep their resolved type; unannotated parameters accept any
    value. Introspection is best-effort — opaque constructors yield an empty
    schema rather than an error.
    """
    try:
        signature = inspect.signature(cls.__init__)  # type: ignore[misc]
        hints = typing.get_type_hints(cls.__init__)  # type: ignore[misc]
    except Exception:
        return ()

    specs: list[ParamSpec] = []
    for name, param in signature.parameters.items():
        if name == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        required = param.default is inspect.Parameter.empty
        specs.append(ParamSpec(name=name, required=required, expected_type=hints.get(name)))
    return tuple(specs)


def _is_union(expected: object) -> bool:
    origin = typing.get_origin(expected)
    return origin is typing.Union or (sys.version_info >= (3, 10) and origin is types.UnionType)


def type_compatible(value: object, expected: object) -> bool:
    """Best-effort check that a literal value satisfies an expected type.

    Accept-all for unannotated (``None``), ``Any``, stringified forward refs,
    and generic origins (``list[float]`` matches ``list``). Unions accept any
    member. Numeric widening: ``int`` satisfies a ``float`` expectation.
    Never asserts — an undecidable check returns ``True`` to avoid
    false positives (backlog 052).
    """
    if expected is None or expected is Any:
        return True
    if isinstance(expected, str):
        return True
    if _is_union(expected):
        return any(type_compatible(value, arg) for arg in typing.get_args(expected))
    origin = typing.get_origin(expected)
    if origin is not None:
        expected = origin
    if expected is float:
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, expected)  # type: ignore[arg-type]


def format_type(expected: object) -> str:
    """Human-readable expected-type name for error messages."""
    if expected is None or expected is Any:
        return "any"
    if isinstance(expected, str):
        return expected
    if _is_union(expected):
        return " or ".join(format_type(arg) for arg in typing.get_args(expected))
    origin = typing.get_origin(expected)
    if origin is not None:
        expected = origin
    return getattr(expected, "__name__", str(expected))
