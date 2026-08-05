# Analysis DSL — Grammar Specification

Status: **implemented**. Backlog 055 (spec) — the grammar below is pinned from
the draft spec and is the contract the lexer (056), parser (057), provider
contracts (058), diagnostics (059), and cross-timeframe extension (061/062)
implement. Changes to the language must update this document and the tests in
`tests/test_dsl_lexer.py`, `tests/test_dsl_parser.py`,
`tests/test_dsl_diagnostics.py`.

The DSL is declarative and concise: it specifies *provider instances*,
*parameter values*, *dependency selection where ambiguous*, and *template
variation points*. Everything else — graph structure, dependencies, execution
order, deduplication, optimisation — is inferred by the compiler. No new
dependencies: the lexer and parser are hand-rolled (`src/marketatlas/analysis/ast/lexer.py`,
`parser.py`).

---

## 1. Overview

A DSL source is a sequence of **definitions**. Each definition instantiates a
provider:

```
name := Type { field: value, field, ... }
```

* `name` — the definition's identifier; other definitions reference it.
* `Type` — a **registry capability key** (`ema`, `atr`, `trend`, `swings`,
  `sr`, ...), resolved against the provider registry. The DSL is decoupled from
  class names: `ema` names the capability, not `EMAAnalyzer`.
* `fields` — comma-separated. Two kinds:
  * `parameter: value` — a constructor parameter of the provider, or a
    **reference** to another definition.
  * `name,` — **shorthand reference**: a bare field that names a declared input
    of the provider, expanding to `name: name`.

Whitespace and `//` line comments are insignificant.

Minimal example:

```
ema := ema { period: 20 }
```

---

## 2. Lexical Grammar

```
letter        := [a-zA-Z] | '_'
digit         := [0-9]
identifier    := (letter) (letter | digit)*
integer       := '-'? digit+
float         := '-'? digit+ '.' digit+
string        := '"' (char | escape)* '"'
escape        := '\' ('"' | '\' | 'n' | 't')        // unknown escapes pass through
comment       := '//' (char - newline)*
ws            := (' ' | '\t' | '\r' | '\n')+

token         := ':=' | '{' | '}' | ':' | ',' | '[' | ']' | '<' | '|' | '>'
               | identifier | integer | float | string
```

Token kinds (lexer token kinds double as the lexeme for structural tokens):

| Kind | Lexeme(s) | Value payload |
|------|-----------|---------------|
| `ASSIGN` | `:=` | — |
| `LBRACE` / `RBRACE` | `{` `}` | — |
| `COLON` | `:` | — |
| `COMMA` | `,` | — |
| `LBRACKET` / `RBRACKET` | `[` `]` | — |
| `LT` / `PIPE` / `GT` | `<` `\|` `>` | — |
| `IDENT` | `[A-Za-z_][A-Za-z0-9_]*` | — |
| `INT` | `-?[0-9]+` | parsed `int` |
| `FLOAT` | `-?[0-9]+\.[0-9]+` | parsed `float` |
| `STRING` | `"..."` (with escapes) | unescaped `str` |

Examples:

```text
// valid
ema := ema { period: 20 }            // INT
atr := atr { period: 1.5 }           // FLOAT (needs a digit after the '.')
tf := timeframe { resolution: "1w" } // STRING
flag: true                           // reserved identifier literal

// invalid
2ema := ema { }                      // identifiers start with a letter or '_'
x := ema { period: 20. }             // '.' with no trailing digit → '20' INT then '.'
x := ema { period: 0x10 }            // '0x10' lexes as INT 0 followed by IDENT 'x10'
```

### 2.1 Lexical constraints

* **Maximal munch**, single pass, left to right.
* A lone `=` is an error (`truncated ':=' operator`).
* A `/` that does not start `//` is an error.
* Choice brackets are balance-checked **lexically** because they have no other
  meaning in the grammar: `<` opens, `>` closes, `|` between them. `|` or `>`
  outside a choice is a lexical error; an unterminated `<` at end of input is a
  lexical error pointing at the opening `<`.
