# No-Read-Ahead Audit

**Epic:** strategy

## Problem

Read-ahead (future data leaking into current-frame decisions) is the most critical correctness bug in a backtesting system. Need a systematic audit and test suite that proves every component only sees data available at or before the current candle.

## Goal

Comprehensive audit of all analyzers, signals, and risk engine to verify no future data access. Add regression tests that would catch read-ahead bugs.

## Design

### 1. Audit Checklist

Every component that processes market data must satisfy:

- [ ] `MarketView` is the only source of price data
- [ ] `view.history + (view.current,)` is the full data scope
- [ ] No component stores state across frames (except config)
- [ ] No component accesses `store[cursor + 1]` or beyond
- [ ] No analyzer reads from a future frame's facts
- [ ] `FrameStore` is append-only, never read during computation
- [ ] `TradeBook` is append-only, never consulted by signals/risk
- [ ] `TradeBook.resolve_at_cursor` only checks current candle's high/low
- [ ] Trade signal at cursor N → order fills at open of cursor N+1
- [ ] Only one trade open at a time
- [ ] Only one pending order at a time

### 2. Components to Audit

**Data layer:**
- `MarketView.history` → `store.slice(start, cursor)` ✓ (already safe)
- `MarketView.current` → `store[cursor]` ✓

**Analysis layer:**
- `EMAAnalyzer` — reads `view.prices` (past + current) ✓
- `ATRAnalyzer` — reads `view.history + (view.current,)` ✓
- `TrendAnalyzer` — reads from `facts` dict (upstream analyzers) ✓
- `SwingStructureAnalyzer` — reads `view.history + (view.current,)` + `facts` ✓
- `FourSwingPullbackDetector` — reads `SwingFact` + `view.current` (confirmation) ✓
- `SupportResistanceAnalyzer` — reads `SwingFact` + current price ✓

**Signal layer:**
- `PullbackSignal` — reads `facts` dict only ✓

**Risk layer:**
- `RiskEngine` — reads `facts` dict + `view.current` only ✓

**TradeBook:**
- `resolve_at_cursor(candle)` — reads only `candle.high` and `candle.low` ✓
- `fill_order(open_price, timestamp)` — reads only current candle's open ✓
- Signal at cursor N → pending order → fills at open of cursor N+1 ✓
- No look-back: resolution does not consult earlier candles ✓

### 3. Regression Tests

File: `tests/test_no_readahead.py`

**Test 1 — Frame independence:**
```python
def test_frame_n_independent_of_frame_n_plus_1():
    """Changing the future should not change the past."""
    # Run backtest over candles 100..200
    # Record frame at index 150
    # Run backtest over candles 100..201 (one more candle)
    # Frame at index 150 should be identical
```

**Test 2 — View boundary:**
```python
def test_market_view_never_sees_future():
    """MarketView at cursor=N only sees candles ≤ N."""
    # Create store with 200 candles
    # Create view at cursor=150
    # Assert max index in view.history + view.current is 150
    # Assert no candle from index 151+ is accessible
```

**Test 3 — Analyzer isolation:**
```python
def test_analyzer_output_unchanged_when_future_appended():
    """Adding future candles to store does not change analyzer output at current cursor."""
    # Create store with 200 candles
    # Run analyzers at cursor=150, record results
    # Append 10 more candles to store
    # Run analyzers at cursor=150 again, record results
    # Results must be identical
```

**Test 4 — Signal isolation:**
```python
def test_signal_output_unchanged_when_future_appended():
    """Adding future candles does not change signal evaluation at current frame."""
    # Same pattern as test 3 but for signals
```

**Test 5 — Risk isolation:**
```python
def test_risk_output_unchanged_when_future_appended():
    """Adding future candles does not change risk sizing at current frame."""
    # Same pattern as test 3 but for risk engine
```

**Test 6 — TradeBook resolution:**
```python
def test_trade_fills_at_next_open():
    """Signal at cursor N fills at open of cursor N+1."""
    # Signal fires at cursor 150 (close of candle 150)
    # Pending order created
    # Cursor 151: fill_order called with candle 151's open
    # Resolution starts at cursor 151's range
    # Verify: entry price = candle 151 open, not candle 150 close
```

**Test 7 — Full pipeline:**
```python
def test_full_backtest_deterministic():
    """Running the same backtest twice produces identical results."""
    # Run backtest, record all frames + trades
    # Run again, assert identical
```

### 4. Implementation Constraint

- Tests must be independent (each creates its own store/data)
- Tests must use synthetic data (deterministic, no network)
- Tests should be fast (<1s total)

## Evidence

- All 7 regression tests pass
- No component accesses data beyond `view.current`
- Backtest is fully deterministic
