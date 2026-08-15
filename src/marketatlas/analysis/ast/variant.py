"""Variant identity for A/B-tested choice templates (backlog 079).

A concrete ``TemplateGraph`` carries the values its choices selected. The
identity of a variant is the set of choice-relevant values across *every*
definition — analyzer parameters, signal rules, and risk parameters — so a
choice on any node (not just ``generate_signal`` rules) is distinguishable.
Human-readable labels (079) and, later, filesystem-safe slugs (080) must be
derived from this same identity so they never disagree.
"""

from __future__ import annotations

from marketatlas.analysis.ast.instrument import TemplateGraph

_ATOMIC = (int, float, str, bool)


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


def variant_labels(templates: tuple[TemplateGraph, ...]) -> list[str]:
    """Human-readable labels naming the chosen values on every varying node.

    A dimension *varies* when its value differs across the variants (i.e. it
    is a choice dimension). Each variant is labeled ``param=value`` per
    varying dimension, in sorted-key order; a bare parameter name is used
    unless two nodes share it, in which case the key is fully qualified. A
    choice-free template (exactly one variant) yields ``["default"]``.
    """
    identities = [variant_identity(t) for t in templates]
    if not identities:
        return []
    if len(identities) == 1:
        return ["default"]
    varying = sorted(k for k in identities[0] if len({i.get(k) for i in identities}) > 1)
    bare_counts: dict[str, int] = {}
    for k in varying:
        bare = k.split(".", 1)[-1]
        bare_counts[bare] = bare_counts.get(bare, 0) + 1

    labels: list[str] = []
    for ident in identities:
        parts: list[str] = []
        for k in varying:
            bare = k.split(".", 1)[-1]
            name = bare if bare_counts[bare] == 1 else k
            parts.append(f"{name}={ident[k]}")
        labels.append(", ".join(parts) if parts else "default")
    return labels
