# Risk Layer & Trade Sizing

**Epic:** strategy

## Problem

No risk management or position sizing exists. Signals indicate direction but not how much to trade, where to place stops, or what target to aim for. Need a risk layer that consumes `TradeSignal` + `SRFact` + `ATRFact` to produce sized `TradeCandidate` objects.

## Goal

`RiskEngine` takes a `TradeSignal` and current facts, computes entry, stop loss, take profit, and position size. Respects configurable risk percentage, RR limits, avoids placing trades where price must cross S/R, and applies optional slippage.

## Design

### 1. TradeCandidate

File: `src/marketatlas/strategy/trade.py`

```python
@dataclass(frozen=True)
class TradeCandidate:
    direction: TrendDirection
    entry: float
    stop: float
    target: float
    size: float               # position size (units of asset)
    risk_amount: float        # currency at risk
    reward_amount: float      # currency expected reward
    rr_ratio: float           # reward / risk
    slippage_pct: float       # slippage applied
    source: str               # strategy name that produced this
    evidence: tuple[EvidenceEntry, ...]
```

### 2. RiskEngine

File: `src/marketatlas/strategy/risk.py`

```python
class RiskEngine:
    def __init__(
        self,
        risk_pct: float = 1.0,           # % of balance to risk per trade
        min_rr: float = 2.0,
        max_rr: float = 4.0,
        max_stop_atr: float = 3.0,
        max_hold_days: int = 10,         # force-close after N days
        avoid_srxing: bool = True,
        slippage_pct: float = 0.1,       # % slippage on entry
        atr_key: str = "atr_14",
        sr_key: str = "sr",
    ): ...
```

### 3. Sizing Logic

**Entry:**
- Use `signal.entry_zone` midpoint as reference price
- Actual fill price = next candle's open (trade placed after close)
- Apply slippage to fill: for bullish → `entry = open × (1 + slippage_pct/100)`, bearish → `entry = open × (1 - slippage_pct/100)`

**Stop placement:**
- For bullish: `stop = entry - N × ATR` where N is chosen so stop is just beyond the nearest swing low
- For bearish: `stop = entry + N × ATR` where N is chosen so stop is just beyond the nearest swing high
- Clamp: if stop distance > `max_stop_atr × ATR` → reject trade (too wide)
- Small buffer beyond swing: `stop_buffer = 0.2 × ATR` past the swing level

**S/R crossing check:**
- If bullish and there's a resistance level between entry and target → reject trade
  (price likely reverses at resistance before reaching target)
- If bearish and there's a support level between entry and target → reject trade

**Target placement:**
- `target = entry + rr_ratio × stop_distance`
- Find `rr_ratio` in `[min_rr, max_rr]` such that target does not cross any S/R level
- If no valid RR ratio exists (target would cross S/R at any RR in range) → reject trade

**Position size:**
- `risk_amount = balance × (risk_pct / 100)` — balance is dynamic, passed per call
- `size = risk_amount / stop_distance`

### 4. Read-Ahead Safety

- SRFact computed from past swings only
- ATRFact computed from past data
- Entry, stop, target all derived from current-frame data
- No future candles consulted
- RiskEngine never stores state across frames

### 5. Evidence

- `"Stop: 52100 (0.8 ATR below entry, beyond swing low 52300)"`
- `"Target: 55400 (RR 3.0)"`
- `"Size: 0.187 BTC (risk 10.00 at 1.0% of 1000.00)"`
- `"Slippage: 0.1% applied to entry"`
- `"Rejected: resistance at 54200 between entry 53100 and target 56200"`
- `"Rejected: stop distance 4.2 ATR exceeds max 3.0 ATR"`

### 6. Tests

**Stop placement:**
- Bullish signal, swing low at 52300 → stop at ~52100
- Stop distance > max_stop_atr → trade rejected

**S/R avoidance:**
- Resistance between entry and target → trade rejected
- No S/R between entry and target → trade accepted

**RR ratio:**
- min_rr=2.0, max_rr=4.0 → find best RR that avoids S/R
- No valid RR → trade rejected

**Slippage:**
- 0.1% slippage on bullish entry 53000 → entry becomes 53053
- 0.1% slippage on bearish entry 53000 → entry becomes 52947

**Size calculation:**
- balance=1000, risk_pct=1%, stop_distance=50 → size=0.2 units
- balance=950 (after loss), risk_pct=1% → risk_amount=9.50 (smaller)

**Edge cases:**
- No S/R levels → no crossing check needed
- Stop at exact swing level → accept (with buffer applied)
- Zero ATR → reject

## Evidence

- Position sizing correctly applies risk percentage of current balance
- Stop placement uses swing levels with ATR buffer
- S/R crossing rejection prevents low-probability trades
- Slippage applied to entry in correct direction
