# Project Scaffolding and Data Model Foundation

**Epic:** mvp

## Problem

No project structure exists. Need a Python package with correct tooling, type checking, and a foundation of core data types that every subsequent component depends on.

## Goal

Runnable Python package with `poetry install`, `pytest`, `mypy`, and `ruff` all passing. Core data types defined and importable.

## Design

### 1. Package Structure

```
marketatlas/
├── pyproject.toml          (exists)
├── src/
│   └── marketatlas/
│       ├── __init__.py
│       ├── data/           (empty __init__.py)
│       ├── view/           (empty __init__.py)
│       ├── analysis/       (empty __init__.py)
│       │   ├── analyzers/  (empty __init__.py)
│       │   └── patterns/   (empty __init__.py)
│       ├── facts/          (empty __init__.py)
│       ├── frames/         (empty __init__.py)
│       ├── evidence/       (empty __init__.py)
│       └── visualization/  (empty __init__.py)
└── tests/
    └── __init__.py
```

### 2. Core Data Types

File: `src/marketatlas/data/types.py`

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class Timeframe(Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"

@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass(frozen=True)
class Symbol:
    name: str

@dataclass(frozen=True)
class MarketData:
    symbol: Symbol
    timeframe: Timeframe
    candles: tuple[Candle, ...]
```

Frozen dataclasses ensure immutability from day one.

### 3. Validation

- `poetry install` succeeds
- `poetry run pytest` passes (even if no tests yet)
- `poetry run mypy src/` passes
- `poetry run ruff check src/` passes

## Evidence

- Package installs without errors
- All tooling passes clean
- Core types importable: `from marketatlas.data.types import Candle, MarketData`
