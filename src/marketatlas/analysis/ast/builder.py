from __future__ import annotations

from marketatlas.analysis.ast.models import Analysis, Binding, Definition, Parameter


class _DefinitionBuilder:
    def __init__(self, builder: AnalysisBuilder, name: str, type: str, impl: str) -> None:
        self._builder = builder
        self._name = name
        self._type = type
        self._impl = impl
        self._parameters: list[Parameter] = []
        self._bindings: list[Binding] = []

    def with_param(self, name: str, value: object) -> _DefinitionBuilder:
        self._parameters.append(Parameter(name=name, value=value))
        return self

    def bind(self, source: str, output: str, target: str, input: str) -> _DefinitionBuilder:
        if source not in self._builder._definitions:
            raise ValueError(f"Unknown source definition: {source}")
        if target not in self._builder._definitions:
            raise ValueError(f"Unknown target definition: {target}")
        self._bindings.append(Binding(source=source, output=output, target=target, input=input))
        return self

    def define(self, name: str, type: str, impl: str) -> _DefinitionBuilder:
        return self._builder.define(name, type, impl)

    def with_metadata(self, key: str, value: str) -> _DefinitionBuilder:
        self._builder.with_metadata(key, value)
        return self

    def build(self) -> Analysis:
        return self._builder.build()

    def _build(self) -> Definition:
        return Definition(
            name=self._name,
            type=self._type,
            impl=self._impl,
            parameters=tuple(self._parameters),
            bindings=tuple(self._bindings),
        )


class AnalysisBuilder:
    def __init__(self, name: str, version: str) -> None:
        self._name = name
        self._version = version
        self._definitions: dict[str, _DefinitionBuilder] = {}
        self._metadata: dict[str, str] = {}

    def with_metadata(self, key: str, value: str) -> AnalysisBuilder:
        self._metadata[key] = value
        return self

    def define(self, name: str, type: str, impl: str) -> _DefinitionBuilder:
        if name in self._definitions:
            raise ValueError(f"Duplicate definition name: {name}")
        db = _DefinitionBuilder(self, name, type, impl)
        self._definitions[name] = db
        return db

    def build(self) -> Analysis:
        return Analysis(
            name=self._name,
            version=self._version,
            definitions=tuple(db._build() for db in self._definitions.values()),
            metadata=self._metadata if self._metadata else None,
        )