* Unterminated string literal is an error.
* All lexical errors are `DslSyntaxError` carrying a 1-based
  `SourcePosition(line, col)`.

---

## 3. Syntactic Grammar

```
analysis    := definition*
definition  := IDENT ':=' IDENT '{' fields '}'
fields      := (field (',' field)*)?
field       := IDENT ':' value            // parameter
             | IDENT ','                  // shorthand reference
value       := literal | reference | list | choice
literal     := INT | FLOAT | STRING | 'true' | 'false' | 'null'
reference   := IDENT                      // not 'true' | 'false' | 'null'
list        := '[' (list_item (',' list_item)*)? ']'
list_item   := INT | FLOAT | STRING | 'true' | 'false' | 'null' | list
choice      := '<' value ('|' value)* '>'
```

Notes:

* **Trailing commas always permitted**: `{ period: 20, }` is valid.
* An empty source (`analysis := ε`) is valid — an empty template.
* `true`/`false`/`null` are reserved: they are literals, never references or
  field values that could collide with a definition name.
* **Lists** are plain data literals (nested lists allowed), never expansion
  points. References are *not* allowed inside lists.
* **Choices** may nest (`<a | <b | c>>`) and may contain any `value`, including
  references and lists. `<>` (empty choice) is a parse error.
* **No operator precedence** exists — the grammar is delimiter-driven, with no
  infix operators.

---

## 4. Semantics

### 4.1 Definitions and providers

`name := Type { ... }` produces a `Definition` whose `provider` field is the
capability key `Type`. The key is validated against the registry at parse time
(unknown keys produce a positioned `DslParseError` listing available
capabilities) and resolved to a concrete `Provider` at compile time
(`RegistryResolutionPass`, the single owner of default-parameter merging).
Definition names must be unique within an analysis.

The default registry provides these capabilities:

| Capability | Category | Default params | Contract inputs (shorthand-able) | Produces |
|-----------|----------|----------------|----------------------------------|----------|
| `ema` | analyzer | `period: 20` | — | `ema_20` |
| `atr` | analyzer | `period: 14` | — | `atr_14` |
| `trend` | analyzer | — | `ema_20`, `ema_50`, `atr_14` | `trend` |
| `swingstructure` | analyzer | `lookback: 50` | — | `swing` |
| `swings` | analyzer | `lookback: 50` | — | `swing` |
| `sr` | analyzer | — | `swing`, `atr_14` | `sr` |
| `detect_pullback` | analyzer | — | `swing`, `trend`, `atr_14` | `four_swing_pullback` |
| `generate_signal` | signal | — | — (no fact contract) | — |
| `manage_risk` | risk | — | — (no fact contract) | — |
| `timeframe` | timeframe | — (`resolution` required) | — | — (compile-time value) |

* `ema`, `atr`, `swingstructure`, `swings` produce no inputs, so no field on
  them can be a shorthand reference — every field must be a parameter.
* `trend`, `sr`, `detect_pullback` consume named facts; their inputs are
  shorthand-able.
* `generate_signal` and `manage_risk` expose no `requires()`/`produces()`, so
  their contract is empty — references to them must be explicit
  (`field: source`), never shorthand.

### 4.2 Fields: parameter vs reference vs shorthand

A field is parsed in one of three ways:

1. **Parameter** — `name: <literal|list>`: a constructor parameter with a
   concrete value.
2. **Reference** — `name: <IDENT>`: a parameter whose value is a reference to
   another definition. `true`/`false`/`null` never resolve as references.
3. **Shorthand** — `name,`: a bare identifier. Valid **iff** `name` is a
   declared input of the provider (from the provider contract, backlog 058);
   expands to `name: name` (a reference to the definition of the same name).
   Otherwise a positioned `DslParseError` listing the provider's declared
   inputs.

