# Four-Swing Pullback Detector

**Epic:** strategy

## Problem

Current `PullbackDetector` only finds one swing high and one swing low. The intended pullback pattern requires 4 swings matching HH/HL/HH/HL (bullish) or LL/LH/LL/LH (bearish), with quality filtering to reject sideways chop, followed by a confirmation candle. Need a complete redesign.

## Goal

`FourSwingPullbackDetector` consumes `SwingFact` + `TrendFact` + `ATRFact`, identifies 4-swing patterns, validates linearity between swings, checks confirmation candle, and produces a `PullbackFact` with richer status information.

## Design

### 1. PullbackFact Enhancement

File: `src/marketatlas/facts/pattern.py`

```python
@dataclass(frozen=True)
class PullbackFact(Fact):
    status: PullbackStatus          # DETECTED / CONFIRMED / INVALIDATED
    direction: TrendDirection       # BULLISH / BEARISH
    swing_pattern: tuple[float, ...]  # the 4 swing prices (e.g. 48k, 51k, 49k, 52k)
    deviation_pct: float            # max deviation from linear path between swings
    retracement_atr: float          # depth from final swing to confirmation
    confirmation_strength: float    # 0.0-1.0 strength of confirmation candle
```

### 2. FourSwingPullbackDetector

File: `src/marketatlas/analysis/patterns/four_swing_pullback.py`

```python
class FourSwingPullbackDetector(Analyzer):
    def __init__(
        self,
        max_deviation_pct: float = 0.15,
        min_swing_separation_atr: float = 0.3,
        confirmation_min_body_pct: float = 0.6,
        confirmation_min_volume_ratio: float = 1.2,
        swing_key: str = "swing",
        trend_key: str = "trend",
        atr_key: str = "atr_14",
    ): ...
```

### 3. Pattern Detection Logic

**Step 1 — Extract swing sequence:**
From `SwingFact.swings`, take the last N swings (enough to cover 4+).

**Step 2 — Check 4-swing pattern:**

For bullish (HH/HL/HH/HL):
```
swing[0] = HL  (higher low)
swing[1] = HH  (higher high)
swing[2] = HL  (higher low, above swing[0])
swing[3] = HH  (higher high, above swing[1])
```

For bearish (LL/LH/LL/LH):
```
swing[0] = LH  (lower high)
swing[1] = LL  (lower low)
swing[2] = LH  (lower high, below swing[0])
swing[3] = LL  (lower low, below swing[1])
```

Validate the sequence:
- Bullish: `swing[1].price > swing[3].price` is wrong — should be `swing[3].price > swing[1].price` (HH) and `swing[2].price > swing[0].price` (HL)
- Bearish: `swing[3].price < swing[1].price` (LL) and `swing[2].price < swing[0].price` (LH)

**Step 3 — Linearity filter (sideways invalidation):**

For each pair of consecutive swings, compute max deviation of closes from the straight line between them:

```python
def _max_deviation(
    candles: tuple[Candle, ...],
    start_idx: int,
    end_idx: int,
) -> float:
    """Max perpendicular distance of candle closes from line[start..end], 
    normalised by price range."""
```

- Draw line from `swing[i]` close to `swing[i+1]` close
- For each candle between them: compute distance of close from line
- `deviation_pct = max_distance / (swing_high - swing_low)`
- If any pair exceeds `max_deviation_pct` → pattern is too choppy, invalidate

**Step 4 — Confirmation candle:**

After the 4th swing, check `view.current`:
- Close must be beyond the 4th swing level:
  - Bullish: `current.close > swing[3].price`
  - Bearish: `current.close < swing[3].price`
- Body must be `> confirmation_min_body_pct` of candle range
- Volume must be `> confirmation_min_volume_ratio × avg_volume` (20-period)

**Step 5 — Status:**
- If 4-swing pattern matches AND linear AND confirmed → `CONFIRMED`
- If 4-swing pattern matches AND linear BUT not confirmed → `DETECTED`
- Otherwise → `INVALIDATED`

### 4. Read-Ahead Safety

- SwingFact is computed from `view.history + (view.current,)` — no future data
- Confirmation candle check uses `view.current` only — the candle being evaluated
- TrendFact and ATRFact are computed from past data by upstream analyzers
- No cross-frame state: each frame is independent

### 5. Evidence

- `"4-swing bullish pattern detected: HL(48200) HH(51500) HL(49100) HH(52800)"`
- `"Max deviation: 8.2% (within 15% threshold)"`
- `"Confirmation: bullish candle close 53100 > HH 52800, body 72%, volume 1.4x"`
- `"Pattern invalidated: swing[2] low 48900 below swing[0] low 49100 — not higher low"`
- `"Pattern invalidated: deviation 22% exceeds 15% — choppy price action"`

### 6. Tests

**Pattern matching:**
- Bullish HH/HL/HH/HL with clean linear swings → DETECTED
- Same + confirmation candle → CONFIRMED
- LL/LH/LL/LH bearish pattern → DETECTED
- Non-matching pattern (e.g. LH/HL/HH/LL) → INVALIDATED

**Linearity filter:**
- Clean linear swings, deviation < threshold → valid
- Choppy swings, deviation > threshold → INVALIDATED
- 3rd swing has large counter-trend spike → INVALIDATED

**Confirmation candle:**
- Strong bullish close above 4th swing → CONFIRMED
- Weak body (< min_body_pct) → DETECTED (pattern valid but unconfirmed)
- Close below 4th swing → DETECTED (not confirmed yet)
- Low volume → DETECTED (not confirmed)

**Read-ahead:**
- Frame at index N uses only candles ≤ N
- Changing frame N+1 does not change frame N's result
- SwingFact computed independently per frame

**Edge cases:**
- Fewer than 4 swings in window → INVALIDATED
- All swings in same direction (no pullback) → INVALIDATED
- Zero ATR → INVALIDATED

## Evidence

- Pattern detection correctly identifies HH/HL/HH/HL and LL/LH/LL/LH
- Linearity filter rejects choppy patterns
- Confirmation candle requires both close level AND candle strength
- Each frame is independent — no read-ahead
