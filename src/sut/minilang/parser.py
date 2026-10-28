"""MiniLang lexer, parser, and semantic checks (spec §7, §8.2)."""

import re
from dataclasses import dataclass


class ParseError(Exception):
    pass


# ---- AST -------------------------------------------------------------------

@dataclass
class Num:
    value: int  # signed 32-bit


@dataclass
class Var:
    name: str


@dataclass
class Index:
    name: str
    index: object


@dataclass
class Unary:
    op: str
    operand: object


@dataclass
class Binary:
    op: str
    left: object
    right: object


@dataclass
class VarDecl:
    name: str
    init: object | None


@dataclass
class ArrayDecl:
    name: str
    size: int


@dataclass
class Assign:
    name: str
    value: object


@dataclass
class IndexAssign:
    name: str
    index: object
    value: object


@dataclass
class Print:
    value: object


@dataclass
class If:
    cond: object
    then: list
    orelse: list


@dataclass
class While:
    cond: object
    body: list


# ---- Lexer -----------------------------------------------------------------

_TOKEN = re.compile(r"""
    (?P<ws>\s+|//[^\n]*)
  | (?P<num>\d+)
  | (?P<name>[A-Za-z_]\w*)
  | (?P<op><<|>>|<=|>=|==|!=|[-+*/%&|^~!<>=;(){}\[\]])
""", re.VERBOSE)

KEYWORDS = {"var", "array", "print", "if", "else", "while"}

# Binary operator precedence (spec §7.1). Higher binds tighter.
PRECEDENCE = {
    "|": 1, "^": 2, "&": 3, "==": 4, "!=": 4,
    "<": 5, "<=": 5, ">": 5, ">=": 5, "<<": 6, ">>": 6,
    "+": 7, "-": 7, "*": 8, "/": 8, "%": 8,
}


def to_s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def tokenize(source: str) -> list[tuple[str, str, int]]:
    tokens = []
    pos, line = 0, 1
    while pos < len(source):
        m = _TOKEN.match(source, pos)
        if not m:
            raise ParseError(f"line {line}: unexpected character {source[pos]!r}")
        kind = m.lastgroup
        text = m.group()
        if kind != "ws":
            if kind == "name" and text in KEYWORDS:
                kind = "kw"
            tokens.append((kind, text, line))
        line += text.count("\n")
        pos = m.end()
    tokens.append(("eof", "", line))
    return tokens


# ---- Parser ----------------------------------------------------------------

