"""Reference interpreter for MiniLang (spec §8).

This is the oracle for MiniLang tests. It does not use the compiler or the
simulator.
"""

from .parser import (ArrayDecl, Assign, Binary, If, Index, IndexAssign, Num,
                     Print, Unary, Var, VarDecl, While, declarations, parse,
                     to_s32)

STEP_LIMIT = 2_000_000


class RuntimeTrap(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _div(a: int, b: int) -> int:
    if b == 0:
        raise RuntimeTrap("div_by_zero")
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _binary(op: str, a: int, b: int) -> int:
    if op == "+":
        return to_s32(a + b)
    if op == "-":
        return to_s32(a - b)
    if op == "*":
        return to_s32(a * b)
    if op == "/":
        return to_s32(_div(a, b))
    if op == "%":
        return to_s32(a - b * _div(a, b))
    if op == "&":
        return to_s32(a & b)
    if op == "|":
        return to_s32(a | b)
    if op == "^":
        return to_s32(a ^ b)
    if op == "<<":
        return to_s32(a << (b & 31))
    if op == ">>":
        return to_s32(a >> (b & 31))  # Python >> on negative ints is arithmetic.
    if op == "<":
        return int(a < b)
    if op == "<=":
        return int(a <= b)
    if op == ">":
        return int(a > b)
    if op == ">=":
        return int(a >= b)
    if op == "==":
        return int(a == b)
    if op == "!=":
        return int(a != b)
    raise ValueError(op)


class _Interp:
    def __init__(self, stmts):
        self.vars: dict[str, int] = {}
        self.arrays: dict[str, list[int]] = {}
        for d in declarations(stmts):
            if isinstance(d, ArrayDecl):
                self.arrays[d.name] = [0] * d.size
        self.output: list[int] = []
        self.steps = 0

    def eval(self, e) -> int:
        if isinstance(e, Num):
            return e.value
        if isinstance(e, Var):
            return self.vars.get(e.name, 0)
        if isinstance(e, Index):
            arr = self.arrays[e.name]
            i = self.eval(e.index)
            if not 0 <= i < len(arr):
                raise RuntimeTrap("index_out_of_range")
            return arr[i]
        if isinstance(e, Unary):
            v = self.eval(e.operand)
            if e.op == "-":
                return to_s32(-v)
            if e.op == "!":
                return int(v == 0)
            return to_s32(~v)
        if isinstance(e, Binary):
            a = self.eval(e.left)
            b = self.eval(e.right)
            return _binary(e.op, a, b)
        raise TypeError(e)

    def run(self, stmts) -> None:
        for s in stmts:
            self.steps += 1
            if self.steps > STEP_LIMIT:
                raise RuntimeTrap("step_limit")
            if isinstance(s, VarDecl):
                self.vars[s.name] = self.eval(s.init) if s.init is not None else 0
            elif isinstance(s, ArrayDecl):
                pass
            elif isinstance(s, Assign):
                self.vars[s.name] = self.eval(s.value)
            elif isinstance(s, IndexAssign):
                arr = self.arrays[s.name]
                i = self.eval(s.index)
                v = self.eval(s.value)
                if not 0 <= i < len(arr):
                    raise RuntimeTrap("index_out_of_range")
                arr[i] = v
            elif isinstance(s, Print):
                self.output.append(self.eval(s.value))
            elif isinstance(s, If):
                self.run(s.then if self.eval(s.cond) != 0 else s.orelse)
            elif isinstance(s, While):
                while self.eval(s.cond) != 0:
                    self.run(s.body)
                    self.steps += 1
                    if self.steps > STEP_LIMIT:
                        raise RuntimeTrap("step_limit")


def evaluate(source: str) -> tuple[list[int], str | None]:
    """Run a program. Return (output values, trap reason or None).
    Raises ParseError for invalid programs."""
    stmts = parse(source)
    interp = _Interp(stmts)
    try:
        interp.run(stmts)
    except RuntimeTrap as t:
        return interp.output, t.reason
    return interp.output, None
