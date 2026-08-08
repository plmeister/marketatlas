from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from marketatlas.analysis.ast.expressions import (
    ChoiceExpression,
    Expression,
    LiteralExpression,
    ReferenceExpression,
    SpanningReferenceExpression,
)
from marketatlas.analysis.ast.models import (
    SCOPE_GROUP,
    SCOPE_INSTRUMENT,
    Analysis,
    Definition,
    Parameter,
    Provider,
    is_group_scope,
)
from marketatlas.data.types import Timeframe


def _expression_to_dict(value: object, param_name: str = "") -> object:
    if isinstance(value, LiteralExpression):
        if isinstance(value.value, Timeframe):
            return value.value.value
        return value.value
    if isinstance(value, ChoiceExpression):
        return {
            "expr": "choice",
            "values": [_expression_to_dict(v, param_name) for v in value.values],
        }
    if isinstance(value, ReferenceExpression):
        if isinstance(value, SpanningReferenceExpression):
            return {"expr": "spanning", "name": value.name}
        return {"expr": "reference", "name": value.name}
    if isinstance(value, Expression):
        name_part = f" in parameter '{param_name}'" if param_name else ""
        raise ValueError(f"Unsupported expression node{name_part}: {type(value).__name__}")
    return value


def _dict_to_expression(value: object) -> Expression:
    """Recursive deserializer for expression nodes; literals are wrapped."""
    if isinstance(value, Mapping) and value.get("expr") == "choice" and "values" in value:
        values = value["values"]
        assert isinstance(values, Sequence)
        return ChoiceExpression(tuple(_dict_to_expression(v) for v in values))
    if isinstance(value, Mapping) and value.get("expr") == "reference" and "name" in value:
        name = value["name"]
        if not isinstance(name, str):
            raise ValueError(f"Invalid reference expression: {value!r}")
        return ReferenceExpression(name)
    if isinstance(value, Mapping) and value.get("expr") == "spanning" and "name" in value:
        name = value["name"]
        if not isinstance(name, str):
            raise ValueError(f"Invalid spanning reference expression: {value!r}")
        return SpanningReferenceExpression(name)
    if isinstance(value, Expression):
        return value
    return LiteralExpression(value)


def _parameter_value_from_dict(value: object) -> object:
    if isinstance(value, Mapping) and value.get("expr") in ("choice", "reference", "spanning"):
        return _dict_to_expression(value)
    return value


def _parameter_to_dict(p: Parameter) -> dict[str, object]:
    return {"name": p.name, "value": _expression_to_dict(p.value, p.name)}


def _provider_to_dict(p: Provider) -> dict[str, object]:
    obj: dict[str, object] = {
        "name": p.name,
        "capability": p.capability,
        "category": p.category,
        "impl": p.impl,
    }
    if p.default_params:
        obj["default_params"] = [_parameter_to_dict(pp) for pp in p.default_params]
    return obj


def _definition_to_dict(d: Definition) -> dict[str, object]:
    obj: dict[str, object] = {
        "name": d.name,
        "provider": d.provider,
    }
    if d.parameters:
        obj["parameters"] = [_parameter_to_dict(p) for p in d.parameters]
    if d.scope != SCOPE_INSTRUMENT:
        obj["scope"] = d.scope
    if d.id:
        obj["id"] = d.id
    if d.metadata:
        obj["metadata"] = d.metadata
    return obj


def to_dict(analysis: Analysis) -> dict[str, object]:
    obj: dict[str, object] = {
        "name": analysis.name,
        "version": analysis.version,
    }
    if analysis.definitions:
        obj["definitions"] = [_definition_to_dict(d) for d in analysis.definitions]
    if analysis.providers:
        obj["providers"] = [_provider_to_dict(p) for p in analysis.providers]
    if analysis.timeframes:
        obj["timeframes"] = list(analysis.timeframes)
    if analysis.id:
        obj["id"] = analysis.id
    if analysis.metadata:
        obj["metadata"] = analysis.metadata
    return obj


def to_json(analysis: Analysis, *, pretty: bool = False) -> str:
    indent = 2 if pretty else None
    return json.dumps(to_dict(analysis), indent=indent, ensure_ascii=False, default=str)


def _dict_to_parameter(d: Mapping[str, object]) -> Parameter:
    if "name" not in d:
        raise ValueError("Missing required field: name")
    if "value" not in d:
        raise ValueError("Missing required field: value")
    return Parameter(name=d["name"], value=_parameter_value_from_dict(d["value"]))  # type: ignore[arg-type]


def _dict_to_provider(d: Mapping[str, object]) -> Provider:
    for field in ("name", "capability", "category", "impl"):
        if field not in d:
            raise ValueError(f"Missing required field: {field}")
    params_raw = d.get("default_params", ())
    assert isinstance(params_raw, Sequence)
    params = tuple(_dict_to_parameter(p) for p in params_raw)
    return Provider(
        name=d["name"],  # type: ignore[arg-type]
        capability=d["capability"],  # type: ignore[arg-type]
        category=d["category"],  # type: ignore[arg-type]
        impl=d["impl"],  # type: ignore[arg-type]
        default_params=params,
    )


def _dict_to_definition(d: Mapping[str, object]) -> Definition:
    for field in ("name", "provider"):
        if field not in d:
            raise ValueError(f"Missing required field: {field}")
    params_raw = d.get("parameters", ())
    assert isinstance(params_raw, Sequence)
    params = tuple(_dict_to_parameter(p) for p in params_raw)
    scope = d.get("scope", SCOPE_INSTRUMENT)
    if not isinstance(scope, str) or not is_group_scope(scope):
        valid = ", ".join(sorted((SCOPE_INSTRUMENT, SCOPE_GROUP)))
        raise ValueError(f"Invalid scope '{scope}'. Valid scopes: {valid}")
    return Definition(
        name=d["name"],  # type: ignore[arg-type]
        provider=d["provider"],  # type: ignore[arg-type]
        parameters=params,
        scope=scope,
        id=d.get("id", ""),  # type: ignore[arg-type]
        metadata=d.get("metadata", None),  # type: ignore[arg-type]
    )


def from_dict(data: Mapping[str, object]) -> Analysis:
    for field in ("name", "version"):
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    definitions_raw = data.get("definitions", ())
    definitions_list: Sequence[Mapping[str, object]] = definitions_raw  # type: ignore[assignment]
    definitions = tuple(_dict_to_definition(d) for d in definitions_list)
    providers_raw = data.get("providers", ())
    providers_list: Sequence[Mapping[str, object]] = providers_raw  # type: ignore[assignment]
    providers = tuple(_dict_to_provider(p) for p in providers_list)
    timeframes_raw = data.get("timeframes", ())
    timeframes_list: Sequence[object] = timeframes_raw  # type: ignore[assignment]
    timeframes = tuple(_dict_to_timeframe_string(tf) for tf in timeframes_list)
    return Analysis(
        name=data["name"],  # type: ignore[arg-type]
        version=data["version"],  # type: ignore[arg-type]
        definitions=definitions,
        providers=providers,
        timeframes=timeframes,
        id=data.get("id", ""),  # type: ignore[arg-type]
        metadata=data.get("metadata", None),  # type: ignore[arg-type]
    )


def _dict_to_timeframe_string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid timeframe: expected a string, got {type(value).__name__}")
    try:
        return Timeframe(value).value
    except ValueError:
        valid = ", ".join(tf.value for tf in Timeframe)
        raise ValueError(f"Invalid timeframe '{value}'. Valid timeframes: {valid}") from None


def from_json(data: str) -> Analysis:
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("JSON root must be an object")
    return from_dict(parsed)
