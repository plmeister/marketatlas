from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from marketatlas.analysis.ast.expressions import (
    ChoiceExpression,
    Expression,
    LiteralExpression,
)
from marketatlas.analysis.ast.models import (
    Analysis,
    Binding,
    Definition,
    Parameter,
    Provider,
)


def _expression_to_dict(value: object, param_name: str = "") -> object:
    if isinstance(value, LiteralExpression):
        return value.value
    if isinstance(value, ChoiceExpression):
        return {
            "expr": "choice",
            "values": [_expression_to_dict(v, param_name) for v in value.values],
        }
    if isinstance(value, Expression):
        name_part = f" in parameter '{param_name}'" if param_name else ""
        raise ValueError(f"Unsupported expression node{name_part}: {type(value).__name__}")
    return value


def _dict_to_expression(value: object) -> Expression:
    """Recursive deserializer for choice nodes; literals are wrapped."""
    if isinstance(value, Mapping) and value.get("expr") == "choice" and "values" in value:
        values = value["values"]
        assert isinstance(values, Sequence)
        return ChoiceExpression(tuple(_dict_to_expression(v) for v in values))
    if isinstance(value, Expression):
        return value
    return LiteralExpression(value)


def _parameter_value_from_dict(value: object) -> object:
    if isinstance(value, Mapping) and value.get("expr") == "choice" and "values" in value:
        return _dict_to_expression(value)
    return value


def _parameter_to_dict(p: Parameter) -> dict[str, object]:
    return {"name": p.name, "value": _expression_to_dict(p.value, p.name)}


def _binding_to_dict(b: Binding) -> dict[str, str]:
    return {"source": b.source, "output": b.output, "target": b.target, "input": b.input}


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
    if d.bindings:
        obj["bindings"] = [_binding_to_dict(b) for b in d.bindings]
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


def _dict_to_binding(d: Mapping[str, object]) -> Binding:
    for field in ("source", "output", "target", "input"):
        if field not in d:
            raise ValueError(f"Missing required field: {field}")
    return Binding(
        source=d["source"],  # type: ignore[arg-type]
        output=d["output"],  # type: ignore[arg-type]
        target=d["target"],  # type: ignore[arg-type]
        input=d["input"],  # type: ignore[arg-type]
    )


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
    bindings_raw = d.get("bindings", ())
    assert isinstance(bindings_raw, Sequence)
    bindings = tuple(_dict_to_binding(b) for b in bindings_raw)
    return Definition(
        name=d["name"],  # type: ignore[arg-type]
        provider=d["provider"],  # type: ignore[arg-type]
        parameters=params,
        bindings=bindings,
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
    return Analysis(
        name=data["name"],  # type: ignore[arg-type]
        version=data["version"],  # type: ignore[arg-type]
        definitions=definitions,
        providers=providers,
        id=data.get("id", ""),  # type: ignore[arg-type]
        metadata=data.get("metadata", None),  # type: ignore[arg-type]
    )


def from_json(data: str) -> Analysis:
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("JSON root must be an object")
    return from_dict(parsed)
