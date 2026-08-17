import json
from typing import Any, cast

import pytest
from marketatlas.analysis.ast.expressions import (

    Choice,
    LiteralExpression,
    ReferenceExpression,
)
from marketatlas.analysis.ast.models import (
    Analysis,
    Definition,
    Parameter,
    Provider,
)
from marketatlas.analysis.ast.serialization import from_dict, from_json, to_dict, to_json
from marketatlas.data.types import Timeframe

pytestmark = pytest.mark.tier2


def _serialized(a: Analysis) -> dict[str, Any]:
    return cast(dict[str, Any], to_dict(a))


def _providers() -> tuple[Provider, ...]:
    return (
        Provider(
            name="EMAAnalyzer", capability="compute_ema", category="analyzer", impl="EMAAnalyzer"
        ),
        Provider(
            name="ATRAnalyzer", capability="compute_atr", category="analyzer", impl="ATRAnalyzer"
        ),
        Provider(
            name="SwingStructureAnalyzer",
            capability="detect_swings",
            category="analyzer",
            impl="SwingStructureAnalyzer",
        ),
    )


class TestToDict:
    def test_minimal_analysis(self) -> None:
        a = Analysis(name="test", version="1.0.0")
        d = _serialized(a)
        assert d == {"name": "test", "version": "1.0.0"}

    def test_with_definitions(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(Definition(name="ema20", provider="EMAAnalyzer"),),
        )
        d = _serialized(a)
        assert d["name"] == "test"
        assert len(d["definitions"]) == 1
        assert d["definitions"][0] == {"name": "ema20", "provider": "EMAAnalyzer"}

    def test_with_parameters(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="ema20",
                    provider="EMAAnalyzer",
                    parameters=(
                        Parameter(name="period", value=LiteralExpression(20)),
                        Parameter(name="source", value=LiteralExpression("close")),
                    ),
                ),
            ),
        )
        d = _serialized(a)
        params = d["definitions"][0]["parameters"]
        assert params == [{"name": "period", "value": 20}, {"name": "source", "value": "close"}]

    def test_with_reference_param(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="swing",
                    provider="SwingStructureAnalyzer",
                    parameters=(Parameter(name="atr_14", value=ReferenceExpression("atr14")),),
                ),
            ),
        )
        d = _serialized(a)
        params = d["definitions"][0]["parameters"]
        assert params == [{"name": "atr_14", "value": {"expr": "reference", "name": "atr14"}}]

    def test_with_choice_param(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(
                Definition(
                    name="ema20",
                    provider="EMAAnalyzer",
                    parameters=(Parameter(name="period", value=Choice([50, 100])),),
                ),
            ),
        )
        d = _serialized(a)
        params = d["definitions"][0]["parameters"]
        assert params == [{"name": "period", "value": {"expr": "choice", "values": [50, 100]}}]

    def test_with_providers(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            providers=_providers(),
        )
        d = _serialized(a)
        assert len(d["providers"]) == 3
        assert d["providers"][0] == {
            "name": "EMAAnalyzer",
            "capability": "compute_ema",
            "category": "analyzer",
            "impl": "EMAAnalyzer",
        }

    def test_with_provider_default_params(self) -> None:
        p = Provider(
            name="EMAAnalyzer",
            capability="compute_ema",
            category="analyzer",
            impl="EMAAnalyzer",
            default_params=(Parameter(name="period", value=LiteralExpression(20)),),
        )
        a = Analysis(name="test", version="1.0", providers=(p,))
        d = _serialized(a)
        assert d["providers"][0]["default_params"] == [{"name": "period", "value": 20}]

    def test_with_timeframes(self) -> None:
        a = Analysis(name="test", version="1.0", timeframes=("1w",))
        d = _serialized(a)
        assert d["timeframes"] == ["1w"]

    def test_with_id(self) -> None:
        a = Analysis(name="t", version="1.0", id="analysis1")
        d = _serialized(a)
        assert d["id"] == "analysis1"

    def test_with_metadata(self) -> None:
        a = Analysis(name="t", version="1.0", metadata={"author": "Scott"})
        d = _serialized(a)
        assert d["metadata"] == {"author": "Scott"}

    def test_empty_ids_omitted(self) -> None:
        a = Analysis(name="t", version="1.0")
        d = _serialized(a)
        assert "id" not in d

    def test_empty_metadata_omitted(self) -> None:
        a = Analysis(name="t", version="1.0")
        d = _serialized(a)
        assert "metadata" not in d

    def test_definition_with_metadata(self) -> None:
        d_def = Definition(name="t", provider="I", metadata={"key": "val"})
        a = Analysis(name="t", version="1.0", definitions=(d_def,))
        d = _serialized(a)
        assert d["definitions"][0]["metadata"] == {"key": "val"}

    def test_definition_with_id(self) -> None:
        d_def = Definition(name="t", provider="I", id="def1")
        a = Analysis(name="t", version="1.0", definitions=(d_def,))
        d = _serialized(a)
        assert d["definitions"][0]["id"] == "def1"

    def test_timeframe_literal_serializes_as_string(self) -> None:
        a = Analysis(
            name="test",
            version="1.0",
            definitions=(
                Definition(
                    name="tf",
                    provider="timeframe",
                    parameters=(
                        Parameter(
                            name="resolution",
                            value=LiteralExpression(Timeframe("1w")),
                        ),
                    ),
                ),
            ),
        )
        d = _serialized(a)
        assert d["definitions"][0]["parameters"] == [{"name": "resolution", "value": "1w"}]


