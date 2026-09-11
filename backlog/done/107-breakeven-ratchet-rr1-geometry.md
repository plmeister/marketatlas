# 107 — Breakeven ratchet + RR≥1 geometry research

**Epic:** strategy

## Context

Prior session research (SR sparsity, spillover/penetration sizing) converged on
a hard constraint from human review: **trade setups must keep RR ≥ 1.0**. The
min-RR sweep had hinted an edge only at mrr 0.5 (wide swing-anchored stop +
tight target, nominally 1:0.5) — a geometry structurally impossible under the
constraint. This item moves the geometry lever to **post-entry exit mechanics
that RR≥1 cannot forbid** and measures whether any workable configuration exists
at all, alongside a full-pool stop-width sweep.

Delivery is twofold: a reusable exit-geometry implementation (de-risk exit
plans incl. a **breakeven ratchet**), and an honest negative verdict on the
RR≥1 geometry space.

## Change

### De-risk exit plans (`ExitPlan`, `TradeBook._resolve_scaled`)

- New frozen `ExitPlan` on `TradeCandidate` (scale-out/trail/runner machinery
  out of the previous commit batch):
  - `scale_out_fraction` / `scale_out_rr` — split the position, bank that
    fraction, run the remainder from a breakeven stop.
  - `runner_target_rr` — hard runner target, `trailing_stop_rr` — ratcheting
    trail on the remainder.
  - `breakeven_after_scale` — arm the breakeven stop for the remainder.
- `TradeBook.resolve_at_cursor` dispatches plan-armed trades to
  `_resolve_scaled` (scale-out path) or `_resolve_ratchet`.

### Breakeven ratchet (`breakeven_at_rr`) — the installable rescue

- `RiskEngine` param `breakeven_at_rr: float = 0.0`. > 0 builds a plan with
  `scale_out_fraction == 0` (pure ratchet).
- Semantic: once price trades **`breakeven_at_rr` × stop_distance** in favour
  (0.25 = a quarter of the risk banked), the single protective stop ratchets to
  **entry** (`TradeBook._resolve_ratchet`). Submitted target untouched. No
  partial fills — executable as a plain stop-modification order, unlike
  scale-outs.
- Stop-first engine convention preserved (stop checked before target; arming
  bar uses the original stop, conservative on gaps).
- Evidence: "Exit plan: stop ratchets to breakeven once price reaches X.XX R".

### Envelope scaling knob (`stop_width_mult`)

- `RiskEngine` param `stop_width_mult: float = 1.0` (clamped 0.05–5.0). Shrinks
  the whole envelope at fixed RR: both stop and stop_distance scaled
  proportionally (target follows), size recomputes so $ risk is preserved.
  Evidence "Stop width: ×k (RR preserved)". Used only by the research sweep.

### Tests

