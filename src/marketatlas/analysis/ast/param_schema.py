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

    Parameters inherited from a base ``__init__`` are included when the most
    derived constructor forwards ``**kwargs`` (the convention every analyzer
    uses). That makes the common ``Analyzer`` slots — ``timeframe``,
    ``bindings``, ``name``, ``fact_name`` — visible as DSL parameters instead
    of being silently unrepresentable. A subclass that does not forward
    ``**kwargs`` gets only its own explicit parameters, so the schema never
    advertises something the constructor will reject.
    """
    own = _specs_from_init(cls.__dict__.get("__init__"))
    if own is None:
        return ()

    merged: dict[str, ParamSpec] = {s.name: s for s in own}
    if _accepts_var_keyword(cls.__dict__.get("__init__")):
        for klass in reversed(cls.__mro__[1:]):
            specs = _specs_from_init(klass.__dict__.get("__init__"))
            if specs:
                for s in specs:
                    merged.setdefault(s.name, s)

    required_names = {s.name for s in own if s.required}
    return tuple(
        ParamSpec(
            name=s.name,
            required=s.name in required_names,
            expected_type=s.expected_type,
        )
        for s in merged.values()
    )


def _specs_from_init(init: object) -> tuple[ParamSpec, ...] | None:
    """ParamSpecs for one ``__init__`` function, or ``None`` if not introspectable."""
    if init is None:
        return None
    try:
        signature = inspect.signature(init)  # type: ignore[arg-type]
        hints = typing.get_type_hints(init)
    except Exception:
        return None

    specs: list[ParamSpec] = []
    for name, param in signature.parameters.items():
        if name == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        required = param.default is inspect.Parameter.empty
        specs.append(ParamSpec(name=name, required=required, expected_type=hints.get(name)))
    return tuple(specs)


def _accepts_var_keyword(init: object) -> bool:
    if init is None:
        return False
    try:
        signature = inspect.signature(init)  # type: ignore[arg-type]
    except Exception:
        return False
    return any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
    )


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
