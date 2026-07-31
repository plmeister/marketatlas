from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from marketatlas.analysis.ast.expressions import Expression, LiteralExpression
from marketatlas.analysis.ast.models import Analysis, Definition, Parameter, Provider
from marketatlas.analysis.ast.registry import ProviderRegistry
from marketatlas.analysis.ast.validation import Diagnostic, validate
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.strategy.config import (
    AnalyzerConfig,
    RiskConfig,
    SignalConfig,
    StrategyConfig,
)
from marketatlas.strategy.loader import build_analyzers


class CompilerPass(ABC):
    """Single compilation stage. Transforms or validates the AST."""

    @abstractmethod
    def run(self, analysis: Analysis) -> Analysis: ...

    @property
    def name(self) -> str:
        return type(self).__name__


class ValidationPass(CompilerPass):
    """Pass 1: Run semantic checks. Raise on errors."""

    def run(self, analysis: Analysis) -> Analysis:
        result = validate(analysis)
        if not result.is_valid:
            msgs = [f"[{d.severity.value}] {d.node_name}: {d.message}" for d in result.errors]
            raise CompilationError(
                f"Validation failed ({len(result.errors)} errors):\n" + "\n".join(msgs),
                errors=result.errors,
                warnings=result.warnings,
            )
        return analysis


class RegistryResolutionPass(CompilerPass):
    """Pass 2: Resolve symbolic capability names to concrete provider references via registry."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def run(self, analysis: Analysis) -> Analysis:
        provider_map = _provider_map(analysis)
        resolved_providers: dict[str, Provider] = dict(provider_map)
        resolved_defs: list[Definition] = []

        for d in analysis.definitions:
            provider_name = d.provider

            try:
                resolved = self._registry.resolve(provider_name)
                resolved_providers[resolved.name] = resolved
                provider_name = resolved.name
            except LookupError:
                if provider_name not in provider_map:
                    raise CompilationError(
                        f"Provider '{d.provider}' not found for definition '{d.name}'. "
                        "Neither in AST providers nor in registry."
                    )

            provider = resolved_providers[provider_name]
            merged_params = _merge_default_params(provider, d.parameters)
            resolved_defs.append(
                Definition(
                    name=d.name,
                    provider=provider_name,
                    parameters=merged_params,
                    bindings=d.bindings,
                    id=d.id,
                    metadata=d.metadata,
                )
            )

        return Analysis(
            name=analysis.name,
            version=analysis.version,
            definitions=tuple(resolved_defs),
            providers=tuple(resolved_providers.values()),
            id=analysis.id,
            metadata=analysis.metadata,
        )


class DefinitionExpansionPass(CompilerPass):
    """Pass 3: Expand definitions — inline default parameters from provider registry."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def run(self, analysis: Analysis) -> Analysis:
        expanded: list[Definition] = []
        for d in analysis.definitions:
            provider = _find_provider(analysis, d.provider)
            if provider is None:
                expanded.append(d)
                continue
            merged = _merge_default_params(provider, d.parameters)
            expanded.append(
                Definition(
                    name=d.name,
                    provider=d.provider,
                    parameters=merged,
                    bindings=d.bindings,
                    id=d.id,
                    metadata=d.metadata,
                )
            )
        return Analysis(
            name=analysis.name,
            version=analysis.version,
            definitions=tuple(expanded),
            providers=analysis.providers,
            id=analysis.id,
            metadata=analysis.metadata,
        )


class GraphGenerationPass(CompilerPass):
    """Pass 4: Convert AST to AnalysisGraph."""

    def run(self, analysis: Analysis) -> Analysis:
        config = _ast_to_config(analysis)
        analyzers = build_analyzers(config)
        return AnalysisGraph(analyzers)  # type: ignore[return-value]


@dataclass(frozen=True)
class CompilationError(Exception):
    message: str = ""
    errors: tuple[Diagnostic, ...] = field(default_factory=tuple)
    warnings: tuple[Diagnostic, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return self.message


class Pipeline:
    """Ordered compilation pipeline. Composable passes."""

    def __init__(self) -> None:
        self._passes: list[CompilerPass] = []

    def add_pass(self, pass_: CompilerPass) -> Pipeline:
        self._passes.append(pass_)
        return self

    def run(self, analysis: Analysis) -> AnalysisGraph:
        current: Analysis = analysis
        for pass_ in self._passes:
            result = pass_.run(current)
            if isinstance(result, Analysis):
                current = result
            elif isinstance(result, AnalysisGraph):
                return result
            else:
                raise CompilationError(
                    f"Pass '{pass_.name}' returned unexpected type: {type(result).__name__}"
                )
        raise CompilationError(
            "Pipeline completed without producing an AnalysisGraph. "
            "Ensure a GraphGenerationPass is included."
        )

    def run_to_ast(self, analysis: Analysis) -> Analysis:
        """Run pipeline but stop before graph generation — returns final AST."""
        current = analysis
        for pass_ in self._passes:
            result = pass_.run(current)
            if isinstance(result, AnalysisGraph):
                return current
            current = result
        return current


def _provider_map(analysis: Analysis) -> dict[str, Provider]:
    return {p.name: p for p in analysis.providers}


def _find_provider(analysis: Analysis, name: str) -> Provider | None:
    return _provider_map(analysis).get(name)


def _merge_default_params(
    provider: Provider, params: tuple[Parameter, ...]
) -> tuple[Parameter, ...]:
    existing = {p.name for p in params}
    merged = list(params)
    for dp in provider.default_params:
        if dp.name not in existing:
            merged.append(dp)
    return tuple(merged)


def _ast_to_config(analysis: Analysis) -> StrategyConfig:
    providers = _provider_map(analysis)
    analyzer_configs: list[AnalyzerConfig] = []
    signal_configs: list[SignalConfig] = []
    risk_config: RiskConfig = RiskConfig(algorithm="none")

    for d in analysis.definitions:
        provider = providers.get(d.provider)
        if provider is None:
            raise CompilationError(f"Unknown provider: {d.provider}")

        params: dict[str, object] = {}
        for p in d.parameters:
            value: object = p.value
            if isinstance(value, LiteralExpression):
                value = value.value
            elif isinstance(value, Expression):
                raise CompilationError(
                    f"Non-literal expression for parameter '{p.name}' of definition "
                    f"'{d.name}' cannot be compiled yet: {type(value).__name__}"
                )
            params[p.name] = value

        if provider.category == "analyzer":
            analyzer_configs.append(AnalyzerConfig(type=provider.impl, params=params))
        elif provider.category == "signal":
            requires = tuple(b.output for b in d.bindings)
            signal_configs.append(SignalConfig(type=provider.impl, requires=requires, rules=params))
        elif provider.category == "risk":
            risk_config = RiskConfig(algorithm=provider.impl, params=params)

    return StrategyConfig(
        name=analysis.name,
        version=analysis.version,
        analyzers=tuple(analyzer_configs),
        signals=tuple(signal_configs),
        risk=risk_config,
    )
