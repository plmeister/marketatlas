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

`strategy/swing.dsl` set `min_strength: 0.01` on `generate_signal` — no gate.
`PullbackSignal` rejects below `min_strength` with evidence naming the strength.

## Change

- `strategy/swing.dsl` `min_strength` raised 0.01 → **0.55**.
- No formula change in `_pattern_strength` (per scope); signal evidence/return
  paths already correct.
- 0.6 was tried first: it culled two *marginal winners* (SPX500 2025-11-14
  strength 0.599, AUDJPY 2026-01-29 strength 0.594) — both lay just under the
  line while every other trade kept strength ≥ 0.615. 0.55 sits between the
  flagged flats (0.49/0.52) and those traders (≥ 0.594).

## Measured limit of a pure threshold

The 0.55 floor kills the two clearly-flagged flats (0.49 AUDUSD 01-11, 0.52
AUDCAD 08-09) and drops no trade. The other three review-flagged setups —
AUDJPY 01-09 (0.70), AUDJPY 01-19 (0.65), AUDCAD 02-11 (0.68) — sit **above**
any floor that keeps the reviewer-positive setups (AUDCAD 02-08 0.64 "pretty
good", AUDNZD 03-17 0.67 "pretty strong"). Strength alone cannot separate
flat-from-good; the geometric mean averages away the "sideways" defect (all 13
traded patterns also landed 0.66–0.77). A higher pure threshold only trades
false positives for false negatives. Full separation needs the follow-up
reweight below.

## Requirements

- [x] `PullbackSignal` rejects pullbacks below the DSL-configured threshold by
      default; threshold evidence text names the strength value
      (existing: pullback_signal.py:91, test_min_strength_filter_returns_rejection).
- [x] `strategy/swing.dsl` `min_strength` raised from 0.01 to 0.55.
- [x] Reviewed 0.49/0.52 flat setups rejected on reproduction; no trade dropped.
- [x] `--ab` A/B semantics intact (choice remains a variant knob).

## Testing

- [x] Signal-unit rejection already covered (test_min_strength_filter_returns_rejection).
- [x] Strong-pattern pass-through covered (PullbackSignal below-threshold tests).
- [x] Tier1+tier2 824 passed; ruff/mypy clean.
- [x] A/B portfolio rerun: floored variant A keeps all 13 trades (6W/2L
      +$4050.20 — the 2 no-strength drops under 0.6 are restored at 0.55).

## Follow-up (not done, now measured)

The `inclination` term (`_pattern_strength`, src/marketatlas/analysis/patterns/
pullback.py:260) or a dedicated leg-v-retrace slope term is required — data shows
flagged flats at 0.65–0.70 interleaved with good setups at 0.64–0.67, so a pure
threshold cannot express "flat/sideways" (or the gradient-mismatch complain on
AUDCAD 02-11). Suggest reweighting or splitting the term; re-verify the three
surviving flats plus the two positive controls.

Depends on: 103 (feedback source), 097 (review loop).