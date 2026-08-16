"""Variant identity for A/B-tested choice templates (backlog 079).

A concrete ``TemplateGraph`` carries the values its choices selected. The
identity of a variant is the set of choice-relevant values across *every*
definition — analyzer parameters, signal rules, and risk parameters — so a
choice on any node (not just ``generate_signal`` rules) is distinguishable.
Human-readable labels (079) and, later, filesystem-safe slugs (080) must be
derived from this same identity so they never disagree.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from marketatlas.analysis.ast.instrument import TemplateGraph

_ATOMIC = (int, float, str, bool)

#: Compact, filesystem-safe abbreviations for common parameter names. Unknown
#: params fall back to their full (sanitized) name, so slugs never collide on
#: the abbreviation step.
_SLUG_ABBREV = {
    "min_strength": "ms",
    "max_strength": "xs",
    "min_rr": "mrr",
    "max_rr": "xrr",
    "max_stop_atr": "atr",
    "sr_buffer_atr": "sba",
    "risk_pct": "rp",
    "period": "p",
    "lookback": "lb",
    "window": "w",
    "timeframe": "tf",
    "min_touches": "mt",
}


def _slug_name(name: str) -> str:
    """Bare param name or node-qualified key, abbreviated to a slug token."""
    if "." in name:
        node, param = name.rsplit(".", 1)
        return _node_token(node) + "_" + _param_token(param)
    return _param_token(name)


def _param_token(param: str) -> str:
    if param in _SLUG_ABBREV:
        return _SLUG_ABBREV[param]
    return re.sub(r"[^a-z0-9]+", "", param.lower()) or "p"


def _node_token(node: str) -> str:
    """Lowercase type name with analyzer/signal/engine suffixes stripped."""
    token = node.lower()
    for suffix in ("analyzer", "structure", "signal", "engine"):
        if token.endswith(suffix) and len(token) > len(suffix):
            token = token[: -len(suffix)]
    return token or "node"


def _value_token(value: object) -> str:
    """Deterministic, filesystem-safe encoding of a choice value."""
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, int):
        return ("n" if value < 0 else "") + str(abs(value))
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return _value_token(int(value))
        sign = "n" if value < 0 else ""
        s = f"{abs(value):g}"
        ip, _, frac = s.partition(".")
        return sign + ip + frac.ljust(2, "0")
    text = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return text or "v"


def variant_identity(template: TemplateGraph) -> dict[str, object]:
    """Choice-relevant values across every definition.

    Keys are ``{node}.{param}`` where ``node`` is the analyzer/signal type or
    ``risk``. ``bindings``/``requires`` are derived wiring, not choice values,
    and are excluded; nested containers (lists, dicts) are skipped because
    they are never expansion points. ``timeframe`` participates: a choice over
    a ``TimeFrame`` reference changes the compiled slot.
    """
    identity: dict[str, object] = {}
    for ac in template.config.analyzers:
        for k, v in ac.params.items():
            if k == "bindings":
                continue
            if v is None or isinstance(v, _ATOMIC):
                identity[f"{ac.type}.{k}"] = v
        if ac.timeframe is not None:
            identity[f"{ac.type}.timeframe"] = ac.timeframe
    for sc in template.config.signals:
        for k, v in sc.rules.items():
            if v is None or isinstance(v, _ATOMIC):
                identity[f"{sc.type}.{k}"] = v
    for k, v in template.config.risk.params.items():
        if v is None or isinstance(v, _ATOMIC):
            identity[f"risk.{k}"] = v
    return identity


def _varying(
    templates: Sequence[TemplateGraph],
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    """Identities and the choice dimensions that actually vary across variants.

    A dimension *varies* when its value differs across the variants (i.e. it
    is a choice dimension). A single variant (choice-free template) has no
    varying dimensions. Labels (079) and slugs (080) both derive from this so
    they never disagree on which dimensions identify a variant.
    """
    identities = [variant_identity(t) for t in templates]
    if not identities or len(identities) == 1:
        return identities, ()
    varying = tuple(sorted(k for k in identities[0] if len({i.get(k) for i in identities}) > 1))
    return identities, varying


def variant_labels(templates: Sequence[TemplateGraph]) -> list[str]:
    """Human-readable labels naming the chosen values on every varying node.

    Each variant is labeled ``param=value`` per varying dimension, in
    sorted-key order; a bare parameter name is used unless two nodes share it,
    in which case the key is fully qualified. A choice-free template (exactly
    one variant) yields ``["default"]``.
    """
    identities, varying = _varying(templates)
    if not identities:
        return []
    if not varying:
        return ["default"]
    bare_counts = _bare_counts(varying)

    labels: list[str] = []
    for ident in identities:
        parts: list[str] = []
        for k in varying:
            bare = k.split(".", 1)[-1]
            name = bare if bare_counts[bare] == 1 else k
            parts.append(f"{name}={ident[k]}")
        labels.append(", ".join(parts))
    return labels


def variant_slugs(templates: Sequence[TemplateGraph]) -> list[str]:
    """Filesystem-safe, deterministic slugs for every variant (backlog 080).

    Each slug names the chosen values on every varying dimension — the same
    dimensions ``variant_labels`` labels — as compact tokens (``min_strength``
    → ``ms``, value digits compacted: ``min_strength=0.5`` → ``ms050``), joined
    by ``_`` in sorted-key order. Identical choice combinations yield identical
    slugs across runs, so A/B output is diffable and free of ordinals. A
    choice-free template (exactly one variant) yields ``["default"]``.
    """
    identities, varying = _varying(templates)
    if not identities:
        return []
    if not varying:
        return ["default"]
    bare_counts = _bare_counts(varying)

    slugs: list[str] = []
    for ident in identities:
        slugs.append(_slug_identity(ident, varying, bare_counts))
    return slugs


def _slug_identity(
    identity: Mapping[str, object],
    varying: Sequence[str],
    bare_counts: Mapping[str, int],
) -> str:
    parts: list[str] = []
    for k in varying:
        bare = k.split(".", 1)[-1]
        name = bare if bare_counts[bare] == 1 else k
        parts.append(_slug_name(name) + _value_token(identity[k]))
    return "_".join(parts)


def variant_columns(
    identities: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, ...], tuple[str, ...], list[str]]:
    """Choice columns and slugs for the A/B index page (backlog 081).

    Returns ``(varying_keys, headers, slugs)`` for a set of variant
    identities. ``varying_keys`` are the ``{node}.{param}`` identity keys that
    vary across the variants; ``headers`` their human column names (bare param
    unless two nodes share it — the naming 079 labels use); ``slugs`` the 080
    output-directory slugs. All three derive from the same varying-dimension
    logic as the labels/slugs, so the index grid never disagrees with the CLI.
    A lone identity yields ``((), (), ["default"])``.
    """
    if not identities:
        return (), (), []
    varying = tuple(sorted(k for k in identities[0] if len({i.get(k) for i in identities}) > 1))
    if not varying:
        return (), (), ["default"]
    bare_counts = _bare_counts(varying)
    headers = tuple(
        bare if bare_counts[bare] == 1 else k for k in varying for bare in (k.split(".", 1)[-1],)
    )
    slugs = [_slug_identity(ident, varying, bare_counts) for ident in identities]
    return varying, headers, slugs


def variant_slug(template: TemplateGraph) -> str:
    """Slug for a single template; a lone template is ``"default"``."""
    return variant_slugs((template,))[0]


def _bare_counts(varying: Sequence[str]) -> dict[str, int]:
    bare_counts: dict[str, int] = {}
    for k in varying:
        bare = k.split(".", 1)[-1]
        bare_counts[bare] = bare_counts.get(bare, 0) + 1
    return bare_counts
