import pytest
from marketatlas.analysis.ast.clone import clone, clone_expression
from marketatlas.analysis.ast.expressions import (
    Choice,
    ChoiceExpression,
    Expression,
    LiteralExpression,
    ReferenceExpression,
)
from marketatlas.analysis.ast.models import (
    Analysis,
    Capability,
    Definition,
    Parameter,
    Provider,
)
from marketatlas.analysis.ast.serialization import to_json


def _full_analysis() -> Analysis:
    return Analysis(
        name="golden",
        version="1.0.0",
        definitions=(
            Definition(
                name="ema20",
                provider="ema",
                parameters=(
                    Parameter(name="period", value=LiteralExpression(20)),
                    Parameter(name="source", value=ReferenceExpression("price")),
                ),
                id="def-1",
                metadata={"author": "test"},
            ),
            Definition(
                name="ema_variant",
                provider="ema",
                parameters=(
                    Parameter(name="period", value=Choice([50, 100])),
                    Parameter(name="periods", value=LiteralExpression([5, 10])),
                ),
                id="def-2",
            ),
        ),
        providers=(
            Provider(
                name="ema",
                capability="compute_ema",
                category="analyzer",
                impl="EMAAnalyzer",
                default_params=(Parameter(name="source", value=LiteralExpression("close")),),
            ),
        ),
        id="analysis-1",
        metadata={"version": "v1"},
    )


class TestExpressionClone:
    def test_literal_returns_equal(self) -> None:
        e = LiteralExpression(20)
        c = clone_expression(e)
        assert c == e
        assert c is not e

    def test_choice_recursive(self) -> None:
        e = Choice([Choice([1, 2]), 3])
        c = clone_expression(e)
        assert c == e
        assert isinstance(c, ChoiceExpression)
        assert c is not e
        c0, e0 = c.values[0], e.values[0]
        assert isinstance(c0, ChoiceExpression)
        assert isinstance(e0, ChoiceExpression)
        assert c0 is not e0
        assert c0.values[0] is not e0.values[0]

    def test_literal_list_payload_independent(self) -> None:
        e = LiteralExpression([50, 100])
        c = clone_expression(e)
        assert c == e
        assert isinstance(c, LiteralExpression)
        payload = c.value
        assert isinstance(payload, list)
        payload.append(999)
        assert e.value == [50, 100]

    def test_unknown_expression_type_raises(self) -> None:
        class _Weird(Expression):  # type: ignore[misc]
            pass

        with pytest.raises(TypeError):
            clone_expression(_Weird())


class TestNodeClone:
    def test_analysis_equal_and_independent(self) -> None:
        a = _full_analysis()
        c = clone(a)
        assert isinstance(c, Analysis)
        assert c == a
        assert c is not a
        assert to_json(c) == to_json(a)

    def test_definition_equal_and_independent(self) -> None:
        d = _full_analysis().definitions[0]
        c = clone(d)
        assert isinstance(c, Definition)
        assert c == d
        assert c is not d
        assert c.parameters[0] is not d.parameters[0]

    def test_parameter_equal_and_independent(self) -> None:
        p = Parameter(name="period", value=Choice([50, 100]))
        c = clone(p)
        assert isinstance(c, Parameter)
        assert c == p
        assert c is not p
        assert c.value is not p.value

    def test_reference_expression_equal_and_independent(self) -> None:
        e = ReferenceExpression("price")
        c = clone_expression(e)
        assert isinstance(c, ReferenceExpression)
        assert c == e
        assert c is not e

    def test_provider_default_params_cloned(self) -> None:
        p = _full_analysis().providers[0]
        c = clone(p)
        assert isinstance(c, Provider)
        assert c == p
        assert c is not p
        assert c.default_params[0] is not p.default_params[0]

    def test_capability_equal_and_independent(self) -> None:
        cap = Capability(id="compute_ema", description="EMA", required_params=("period",))
        c = clone(cap)
        assert isinstance(c, Capability)
        assert c == cap
        assert c is not cap

    def test_metadata_dict_independent(self) -> None:
        d = _full_analysis().definitions[0]
        assert d.metadata is not None
        c = clone(d)
        assert c.metadata is not None
        assert c.metadata is not d.metadata
        c.metadata["author"] = "hacked"
        assert d.metadata["author"] == "test"

    def test_choice_param_payload_mutation_isolated(self) -> None:
        a = _full_analysis()
        c = clone(a)
        payload = c.definitions[1].parameters[1].value
        assert isinstance(payload, LiteralExpression)
        value = payload.value
        assert isinstance(value, list)
        value.append(999)
        assert a.definitions[1].parameters[1].value == [5, 10]

    def test_pure_literal_round_trip_equal(self) -> None:
        a = _full_analysis()
        c = clone(clone(a))
        assert c == a

    def test_id_and_metadata_preserved(self) -> None:
        a = _full_analysis()
        c = clone(a)
        assert c.id == "analysis-1"
        assert c.definitions[0].id == "def-1"
        assert c.definitions[0].metadata == {"author": "test"}

    def test_unknown_node_raises(self) -> None:
        with pytest.raises(TypeError):
            clone("not-a-node")


class TestCloneTyping:
    def test_analysis_static_type(self) -> None:
        a: Analysis = _full_analysis()
        assert isinstance(clone(a), Analysis)
        assert isinstance(clone(a.definitions[0]), Definition)
        assert isinstance(clone(a.definitions[0].parameters[0]), Parameter)
        assert isinstance(clone(a.definitions[1].parameters[0].value), Expression)
        assert isinstance(clone(a.providers[0]), Provider)
        assert isinstance(clone(a.definitions[1].parameters[0].value), Expression)
