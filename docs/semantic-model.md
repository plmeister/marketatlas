# Semantic Model — Reference

Status: **implemented**. Backlog 044 (doc). This document is the reference for
the AST/semantic layer of MarketAtlas: every concept in
`src/marketatlas/analysis/ast/`, its purpose, constraints, and how it relates to
the runtime (`AnalysisGraph`, facts, analyzers). It pins the model as implemented
by backlogs 036-065 and the corresponding code; keep it in sync when the model
changes.

## 1. Overview

The AST layer separates three concerns:

1. **Description** — a declarative `Analysis`: *what* to compute, with *which*
   provider, using *which* parameter values, at *which* timeframe.
2. **Compilation** — a pipeline turning the description into an executable
   `AnalysisGraph` (or a reusable `TemplateGraph`), validating every step.
3. **Execution** — the runtime `AnalysisGraph` replaying over a `MarketStore`
   and producing `Fact` objects.

A definition never names a market data series or an instrument. The AST describes
one implicit instrument; instruments (backlog 063) and data (backlog 065) are
runtime concerns injected after compilation.

```
   description            compilation                      execution
  +------------+    +----------------------------+   +------------------+
  |  DSL text  |--->|  lexer/parser → Analysis   |-->|  AnalysisGraph   |--> Facts
  +------------+    |  (template AST)            |   |  (per-instrument,|    (at
        |           |        |                   |   |   instantiated)  |     runtime)
        |           |  stage 1: validate,        |   +------------------+
        |           |  resolve registry,         |
        +-----------+  check param schema        |
                    |        |                   |
                    |  stage 2: expand choices   |  (template → concrete)
                    |        |                   |
                    |  stage 3: validate          |
                    |  concrete AST(s)            |
                    |        |                   |
                    |  stage 4: graph generation  |
                    +----------------------------+
```

## 2. Concepts

### 2.1 Analysis

The root semantic node: a named, versioned description of one strategy's
computation.

```python
Analysis(name, version, definitions, providers, timeframes, id, metadata)
```

- `definitions` — the nodes to instantiate (section 2.2).
- `providers` — provider declarations attached to the analysis. Symbolic provider
  names resolve against these first, then the registry (section 2.5).
- `timeframes` — declared timeframe set, derived from `TimeFrame` definitions
  (backlog 061), used for data-requirements inference (backlog 065).
- `id` / `metadata` — opaque identity and annotation; preserved through clone,
  expansion, and serialization.

Constraint: an `Analysis` is **immutable** (frozen dataclasses). Every
transformation (clone 049, expansion 050) returns a new instance; inputs are
never mutated.

Example (DSL, `tests/test_dsl_integration.py`):

```
ema_50 := ema { period: 50 }
atr_14 := atr { period: 14 }
trend  := trend { fast: ema_50, atr: atr_14 }
```

The equivalent `Analysis` has three `Definition`s; `fast` and `atr` are
`ReferenceExpression` parameters (section 2.4).

### 2.2 Definition

One node in the analysis: an instantiation of a provider with a parameter set.

```python
Definition(name, provider, parameters, id, metadata)
```

- `name` — unique identifier within the analysis; other definitions reference
  it. Duplicate names are rejected by validation (backlog 038) and, again, after
  template expansion (convergent choices, backlog 051).
- `provider` — a provider name. Either a registry capability key (`ema`) or a
  concrete provider declared in `Analysis.providers`. Resolved to a concrete
  provider by the `RegistryResolutionPass` (backlog 051).
- `parameters` — ordered `(name, value)` pairs; `value` is an `Expression`
  (section 2.3). Default parameters from the provider are merged here during
  registry resolution — no later stage re-merges defaults.

Every definition either produces a **fact** at runtime (analyzer/signal/risk) or
is a **compile-time value** (`TimeFrame`, section 2.8). The distinction is
carried by the provider's `category`.

### 2.3 Parameter

A named value slot on a definition.

```python
Parameter(name, value)   # value: Expression
```

Parameter values are always `Expression` nodes, never raw values, so they can be
validated, cloned, expanded, and serialized structurally (backlog 047). Reading
code that expects the raw value keeps working because `LiteralExpression` is
equal to its payload (`param.value == 20`).

### 2.4 Expression

The expression hierarchy is the value model for parameters.