class TestFromDict:
    def test_minimal_analysis(self) -> None:
        a = from_dict({"name": "test", "version": "1.0.0"})
        assert a.name == "test"
        assert a.version == "1.0.0"
        assert a.definitions == ()
        assert a.providers == ()
        assert a.id == ""
        assert a.metadata is None

    def test_full_strategy(self) -> None:
        data: dict[str, Any] = {
            "name": "pullback_4swing",
            "version": "1.0.0",
            "providers": [
                {
                    "name": "EMAAnalyzer",
                    "capability": "compute_ema",
                    "category": "analyzer",
                    "impl": "EMAAnalyzer",
                },
                {
                    "name": "ATRAnalyzer",
                    "capability": "compute_atr",
                    "category": "analyzer",
                    "impl": "ATRAnalyzer",
                },
                {
                    "name": "SwingStructureAnalyzer",
                    "capability": "detect_swings",
                    "category": "analyzer",
                    "impl": "SwingStructureAnalyzer",
                },
            ],
            "definitions": [
                {
                    "name": "ema20",
                    "provider": "EMAAnalyzer",
                    "parameters": [{"name": "period", "value": 20}],
                },
                {
                    "name": "atr14",
                    "provider": "ATRAnalyzer",
                    "parameters": [{"name": "period", "value": 14}],
                },
                {
                    "name": "swing",
                    "provider": "SwingStructureAnalyzer",
                    "parameters": [
                        {"name": "lookback", "value": 100},
                        {"name": "min_separation_atr", "value": 1.5},
                        {"name": "atr_14", "value": {"expr": "reference", "name": "atr14"}},
                    ],
                },
            ],
            "metadata": {"author": "Scott", "description": "4-swing pullback strategy"},
        }
        a = from_dict(data)
        assert a.name == "pullback_4swing"
        assert a.version == "1.0.0"
        assert len(a.definitions) == 3
        assert len(a.providers) == 3
        assert a.metadata == {"author": "Scott", "description": "4-swing pullback strategy"}

        ema = a.definitions[0]
        assert ema.name == "ema20"
        assert ema.provider == "EMAAnalyzer"
        assert ema.parameters[0].value == LiteralExpression(20)

        swing = a.definitions[2]
        assert len(swing.parameters) == 3
        assert swing.parameters[2].value == ReferenceExpression("atr14")

    def test_missing_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: name"):
            from_dict({"version": "1.0.0"})

    def test_missing_version_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: version"):
            from_dict({"name": "test"})

    def test_definition_missing_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: name"):
            from_dict({"name": "test", "version": "1.0", "definitions": [{"provider": "P"}]})

    def test_parameter_missing_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing required field: name"):
            from_dict(
                {
                    "name": "test",
                    "version": "1.0",
                    "definitions": [
                        {"name": "d", "provider": "P", "parameters": [{"value": 20}]}
                    ],
                }
            )

    def test_provider_missing_field_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing required field"):
            from_dict(
                {
                    "name": "test",
                    "version": "1.0",
                    "providers": [{"name": "P", "capability": "c", "category": "a"}],
                }
            )

    def test_invalid_timeframe_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid timeframe '13m'"):
            from_dict({"name": "test", "version": "1.0", "timeframes": ["13m"]})

    def test_round_trip(self) -> None:
        original = Analysis(
            name="pullback_4swing",
            version="1.0.0",
            providers=_providers(),
            definitions=(
                Definition(
                    name="ema20",
                    provider="EMAAnalyzer",
                    parameters=(
                        Parameter(name="period", value=LiteralExpression(20)),
                        Parameter(name="source", value=LiteralExpression("close")),
                    ),
                ),
                Definition(
                    name="atr14",
                    provider="ATRAnalyzer",
                    parameters=(Parameter(name="period", value=LiteralExpression(14)),),
                ),
                Definition(
                    name="swing",
                    provider="SwingStructureAnalyzer",
                    parameters=(
                        Parameter(name="lookback", value=LiteralExpression(100)),
                        Parameter(name="atr_14", value=ReferenceExpression("atr14")),
                    ),
                ),
            ),
            metadata={"author": "Scott", "description": "4-swing pullback strategy"},
        )
        restored = from_dict(to_dict(original))
        assert restored == original
        assert restored.definitions[0].parameters[0].value == LiteralExpression(20)
        assert restored.definitions[2].parameters[1].value == ReferenceExpression("atr14")
        assert restored.metadata == original.metadata
        assert len(restored.providers) == 3

    def test_round_trip_minimal(self) -> None:
        original = Analysis(name="test", version="1.0.0")
        restored = from_dict(to_dict(original))
        assert restored == original

    def test_empty_definitions(self) -> None:
        a = from_dict({"name": "test", "version": "1.0", "definitions": []})
        assert a.definitions == ()


