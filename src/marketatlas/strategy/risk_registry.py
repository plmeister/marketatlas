"""Risk node registry (mirrors ``analysis/signals/registry.py``).

The DSL lowers a risk node to ``RiskConfig(algorithm=<impl class name>)`` and
the runtime resolves that class name here, so the strategy's risk node is
swappable without touching ``Strategy``. Add a new risk node: define the class,
add one line to ``RISK_TYPES`` below, and register its DSL capability in
``analysis/ast/registry.py``.
"""
from __future__ import annotations

from marketatlas.strategy.atr_risk import AtrBracketRisk
from marketatlas.strategy.risk import RiskEngine, RiskNode

RISK_TYPES: dict[str, type] = {
    "RiskEngine": RiskEngine,
    "AtrBracketRisk": AtrBracketRisk,
}

__all__ = ["RISK_TYPES", "RiskNode", "RiskEngine", "AtrBracketRisk"]
