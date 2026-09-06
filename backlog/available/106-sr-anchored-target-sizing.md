# 106 — SR-anchored target: sizing must be level-constrained

**Epic:** strategy

## Context

Human notebook review (backlog 103) flagged three trades whose target sat above
every detected S/R level, calling the sizing "guesswork":

- AUDCAD 2026-02-12 (cancelled) — "a lack of SR above the entry so the sizing is
  guesswork to an extent.. we should be looking to make trades where the target
  is detectably constrained by SR lines so that there's a higher chance that we
  know where the price will turn"
- AUDJPY 2026-01-12 (win) — "can't see SR above this bullish trade - sizing
  should use SR as part of the input"
- AUDNZD 2026-03-17 (cancelled) — "i don't see SR lines above the target, so
  we're flying blind a bit on this trade, probably should not have been placed"

Measured S/R for those trades (2026-01-29 run):

| trade           | entry     | target    | SR ceiling        | gap            |
|-----------------|-----------|-----------|-------------------|----------------|
| AUDCAD 02-12    | 0.9693    | 0.9860    | res 0.9264        | +0.06 above    |
| AUDJPY 01-12    | 105.78    | 107.14    | res 102.26        | +4.9 above     |
| AUDNZD 03-17    | 1.2159    | 1.2294    | res 1.1664        | +0.06 above    |

## Current behavior

`RiskEngine` (src/marketatlas/strategy/risk.py) already uses S/R in two ways:

1. `_crosses_sr` / `_avoid_srxing` (:298) — a target that **crosses over** an S/R
   level bumps RR to the next clear level (or rejects).
2. `_find_valid_rr` (:415) / `_target_clear` (:465) — picks the RR whose target
   lands between levels, with `sr_buffer_atr` clearance.

Neither requires the target to sit **near** an S/R level. When no level exists in
the entry→target band at all, the engine sizes purely off ATR × RR — exactly the
"flying blind" the reviewer flagged.

## Scope

Add an optional SR-anchoring mode to `RiskEngine`:

- Require a detected S/R level within `N × ATR` **beyond** the target (resistance
  for longs, support for shorts) so the target sits in a level-constrained spot.
- Without a qualifying level at acceptable RR, reject the trade with SR evidence
  ("no S/R anchoring beyond target within max_rr band").
- Off by default; switchable from DSL (`manage_risk { anchor_sr: true, ... }`).

## Requirements

- [ ] RiskEngine option requiring an S/R level just beyond target (within
      `max_anchor_atr`, default ~1×ATR) else rejection.
- [ ] DSL wiring: `anchor_sr` key on `manage_risk`; default off keeps existing
      behavior byte-identical.
- [ ] Rejection evidence names the expected anchor zone and nearest level.
- [ ] Reviewed trades reproduce: AUDJPY 01-12 / AUDNZD 03-17 / AUDCAD 02-12
      rejected (or re-targeted) under `anchor_sr: true`.

## Testing

- [ ] Unit: candidate whose target has no SR beyond it rejected with SR evidence.
- [ ] Unit: candidate with SR just beyond target accepted, RR unchanged.
- [ ] Unit: anchor threshold (level inside vs outside `max_anchor_atr`).
- [ ] DSL: `anchor_sr: true` flows into RiskEngine; `--ab` variants toggle it.

## Follow-up (not in scope)

The stale-level observation (SR res 102.26 while AUDJPY traded ~105–107) points
at the SR window/cluster config in `swing.dsl` (`sr { swing: swing1w, ... }`):
weekly swings age quickly on daily trades. Revisit `swing_buffer_atr` /
cluster freshness as a separate item if anchoring exposes it.

Depends on: 103 (feedback), 097 (review loop), backlog note 083 (explicit fact
wiring, already in place for `sr`).