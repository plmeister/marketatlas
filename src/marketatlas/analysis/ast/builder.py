from __future__ import annotations

from marketatlas.analysis.ast.expressions import ReferenceExpression, wrap
from marketatlas.analysis.ast.models import (
    Analysis,
    Definition,
    Parameter,
    Provider,
    derive_timeframes,
)


class _DefinitionBuilder:
    def __init__(self, builder: AnalysisBuilder, name: str, provider_name: str) -> None:
        self._builder = builder
        self._name = name
        self._provider_name = provider_name
        self._parameters: list[Parameter] = []

    def with_param(self, name: str, value: object) -> _DefinitionBuilder:
        self._parameters.append(Parameter(name=name, value=wrap(value)))
        return self

    def with_reference(self, name: str, source: str) -> _DefinitionBuilder:
        """Pass the ``source`` definition as a reference parameter (backlog 061).

        Equivalent to the DSL ``name: source``: the referenced definition is a
        parameter value. A reference to a ``TimeFrame`` definition resolves to
        the consumer's timeframe at compile time; a reference to a
        fact-producing definition is a dependency edge (consumed as a fact
        requirement on signal definitions).
        """
        self._builder._require_definition(source)
        self._parameters.append(Parameter(name=name, value=ReferenceExpression(source)))
        return self

    def with_timeframe(self, source: str) -> _DefinitionBuilder:
        """Bind the definition's timeframe to a ``TimeFrame`` definition.

        Equivalent to ``with_reference("timeframe", source)`` but validates up
        front that ``source`` names a ``TimeFrame`` definition (backlog 061).
        """
        if source not in self._builder._definitions:
            raise ValueError(f"Unknown source definition: {source}")
        if source not in self._builder._timeframe_defs:
            raise ValueError(f"'{source}' is not a TimeFrame definition")
        self._parameters.append(Parameter(name="timeframe", value=ReferenceExpression(source)))
        return self

    def define(
        self, name: str, type_or_provider: str, impl: str | None = None
    ) -> _DefinitionBuilder:
        return self._builder.define(name, type_or_provider, impl)

    def define_provider(
        self, name: str, capability: str, category: str, impl: str, **default_params: object
    ) -> _DefinitionBuilder:
        self._builder.define_provider(name, capability, category, impl, **default_params)
        return self

    def with_metadata(self, key: str, value: str) -> _DefinitionBuilder:
        self._builder.with_metadata(key, value)
        return self

    def build(self) -> Analysis:
        return self._builder.build()

    def _build(self) -> Definition:
        return Definition(
            name=self._name,
            provider=self._provider_name,
            parameters=tuple(self._parameters),
        )


class AnalysisBuilder:
    def __init__(self, name: str, version: str) -> None:
        self._name = name
        self._version = version
        self._definitions: dict[str, _DefinitionBuilder] = {}
        self._providers: dict[str, Provider] = {}
        self._timeframe_defs: set[str] = set()
        self._metadata: dict[str, str] = {}

    def with_metadata(self, key: str, value: str) -> AnalysisBuilder:
        self._metadata[key] = value
        return self

    def define(
        self, name: str, type_or_provider: str, impl: str | None = None
    ) -> _DefinitionBuilder:
        if name in self._definitions:
            raise ValueError(f"Duplicate definition name: {name}")

        if impl is not None:
            provider_name = impl
            if provider_name not in self._providers:
                provider = Provider(
                    name=provider_name,
                    capability="",
                    category=type_or_provider,
                    impl=provider_name,
                )
                self._providers[provider_name] = provider
        else:
            provider_name = type_or_provider

        if provider_name not in self._providers:
            raise ValueError(f"Unknown provider: {provider_name}")

        provider = self._providers[provider_name]
        if provider_name == "timeframe" or provider.category == "timeframe":
            self._timeframe_defs.add(name)

        db = _DefinitionBuilder(self, name, provider_name)
        self._definitions[name] = db
        return db

    def define_provider(
        self, name: str, capability: str, category: str, impl: str, **default_params: object
    ) -> AnalysisBuilder:
        params = tuple(Parameter(name=k, value=wrap(v)) for k, v in default_params.items())
        self._providers[name] = Provider(
            name=name,
            capability=capability,
            category=category,
            impl=impl,
            default_params=params,
        )
        return self

    def build(self) -> Analysis:
        definitions = tuple(db._build() for db in self._definitions.values())
        return Analysis(
            name=self._name,
            version=self._version,
            definitions=definitions,
            providers=tuple(self._providers.values()),
            timeframes=derive_timeframes(definitions),
            metadata=self._metadata if self._metadata else None,
        )

    def _require_definition(self, name: str) -> None:
        if name not in self._definitions:
            raise ValueError(f"Unknown source definition: {name}")
