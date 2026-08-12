"""Known data-provider names and the default chain order.

Kept dependency-free so both ``data.instrument`` and ``data.providers`` can
import it without a package-init cycle.
"""

PROVIDER_NAMES: tuple[str, ...] = ("yahoo", "dukascopy")

DEFAULT_PROVIDER_ORDER: tuple[str, ...] = ("yahoo",)