class TestToJson:
    def test_basic_json(self) -> None:
        a = Analysis(name="test", version="1.0.0")
        s = to_json(a)
        parsed = json.loads(s)
        assert parsed["name"] == "test"
        assert parsed["version"] == "1.0.0"

    def test_pretty_print(self) -> None:
        a = Analysis(name="test", version="1.0.0")
        compact = to_json(a, pretty=False)
        pretty = to_json(a, pretty=True)
        assert "\n" not in compact
        assert "\n" in pretty

    def test_includes_definitions(self) -> None:
        a = Analysis(
            name="test",
            version="1.0.0",
            definitions=(Definition(name="d1", provider="P"),),
        )
        s = to_json(a)
        parsed = json.loads(s)
        assert len(parsed["definitions"]) == 1
        assert parsed["definitions"][0]["name"] == "d1"


class TestFromJson:
    def test_basic_deserialize(self) -> None:
        s = '{"name": "test", "version": "1.0.0"}'
        a = from_json(s)
        assert a.name == "test"
        assert a.version == "1.0.0"

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(ValueError, match="Malformed JSON"):
            from_json("not json")

    def test_non_object_json_raises(self) -> None:
        with pytest.raises(ValueError, match="JSON root must be an object"):
            from_json('"string"')

    def test_round_trip_json(self) -> None:
        original = Analysis(
            name="pullback_4swing",
            version="1.0.0",
            providers=_providers(),
            definitions=(
                Definition(
                    name="ema20",
                    provider="EMAAnalyzer",
                    parameters=(Parameter(name="period", value=LiteralExpression(20)),),
                ),
            ),
            metadata={"author": "Scott"},
        )
        restored = from_json(to_json(original))
        assert restored == original

    def test_round_trip_no_information_loss(self) -> None:
        original = Analysis(
            name="full_strategy",
            version="2.0.0",
            providers=_providers(),
            definitions=(
                Definition(
                    name="ema20",
                    provider="EMAAnalyzer",
                    parameters=(
                        Parameter(name="period", value=LiteralExpression(20)),
                        Parameter(name="source", value=LiteralExpression("close")),
                    ),
                    id="def_ema20",
                    metadata={"label": "Fast EMA"},
                ),
                Definition(
                    name="atr14",
                    provider="ATRAnalyzer",
                    parameters=(
                        Parameter(name="period", value=LiteralExpression(14)),
                        Parameter(name="trend", value=ReferenceExpression("ema20")),
                    ),
                ),
            ),
            id="analysis_v2",
            metadata={"author": "Scott", "description": "Full round-trip test"},
        )
        restored = from_json(to_json(original))
        assert restored == original
        assert restored.id == "analysis_v2"
        assert restored.definitions[0].id == "def_ema20"
        assert restored.definitions[0].metadata == {"label": "Fast EMA"}
        assert restored.definitions[1].parameters[1].value == ReferenceExpression("ema20")


class TestEdgeCases:
    def test_float_values(self) -> None:
        a = Analysis(
            name="t",
            version="1.0",
            definitions=(
                Definition(
                    name="d",
                    provider="I",
                    parameters=(Parameter(name="threshold", value=LiteralExpression(1.5)),),
                ),
            ),
        )
        restored = from_json(to_json(a))
        assert restored.definitions[0].parameters[0].value == LiteralExpression(1.5)

    def test_bool_values(self) -> None:
        a = Analysis(
            name="t",
            version="1.0",
            definitions=(
                Definition(
                    name="d",
                    provider="I",
                    parameters=(Parameter(name="enabled", value=LiteralExpression(True)),),
                ),
            ),
        )
        restored = from_json(to_json(a))
        assert restored.definitions[0].parameters[0].value is True

    def test_none_value(self) -> None:
        a = Analysis(
            name="t",
            version="1.0",
            definitions=(
                Definition(
                    name="d",
                    provider="I",
                    parameters=(Parameter(name="optional", value=LiteralExpression(None)),),
                ),
            ),
        )
        restored = from_json(to_json(a))
        assert restored.definitions[0].parameters[0].value == LiteralExpression(None)

    def test_choice_round_trip(self) -> None:
        a = Analysis(
            name="t",
            version="1.0",
            definitions=(
                Definition(
                    name="d",
                    provider="I",
                    parameters=(Parameter(name="period", value=Choice([50, 100])),),
                ),
            ),
        )
        restored = from_json(to_json(a))
        assert restored == a
        assert restored.definitions[0].parameters[0].value == Choice([50, 100])

    def test_empty_definition_list(self) -> None:
        a = Analysis(name="t", version="1.0", definitions=())
        restored = from_json(to_json(a))
        assert restored == a
        assert restored.definitions == ()

    def test_id_empty_string_default(self) -> None:
        a = from_dict({"name": "t", "version": "1.0"})
        assert a.id == ""
