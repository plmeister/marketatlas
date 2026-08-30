"""Signal type registry.

Adding a new signal type: create the file in ``analysis/signals/``,
add one line to ``SIGNAL_TYPES`` below.  No edits to
``strategy/strategy.py`` required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from marketatlas.strategy.signals import Signal

from marketatlas.analysis.signals.breakout_signal import BreakoutSignal
from marketatlas.analysis.signals.pullback_signal import PullbackSignal

SIGNAL_TYPES: dict[str, type[Signal]] = {
    "PullbackSignal": PullbackSignal,
    "BreakoutSignal": BreakoutSignal,
}