- `tests/test_tradebook.py` `TestDeRiskExits` scale-out/trail/runner batches +
  `TestBreakevenRatchet` (arm→breakeven, arm→win-unharmed, stop-before-arm =
  full loss, poor-man's 0.25R stop = breakeven).
- `tests/test_risk_engine.py` `TestExitPlanBuilding` + ratchet plan build/clamp.
- `tests/test_ast_param_schema.py` de-risk keys present in the `manage_risk`
  DSL schema.
- tier1 329 → 335 pass; ruff clean. mypy blocked by pre-existing numpy .pyi
  3.12 syntax noise.

## Sweep: stop-width (− RR≤1 substitution)

Full 54-symbol pool, min_rr 1.0, slip {0.1, 0.2}, window 100, hold 10,
$1000. `stop_width_mult` k ∈ {0.5, 0.6, 0.75}:

| config | trades | sumR | bull | bear |
|---|---|---|---|---|
| k0.5 s0.1 | 1421 | −29.93 | +13.07 | −43.00 |
| k0.6 s0.1 | 1398 | −28.79 | +0.06 | −28.85 |
| k0.75 s0.1 | 1234 | −43.63 | −8.95 | −34.68 |
| k0.5 s0.2 | 1413 | −45.00 | −2.00 | −43.00 |
| k0.6 s0.2 | 1395 | −24.88 | +4.00 | −28.88 |
| k0.75 s0.2 | 1303 | −2.70 | +11.00 | −13.70 |

All negative. Tightening the stop kills the stop-crossing-SR rejection and the
entry gating collapses — the pool floods with lower-quality entries (1234–1421
vs 599 baseline). The mrr0.5 edge structurally lives in *wide stop + tight
target*; RR≥1 forbids it. Verdict: **stop shrinkage is not a viable geometry
lever at RR≥1.**

## Oracle: favourable excursion ceiling

Per-trade MFE/MAE tool on the cached 549-trade pool (barrier sim at the RR1
grid, stop-first, cancel-at-0 conventions):

- Median favourable excursion **0.34R**, mean 0.43R; only ~14% of trades ever
  reach 1R (bull 16.4%, bear 11.4%).
- Oracle k-curve (stop/target scaled together, whole-position exits): negative
  at every k.
- So the pool *cannot deliver* even a close-to-RR1 win rate; the goods below
  1R simply are not there. This is the fundamental picture: the signal puts
  targets unreachably far from the observable favourable excursion.

## Ratchet sweep

`breakeven_at_rr` B ∈ {0.25, 0.5}, full 54 symbols:

| config | sumR | bull | bear |
|---|---|---|---|
| baseline (no plan) | −12.32 | +1.04 | −13.36 |
| B=0.25 s0.1 | **−3.47** | +4.04 | −7.51 |
| B=0.25 s0.2 | **+0.47** | **+9.00** (WR 57.6%) | −8.53 |
| B=0.5 s0.1 | −10.32 | +1.04 | −11.36 |
| B=0.5 s0.2 | −6.46 | +2.00 | −8.46 |

- B=0.25 is the winning arm level (32% of losses touch ≥0.25R before dying;
  only 9% touch 0.5R). B=0.5 barely rescues anything.
- Ratchet effect is monotone-improving per trade (rescue a loss → 0, cap a win
  → breakeven) and nets ≈ +1R per 3 rescued losses on the full pool. On the
  full-pool **bull** leg it converts +1.04 → +9.00R. Bearish leg stays deeply
  negative (−7.5..−11.4 across all configs): the bearish side accounts for
  ~100% of baseline loss.

## Honest portfolio estimate (14-instrument filter + ratchet 0.25, slip 0.2)

14 instruments previously both-positive in the 54-pool sweep (slip 0.2/0.4).

| run | n | sumR | eqpts | maxDD |
|---|---|---|---|---|
| 14-pool **control** (ratchet off) | 135 | **+19.47** | +19.54 | — |
| 14-pool + ratchet 0.25 | 136 | +20.47 | +20.65 | −20.17 |
| full 54 pool, bull-only, ratchet 0.25 s0.2 | ~219 | ~+9.0 | — | — |

- The ratchet adds **+1.00R** over the 14-pool control. **The instrument filter
  does essentially all the work** (54-pool baseline −12.32 → 14-subset +19.47).
- Per-year: every year within ±6R, mostly breakevens; the whole profit is ~5
  wins in 2021 + 6 in 2023. maxDD ≈ −20.2 eqpts — the entire cumulative gain in
  one drawdown. Mean +1.8 eqpts/yr over an 11.3y span, Sharpe ≈ 0.8.
- Static sizing features (atr_pct, vol_ratio, trend_eff, rng20_atr) do **not**
  separate delivery — no non-forward-looking sizing rule usable.

## Roster-legitimacy test (2026-09-11, time-split)

Does **any** ex-ante computable instrument/regime score predict *forward*
delivery? Same 542-trade oracle pool, split front (<2021) / back (≥2021),
52 instruments, median ~5–6 trades per instrument per half. Spearman across
instruments, front → back:

| X (front) | Y (back) | rho | p |
|---|---|---|---|
| sumR | sumR | **−0.073** | 0.61 |
| reach-1R | reach-1R | +0.069 | 0.62 |
| reach-1R | sumR | −0.125 | 0.37 |
| atr_pct | sumR | +0.061 | 0.67 |
| vol_ratio | sumR | −0.055 | 0.70 |
| trend_eff | sumR | −0.141 | 0.31 |
| rng20_atr | sumR | +0.122 | 0.38 |
| atr_pct | atr_pct | **+0.412** | 0.001 |
| trend_eff | trend_eff | **+0.341** | 0.010 |

Instrument **identity is stable** across the regime boundary (atr_pct,
trend_eff persist, p<0.01) — but that stable identity **predicts nothing**
(all delivery/sumR columns null). Delivery itself does not persist
(rho ≈ 0).

**Roster selection as selection — dead.** Top-14 chosen by front-half sumR
makes **−0.85R** on the back half (random-14 bootstrap: mean −3.6, sd 4.7 —
indistinguishable). Top-14 by front reach makes **−9.85R** (below random).
Top-14 by any single feature ≈ random. Winners are disjoint half to half:
each top-8 back-half name was flat-to-negative in front (USDPLN +3.00 ↔
−0.00, EURAUD +2.00 ↔ −2.00, EURCAD +1.00 ↔ −1.00). The +12.49 "forward"
win of the original in-sample 14 is a **contamination artifact** — that
roster was selected on the full pane, so its back-half result is baked-in
look-ahead, not prediction.

Verdict: the 14-pool edge (+19.47R control) was selection noise. No static
roster and no regime-stable feature (vol level, trend efficiency) trades the
signal; a legitimately forward-selected roster is ≈ random. The instrument
"good/bad" idea collapses to regime gating, and the regime-stable features
available do not gate it.

## Conclusions (what survived / what died)

**Survived — keep, commit:**
- De-risk exit plan machinery is honest, tested, and byte-identical when off.
- `breakeven_at_rr` ratchet at 0.25 is a real, executably-installable
  monotone improvement (biggest single geometry lever found; transforms the
  full-pool bull leg +1 → +9R).

**Dead ends under RR ≥ 1.0 (documented, do not retry):**
- Stop-width envelope shrinkage — counterproductive (entry gating collapse).
- Any rating of the 54-pool as a whole: the bearish leg alone carries ~−13R
  and no ratchet/gate/sizing feature fixes it.
- Static-feature sizing at the trade level.
- **Instrument roster selection (any static form).** The time-split test above
  is a kill-shot: identity is stable, prediction is zero; forward-selected
  rosters score ≈ random. Retach this item with a *live regime* feature that
  demonstrably gates delivery — not more pane-mined names.

## Requirements

Backlog priority: none assigned; research output only.