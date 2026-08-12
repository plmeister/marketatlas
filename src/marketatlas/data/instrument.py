from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from marketatlas.data.provider_names import DEFAULT_PROVIDER_ORDER, PROVIDER_NAMES


class Instrument:
    def __init__(
        self,
        canonical: str,
        asset_class: str,
        description: str,
        providers: dict[str, str] | None = None,
        provider_priority: tuple[str, ...] = (),
    ) -> None:
        self._canonical = canonical
        self._asset_class = asset_class
        self._description = description
        self._providers = providers or {}
        self._provider_priority = tuple(provider_priority)
        unknown = [name for name in self._provider_priority if name not in PROVIDER_NAMES]
        if unknown:
            raise ValueError(
                f"Unknown provider(s) in provider_priority: {', '.join(unknown)} "
                f"(known: {', '.join(PROVIDER_NAMES)})"
            )

    @property
    def canonical(self) -> str:
        return self._canonical

    @property
    def asset_class(self) -> str:
        return self._asset_class

    @property
    def description(self) -> str:
        return self._description

    @property
    def providers(self) -> dict[str, str]:
        return dict(self._providers)

    @property
    def provider_priority(self) -> tuple[str, ...]:
        return self._provider_priority

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "class": self._asset_class,
            "description": self._description,
        }
        if self._providers:
            d["providers"] = self._providers
        if self._provider_priority:
            d["provider_priority"] = list(self._provider_priority)
        return d

    @staticmethod
    def from_dict(canonical: str, d: dict[str, Any]) -> Instrument:
        return Instrument(
            canonical=canonical,
            asset_class=str(d["class"]),
            description=str(d["description"]),
            providers=d.get("providers"),
            provider_priority=tuple(d.get("provider_priority") or ()),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Instrument):
            return NotImplemented
        return (
            self._canonical == other._canonical
            and self._asset_class == other._asset_class
            and self._description == other._description
            and self._providers == other._providers
            and self._provider_priority == other._provider_priority
        )

    def __hash__(self) -> int:
        return hash(
            (self._canonical, self._asset_class, self._description, self._provider_priority)
        )

    def __repr__(self) -> str:
        return f"Instrument({self._canonical}, {self._asset_class})"


class InstrumentRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self._instruments: dict[str, Instrument] = {}
        self._path = path
        if path is not None and path.exists():
            self._load(path)

    def _load(self, path: Path) -> None:
        raw = path.read_text()
        if not raw.strip():
            return
        data: dict[str, Any] = yaml.safe_load(raw) or {}
        instrs = data.get("instruments", {})
        for canonical, d in instrs.items():
            self._instruments[canonical] = Instrument.from_dict(canonical, d)

    def get(self, canonical: str) -> Instrument | None:
        return self._instruments.get(canonical)

    def get_symbol(self, canonical: str, provider: str) -> str | None:
        inst = self._instruments.get(canonical)
        if inst is None:
            return None
        return inst.providers.get(provider)

    def get_priority(self, canonical: str) -> tuple[str, ...]:
        inst = self._instruments.get(canonical)
        if inst is not None and inst.provider_priority:
            return inst.provider_priority
        return DEFAULT_PROVIDER_ORDER

    def resolve(self, symbol: str, provider: str) -> str | None:
        for canonical, inst in self._instruments.items():
            if inst.providers.get(provider) == symbol:
                return canonical
        return None

    def list_all(self) -> list[Instrument]:
        return list(self._instruments.values())

    def add(self, instrument: Instrument) -> None:
        self._instruments[instrument.canonical] = instrument

    def save(self, path: Path | None = None) -> None:
        path = path or self._path
        if path is None:
            raise ValueError("No path specified for save")
        data: dict[str, dict[str, Any]] = {"instruments": {}}
        for canonical, inst in self._instruments.items():
            data["instruments"][canonical] = inst.to_dict()
        path.write_text(yaml.dump(data, default_flow_style=False))