class _Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

    def peek(self, k: int = 0):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self):
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def at(self, text: str) -> bool:
        kind, value, _ = self.peek()
        return value == text and kind in ("op", "kw")

    def expect(self, text: str):
        kind, value, line = self.next()
        if value != text or kind not in ("op", "kw"):
            raise ParseError(f"line {line}: expected {text!r}, got {value or 'end of input'!r}")

    def name(self) -> str:
        kind, value, line = self.next()
        if kind != "name":
            raise ParseError(f"line {line}: expected a name, got {value or 'end of input'!r}")
        return value

    def program(self) -> list:
        stmts = []
        while self.peek()[0] != "eof":
            stmts.append(self.stmt())
        return stmts

    def block(self) -> list:
        self.expect("{")
        stmts = []
        while not self.at("}"):
            if self.peek()[0] == "eof":
                raise ParseError(f"line {self.peek()[2]}: missing '}}'")
            stmts.append(self.stmt())
        self.expect("}")
        return stmts

    def stmt(self):
        kind, value, line = self.peek()
        if kind == "kw" and value == "var":
            self.next()
            name = self.name()
            init = None
            if self.at("="):
                self.next()
                init = self.expr()
            self.expect(";")
            return VarDecl(name, init)
        if kind == "kw" and value == "array":
            self.next()
            name = self.name()
            self.expect("[")
            k, size, ln = self.next()
            if k != "num" or int(size) <= 0:
                raise ParseError(f"line {ln}: array size must be a positive integer")
            self.expect("]")
            self.expect(";")
            return ArrayDecl(name, int(size))
        if kind == "kw" and value == "print":
            self.next()
            e = self.expr()
            self.expect(";")
            return Print(e)
        if kind == "kw" and value == "if":
            self.next()
            self.expect("(")
            cond = self.expr()
            self.expect(")")
            then = self.block()
            orelse = []
            if self.at("else"):
                self.next()
                orelse = self.block()
            return If(cond, then, orelse)
        if kind == "kw" and value == "while":
            self.next()
            self.expect("(")
            cond = self.expr()
            self.expect(")")
            return While(cond, self.block())
        if kind == "name":
            name = self.name()
            if self.at("["):
                self.next()
                idx = self.expr()
                self.expect("]")
                self.expect("=")
                val = self.expr()
                self.expect(";")
                return IndexAssign(name, idx, val)
            self.expect("=")
            val = self.expr()
            self.expect(";")
            return Assign(name, val)
        raise ParseError(f"line {line}: unexpected {value or 'end of input'!r}")

    def expr(self, min_prec: int = 1):
        left = self.unary()
        while True:
            kind, op, _ = self.peek()
            prec = PRECEDENCE.get(op) if kind == "op" else None
            if prec is None or prec < min_prec:
                return left
            self.next()
            right = self.expr(prec + 1)
            left = Binary(op, left, right)

    def unary(self):
        if self.at("-") or self.at("!") or self.at("~"):
            op = self.next()[1]
            return Unary(op, self.unary())
        return self.primary()

    def primary(self):
        kind, value, line = self.next()
        if kind == "num":
            n = int(value)
            if n > 0xFFFFFFFF:
                raise ParseError(f"line {line}: integer literal {n} is larger than 2^32-1")
            return Num(to_s32(n))
        if kind == "name":
            if self.at("["):
                self.next()
                idx = self.expr()
                self.expect("]")
                return Index(value, idx)
            return Var(value)
        if value == "(" and kind == "op":
            e = self.expr()
            self.expect(")")
            return e
        raise ParseError(f"line {line}: unexpected {value or 'end of input'!r}")


# ---- Semantic checks (spec §8.2) ------------------------------------------

def _check(stmts: list, scope: dict[str, str]) -> None:
    def use(name: str, kind: str) -> None:
        if name not in scope:
            raise ParseError(f"name {name!r} is used before it is declared")
        if scope[name] != kind:
            raise ParseError(f"name {name!r} is a {scope[name]}, not a {kind}")

    def expr(e) -> None:
        if isinstance(e, Var):
            use(e.name, "var")
        elif isinstance(e, Index):
            use(e.name, "array")
            expr(e.index)
        elif isinstance(e, Unary):
            expr(e.operand)
        elif isinstance(e, Binary):
            expr(e.left)
            expr(e.right)

    for s in stmts:
        if isinstance(s, (VarDecl, ArrayDecl)):
            if isinstance(s, VarDecl) and s.init is not None:
                expr(s.init)
            if s.name in scope:
                raise ParseError(f"name {s.name!r} is declared twice")
            scope[s.name] = "var" if isinstance(s, VarDecl) else "array"
        elif isinstance(s, Assign):
            expr(s.value)
            use(s.name, "var")
        elif isinstance(s, IndexAssign):
            use(s.name, "array")
            expr(s.index)
            expr(s.value)
        elif isinstance(s, Print):
            expr(s.value)
        elif isinstance(s, If):
            expr(s.cond)
            _check(s.then, scope)
            _check(s.orelse, scope)
        elif isinstance(s, While):
            expr(s.cond)
            _check(s.body, scope)


def parse(source: str) -> list:
    """Parse and check a MiniLang program. Raises ParseError."""
    stmts = _Parser(tokenize(source)).program()
    _check(stmts, {})
    return stmts


def declarations(stmts: list) -> list:
    """All VarDecl and ArrayDecl statements, in program text order."""
    out = []
    for s in stmts:
        if isinstance(s, (VarDecl, ArrayDecl)):
            out.append(s)
        elif isinstance(s, If):
            out += declarations(s.then) + declarations(s.orelse)
        elif isinstance(s, While):
            out += declarations(s.body)
    return out
