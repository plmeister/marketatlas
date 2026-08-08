# 067: Confirmed Pullback Entry

**Status:** done  
**Epic:** strategy  
**Priority:** high

## Description

Today `PullbackPatternAnalyzer` (`src/marketatlas/analysis/patterns/pullback.py`) emits a `PullbackFact` on **every** frame where a monotonic swing structure exists — the pullback "fires" repeatedly while the pattern persists, not when an actual tradeable entry happens. Two things are missing:

1. **Entry timing** — a pullback is only actionable on the candle *after* the last swing point of the `SwingStructureFact` completes. The current analyzer re-emits the fact on every subsequent bar with no relation to that point.
2. **Confirmation** — the fact should be placed only when the candle on that entry day confirms the expected movement (a strong bullish candle for a bullish pullback, strong bearish for a bearish pullback). Today there is no candle-strength gate at all.

Plus the flow must end in a trade: `PullbackSignal` already produces a `TradeSignal` (`src/marketatlas/analysis/signals/pullback_signal.py`) and `RiskEngine` (`src/marketatlas/strategy/risk.py`) already sizes a `TradeCandidate` from SR/ATR/swing/RR — but no end-to-end path wires confirmed pullback → signal → risk sizing.

## Goal

- `PullbackPatternAnalyzer` emits `PullbackFact` only on the candle immediately following the final swing point of the swing structure, and only when that candle confirms expected movement.
- A failed confirmation (pattern present, candle too weak) is recorded in that frame's evidence — never silently dropped.
- Confirmed pullback flows to `PullbackSignal` → `RiskEngine` so the risk node places a sized trade using available SR, ATR, RR.

## Scope

- **Entry-day gating** in `PullbackPatternAnalyzer.analyze`:
  - Take `view.current.index` (via `view.current`/store), compare against `max(point.index for point in struct.points)`.
  - Emit `PullbackFact` only when `current.index == last_swing.index + 1`. All earlier/later frames emit no fact.
- **Confirmation candle gate**:
  - Bullish pullback → confirm when candle is strong bullish: `close > open`, body ratio `|close-open| / (high-low)` ≥ threshold (e.g. `min_body_pct=0.6`), close beyond the final swing price (bullish: `close > last_swing.price`).
  - Bearish → mirror image.
  - Parametrized: `min_body_pct: float = 0.6`, `confirm_beyond_swing: bool = True`, `lookback_swings: int = 5` (aligns with `SwingStructureAnalyzer`'s 5-point window).
- **Evidence on rejection**:
  - When the entry day arrives and the pattern is valid but the candle fails the gate, return `AnalysisResult(facts=(), evidence=(EvidenceEntry(...)))` with a `WARNING`/`INFO` entry naming the candle and reason: e.g. `"Pullback pattern detected but confirmation candle weak: body 0.42 < 0.60 — no pullback placed"`.
  - When the entry day is wrong (pattern exists but candle is the swing candle itself, or too early/late), emit an evidence entry only for the missed/upcoming state — no stale facts.
- **Signal → risk wiring**:
  - Keep `PullbackSignal` producing `TradeSignal` (direction, entry zone, confidence) on a confirmed `PullbackFact` only.
  - Ensure strategies that declare `pullbackpattern` + `generate_signal` + `manage_risk` compile and produce `TradeCandidate` with size from `RiskEngine` (SR levels for RR/target, ATR for stop buffer, `risk_pct` for sizing).
  - If `PullbackSignal` needs SR to carry entry/stop hints, extend its params (`sr_key`) rather than duplicating risk logic.
- **Tests** (`tests/`):
  - Entry-day gating: fact placed exactly on `last_swing.index + 1`, absent on the swing candle and on later candles.
  - Confirmation: strong candle → fact; weak body → no fact + evidence entry; wrong-direction candle → no fact + evidence entry.
  - Cross-timeframe: swing structure at `1w`, confirmation candle at `1d` — entry day derived from the swing point's *store timestamp* index, not the raw index (points carry `timestamp`).
  - End-to-end: DSL/bundle strategy `swings → swingstructure → pullbackpattern → generate_signal → manage_risk` produces a `TradeCandidate` sized from SR/ATR/RR.
  - No-readahead: nothing after `current` is read.

## Non-Goals

- No new fact fields on `PullbackFact` (keep `direction` + `swing_pattern`).
- No position management/exit logic (risk node stays sizing-only).
- No multi-candle confirmation (e.g. "two strong candles"); single-candle gate only.

## Acceptance Criteria

- [ ] `PullbackFact` placed only on the candle following the final swing point of the swing structure
- [ ] Strong confirmation candle required; weak/opposite candle yields no fact
- [ ] Every rejected confirmation produces a per-candle evidence entry (visible in frame evidence / visualization)
- [ ] Confirmed pullback reaches `PullbackSignal` and `RiskEngine` sizes a trade from SR + ATR + RR
- [ ] Cross-timeframe (1w structure → 1d confirmation) works via swing point timestamps
- [ ] No-readahead audit stays green

## Technical Notes

- `SwingStructureFact.points` carry `SwingPoint.timestamp`; use store lookup for the follow-up candle rather than assuming index+1 across timeframes (046/045 views select per timeframe).
- Evidence without a fact is already expressible: `AnalysisResult.evidence` is independent of `facts` — keep rejection evidence on the frame.
- `PullbackSignal` currently requires `trend`, `atr_14`, `pullback_pattern`; RiskEngine requires `atr_14`, `sr`, `swing`. Wiring needs `sr` present for sizing — add to strategy templates as needed.

## Related

- Backlog 017/018 (swing structure / four-swing detector — superseded), 020 (signal system), 021 (risk/trade sizing)
- `src/marketatlas/analysis/patterns/pullback.py`, `src/marketatlas/analysis/signals/pullback_signal.py`, `src/marketatlas/strategy/risk.py`
