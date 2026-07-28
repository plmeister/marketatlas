from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BaseNode:
    id: str
    metadata: dict[str, str] | None

    def __init__(self, id: str = "", metadata: dict[str, str] | None = None) -> None:
        self.id = id
        self.metadata = metadata


@dataclass(frozen=True)
class Parameter:
    name: str
    value: Any


@dataclass(frozen=True)
class Binding:
    source: str
    output: str
    target: str
    input: str


@dataclass(frozen=True)
class Definition:
    name: str
    type: str
    impl: str
    parameters: tuple[Parameter, ...] = ()
    bindings: tuple[Binding, ...] = ()
    id: str = ""
    metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class Analysis:
    name: str
    version: str
    definitions: tuple[Definition, ...] = ()
    id: str = ""
    metadata: dict[str, str] | None = None
