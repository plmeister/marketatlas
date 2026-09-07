# 106 — S/R-anchored target sizing

**Epic:** strategy

## Context

Human notebook review (backlog 103) flagged targets flying "blind" relative to
S/R — targets placed above the nearest resistance with no level constraining the
turn:

- AUDCAD 02-12 — "lack of SR above the entry so the sizing is guesswork"
- AUDJPY 01-12 — "can't see SR above this bullish trade — sizing should use SR"
- AUDNZD 03-17 — "i don't see SR lines above the target, so we're flying blind"

Measured: SR resistance ceilings sat well below the trade zones (e.g. AUDCAD
02-12: res 0.9264 vs entry 0.9693/target 0.986; AUDJPY 01-12: res 102.26 vs
entry 105.78/target 107.14; AUDNZD 03-17: res 1.1664 vs entry 1.2159/target
1.2294). SR facts come from weekly swings; the levels are stale by the time the
daily trade zone forms far above them.

`RiskEngine` already avoided targets *crossing* S/R (`_avoid_srxing`,
`_target_clear`) but never required an S/R level *beyond* the target.

## Change

- `RiskEngine` new params:
  - `anchor_sr: bool = False` — when on, require an S/R level within
    `max_anchor_atr × ATR` beyond the target: a `resistance` for longs, a
    `support` for shorts. No qualifying level → reject with SR evidence.
  - `max_anchor_atr: float = 1.0` — window size beyond target (in ATR).
- New helper `RiskEngine._find_anchor(direction, target, levels, atr)` returns
  nearest qualifying level within the window, or None.
- Accepted anchored candidates emit `S/R anchor: <type> <price> (… ATR beyond
  target)` evidence.
- `strategy/swing.dsl` `manage_risk` block: `anchor_sr: <false|true>` — A = off
  (baseline, behavior byte-identical to pre-106), B = on (anchored). The choice
  is the A/B knob; `marketatlas run --ab` runs both.
- Defaults keep every existing run identical when `anchor_sr` is unset.

## Measured impact (2026-09-05 portfolio rerun, `--ab`)

- Variant A (`anchor_sr=false`): 13 trades, 6W/2L, P&L +$4050.20 — identical to
  baseline.
- Variant B (`anchor_sr=true`, `max_anchor_atr=1.0`): **0 trades**. Every signal
  rejected for lacking an S/R anchor.

Root cause: the `sr` fact is built from **weekly** swing clusters and emits only
1–3 levels per timestamp, clustered near the current weekly structure. Targets
of daily-swing trades sit far above the highest resistance — measured across the
reviewed run, 13 of 15 trades had **no** resistance (longs) / support (shorts)
beyond the target at all, and the two that did had levels 2.8 and 4.1 ATR out
(EURNZD, NZDUSD winners). So `anchor_sr` is currently a hard kill switch, not a
tuning dial: its window is bounded by SR coverage that the weekly-cluster
analyzer does not provide.

This is a data-reach finding, not a filter bug. The knob is still the right
device — follow-up is SR reach (more/larger clusters, or daily-swing levels) so
a meaningful number of targets can actually anchor.

## Requirements

- [x] `anchor_sr` and `max_anchor_atr` accepted by `RiskEngine`; default off.
- [x] Longs require a resistance within the window beyond target; shorts require
      a support within the window below target.
- [x] No qualifying level → reject with "no S/R anchor" evidence.
- [x] Accepted candidates carry S/R anchor evidence on the candidate.
- [x] DSL `manage_risk` exposes `anchor_sr: <false|true>`; compiles to 2 graphs.
- [x] `max_anchor_atr` controls the window (narrow window rejects a level that a
      wider window admits).

## Testing

- [x] `test_anchor_sr_off_accepts_without_anchor` — baseline unaffected.
- [x] `test_anchor_sr_rejects_when_no_level_beyond_target`
- [x] `test_anchor_sr_rejects_level_too_far_beyond_target`
- [x] `test_anchor_sr_accepts_resistance_near_target`
- [x] `test_anchor_sr_bearish_accepts_support_near_target`
- [x] `test_anchor_sr_bearish_rejects_resistance_only`
- [x] `test_anchor_sr_max_atr_controls_window`

Tier1+tier2 824 passed; ruff/mypy clean; DSL compiles to 2 graphs (A off / B on).

Depends on: 103 (feedback source), 083 (explicit risk inputs), 079/081 (A/B).