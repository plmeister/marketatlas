"""Backlog 057: recursive-descent parser — DSL text to template AST.

Parses the DSL grammar (backlog 055) over the positioned token stream from
the lexer (backlog 056) into a template ``Analysis`` — the exact AST the
compiler pipeline (backlog 051) accepts. Choice expansion happens downstream
(stage 2, backlog 050); this parser preserves ``ChoiceExpression`` nodes
intact and never expands them.

Grammar::

    analysis  := definition+
    definition := IDENT ':=' IDENT '{' fields '}'
    fields    := (field (',' field)*)?          // trailing comma allowed
    field     := IDENT ':' value                // parameter
               | IDENT ':' IDENT                // reference binding (backlog 062)
               | IDENT ','                      // shorthand dependency
    value     := literal | list | choice
    literal   := INT | FLOAT | STRING | 'true' | 'false' | 'null'
    list      := '[' (literal (',' literal)*)? ']'
    choice    := '<' value ('|' value)* '>'     // nested choices allowed

Field disambiguation (backlog 055 decision): an unquoted identifier on the
right of ``:`` is a *reference* to another definition and becomes a
``Binding``; every other value is a ``Parameter``. ``true``/``false``/``null``
are reserved literals, never references. A bare ``name,`` field is a
*shorthand*: it must name a provider input (derived from the provider
contract, backlog 058) and expands to
``Binding(source=name, output=name, target=self, input=name)``.

Both binding forms carry the *fact name* in the field name: ``ema_20: ema``
wires the fact ``ema_20`` produced by definition ``ema`` into this
definition's ``ema_20`` slot — the binding is
``Binding(source="ema", output="ema_20", target=self, input="ema_20")``.
This is the ``name: name`` mapping of backlog 055: source/output/target/input
are all plain names, so no provider-contract lookup is needed at parse time
and period-parameterised fact names (``ema := ema { period: 50 }`` producing
``ema_50``) stay correct.

``Type`` resolves as a registry capability key. Each definition keeps the
capability as its ``provider`` field and the analysis' ``providers`` list is
populated from the registry (via ``build_analysis``) so the template is
self-contained and serializable (backlog 039/046) and equals a
``build_analysis``-constructed equivalent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from marketatlas.analysis.ast.constructors import build_analysis
from marketatlas.analysis.ast.expressions import ChoiceExpression, Expression, LiteralExpression
from marketatlas.analysis.ast.lexer import (
    ASSIGN,
    COLON,
    COMMA,
    FLOAT,
    GT,
    IDENT,
    INT,
    LBRACE,
    LBRACKET,
    LT,
    PIPE,
    RBRACE,
    RBRACKET,
    STRING,
    SourcePosition,
    Token,
    tokenize,
)
from marketatlas.analysis.ast.models import Analysis, Binding, Definition, Parameter, Provider
from marketatlas.analysis.ast.registry import ProviderRegistry, create_default_registry

#: Identifiers treated as literal values, never references.
_RESERVED = frozenset({"true", "false", "null"})


class DslParseError(Exception):
    """Grammar error in DSL source, carrying the offending source position."""

    def __init__(self, message: str, position: SourcePosition) -> None:
        self.message = message
        self.position = position
        super().__init__(f"{position.line}:{position.col}: {message}")


@dataclass(frozen=True)
class _RawBinding:
    """Binding discovered during field parsing, resolved after the whole
    analysis is parsed (references may target later definitions)."""

    source: str
    target: str
    input: str
    position: SourcePosition


class _Parser:
    def __init__(
        self, source: str, registry: ProviderRegistry, name: str, version: str
    ) -> None:
        self._tokens = tokenize(source)
        self._pos = 0
        self._registry = registry
        self._name = name
        self._version = version
        self._def_positions: dict[str, SourcePosition] = {}
        self._raw_bindings: list[_RawBinding] = []

    # -- token helpers -------------------------------------------------

    def _peek(self, offset: int = 0) -> Token:
        index = self._pos + offset
        if index < len(self._tokens):
            return self._tokens[index]
        last = self._tokens[-1].position if self._tokens else SourcePosition(1, 1)
        return Token(kind="", lexeme="", position=last)

    def _advance(self) -> Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _expect(self, kind: str, message: str) -> Token:
        token = self._peek()
        if token.kind != kind:
            self._error(message, token.position)
        return self._advance()

    def _expect_ident(self, message: str) -> Token:
        return self._expect(IDENT, message)

    def _error(self, message: str, position: SourcePosition) -> NoReturn:
        raise DslParseError(message, position)

    # -- entry point ---------------------------------------------------

    def parse(self) -> Analysis:
        definitions: list[Definition] = []
        while self._peek().kind == IDENT:
            definitions.append(self._parse_definition())
        if self._peek().kind:
            token = self._peek()
            self._error(f"unexpected token {token.lexeme!r}", token.position)

        bindings_map = self._resolve_bindings(definitions)
        definitions = [
            Definition(
                name=d.name,
                provider=d.provider,
                parameters=d.parameters,
                bindings=bindings_map[d.name],
                id=d.id,
                metadata=d.metadata,
            )
            for d in definitions
        ]
        return build_analysis(
            self._name, definitions, version=self._version, registry=self._registry
        )

    # -- grammar rules -------------------------------------------------

    def _parse_definition(self) -> Definition:
        name_tok = self._expect_ident("expected a definition name")
        name = name_tok.lexeme
        if name in self._def_positions:
            self._error(f"duplicate definition name '{name}'", name_tok.position)
        self._def_positions[name] = name_tok.position

        self._expect(ASSIGN, f"expected ':=' after definition name '{name}'")
        type_tok = self._expect_ident(f"expected a provider type after ':=' for '{name}'")
        provider = self._resolve_type(type_tok)
        self._expect(LBRACE, f"expected '{{' after type '{type_tok.lexeme}'")
        params = self._parse_fields(name, provider)
        self._expect(RBRACE, f"expected '}}' to close definition '{name}'")
        return Definition(name=name, provider=type_tok.lexeme, parameters=params)

    def _parse_fields(
        self, target_name: str, target_provider: Provider
    ) -> tuple[Parameter, ...]:
        params: list[Parameter] = []
        while self._peek().kind != RBRACE:
            field_tok = self._expect_ident("expected a field name or '}'")
            if self._peek().kind == COLON:
                self._advance()
                if self._peek().kind == IDENT and self._peek().lexeme not in _RESERVED:
                    ref_tok = self._advance()
                    self._raw_bindings.append(
                        _RawBinding(
                            source=ref_tok.lexeme,
                            target=target_name,
                            input=field_tok.lexeme,
                            position=ref_tok.position,
                        )
                    )
                else:
                    params.append(
                        Parameter(field_tok.lexeme, self._parse_value("as a parameter value"))
                    )
            elif self._peek().kind in (COMMA, RBRACE):
                self._shorthand(field_tok, target_name, target_provider)
            else:
                self._error(
                    f"expected ':', ',' or '}}' after field name {field_tok.lexeme!r}",
                    self._peek().position,
                )
            if self._peek().kind == COMMA:
                self._advance()
            elif self._peek().kind != RBRACE:
                self._error("expected ',' or '}}'", self._peek().position)
        return tuple(params)

    def _shorthand(
        self, field_tok: Token, target_name: str, target_provider: Provider
    ) -> None:
        contract = self._registry.contract(target_provider.capability) or self._registry.contract(
            target_provider.name
        )
        inputs = contract.inputs if contract is not None else ()
        if field_tok.lexeme not in inputs:
            known = ", ".join(inputs) if inputs else "(none)"
            self._error(
                f"shorthand dependency '{field_tok.lexeme}' is not a declared input of "
                f"provider '{target_provider.capability}'. Declared inputs: {known}",
                field_tok.position,
            )
        self._raw_bindings.append(
            _RawBinding(
                source=field_tok.lexeme,
                target=target_name,
                input=field_tok.lexeme,
                position=field_tok.position,
            )
        )

    def _parse_value(self, context: str) -> Expression:
        token = self._peek()
        if token.kind in (INT, FLOAT, STRING):
            self._advance()
            return LiteralExpression(token.value)
        if token.kind == IDENT:
            if token.lexeme == "true":
                self._advance()
                return LiteralExpression(True)
            if token.lexeme == "false":
                self._advance()
                return LiteralExpression(False)
            if token.lexeme == "null":
                self._advance()
                return LiteralExpression(None)
            self._error(
                f"reference '{token.lexeme}' not allowed {context}",
                token.position,
            )
        if token.kind == LBRACKET:
            return self._parse_list()
        if token.kind == LT:
            return self._parse_choice()
        self._error(f"expected a value, got {token.lexeme or 'end of input'!r}", token.position)

    def _parse_list(self) -> LiteralExpression:
        self._advance()  # consume '['
        items: list[object] = []
        while self._peek().kind != RBRACKET:
            items.append(self._parse_list_item())
            if self._peek().kind == COMMA:
                self._advance()
                if self._peek().kind == RBRACKET:
                    break
            elif self._peek().kind != RBRACKET:
                self._error("expected ',' or ']' in list", self._peek().position)
        self._advance()  # consume ']'
        return LiteralExpression(items)

    def _parse_list_item(self) -> object:
        token = self._peek()
        if token.kind in (INT, FLOAT, STRING):
            self._advance()
            return token.value
        if token.kind == IDENT:
            if token.lexeme == "true":
                self._advance()
                return True
            if token.lexeme == "false":
                self._advance()
                return False
            if token.lexeme == "null":
                self._advance()
                return None
            self._error(f"reference '{token.lexeme}' not allowed inside a list", token.position)
        if token.kind == LBRACKET:
            return self._parse_list().value
        self._error(f"expected a list item, got {token.lexeme or 'end of input'!r}", token.position)

    def _parse_choice(self) -> ChoiceExpression:
        self._advance()  # consume '<'
        values: list[Expression] = []
        while True:
            values.append(self._parse_value("inside a choice"))
            if self._peek().kind == PIPE:
                self._advance()
                continue
            if self._peek().kind == GT:
                break
            self._error("expected '|' or '>' in choice", self._peek().position)
        self._advance()  # consume '>'
        return ChoiceExpression(tuple(values))

    # -- helpers -------------------------------------------------------

    def _resolve_type(self, type_tok: Token) -> Provider:
        try:
            return self._registry.resolve(type_tok.lexeme)
        except LookupError:
            available = ", ".join(self._registry.capabilities())
            self._error(
                f"unknown provider type '{type_tok.lexeme}'. Available capabilities: {available}",
                type_tok.position,
            )

    def _resolve_bindings(
        self, definitions: list[Definition]
    ) -> dict[str, tuple[Binding, ...]]:
        result: dict[str, tuple[Binding, ...]] = {d.name: () for d in definitions}
        for raw in self._raw_bindings:
            if raw.source not in self._def_positions:
                self._error(
                    f"unknown source definition '{raw.source}' referenced by "
                    f"'{raw.target}'",
                    raw.position,
                )
            result[raw.target] = result[raw.target] + (
                Binding(
                    source=raw.source,
                    output=raw.input,
                    target=raw.target,
                    input=raw.input,
                ),
            )
        return result


def parse(
    source: str,
    *,
    name: str = "analysis",
    version: str = "1.0",
    registry: ProviderRegistry | None = None,
) -> Analysis:
    """Parse DSL text into a template ``Analysis`` (backlog 057).

    The template keeps ``ChoiceExpression`` values intact (expansion is the
    pipeline's job, backlog 050) and is self-contained: ``providers`` is
    populated from the registry so the result serializes and validates
    standalone. Raises ``DslSyntaxError`` for lexical errors and
    ``DslParseError`` (both positioned) for grammar errors.
    """
    reg = registry if registry is not None else create_default_registry()
    return _Parser(source, reg, name, version).parse()
