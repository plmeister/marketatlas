from __future__ import annotations

import pytest
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
    DslSyntaxError,
    SourcePosition,
    Token,
    tokenize,
)


def _kinds(source: str) -> list[str]:
    return [t.kind for t in tokenize(source)]


def _lexemes(source: str) -> list[str]:
    return [t.lexeme for t in tokenize(source)]


def _token(source: str, kind: str) -> Token:
    for t in tokenize(source):
        if t.kind == kind:
            return t
    raise AssertionError(f"no {kind} token in {source!r}")


class TestTokenTable:
    def test_empty_input(self) -> None:
        assert tokenize("") == []

    def test_whitespace_only(self) -> None:
        assert tokenize("  \n\t\r\n  ") == []

    def test_full_definition(self) -> None:
        source = """
            trend := Trend {
                period: 20,
                source: close,
                mult: 1.5,
                tags: ["trend", "fast"],
                scale: <1 | 2 | 4>,
            }
        """
        assert _kinds(source) == [
            IDENT,
            ASSIGN,
            IDENT,
            LBRACE,
            IDENT,
            COLON,
            INT,
            COMMA,
            IDENT,
            COLON,
            IDENT,
            COMMA,
            IDENT,
            COLON,
            FLOAT,
            COMMA,
            IDENT,
            COLON,
            LBRACKET,
            STRING,
            COMMA,
            STRING,
            RBRACKET,
            COMMA,
            IDENT,
            COLON,
            LT,
            INT,
            PIPE,
            INT,
            PIPE,
            INT,
            GT,
            COMMA,
            RBRACE,
        ]

    def test_minimal_definition(self) -> None:
        assert _kinds("ema := EMA { period: 20 }") == [
            IDENT,
            ASSIGN,
            IDENT,
            LBRACE,
            IDENT,
            COLON,
            INT,
            RBRACE,
        ]

    def test_shorthand_dependency(self) -> None:
        assert _kinds("trend := Trend { swings, }") == [
            IDENT,
            ASSIGN,
            IDENT,
            LBRACE,
            IDENT,
            COMMA,
            RBRACE,
        ]

    def test_trailing_commas_allowed(self) -> None:
        assert _kinds("a := B { x: 1,, }") == [
            IDENT,
            ASSIGN,
            IDENT,
            LBRACE,
            IDENT,
            COLON,
            INT,
            COMMA,
            COMMA,
            RBRACE,
        ]

    def test_int_vs_float_distinguished(self) -> None:
        source = "a: 5, b: 5.0, c: -3, d: -1.25"
        tokens = tokenize(source)
        values = [(t.kind, t.value) for t in tokens if t.kind in (INT, FLOAT)]
        assert values == [
            (INT, 5),
            (FLOAT, 5.0),
            (INT, -3),
            (FLOAT, -1.25),
        ]
        assert _lexemes(source) == [
            "a",
            ":",
            "5",
            ",",
            "b",
            ":",
            "5.0",
            ",",
            "c",
            ":",
            "-3",
            ",",
            "d",
            ":",
            "-1.25",
        ]

    def test_float_requires_trailing_digit(self) -> None:
        tokens = tokenize("x: 1.5,")
        assert tokens[2].kind == FLOAT
        assert tokens[2].lexeme == "1.5"
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("x: 1.")
        assert exc.value.position == SourcePosition(1, 5)

    def test_string_escapes(self) -> None:
        tok = _token('s: "a\\n b\\t c\\" d\\\\ e"', STRING)
        assert tok.value == 'a\n b\t c" d\\ e'
        assert tok.lexeme == '"a\\n b\\t c\\" d\\\\ e"'

    def test_string_unknown_escape_kept(self) -> None:
        assert _token(r's: "a\qb"', STRING).value == r"aqb"

    def test_identifier_characters(self) -> None:
        assert _lexemes("foo _bar baz9 _") == ["foo", "_bar", "baz9", "_"]

    def test_comment_skipped(self) -> None:
        source = "// header comment\nperiod: 20 // trailing"
        tokens = tokenize(source)
        kinds = _kinds(source)
        assert kinds == [IDENT, COLON, INT]
        assert tokens[0].position == SourcePosition(line=2, col=1)
        assert tokens[2].position == SourcePosition(line=2, col=9)
        with pytest.raises(DslSyntaxError):
            tokenize("/* not a comment */")

    def test_comment_only_source(self) -> None:
        assert tokenize("// just a comment\n// and another\n") == []

    def test_comment_between_tokens(self) -> None:
        assert _kinds("a: 1, // gap\n b: 2") == [IDENT, COLON, INT, COMMA, IDENT, COLON, INT]


