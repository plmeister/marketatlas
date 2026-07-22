# Analysis Frame Storage

**Epic:** mvp

## Problem

Analysis results are ephemeral. Need to persist every candle's analysis as an immutable frame for replay and visualization.

## Goal

`AnalysisFrame` captures all facts, evidence, and metadata for a single candle. `FrameStore` collects frames during replay.

## Design

### 1. AnalysisFrame

File: `src/marketatlas/frames/frame.py`

```python
@dataclass(frozen=True)
class AnalysisFrame:
    timestamp: datetime
    candle: Candle
    facts: dict[type[Fact], Fact]
    evidence: tuple[str, ...]
    annotations: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
```

### 2. FrameStore

File: `src/marketatlas/frames/store.py`

```python
class FrameStore:
    def __init__(self) -> None: ...

    def append(self, frame: AnalysisFrame) -> None: ...

    def __len__(self) -> int: ...

    def __getitem__(self, index: int) -> AnalysisFrame: ...

    def slice(self, start: int, end: int) -> list[AnalysisFrame]: ...

    def by_timestamp(self, ts: datetime) -> AnalysisFrame | None: ...

    def to_parquet(self, path: Path) -> None: ...

    @classmethod
    def from_parquet(cls, path: Path) -> FrameStore: ...
```

### 3. Serialization

- Store frames in-memory as list
- `to_parquet()` serializes all frames to a single Parquet file
- Columns: timestamp, candle OHLCV, fact values, evidence (as JSON string)
- `from_parquet()` restores frames

### 4. Tests

- Append 10 frames → `len(store) == 10`
- `store[5]` returns correct frame
- Round-trip through Parquet preserves data
- `by_timestamp()` finds correct frame

## Evidence

- `FrameStore` collects frames during replay
- Parquet round-trip preserves all fact values