```
Expression
├── LiteralExpression(value)     concrete value (int, float, str, bool, None, list, ...)
├── ChoiceExpression(values)     template expansion point: one of several candidates
└── ReferenceExpression(name)    reference to another definition
```

- **LiteralExpression** — a concrete value. Serializes as the raw JSON value;
  the plain `20` in `period: 20`.
- **ChoiceExpression** — the template primitive (backlog 048): `period` may be
  `50` *or* `100`. Built with `Choice([50, 100])`. A raw `list` literal is *not*
  a choice. Choices across parameters/definitions expand by cartesian product
  (backlog 050), so one template becomes N concrete analyses.
- **ReferenceExpression** — a reference to a named definition used as a parameter
  value (backlog 061). The compiler interprets it by the target's kind: a
  `TimeFrame` definition resolves to the consumer's `timeframe`; a fact-producing
  definition is a dependency edge (consumed fact / `requires` entry, with
  `name@timeframe` suffixing for cross-timeframe references, backlog 062).

The retired `Binding` node (backlogs 037/042) is gone: a reference is now a
`ReferenceExpression` parameter value, and the compile-time dependency graph over
those references replaces the explicit binding list.

### 2.5 Capability and Provider

The separation that keeps the DSL decoupled from class names.

```python
Capability(id, description, required_params)
Provider(name, capability, category, impl, default_params)
```

- **Capability** — an abstract, computable thing: `ema`, `atr`, `trend`,
  `swingstructure`, `sr`, `detect_pullback`, `generate_signal`, `manage_risk`,
  `timeframe`. The DSL types on capability keys, not classes.
- **Provider** — a concrete implementation of a capability: `Provider` metadata
  referencing the impl class (`EMAAnalyzer` implements capability `ema`) plus
  `default_params`. Categories (`analyzer` / `signal` / `risk` / `timeframe`)
  determine how the compiler lowers a definition (section 3.4).

The `ProviderRegistry` (backlog 043) maps capability keys to providers and holds
per-provider **metadata** derived at registration:

- `param_schema` — `ParamSpec`s from the constructor signature (backlog 052),
  used by the `ParamValidationPass`.
- `ProviderContract(inputs, outputs)` — fact-level inputs/outputs from the
  analyzer's `requires()`/`produces()` (backlog 058), used for DSL shorthand
  disambiguation (backlog 057) and later binding validation.

Providers are declared either in the AST (`Analysis.providers`, for
opaque/custom providers) or in the default registry
(`create_default_registry()`). Registry resolution prefers AST-declared
providers and falls back to the registry.

### 2.6 Fact

A runtime value produced by an analyzer during graph execution.

```python
Fact(timestamp, evidence, visible_on)
```

Facts are the wires of the execution graph: one analyzer's `produces()` become
another's `requires()`. Concrete facts live in the fact hierarchy
(`EMAFact`, `ATRFact`, `TrendFact`, `SwingFact`, `PullbackFact`, ...) under
`src/marketatlas/facts/`.

### 2.7 FactKey

The stable identity of a fact within a graph run.

```python
FactKey(name, params, timeframe)
```

`name` is the fact kind (`ema`, `atr`, ...); `params` are the identifying
parameters (`period_50`); `timeframe` the resolution it was computed on
(backlog 045/061). String form joins them: `ema_50_tf_1d`. Graph wiring
(`AnalysisGraph._topo_sort`) matches `requires()` against `produces()` by
`FactKey` equality; cross-timeframe references produce keys like
`ema_50@1w` resolved via analyzer `bindings` (backlog 062).

### 2.8 TimeFrame

A definition whose provider is the `timeframe` capability (backlog 061) is a
compile-time value, not a runtime analyzer:

```
weekly := timeframe { resolution: "1w" }
ema_50 := ema { period: 50, timeframe: weekly }
```

`TimeFrame` definitions contribute the declared `Analysis.timeframes`
(`derive_timeframes`) and feed data-requirements inference (backlog 065).

## 3. Relationships

The concepts nest and wire together as follows:

```
Analysis
├── definitions: Definition             an instantiation of a provider
│   ├── provider: name ──────────────>  ProviderRegistry.resolve(capability)  or  Analysis.providers
│   └── parameters: Parameter
│       └── value: Expression
│           ├── LiteralExpression       concrete param value
│           ├── ChoiceExpression        template expansion point
│           └── ReferenceExpression ──> another Definition (dependency edge / timeframe)
├── providers: Provider
│   └── (name, capability, category, impl, default_params)
│        └── capability ──────────────> Capability (abstract "what to compute")
└── timeframes: str[]                   from TimeFrame definitions

Compilation (per concrete AST)
└── StrategyConfig
    ├── AnalyzerConfig(type, params, timeframe, bindings) ──> Analyzer (impl class)
    ├── SignalConfig(requires, rules) ──────────────────────> Signal
    └── RiskConfig ─────────────────────────────────────────> RiskEngine

Execution
└── AnalysisGraph(analyzers)
    ├── Analyzer.produces() ──────────> FactKey
    ├── Analyzer.requires() ──────────> FactKey
    └── run(view) ────────────────────> dict[FactKey, Fact]
```

Key rules:

- A `Definition` references a `Provider` that implements a `Capability`:
  `provider: "ema"` + `capability: "ema"` + `impl: "EMAAnalyzer"`.
- A definition **consumes** facts only through `ReferenceExpression` parameters
  (explicit in the DSL: `trend { fast: ema_50 }`); shorthand `ema_50,` on a
  consumer is a contract-derived reference (backlog 057). Undeclared
  cross-timeframe consumption fails loudly at graph construction as an
  `UnsatisfiedDependencyError` (backlog 062).
- Facts are the only runtime currency: the compiler never wires analyzers
  directly; it wires `FactKey`s.
- Providers are selected by capability; when multiple providers implement a
  capability, the registry picks the first and warns. Explicit selection is a
  future concern (backlog 064 deferred provider-selection choices).

## 4. Lifecycle

### 4.1 Construct (AST)

Three equivalent entry points produce an `Analysis`:

| Entry point | Source |
|---|---|
| `AnalysisBuilder` (fluent, backlog 037) | Python API: `AnalysisBuilder("s", "1.0").define(...).with_param(...).build()` |
| `build_analysis` + `construct` (backlog 053) | Factories: `EMA(period=20)` / `build_analysis(...)` |
| `parse` / `parse_with_positions` (backlog 057) | DSL text; the latter also returns a `SourceMap` for positioned diagnostics |

Serialization (backlog 039): `to_json`/`from_json`, `to_dict`/`from_dict`.
`clone` (backlog 049) deep-copies a node without mutating the input.

### 4.2 Validate → Compile

The compiler pipeline (backlog 051) is four stages orchestrated by `Pipeline`
and exposed by `ASTCompiler`:

```
DSL text
  │  parse (lexer 056 → parser 057)   ── positioned errors (059)
  ▼
template Analysis
  │  stage 1  ValidationPass          ── semantic checks (038), no-read-ahead-safe
  │            RegistryResolutionPass ── symbolic → concrete providers, merge defaults (051)
  │            ParamValidationPass    ── name/required/type vs provider schema (052)
  ▼
  │  stage 2  TemplateExpansionPass   ── choices → concrete ASTs, cartesian product (050)
  ▼
concrete Analysis(s)
  │  stage 3  ConcreteValidationPass  ── choice-free, no duplicate definitions (051/054)
  ▼
  │  stage 4  GraphGenerationPass     ── AST → StrategyConfig → build_analyzers → AnalysisGraph
  ▼
AnalysisGraph / TemplateGraph
```

Single- vs multi-output:

- `Pipeline.run` / `ASTCompiler.compile` — single concrete graph; raises when the
  template expands to more than one.
- `Pipeline.compile_all` / `ASTCompiler.compile_all` — one graph per concrete AST.
- `Pipeline.expand` / `ASTCompiler.expand` — the concrete ASTs themselves.
- `Pipeline.compile_template` / `compile_templates` / `ASTCompiler.*` — an
  instrument-neutral `TemplateGraph` (backlog 063).
- `ASTCompiler.compile_dsl` — DSL text → every concrete graph end to end.

Compiler failures raise `CompilationError` whose `errors` carry `Diagnostic`s
with `line:col` positions where a `SourceMap` exists (backlog 059).

### 4.3 Instantiate (instruments)

`TemplateGraph` is the recipe between AST and execution (backlog 063): it owns
the concrete `Analysis` + `StrategyConfig`, and `instantiate(instrument)`
materializes a fresh, isolated `AnalysisGraph` per instrument. `instantiate_all`
rejects an empty instrument list. Per-instrument graphs never share analyzer
instances, so facts cannot leak between instruments.