class TestPositions:
    def test_positions_multiline(self) -> None:
        source = "ema := EMA {\n  period: 20,\n  scale: <1 | 2>\n}"
        tokens = tokenize(source)
        positions = [(t.kind, t.position.line, t.position.col) for t in tokens]
        assert positions == [
            (IDENT, 1, 1),
            (ASSIGN, 1, 5),
            (IDENT, 1, 8),
            (LBRACE, 1, 12),
            (IDENT, 2, 3),
            (COLON, 2, 9),
            (INT, 2, 11),
            (COMMA, 2, 13),
            (IDENT, 3, 3),
            (COLON, 3, 8),
            (LT, 3, 10),
            (INT, 3, 11),
            (PIPE, 3, 13),
            (INT, 3, 15),
            (GT, 3, 16),
            (RBRACE, 4, 1),
        ]

    def test_position_column_1based(self) -> None:
        tok = _token("abc", IDENT)
        assert tok.position == SourcePosition(1, 1)

    def test_position_after_newline_col_reset(self) -> None:
        tok = tokenize("\n\nx")[0]
        assert tok.position == SourcePosition(3, 1)


class TestSyntaxErrors:
    def test_unterminated_string(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize('a: "never closed')
        err = exc.value
        assert err.position == SourcePosition(1, 4)
        assert "unterminated string" in err.message

    def test_unterminated_string_with_escape_at_eof(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize('"a\\')
        assert exc.value.position == SourcePosition(1, 1)

    def test_unterminated_string_after_newline(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize('a: "x\nb: 2')
        assert exc.value.position == SourcePosition(1, 4)

    def test_illegal_character(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("a @ b")
        assert exc.value.position == SourcePosition(1, 3)
        assert "illegal character" in exc.value.message

    def test_illegal_character_on_second_line(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("a: 1\nb # 2")
        assert exc.value.position == SourcePosition(2, 3)

    def test_truncated_assign_lone_equals(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("ema = EMA")
        err = exc.value
        assert err.position == SourcePosition(1, 5)
        assert "truncated ':=' operator" in err.message

    def test_truncated_assign_split(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("ema : = EMA")
        assert exc.value.position == SourcePosition(1, 7)

    def test_pipe_outside_choice(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("a | b")
        assert exc.value.position == SourcePosition(1, 3)
        assert "outside a choice" in exc.value.message

    def test_gt_outside_choice(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("a > b")
        assert exc.value.position == SourcePosition(1, 3)

    def test_unterminated_choice(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("a: <1 | 2")
        err = exc.value
        assert err.position == SourcePosition(1, 4)
        assert "unterminated choice" in err.message

    def test_unterminated_choice_nested(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("a: <1 | <2 | 3>")
        assert exc.value.position == SourcePosition(1, 9)

    def test_single_slash_illegal(self) -> None:
        with pytest.raises(DslSyntaxError):
            tokenize("a / b")

    def test_lone_dot_illegal(self) -> None:
        with pytest.raises(DslSyntaxError) as exc:
            tokenize("a: .")
        assert exc.value.position == SourcePosition(1, 4)


class TestNestedChoices:
    def test_nested_choice_tokens(self) -> None:
        assert _kinds("s: <1 | <2 | 3>>") == [
            IDENT,
            COLON,
            LT,
            INT,
            PIPE,
            LT,
            INT,
            PIPE,
            INT,
            GT,
            GT,
        ]

    def test_balanced_choices_no_error(self) -> None:
        assert _kinds("a: <1 | 2>, b: <3 | <4 | 5>>")[-3:] == [INT, GT, GT]


class TestRoundTrip:
    def test_lexeme_concat_reproduces_source_modulo_whitespace_comments(self) -> None:
        sources = [
            "trend := Trend { period: 20 }",
            "a: [1, 2, 3], b: <1 | 2>",
            "n: -1.5, i: 42",
        ]
        for source in sources:
            joined = "".join(_lexemes(source))
            stripped = source.strip()
            assert joined == stripped.replace(" ", "")

    def test_lexeme_concat_preserves_string_inner_whitespace(self) -> None:
        source = 's: "quoted \\" string", t: 1'
        assert "".join(_lexemes(source)) == 's:"quoted \\" string",t:1'

    def test_lexeme_concat_multiline(self) -> None:
        source = "ema := EMA {\n  period: 20,\n}"
        joined = "".join(_lexemes(source))
        assert joined == "ema:=EMA{period:20,}"

    def test_lexeme_concat_skips_comments(self) -> None:
        source = "a: 1, // note\nb: 2"
        assert "".join(_lexemes(source)) == "a:1,b:2"