Disambiguation rule (decision pin): a field whose name matches a provider input
becomes a *dependency binding* (shorthand); any other field is a *parameter*.
The two forms never overlap in source: parameters carry `: value`, shorthand is
a bare identifier followed by `,` or `}`.

**References are forward-safe**: a reference may name a definition that appears
later in the source. Resolution happens after the full parse.

### 4.3 The fact name is the field name

A reference `trend := trend { ema_20: ema, ema_50: ema50 }` means the `trend`
node depends on the *facts* `ema_20` and `ema_50` produced by `ema` and `ema50`.
The consumed fact name is carried by the **field name**, not inferred from the
provider contract. This keeps parameterised fact names correct:
`ema := ema { period: 50 }` produces `ema_50`, and
`trend := trend { ema_50: ema }` names exactly that fact — no provider-contract
lookup at parse time. The compiler verifies the field names a fact the target
actually produces (`_check_fact_declared`, instantiating the target analyzer
with literal params and reading `produces()`).

### 4.4 Expressions

| Value | AST node | Notes |
|-------|----------|-------|
| `20`, `-3`, `1.5`, `"1w"`, `true`, `false`, `null` | `LiteralExpression` | |
| `[...]` | `LiteralExpression(list)` | plain data, never expanded |
| `ema_20` (reference) | `ReferenceExpression("ema_20")` | interpreted at compile time |
| `<a \| b>` | `ChoiceExpression` | template expansion point, never a runtime value |

A reference's compile-time interpretation depends on the *referenced
definition's category* (`_resolve_reference`, backlog 062):

* **`timeframe` category** → **value substitution**: the reference fills the
  consumer's `AnalyzerConfig.timeframe` slot (backlog 061). Valid only on
  analyzer definitions.
* **analyzer/pattern category** → **fact dependency**: on an analyzer it
  becomes a `bindings` override (`name@timeframe` when the reference crosses
  timeframes, bare name otherwise); on a signal it becomes a `requires` entry
  (with the `@timeframe` suffix for cross-timeframe references).
* **signal/risk category** → produces no consumable fact or value; referencing
  one is a validation error.
* **opaque/risk consumer** → contributes nothing.

### 4.5 Timeframes

Timeframes are **not** a reserved field. `tf1w := timeframe { resolution: "1w" }`
is an ordinary definition of the `timeframe` capability, and a node links to it
through an ordinary reference:

```
tf1w := timeframe { resolution: "1w" }
ema1w := ema { period: 20, timeframe: tf1w }
```

The reference-slot field name is always `timeframe`. The compiler collects the
declared set into `Analysis.timeframes` and `StrategyConfig.timeframes`
(backlog 061); cross-timeframe references carry the source timeframe through
`name@timeframe` keys (backlog 062). The grammar is unchanged by this — it is
just a definition plus a reference.

### 4.6 Template expansion

`<a | b | c>` is a compile-time **expansion point** (backlog 050): the pipeline
forks one template into one concrete AST per choice leaf combination. Lists are
never expansion points. Expansion semantics:

* Nested choices flatten recursively: `<a | <b | c>>` → leaves `a, b, c`.
* Multiple choices across parameters/definitions combine as a cartesian product
  in declaration order, **rightmost varies fastest**:
  `(period: <20|50>) x (period: <14|28>)` yields `(20,14), (20,28), (50,14),
  (50,28)`.
* An empty choice is an error naming definition and parameter.
* A choice-free template is already concrete: expansion yields a single AST,
  and `ASTCompiler.compile` works directly.

---

