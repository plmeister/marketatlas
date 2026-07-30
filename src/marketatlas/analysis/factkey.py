from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from marketatlas.data.types import Timeframe


@dataclass(frozen=True)
class FactKey:
    name: str
    params: frozenset[tuple[str, Any]] = frozenset()
    timeframe: Timeframe | None = None

    def __str__(self) -> str:
        parts = [self.name]
        for k, v in sorted(self.params):
            parts.append(f"{k}_{v}")
        if self.timeframe is not None:
            parts.append(f"tf_{self.timeframe.value}")
        return "_".join(parts)

    @classmethod
    def from_params(
        cls, name: str, timeframe: Timeframe | None = None, **params: Any
    ) -> FactKey:
        return cls(name, frozenset(params.items()), timeframe)
