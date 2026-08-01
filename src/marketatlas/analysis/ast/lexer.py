from __future__ import annotations

from dataclasses import dataclass

# Structural token kinds (lexeme doubles as the kind name).
ASSIGN = ":="
LBRACE = "{"
RBRACE = "}"
COLON = ":"
COMMA = ","
LBRACKET = "["
RBRACKET = "]"
LT = "<"
PIPE = "|"
GT = ">"

# Value token kinds.
IDENT = "IDENT"
INT = "INT"
FLOAT = "FLOAT"
STRING = "STRING"

_SINGLE = {
    "{": LBRACE,
    "}": RBRACE,
    ":": COLON,
    ",": COMMA,
    "[": LBRACKET,
    "]": RBRACKET,
    "<": LT,
    "|": PIPE,
    ">": GT,
}

_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "n": "\n",
    "t": "\t",
}


@dataclass(frozen=True)
class SourcePosition:
    """1-based source location shared by lexer, parser, and diagnostics (backlog 059)."""

    line: int
    col: int


class DslSyntaxError(Exception):
    """Lexical error in DSL source, carrying the offending source position."""

    def __init__(self, message: str, position: SourcePosition) -> None:
        self.message = message
        self.position = position
        super().__init__(f"{position.line}:{position.col}: {message}")


@dataclass(frozen=True)
class Token:
    """A lexed token: kind, exact source slice (``lexeme``), and position.

    ``value`` holds the parsed payload for value tokens — an ``int`` or
    ``float`` for ``INT``/``FLOAT``, the unescaped string for ``STRING`` —
    and is ``None`` for structural and ``IDENT`` tokens.
    """

    kind: str
    lexeme: str
    position: SourcePosition
    value: object = None


class _Lexer:
    def __init__(self, source: str) -> None:
        self._source = source
        self._pos = 0
        self._line = 1
        self._col = 1
        self._tokens: list[Token] = []
        self._choice_depth = 0
        self._open_choice: SourcePosition | None = None

    def _peek(self, offset: int = 0) -> str:
        index = self._pos + offset
        return self._source[index] if index < len(self._source) else ""

    def _advance(self) -> str:
        char = self._source[self._pos]
        self._pos += 1
        if char == "\n":
            self._line += 1
            self._col = 1
        else:
            self._col += 1
        return char

    def _at(self, line: int, col: int) -> SourcePosition:
        return SourcePosition(line=line, col=col)

    def _error(self, message: str, position: SourcePosition) -> None:
        raise DslSyntaxError(message, position)

    def _skip_whitespace_and_comments(self) -> None:
        while self._pos < len(self._source):
            char = self._peek()
            if char in " \t\r\n":
                self._advance()
                continue
            if char == "/" and self._peek(1) == "/":
                while self._pos < len(self._source) and self._peek() != "\n":
                    self._advance()
                continue
            break

    def _emit(self, kind: str, lexeme: str, position: SourcePosition, value: object = None) -> None:
        self._tokens.append(Token(kind=kind, lexeme=lexeme, position=position, value=value))

    def _emit_single(self) -> None:
        char = self._peek()
        position = self._at(self._line, self._col)
        kind = _SINGLE[char]
        self._advance()
        if kind == LT:
            self._choice_depth += 1
            self._open_choice = position
        elif kind == GT:
            if self._choice_depth == 0:
                self._error("unexpected '>' outside a choice", position)
            self._choice_depth -= 1
            if self._choice_depth == 0:
                self._open_choice = None
        elif kind == PIPE and self._choice_depth == 0:
            self._error("unexpected '|' outside a choice", position)
        self._emit(kind, char, position)

    def _lex_assign(self) -> None:
        position = self._at(self._line, self._col)
        self._advance()
        if self._peek() == "=":
            self._advance()
            self._emit(ASSIGN, ":=", position)
        else:
            self._emit(COLON, ":", position)

    def _lex_ident(self) -> None:
        position = self._at(self._line, self._col)
        start = self._pos
        while self._pos < len(self._source):
            char = self._peek()
            if char.isalnum() or char == "_":
                self._advance()
            else:
                break
        lexeme = self._source[start : self._pos]
        self._emit(IDENT, lexeme, position)

    def _lex_number(self) -> None:
        position = self._at(self._line, self._col)
        start = self._pos
        if self._peek() == "-":
            self._advance()
        while self._peek().isdigit():
            self._advance()
        is_float = False
        if self._peek() == "." and self._peek(1).isdigit():
            is_float = True
            self._advance()
            while self._peek().isdigit():
                self._advance()
        lexeme = self._source[start : self._pos]
        if is_float:
            self._emit(FLOAT, lexeme, position, value=float(lexeme))
        else:
            self._emit(INT, lexeme, position, value=int(lexeme))

    def _lex_string(self) -> None:
        position = self._at(self._line, self._col)
        self._advance()
        start = self._pos
        chars: list[str] = []
        while True:
            if self._pos >= len(self._source):
                self._error("unterminated string literal", position)
            char = self._advance()
            if char == '"':
                break
            if char == "\\":
                if self._pos >= len(self._source):
                    self._error("unterminated string literal", position)
                escaped = self._advance()
                chars.append(_ESCAPES.get(escaped, escaped))
            else:
                chars.append(char)
        lexeme = self._source[start - 1 : self._pos]
        self._emit(STRING, lexeme, position, value="".join(chars))

    def tokenize(self) -> list[Token]:
        while self._pos < len(self._source):
            self._skip_whitespace_and_comments()
            if self._pos >= len(self._source):
                break
            char = self._peek()
            if char == ":":
                self._lex_assign()
            elif char in _SINGLE:
                self._emit_single()
            elif char == "=":
                self._error(
                    "truncated ':=' operator (use ':' or ':=')", self._at(self._line, self._col)
                )
            elif char == "/":
                self._error(
                    "illegal character '/' (expected '//' comment)", self._at(self._line, self._col)
                )
            elif char.isalpha() or char == "_":
                self._lex_ident()
            elif char == "-" or char.isdigit():
                self._lex_number()
            elif char == '"':
                self._lex_string()
            else:
                self._error(f"illegal character {char!r}", self._at(self._line, self._col))
        if self._choice_depth > 0:
            assert self._open_choice is not None
            self._error("unterminated choice, missing '>'", self._open_choice)
        return self._tokens


def tokenize(source: str) -> list[Token]:
    """Tokenize DSL source into an ordered token stream (backlog 056).

    Single-pass, maximal-munch scanner. Whitespace and ``//`` line comments
    are skipped; choice brackets ``<``/``|``/``>`` are balance-checked because
    they have no other meaning in the grammar (backlog 055).
    """
    return _Lexer(source).tokenize()