## 5. Design Decisions

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| `Type` mapping | Registry **capability key**, not class name | Concise (`ema` not `EMAAnalyzer`), decouples DSL from implementation. `registry.resolve()` picks the first of multiple providers per capability — the grammar must not rely on multi-provider ordering, and today's default registry has one provider per key. |
| Shorthand vs parameter | Field name ∈ provider contract inputs ⇒ shorthand dependency; else parameter | Unambiguous at parse time, zero backtracking. Requires provider input metadata (058), which exists. |
| Provider-selection choice (`provider: <A \| B>`) | **Deferred** | Ambiguous in the draft (param named `provider` vs definition-level type selection). Only choices over *parameter values* are supported. Definition-level `name := <A \| B> { ... }` is future work. |
| Timeframe | Ordinary `timeframe`-capability definition + ordinary reference; **no reserved field** | Keeps EBNF generic; value substitution is decided by provider category at compile time, not by grammar position. |
| Group scoping | **Deferred** (backlog 064) | `group` scope marker + spanning references have unowned syntax. Recorded as an open question in §8. |
| Reference expression | `field: dep` ⇒ `ReferenceExpression` at parse time; compiler disambiguates by category | No new AST node needed. Timeframe refs become value substitution; fact refs become bindings/requires. |
| Literals | int, float, string, bool, null; list `[...]`; choice `<a\|b\|c>` | As drafted. |
| Comments / whitespace | Whitespace-insensitive; `//` line comments | Braces and commas delimit; `//` matches the zero-dep, hand-rolled style. |

---

## 6. Mapping Table — DSL Construct → AST Node

| DSL construct | AST node |
|---------------|----------|
| whole source | `Analysis` (built via `build_analysis`; `providers` populated from registry, `timeframes` derived) |
| `name := Type { ... }` | `Definition(name, provider=Type, parameters=...)` |
| `field: value` (literal) | `Parameter(field, LiteralExpression(value))` |
| `field: ref` | `Parameter(field, ReferenceExpression(ref))` |
| `field,` (shorthand) | `Parameter(field, ReferenceExpression(field))` |
| `field: [a, b]` | `Parameter(field, LiteralExpression([a, b]))` |
| `field: <a \| b>` | `Parameter(field, ChoiceExpression(...))` |
| `tf := timeframe { resolution: "1w" }` | `Definition` + `Analysis.timeframes` entry |

The retired `Binding` node (036) is not produced: references become
`ReferenceExpression` parameter values, and the compiler emits `bindings`/
`requires` overrides into `AnalyzerConfig`/`SignalConfig` at compile time.

---

## 7. Draft-Spec Examples, Transcribed and Annotated

```text
// 1. Single definition
ema := ema { period: 20 }
// → one Definition; period 20; produces fact "ema_20".

// 2. Linear chain
atr_14 := atr { period: 14 }
trend := trend { ema_20: ema, ema_50: ema50 }
ema50 := ema { period: 50 }
// forward reference: ema50 is defined after trend; resolved post-parse.
// ema_20/ema_50 are fact names carried by the field names.

// 3. Branching
swing := swings { lookback: 50 }
sr := sr { swing, atr_14 }
pullback := detect_pullback { swing, trend, atr_14 }
// 'swing' and 'atr_14' are shorthand — both are declared inputs of sr;
// 'swing', 'trend', 'atr_14' are declared inputs of detect_pullback.

// 4. Full strategy (compiles to a 7-analyzer graph, see §7.1)
signal := generate_signal { four_swing_pullback: pullback, trend: trend, atr_14: atr_14 }
// generate_signal has no contract inputs, so references must be explicit.

// 5. Choice parameter (template expansion point)
ema := ema { period: <20 | 50> }
// expands to 2 concrete ASTs: period 20 and period 50.

// 6. Nested choice
ema := ema { period: <20 | <50 | 100>> }
// flattens to leaves 20, 50, 100.

// 7. List parameter (plain data, never expanded)
x := ema { periods: [20, 50, 100] }
// one concrete AST; the list stays intact.

// 8. Timeframe as an ordinary definition (061)
tf1w := timeframe { resolution: "1w" }
ema1w := ema { period: 20, timeframe: tf1w }

// 9. Trailing comma, comments, empty analysis
// legal:
ema := ema { period: 20, }
// legal (empty template):
x := ema { }
```

### 7.1 The canonical strategy example

