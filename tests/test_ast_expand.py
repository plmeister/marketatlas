import pytest
from marketatlas.analysis.ast.expressions import (
    Choice,
    ChoiceExpression,
    LiteralExpression,
    wrap,
)
from marketatlas.analysis.ast.models import (
    Analysis,
    Binding,
    Definition,
    Parameter,
    Provider,
)
from marketatlas.analysis.ast.pipeline import CompilationError, expand
from marketatlas.analysis.ast.serialization import to_dict, to_json


def _analysis(*definitions: Definition, providers: tuple[Provider, ...] = ()) -> Analysis:
    return Analysis(name="test", version="1.0.0", definitions=definitions, providers=providers)


def _def(name: str, *params: Parameter) -> Definition:
    return Definition(name=name, provider=name, parameters=params)


def _param(name: str, value: object) -> Parameter:
    return Parameter(name=name, value=wrap(value))


def _literal_value(param: Parameter) -> object:
    assert isinstance(param.value, LiteralExpression)
    assert not isinstance(param.value, ChoiceExpression)
    return param.value.value


def _contains_choice(analysis: Analysis) -> bool:
    for d in analysis.definitions:
        for p in d.parameters:
            if isinstance(p.value, ChoiceExpression):
                return True
    return False


class TestSingleChoice:
    def test_two_ast_one_per_leaf(self) -> None:
        a = _analysis(_def("ema", _param("period", Choice([50, 100]))))
        out = expand(a)
        assert len(out) == 2
        assert _literal_value(out[0].definitions[0].parameters[0]) == 50
        assert _literal_value(out[1].definitions[0].parameters[0]) == 100

    def test_definition_order_preserved(self) -> None:
        a = _analysis(_def("ema", _param("period", Choice([50, 100]))))
        out = expand(a)
        assert [d.name for d in out[0].definitions] == ["ema"]


class TestNestedChoice:
    def test_nested_flattened(self) -> None:
        a = _analysis(_def("ema", _param("period", Choice([Choice([1, 2]), 3]))))
        out = expand(a)
        assert len(out) == 3
        assert [_literal_value(o.definitions[0].parameters[0]) for o in out] == [1, 2, 3]


class TestMultipleChoices:
    def test_same_definition_product(self) -> None:
        a = _analysis(
            _def(
                "ema",
                _param("period", Choice([50, 100])),
                _param("lookback", Choice([5, 10])),
            )
        )
        out = expand(a)
        assert len(out) == 4
        pairs = [
            (_literal_value(d.parameters[0]), _literal_value(d.parameters[1]))
            for d in (o.definitions[0] for o in out)
        ]
        assert pairs == [(50, 5), (50, 10), (100, 5), (100, 10)]

    def test_across_definitions_product(self) -> None:
        a = _analysis(
            _def("ema", _param("period", Choice([50, 100]))),
            _def("atr", _param("period", Choice([14, 21]))),
        )
        out = expand(a)
        assert len(out) == 4
        pairs = [
            (
                _literal_value(o.definitions[0].parameters[0]),
                _literal_value(o.definitions[1].parameters[0]),
            )
            for o in out
        ]
        assert pairs == [(50, 14), (50, 21), (100, 14), (100, 21)]

    def test_choice_and_plain_definitions(self) -> None:
        a = _analysis(
            _def("ema", _param("period", Choice([50, 100]))),
            _def("trend", _param("source", "close")),
        )
        out = expand(a)
        assert len(out) == 2
        assert _literal_value(out[0].definitions[1].parameters[0]) == "close"
        assert _literal_value(out[1].definitions[1].parameters[0]) == "close"


class TestListLiteral:
    def test_raw_list_never_expands(self) -> None:
        a = _analysis(_def("ema", _param("periods", [50, 100])))
        out = expand(a)
        assert len(out) == 1
        v = out[0].definitions[0].parameters[0].value
        assert isinstance(v, LiteralExpression)
        assert v == [50, 100]

    def test_list_literal_next_to_choice(self) -> None:
        a = _analysis(
            _def(
                "ema",
                _param("period", Choice([50, 100])),
                _param("periods", [5, 10]),
            )
        )
        out = expand(a)
        assert len(out) == 2
        for o in out:
            p = o.definitions[0].parameters[1]
            assert isinstance(p.value, LiteralExpression)
            assert p.value == [5, 10]


