"""Typed fact JSON codec.

Serializes ``Fact`` objects (and the small nested value dataclasses they
carry) to plain JSON-compatible dicts and back, preserving concrete types.

This is the single structured-output codec: interactive HTML, portfolio tables
and the PNG snapshot renderer all read the same encoded form, so the typed
``AnalysisFrame.facts`` is the one source of truth (no lookahead: a frame only
carries the facts visible at its cursor).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum
from typing import Any, cast

from marketatlas.facts.base import Fact

_FACT_BY_TAG: dict[str, type] = {}
_NESTED_BY_TAG: dict[str, type] = {}
_ENUM_BY_TAG: dict[str, type] = {}

# Canonical field tags we deliberately keep out of the encoded payload (they
# carry cross-cutting/lookup metadata handled by consumers, not the fact body).
_SKIP_BASE_FIELDS = ("evidence", "visible_on")


def _qualname(cls: type) -> str:
    return f"{cls.__module__}.{cls.__name__}"


def _lazy_register_all() -> None:
    if _FACT_BY_TAG:
        return
    from marketatlas.facts import channel, pattern, primitive, structural

    for mod in (channel, pattern, primitive, structural):
        for _name in dir(mod):
            obj = getattr(mod, _name)
            if not isinstance(obj, type):
                continue
            if issubclass(obj, Enum):
                _ENUM_BY_TAG[_qualname(obj)] = obj
            elif issubclass(obj, Fact):
                _FACT_BY_TAG[_qualname(obj)] = obj
            elif dataclasses.is_dataclass(obj):
                _NESTED_BY_TAG[_qualname(obj)] = obj


def _encode_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__t": "dt", "v": value.isoformat()}
    if isinstance(value, Enum):
        return {"__t": "enum", "cls": _qualname(type(value)), "v": value.value}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _encode_dataclass(value)
    if isinstance(value, frozenset):
        return [_encode_value(v) for v in sorted(value, key=str)]
    if isinstance(value, tuple):
        return {"__t": "tuple", "v": [_encode_value(v) for v in value]}
    if isinstance(value, list):
        return [_encode_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _encode_value(v) for k, v in value.items()}
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise TypeError(f"cannot encode {type(value).__name__}: {value!r}")


def _encode_dataclass(obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"__cls": _qualname(type(obj))}
    for f in dataclasses.fields(obj):
        if f.name in _SKIP_BASE_FIELDS:
            continue
        out[f.name] = _encode_value(getattr(obj, f.name))
    return out


def encode_fact(fact: Fact) -> dict[str, Any]:
    """Encode a typed fact to a JSON-compatible dict (preserving its type)."""
    _lazy_register_all()
    return _encode_dataclass(fact)


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict):
        tag = value.get("__t")
        if tag == "dt":
            return datetime.fromisoformat(value["v"])
        if tag == "enum":
            return _ENUM_BY_TAG[value["cls"]](value["v"])
        if tag == "tuple":
            return tuple(_decode_value(v) for v in value["v"])
        if "__cls" in value:
            return _decode_dataclass(value)
        return {k: _decode_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode_value(v) for v in value]
    return value


def _decode_dataclass(data: dict[str, Any]) -> Any:
    cls = _FACT_BY_TAG.get(data["__cls"]) or _NESTED_BY_TAG[data["__cls"]]
    kwargs = {k: _decode_value(v) for k, v in data.items() if k != "__cls"}
    if issubclass(cls, Fact) and "evidence" not in kwargs:
        kwargs["evidence"] = ()
    return cls(**kwargs)


def decode_fact(data: dict[str, Any]) -> Fact:
    """Rebuild a typed ``Fact`` from its encoded dict."""
    _lazy_register_all()
    return cast(Fact, _decode_value(data))


def encode_frame_facts(frame: Any) -> dict[str, Any]:
    """Encode an ``AnalysisFrame``'s fact map (key name -> encoded fact)."""
    return {key.name: encode_fact(fact) for key, fact in frame.facts.items()}