```text
ema := ema { period: <20 | 50> }
atr_14 := atr { period: 14 }
swing := swings { lookback: 50 }
trend := trend { ema_20: ema, ema_50: ema50 }
ema50 := ema { period: 50 }
sr := sr { swing, atr_14 }
pullback := detect_pullback { swing, trend, atr_14 }
signal := generate_signal { four_swing_pullback: pullback, trend: trend, atr_14: atr_14 }
```

* Parses to a template `Analysis` (2 definitions with choices intact).
* Expands to **2 concrete ASTs** (cartesian: the only choice is `ema.period`,
  and `ema` appears once).
* The choice-free variant (fixed `period: 20`) compiles to an `AnalysisGraph`
  containing `ATRAnalyzer, BasicSwingAnalyzer, EMAAnalyzer ×2,
  FourSwingPullbackDetector, SupportResistanceAnalyzer, TrendAnalyzer`.

---

## 8. Relationship to the Compiler Pipeline

```
DSL text
  │  tokenize()                     lexer (056)
  ▼
Token stream                        DslSyntaxError (positioned)
  │  parse() / parse_with_positions parser (057)
  ▼
Template Analysis (+ SourceMap)     DslParseError (positioned); SourceMap → diagnostics (059)
  │  ASTCompiler._pipeline()        stage 1: ValidationPass → RegistryResolutionPass → ParamValidationPass
  ▼
Concrete AST(s)
  │  TemplateExpansionPass          stage 2: choice expansion (050)
  ▼
Concrete ASTs (choice-free)
  │  ConcreteValidationPass         stage 3: choice-free + duplicate-definition checks
  ▼
Concrete AST(s)                     stage 4: GraphGenerationPass → AnalysisGraph (051)
```

* The template AST produced by the parser **is** the AST the pipeline accepts;
  the DSL front end replaces manual `AnalysisBuilder` construction.
* `ASTCompiler.compile_dsl(source)` is the end-to-end entry point: parse →
  thread the `SourceMap` through all stages → one `AnalysisGraph` per concrete
  AST. `Pipeline.expand` / `ASTCompiler.expand` expose stages 1–3;
  `Pipeline.run_to_ast` runs the registered stage-1 passes only; `Pipeline.run` /
  `ASTCompiler.compile` run the full pipeline and return a single graph (raise
  for multi-output templates).
* Default-param merging happens exactly once, in `RegistryResolutionPass`;
  param-schema validation (`ParamValidationPass`, 052) rejects unknown params,
  missing required params, and type-incompatible literals before expansion.
* Positioned errors: lexical/grammar errors raise `DslSyntaxError`/
  `DslParseError` directly; pipeline findings raise `CompilationError` whose
  `errors` carry `line:col` where the `SourceMap` has an entry. Render with
  `format_diagnostic` / `format_errors` / `render_snippet` (059).
* `generate_signal` and `manage_risk` definitions flow into `SignalConfig` /
  `RiskConfig`; analyzer definitions into `AnalyzerConfig`. `StrategyConfig` is
  produced by `_ast_to_config`.

---

## 9. Open Questions / Deferred

* **Definition-level provider choice** — `name := <A | B> { ... }` is deferred;
  only parameter-value choices are supported.
* **Group scoping** — the `group` scope marker + spanning references (backlog
  064) have unowned syntax. The EBNF above contains no placeholder token;
  whichever syntax 064 chooses is a grammar extension owned there.
* **Reserved field set** — `true`/`false`/`null` are reserved identifiers;
  provider inputs are *not* reserved (a param named `swing` on a provider that
  declares `swing` as an input is legal as a parameter `swing: value`, only the
  bare `swing,` form is shorthand).
* **Multi-provider capabilities** — the default registry has one provider per
  capability key. The grammar does not address selecting a non-default provider
  within a capability (deferred with definition-level choices).
* **YAML loader** — the legacy YAML `StrategyConfig` path is untouched; the DSL
  is its eventual replacement but retirement is out of scope.
