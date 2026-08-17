from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from marketatlas.data.providers.base import DataProvider

_PROVIDERS: dict[str, type[DataProvider]] = {}


def register(name: str, cls: type[DataProvider]) -> None:
    _PROVIDERS[name] = cls


def get(name: str) -> type[DataProvider] | None:
    return _PROVIDERS.get(name)


def names() -> list[str]:
    return sorted(_PROVIDERS)