def _candle_to_dict(candle: Any) -> dict[str, Any]:
    return {
        "ts": candle.timestamp.isoformat(),
        "o": candle.open,
        "h": candle.high,
        "l": candle.low,
        "c": candle.close,
        "v": candle.volume,
    }


def _trade_to_dict(trade: Any) -> dict[str, Any]:
    c = trade.candidate
    return {
        "submit_ts": trade.submit_time.isoformat(),
        "entry_ts": trade.entry_timestamp.isoformat(),
        "entry": c.entry,
        "stop": c.stop,
        "target": c.target,
        "direction": c.direction.value,
        "result": trade.result,
        "pnl": trade.pnl,
        "rr_ratio": c.rr_ratio,
        "source": trade.source_strategy,
    }


def _patterns_by_ts(frames: Any) -> dict[str, dict[str, Any]]:
    """Collect pattern facts (pullback/channel/etc.) per frame timestamp."""
    from marketatlas.facts import channel, pattern

    pattern_types = {
        obj.__name__: obj
        for mod in (channel, pattern)
        for obj in vars(mod).values()
        if isinstance(obj, type) and issubclass(obj, Fact)
    }
    by_ts: dict[str, dict[str, Any]] = {}
    for frame in frames:
        pats = {}
        for key, fact in frame.facts.items():
            if type(fact).__name__ in pattern_types:
                pats[key.name] = _encode_dataclass(fact)
        if pats:
            by_ts[frame.timestamp.isoformat()] = pats
    return by_ts


def _rejections_by_ts(frames: Any) -> dict[str, list[dict[str, str]]]:
    """Collect signal-rejection evidence per frame timestamp."""
    by_ts: dict[str, list[dict[str, str]]] = {}
    for frame in frames:
        if frame.signal_rejections:
            by_ts[frame.timestamp.isoformat()] = [
                {"text": e.text, "level": e.level.value, "source": e.source}
                for e in frame.signal_rejections
            ]
    return by_ts


def encode_analysis_output(output: Any) -> dict[str, Any]:
    """Encode one instrument's renderable payload.

    Consumer-oriented schema (single source of truth for HTML/PNG consumers):
    per-timeframe candles, per-frame typed facts keyed by timestamp, the
    traded outcomes, and per-frame signal rejections. Does not reconstruct the
    live object graph — it carries everything a renderer needs.
    """
    return {
        "symbol": output.symbol,
        "timeframe": output.timeframe,
        "timeframes": list(output.timeframes),
        "max_hold_days": getattr(output, "max_hold_days", 10),
        "candles": {
            tf: [_candle_to_dict(c) for c in candles]
            for tf, candles in output.candles.items()
        },
        "facts_by_ts": {
            frame.timestamp.isoformat(): encode_frame_facts(frame)
            for frame in output.frames
        },
        "patterns_by_ts": _patterns_by_ts(output.frames),
        "rejections_by_ts": _rejections_by_ts(output.frames),
        "trades": [_trade_to_dict(t) for t in output.trades],
    }


def encode_portfolio(po: Any) -> dict[str, Any]:
    """Encode a ``PortfolioOutput`` as a typed structured JSON document."""
    return {
        "summary": po.summary.to_dict(),
        "instruments": list(po.instruments),
        "per_instrument": {
            canonical: encode_analysis_output(out)
            for canonical, out in po.outputs.items()
        },
        "monthly": po.monthly,
        "window_size": po.window_size,
        "max_hold_days": po.max_hold_days,
        "title": po.title,
    }


def encode_facts_by_symbol(outputs: Any) -> dict[str, dict[str, Any]]:
    """Encode each instrument's per-frame facts from ``PortfolioOutput.outputs``.

    Returns ``{symbol: {frame_timestamp: {fact_key: encoded_fact}}}`` keyed so a
    renderer can pair facts with candles by timestamp without lookahead.
    """
    result: dict[str, dict[str, Any]] = {}
    for symbol, out in outputs.items():
        by_ts: dict[str, Any] = {}
        for frame in out.frames:
            by_ts[frame.timestamp.isoformat()] = encode_frame_facts(frame)
        result[symbol] = by_ts
    return result
