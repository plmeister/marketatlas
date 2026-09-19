"""Per-trade regime context capture (backlog 098).

At the moment a trade is submitted, the backtester snapshots a handful of
cheap market-regime features onto the order so every ``TradeOutcome`` carries
the conditions that produced it. All features are computed from the same
candle data the strategy saw at the signal candle — no lookahead.

These per-trade features are the raw material for the open research question
behind backlog 107: does any *live* regime feature gate delivery? (The 107
time-split showed instrument identity is stable but predicts nothing, and
static roster selection is dead; only regime gating remains untested.)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from marketatlas.facts.primitive import ATRFact


class _CurrentLike(Protocol):
    """Just what the snapshot needs from the last candle."""

    @property
    def close(self) -> float: ...


class _ViewLike(Protocol):
    """Structural stand-in for ``MarketView`` (lets tests stub series cheaply)."""

    @property
    def prices(self) -> tuple[float, ...]: ...

    @property
    def volumes(self) -> tuple[float, ...]: ...

    @property
    def highs(self) -> tuple[float, ...]: ...

    @property
    def lows(self) -> tuple[float, ...]: ...

    @property
    def current(self) -> _CurrentLike: ...

_BASE_LOOKBACK = 20
_TREND_LOOKBACK = 63

_EMPTY: dict[str, float] = {}


def _signed_eff(prices: tuple[float, ...], lookback: int) -> float | None:
    """Signed Kaufman efficiency over the lookback; None if insufficient.

    Positive -> drifting up, negative -> down, ~0 -> zigzag. Mirrors the
    RiskEngine trend-efficiency gate so recorded values match gated decisions.
    """
    if len(prices) < lookback + 1:
        return None
    window = prices[-(lookback + 1):]
    drift = window[-1] - window[0]
    path = sum(abs(window[i] - window[i - 1]) for i in range(1, len(window)))
    return drift / path if path > 0 else 0.0


def extract_atr_value(fact_values: Iterable[object]) -> float | None:
    """First scalar ATR value present in a frame's facts (regime context).

    Returns None when the graph carries no scalar ATR fact (e.g. no atr node,
    or only an ``ATRSeriesFact``); the context snapshot then omits ATR-derived
    keys rather than inventing a value. Looked up by type, so the fact's name
    (``atr_14`` vs ``atr``) does not matter.
    """
    for fact in fact_values:
        if isinstance(fact, ATRFact):
            return fact.value
    return None


def trade_context(view: _ViewLike, atr_value: float | None = None) -> dict[str, float]:
    """Snapshot regime features from ``view`` into a small float dict.

    Keys (mirror the 107 research feature table):
    * ``atr_pct``  — ATR as % of close (absent when ``atr_value`` unknown).
    * ``vol_ratio`` — current volume / 20-candle average (absent with no volume).
    * ``rng20_atr`` — 20-candle high-low range in ATR units.
    * ``trend_eff`` — signed Kaufman efficiency over the 63-candle lookback.

    Returns an immutable-style plain dict; empty stays empty (no sentinels).
    """
    close = view.current.close
    out: dict[str, float] = {}
    if atr_value is not None and atr_value > 0 and close:
        out["atr_pct"] = atr_value / close * 100.0

    if len(view.volumes) >= 2:
        recent = view.volumes[-(_BASE_LOOKBACK + 1):]
        avg_vol = sum(recent[:-1]) / len(recent[:-1])
        if avg_vol > 0:
            out["vol_ratio"] = recent[-1] / avg_vol

    if len(view.highs) >= _BASE_LOOKBACK and len(view.lows) >= _BASE_LOOKBACK:
        window_high = max(view.highs[-_BASE_LOOKBACK:])
        window_low = min(view.lows[-_BASE_LOOKBACK:])
        if atr_value is not None and atr_value > 0:
            out["rng20_atr"] = (window_high - window_low) / atr_value

    eff = _signed_eff(view.prices, _TREND_LOOKBACK)
    if eff is not None:
        out["trend_eff"] = eff

    if not out:
        return _EMPTY
    return out
