from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FactKey:
    name: str
    params: frozenset[tuple[str, Any]] = frozenset()

    def __str__(self) -> str:
        if not self.params:
            return self.name
        parts = [self.name]
        for k, v in sorted(self.params):
            parts.append(f"{k}_{v}")
        return "_".join(parts)

    @classmethod
    def from_params(cls, name: str, **params: Any) -> FactKey:
        return cls(name, frozenset(params.items()))
