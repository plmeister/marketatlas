from __future__ import annotations

from dataclasses import dataclass

from marketatlas.analysis.ast.expressions import Expression


class BaseNode:
    id: str
    metadata: dict[str, str] | None

    def __init__(self, id: str = "", metadata: dict[str, str] | None = None) -> None:
        self.id = id
        self.metadata = metadata


@dataclass(frozen=True)
class Parameter:
    name: str
    value: Expression


@dataclass(frozen=True)
class Binding:
    source: str
    output: str
    target: str
    input: str


@dataclass(frozen=True)
class Capability:
    id: str
    description: str
    required_params: tuple[str, ...] = ()


@dataclass(frozen=True)
class Provider:
    name: str
    capability: str
    category: str
    impl: str
    default_params: tuple[Parameter, ...] = ()


@dataclass(frozen=True)
class Definition:
    name: str
    provider: str
    parameters: tuple[Parameter, ...] = ()
    bindings: tuple[Binding, ...] = ()
    id: str = ""
    metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class Analysis:
    name: str
    version: str
    definitions: tuple[Definition, ...] = ()
    providers: tuple[Provider, ...] = ()
    id: str = ""
    metadata: dict[str, str] | None = None
