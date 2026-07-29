from __future__ import annotations

from marketatlas.analysis.ast.models import Analysis
from marketatlas.analysis.ast.pipeline import (
    DefinitionExpansionPass,
    GraphGenerationPass,
    Pipeline,
    RegistryResolutionPass,
    ValidationPass,
)
from marketatlas.analysis.ast.registry import ProviderRegistry, create_default_registry
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.strategy.config import StrategyConfig


class ASTCompiler:
    @staticmethod
    def to_config(analysis: Analysis) -> StrategyConfig:
        from marketatlas.analysis.ast.pipeline import _ast_to_config

        return _ast_to_config(analysis)

    @staticmethod
    def compile(
        analysis: Analysis,
        registry: ProviderRegistry | None = None,
    ) -> AnalysisGraph:
        if registry is None:
            registry = create_default_registry()

        pipeline = (
            Pipeline()
            .add_pass(ValidationPass())
            .add_pass(RegistryResolutionPass(registry))
            .add_pass(DefinitionExpansionPass(registry))
            .add_pass(GraphGenerationPass())
        )
        return pipeline.run(analysis)