Data needs are derived before execution (backlog 065): `TemplateGraph.required_timeframes()`
and `required_data(instruments, start, end)` → `DataRequirement` tuples, which
`ensure_required_data` feeds to the `DataStore` for gap-only fetching.

### 4.4 Execute

`AnalysisGraph.run(view)` executes analyzers in topological order, giving each
its `MarketView` (selecting the analyzer's timeframe via `view.select` when it
differs from the store's, backlog 045), collecting `Fact`s keyed by `FactKey`,
and returning the fact dict. The graph is read-only at run time; the replay loop
(backtest 014) drives it one candle at a time and stores `AnalysisFrame`s.

```
MarketStore ──cursor──▶ MarketView ──▶ AnalysisGraph.run ──▶ dict[FactKey, Fact]
                                            ▲
                                   analyzers (topo order,
                                   requires() satisfied)
```

## 5. Naming Conventions and Best Practices

- **Capability keys** are short lowercase verbs/nouns: `ema`, `atr`, `trend`,
  `swingstructure`, `swings`, `sr`, `detect_pullback`, `generate_signal`,
  `manage_risk`, `timeframe`. A new provider registers under a capability key,
  not a class name (`registry.register("ema", EMAAnalyzer, ...)`).
- **Definition names** are lowercase identifiers, unique per analysis, that read
  as the fact they produce (`ema_50`), so references stay readable:
  `trend { fast: ema_50 }`.
- **Fact names** in `produces()`/`requires()` may be parameterised
  (`ema_50`); a reference field must name the produced fact exactly — the
  compiler verifies it by instantiating the target analyzer (backlog 062).
- **References are explicit.** Prefer `trend { atr: atr_14 }` over relying on
  implicit wiring; shorthand (`atr_14,`) only works when the field is a
  declared provider input (contract, backlog 058). Never name an instrument or
  a data series in the AST — instruments (063) and data (065) are runtime.
- **Choices are for templates.** Use `Choice([50, 100])` only where a template
  expansion is intended; a plain list is a literal value. Empty choices raise.
- **Keep the AST immutable.** Prefer `clone` + rebuild over in-place mutation;
  expansion and compilation never mutate their input.
- **Never bypass the pipeline** for validation. Register providers in
  `create_default_registry()`; parameter schemas and contracts are derived
  automatically, so hand-written metadata drifts.
- **Opaque providers are fine but unvalidated.** Providers with no registry
  counterpart, no param schema, or no fact contract are skipped by
  validation — they must not false-positive.

## 6. Model Map

| Concept | Module | Backlog |
|---|---|---|
| `Analysis`, `Definition`, `Parameter`, `Provider`, `Capability` | `ast/models.py` | 036, 041 |
| `Expression`, `LiteralExpression`, `ChoiceExpression`, `ReferenceExpression` | `ast/expressions.py` | 047, 048, 061 |
| `AnalysisBuilder` | `ast/builder.py` | 037 |
| `validate`, `Diagnostic` | `ast/validation.py` | 038, 059 |
| `to_json`/`from_json` | `ast/serialization.py` | 039 |
| `clone` | `ast/clone.py` | 049 |
| `Pipeline`, passes, `expand`, `CompilationError` | `ast/pipeline.py` | 050-051 |
| `ParamSpec`, `derive_param_schema` | `ast/param_schema.py` | 052 |
| `construct`, `build_analysis` | `ast/constructors.py` | 053 |
| `ProviderRegistry`, `ProviderContract` | `ast/registry.py` | 043, 058 |
| lexer / parser / `SourceMap` | `ast/lexer.py`, `parser.py`, `diagnostics.py` | 056-059 |
| `TemplateGraph`, `InstrumentGraph`, `backtest_template` | `ast/instrument.py` | 063 |
| `required_timeframes`, `required_data` | `ast/requirements.py` | 065 |
| `ASTCompiler` | `ast/compiler.py` | 040, 051, 053, 063 |
| `Fact` | `facts/base.py` | 006 |
| `FactKey` | `analysis/factkey.py` | 042, 045, 062 |
| `AnalysisGraph` | `analysis/graph.py` | 007 |
| DSL grammar spec | `docs/dsl.md` | 055 |