class TestEmptyChoice:
    def test_raises_with_definition_and_param(self) -> None:
        a = _analysis(_def("ema", _param("period", Choice([]))))
        with pytest.raises(CompilationError, match="'period'.*'ema'"):
            expand(a)

    def test_raises_even_alongside_other_params(self) -> None:
        a = _analysis(
            _def(
                "ema",
                _param("period", Choice([50, 100])),
                _param("lookback", Choice([])),
            )
        )
        with pytest.raises(CompilationError, match="'lookback'.*'ema'"):
            expand(a)


class TestConcreteGuarantees:
    def test_no_choice_in_output(self) -> None:
        a = _analysis(
            _def(
                "ema",
                _param("period", Choice([Choice([1, 2]), 3])),
                _param("lookback", Choice([5, 10])),
            ),
            _def("atr", _param("period", Choice([14, 21]))),
        )
        out = expand(a)
        assert len(out) == 12
        for o in out:
            assert not _contains_choice(o)

    def test_idempotent_on_concrete(self) -> None:
        a = _analysis(_def("ema", _param("period", 20)))
        out = expand(a)
        assert len(out) == 1
        assert out[0] == a

    def test_expanding_concrete_variant_is_identity(self) -> None:
        a = _analysis(_def("ema", _param("period", Choice([50, 100]))))
        out = expand(a)
        assert all(expand(v) == (v,) for v in out)

    def test_no_params_single_variant(self) -> None:
        a = _analysis(_def("ema"))
        out = expand(a)
        assert len(out) == 1
        assert out[0] == a


class TestPurity:
    def test_input_not_mutated(self) -> None:
        a = _analysis(
            _def(
                "ema",
                _param("period", Choice([Choice([1, 2]), 3])),
                _param("periods", [5, 10]),
            )
        )
        before = to_json(a)
        expand(a)
        assert to_json(a) == before

    def test_variant_literals_independent(self) -> None:
        a = _analysis(_def("ema", _param("periods", [5, 10])))
        out = expand(a)
        v = out[0].definitions[0].parameters[0].value
        assert isinstance(v, LiteralExpression)
        assert isinstance(v.value, list)
        v.value.append(999)
        assert a.definitions[0].parameters[0].value == [5, 10]

    def test_choice_node_identity_preserved_in_template(self) -> None:
        choice = Choice([50, 100])
        a = _analysis(_def("ema", _param("period", choice)))
        expand(a)
        assert a.definitions[0].parameters[0].value is choice


class TestStructurePreserved:
    def test_bindings_preserved_in_variants(self) -> None:
        binding = Binding(source="price", output="close", target="ema", input="source")
        a = Analysis(
            name="test",
            version="1.0",
            definitions=(
                Definition(
                    name="price",
                    provider="price",
                    parameters=(),
                    bindings=(),
                ),
                Definition(
                    name="ema",
                    provider="ema",
                    parameters=(_param("period", Choice([50, 100])),),
                    bindings=(binding,),
                ),
            ),
        )
        out = expand(a)
        for o in out:
            assert o.definitions[1].bindings == (binding,)

    def test_providers_preserved(self) -> None:
        provider = Provider(
            name="ema",
            capability="compute_ema",
            category="analyzer",
            impl="EMAAnalyzer",
        )
        a = _analysis(
            _def("ema", _param("period", Choice([50, 100]))),
            providers=(provider,),
        )
        out = expand(a)
        for o in out:
            assert o.providers == (provider,)

    def test_id_and_metadata_preserved(self) -> None:
        a = Analysis(
            name="test",
            version="1.0",
            definitions=(
                Definition(
                    name="ema",
                    provider="ema",
                    parameters=(_param("period", Choice([50, 100])),),
                    id="def-id",
                    metadata={"author": "test"},
                ),
            ),
            id="analysis-id",
            metadata={"env": "prod"},
        )
        out = expand(a)
        assert out[0].id == "analysis-id"
        assert out[0].metadata == {"env": "prod"}
        assert out[0].definitions[0].id == "def-id"
        assert out[0].definitions[0].metadata == {"author": "test"}
        assert out[1].id == "analysis-id"

    def test_serializable_round_trip(self) -> None:
        a = _analysis(_def("ema", _param("period", Choice([50, 100]))))
        out = expand(a)
        for o in out:
            restored = to_dict(o)
            value = restored["definitions"][0]["parameters"][0]["value"]  # type: ignore[index]
            assert isinstance(value, int)
            assert value in (50, 100)


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        a = _analysis(
            _def(
                "ema",
                _param("period", Choice([50, 100])),
                _param("lookback", Choice([5, 10])),
            )
        )
        assert expand(a) == expand(a)
