from __future__ import annotations

from dataclasses import dataclass

from marketatlas.data.store import MarketStore
from marketatlas.frames.store import FrameStore
from marketatlas.strategy.tradebook import TradeBook


@dataclass(frozen=True)
class RenderContext:
    frames: FrameStore
    store: MarketStore
    tradebook: TradeBook
    max_hold_days: int = 10
    window_size: int = 100
    title: str = ""
    min_touches: int = 2
