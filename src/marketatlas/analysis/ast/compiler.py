from __future__ import annotations

from marketatlas.analysis.ast.diagnostics import SourceMap
from marketatlas.analysis.ast.instrument import TemplateGraph
from marketatlas.analysis.ast.models import Analysis
from marketatlas.analysis.ast.pipeline import (
    ParamValidationPass,
    Pipeline,
    RegistryResolutionPass,
    ValidationPass,
)
from marketatlas.analysis.ast.registry import ProviderRegistry, create_default_registry
from marketatlas.analysis.graph import AnalysisGraph
from marketatlas.strategy.config import StrategyConfig


class ASTCompiler:
    @staticmethod
    def _pipeline(registry: ProviderRegistry, source_map: SourceMap | None = None) -> Pipeline:
        return (
            Pipeline(source_map)
            .add_pass(ValidationPass(source_map))
            .add_pass(RegistryResolutionPass(registry))
            .add_pass(ParamValidationPass(registry, source_map))
        )

    @staticmethod
    def to_config(analysis: Analysis) -> StrategyConfig:
        from marketatlas.analysis.ast.pipeline import _ast_to_config

        return _ast_to_config(analysis)

    @staticmethod
    def compile(
        analysis: Analysis,
        registry: ProviderRegistry | None = None,
    ) -> AnalysisGraph:
        """Compile a single concrete AST to an ``AnalysisGraph``.

        Unchanged for literal-only (choice-free) templates. Templates that
        expand to multiple concrete ASTs raise — use ``compile_all``.
        """
        if registry is None:
            registry = create_default_registry()
        return ASTCompiler._pipeline(registry).run(analysis)

    @staticmethod
    def expand(
        analysis: Analysis,
        registry: ProviderRegistry | None = None,
    ) -> tuple[Analysis, ...]:
        """Stages 1-3: validate, expand choices, validate each concrete AST."""
        if registry is None:
            registry = create_default_registry()
        return ASTCompiler._pipeline(registry).expand(analysis)

    @staticmethod
    def compile_all(
        analysis: Analysis,
        registry: ProviderRegistry | None = None,
    ) -> tuple[AnalysisGraph, ...]:
        """Compile every concrete AST to its own ``AnalysisGraph``.

        Multi-output path for choice templates: one graph per concrete AST,
        never silently merged (backlog 051).
        """
        if registry is None:
            registry = create_default_registry()
        return ASTCompiler._pipeline(registry).compile_all(analysis)

    @staticmethod
    def compile_template(
        analysis: Analysis,
        registry: ProviderRegistry | None = None,
    ) -> TemplateGraph:
        """Compile a single concrete AST to an instrument-neutral template.

        Backlog 063: the ``TemplateGraph`` holds the recipe (concrete
        ``Analysis`` + ``StrategyConfig``) and materializes fresh, isolated
        per-instrument ``AnalysisGraph`` objects on demand. Templates that
        expand to multiple concrete ASTs raise — use ``compile_templates``.
        """
        if registry is None:
            registry = create_default_registry()
        return ASTCompiler._pipeline(registry).compile_template(analysis)

    @staticmethod
    def compile_templates(
        analysis: Analysis,
        registry: ProviderRegistry | None = None,
    ) -> tuple[TemplateGraph, ...]:
        """Compile every concrete AST to its own ``TemplateGraph``.

        Multi-output path for choice templates (backlog 063): one template per
        concrete AST, matching the explicit multi-return convention of
        ``compile_all`` (backlog 051).
        """
        if registry is None:
            registry = create_default_registry()
        return ASTCompiler._pipeline(registry).compile_templates(analysis)

    @staticmethod
    def compile_dsl(
        source: str,
        *,
        name: str = "analysis",
        version: str = "1.0",
        registry: ProviderRegistry | None = None,
    ) -> tuple[AnalysisGraph, ...]:
        """End-to-end: DSL text → template AST → every concrete graph.

        Parses ``source`` (backlog 057), threads the resulting ``SourceMap``
        (backlog 059) through the whole pipeline, and returns one
        ``AnalysisGraph`` per concrete AST — choice templates expand to
        multiple graphs (backlog 051). Compiler failures raise
        ``CompilationError`` whose ``errors`` carry ``line:col`` positions
        where the source is mapped; lexical/grammar errors raise
        ``DslSyntaxError``/``DslParseError`` directly.
        """
        from marketatlas.analysis.ast.parser import parse_with_positions

        if registry is None:
            registry = create_default_registry()
        analysis, source_map = parse_with_positions(
            source, name=name, version=version, registry=registry
        )
        return ASTCompiler._pipeline(registry, source_map).compile_all(analysis)
