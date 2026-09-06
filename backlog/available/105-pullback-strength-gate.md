# 105 — Pullback strength gate: reject flat/sideways setups

**Epic:** strategy

## Context

Human notebook review (backlog 103) flagged five pullback patterns as too flat /
sideways / gradient-inconsistent:

- AUDCAD 2026-08-09 — "pattern too flat (sideways movement, not vertical)"
- AUDJPY 2026-01-09 — "pattern too flat. sideways movement, not enough vertical change"
- AUDJPY 2026-01-19 — "too flat, certainly for the time period"
- AUDUSD 2026-01-11 — "flat"
- AUDCAD 2026-02-11 — "the highs are not increasing with a similar gradient to the lows"

Measured `PullbackFact.strength` for these flagged setups (from the 2026-01-29
run's `facts_by_ts`): 0.52, 0.70, 0.65, 0.49, 0.68.

`strategy/swing.dsl` sets `min_strength: 0.01` on `generate_signal`
(strategy/swing.dsl:45). That is effectively **no gate** — every detected
pullback, however flat, passes straight to risk.

The signal's gate lives in `PullbackSignal` (src/marketatlas/analysis/signals/
pullback_signal.py:34, `min_strength` default 0.5, `evaluate` compares at :91).
The DSL "acceptance testing" knob (`--ab`) was the intended A/B device, but its
current setting makes flat patterns unhindered.

## Scope

- Raise the pullback quality requirement so flat, low-displacement patterns are
  rejected before reaching risk.
- Suggested floor ~0.6 (kills the 0.49/0.52/0.65-non-trend cases while keeping
  strong setups) — tune against the reviewed run.
- Do **not** change the `_pattern_strength` formula itself here; a pure
  threshold bump is the minimal, reversible move. (A follow-up may reweight
  `inclination` — see backlog note below.)

## Requirements

- [ ] `PullbackSignal` rejects pullbacks below the DSL-configured threshold by
      default; threshold evidence text names the strength value.
- [ ] `strategy/swing.dsl` `min_strength` raised from 0.01 to a tuned floor.
- [ ] Flat patterns from the reviewed run no longer produce pattern snapshots /
      signals when reproduced with current data.
- [ ] Keep `--ab` A/B semantics working (choice remains a variant knob).

## Testing

- [ ] Signal-unit: a flat pattern (low strength) below threshold is rejected
      with the strength evidence.
- [ ] Signal-unit: a strong pattern passes unchanged.
- [ ] Reproduce reviewed run: flat AUDCAD/AUDJPY/AUDUSD setups now rejected.

## Follow-up (not in scope)

Given the "not even a similar gradient high-vs-low" comment on AUDCAD 2026-02-11,
the `inclination` term (`_pattern_strength`, src/marketatlas/analysis/patterns/
pullback.py:260) may deserve heavier weight — leg v. retrace leg slope mismatch is
currently not its own term. Separate item if the plain threshold is insufficient.

Depends on: 103 (feedback source), 097 (review loop).