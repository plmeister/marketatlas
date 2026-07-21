# Backtesting Replay Loop

**Epic:** mvp

## Problem

No way to run analysis over historical data. Need a replay loop that advances through candles, runs analyzers, and stores frames.

## Goal

`Backtester` iterates over `MarketStore`, creates `MarketView` at each step, runs `AnalysisGraph`, stores `AnalysisFrame`. Produces a complete `FrameStore`.

## Design

### 1. Backtester

File: `src/marketatlas/backtesting/backtester.py`

```python
class Backtester:
    def __init__(
        self,
        store: MarketStore,
        graph: AnalysisGraph,
        window_size: int = 100,
    ): ...

    def run(self) -> FrameStore: ...

    def run_with_progress(self, callback: Callable[[int, int], None] | None = None) -> FrameStore: ...
```

### 2. Replay Loop

```python
def run(self) -> FrameStore:
    frame_store = FrameStore()
    for cursor in range(self.window_size, len(self.store)):
        view = MarketView(self.store, cursor, self.window_size)
        facts = self.graph.run(view)
        evidence = EvidenceCollector()  # populated by analyzers
        frame = AnalysisFrame(
            timestamp=view.current.timestamp,
            candle=view.current,
            facts=facts,
            evidence=evidence.entries(),
        )
        frame_store.append(frame)
    return frame_store
```

### 3. Design Constraints

- First `window_size` candles skipped (insufficient history)
- Each frame is immutable
- Analyzers receive accumulated facts from current step only (not across time)
- Progress callback for long backtests

### 4. Tests

- 100 candles, window_size=50 → 50 frames produced
- Each frame has correct timestamp
- Frame facts dict contains all expected fact types
- `FrameStore` is complete and ordered

## Evidence

- `Backtester(store, graph).run()` returns `FrameStore` with correct frame count
- Frames contain all analyzer outputs
