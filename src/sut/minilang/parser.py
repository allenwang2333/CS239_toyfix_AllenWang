"""MiniLang frontend: parse, check, and walk a program (spec §7, §8).

MiniLang source is a subset of Python. The parser uses Python's ast module.
All integers are compile-time values, so the walker inlines every function
call and unrolls every loop. It checks types and shapes on the way and sends
each tensor operation to a Domain:

- CheckDomain does nothing (parse() uses it to find all errors),
- the reference interpreter computes values,
- the compiler builds IR.
"""

import ast
from dataclasses import dataclass

MAX_OPS = 100_000  # spec §8.9

BUILTINS = {"print", "range", "relu", "transpose", "tensor", "zeros", "ones", "full", "iota"}


class ParseError(Exception):
    pass


def to_s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


@dataclass(frozen=True)
class TensorType:
    shape: tuple[int, ...]  # rank 1 or 2; the element type is always i32

    @property
    def rank(self) -> int:
        return len(self.shape)

    @property
    def size(self) -> int:
        n = 1
        for d in self.shape:
            n *= d
        return n

    def __str__(self) -> str:
        return f"Tensor[{', '.join(map(str, self.shape))}, i32]"


@dataclass(frozen=True)
class Tensor:
    """A tensor value in the walker: its static type and the domain's handle."""
    type: TensorType
    handle: object


class Domain:
    """Receives the tensor operations of a program, in execution order.

    constant() values are row-major. A list of one value is a splat: every
    element has that value. Operands of binary() have the result's shape
    (the walker makes broadcasts explicit with broadcast()).
    """

    def constant(self, type: TensorType, values: list[int]): ...
    def broadcast(self, x: Tensor, type: TensorType): ...
    def binary(self, op: str, a: Tensor, b: Tensor, type: TensorType): ...  # op: add, sub, mul
    def matmul(self, a: Tensor, b: Tensor, type: TensorType): ...
    def relu(self, x: Tensor, type: TensorType): ...
    def transpose(self, x: Tensor, type: TensorType): ...
    def print(self, x: Tensor) -> None: ...


class CheckDomain(Domain):
    pass


# ---- program structure -------------------------------------------------------

@dataclass
class Function:
    name: str
    node: ast.FunctionDef
    params: list[tuple[str, object]]  # (name, TensorType or int)
    returns: object                   # TensorType, int, None (no value), or ... (no annotation)


@dataclass
class Program:
    functions: dict[str, Function]


def _err(node, message: str) -> ParseError:
    line = getattr(node, "lineno", None)
    return ParseError(f"line {line}: {message}" if line else message)


def _annotation(node) -> object:
    """Parse a type annotation: int, None, Tensor[N, i32], or Tensor[M, N, i32]."""
    if isinstance(node, ast.Name) and node.id == "int":
        return int
    if isinstance(node, ast.Constant) and node.value is None:
        return None
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
            and node.value.id == "Tensor":
        items = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        *dims, dtype = items
        if not (isinstance(dtype, ast.Name) and dtype.id == "i32"):
            raise _err(node, "the element type of a Tensor must be i32")
        if not 1 <= len(dims) <= 2:
            raise _err(node, "a Tensor must have rank 1 or 2")
        shape = []
        for d in dims:
            if not (isinstance(d, ast.Constant) and type(d.value) is int and d.value >= 1):
                raise _err(node, "Tensor dimensions must be positive integer literals")
            shape.append(d.value)
        return TensorType(tuple(shape))
    raise _err(node, "unsupported type annotation: use int, None, or Tensor[..., i32]")


def _function(node: ast.FunctionDef) -> Function:
    a = node.args
    if node.decorator_list:
        raise _err(node, "decorators are not supported")
    if a.posonlyargs or a.vararg or a.kwonlyargs or a.kwarg or a.defaults:
        raise _err(node, "only plain positional parameters are supported")
    params = []
    for p in a.args:
        if p.annotation is None:
            raise _err(p, f"parameter {p.arg!r} needs a type annotation")
        t = _annotation(p.annotation)
        if t is None:
            raise _err(p, f"parameter {p.arg!r} must be an int or a Tensor")
        params.append((p.arg, t))
    returns = ... if node.returns is None else _annotation(node.returns)
    return Function(node.name, node, params, returns)


def parse(source: str) -> Program:
    """Parse and check a MiniLang program. Raises ParseError."""
    try:
        module = ast.parse(source)
    except SyntaxError as e:
        raise ParseError(f"line {e.lineno}: syntax error: {e.msg}") from None
    functions: dict[str, Function] = {}
    for node in module.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue  # docstring
        if not isinstance(node, ast.FunctionDef):
            raise _err(node, "only function definitions are allowed at the top level")
        if node.name in functions or node.name in BUILTINS:
            raise _err(node, f"function {node.name!r} is defined twice or shadows a builtin")
        functions[node.name] = _function(node)
    main = functions.get("main")
    if main is None:
        raise ParseError("the program has no main() function")
    if main.params:
        raise _err(main.node, "main() must not have parameters")
    program = Program(functions)
    run(program, CheckDomain())
    return program


# ---- walker ------------------------------------------------------------------

class _Walker:
    def __init__(self, program: Program, domain: Domain):
        self.p = program
        self.d = domain
        self.ops = 0
        self.stack: list[str] = []

    def tick(self, node) -> None:
        self.ops += 1
        if self.ops > MAX_OPS:
            raise _err(node, f"the program is too large: more than {MAX_OPS} operations "
                             "after inlining and unrolling")

    # -- calls and statements --

    def call(self, fn: Function, args: list, node) -> object:
        if fn.name in self.stack:
            raise _err(node, f"recursive call of {fn.name!r}")
        if len(args) != len(fn.params):
            raise _err(node, f"{fn.name}() takes {len(fn.params)} arguments, got {len(args)}")
        env = {}
        for (name, want), value in zip(fn.params, args):
            if want is int and not isinstance(value, int):
                raise _err(node, f"argument {name!r} of {fn.name}() must be an int")
            if isinstance(want, TensorType) and (not isinstance(value, Tensor) or value.type != want):
                got = value.type if isinstance(value, Tensor) else "int"
                raise _err(node, f"argument {name!r} of {fn.name}() must be {want}, got {got}")
            env[name] = value
        self.stack.append(fn.name)
        body = fn.node.body
        result = None
        for i, stmt in enumerate(body):
            if isinstance(stmt, ast.Return):
                if i != len(body) - 1:
                    raise _err(stmt, "return must be the last statement of a function")
                result = None if stmt.value is None else self.expr(stmt.value, env)
            else:
                self.stmt(stmt, env)
        self.stack.pop()
        if fn.returns is not ...:
            want = fn.returns
            ok = (want is None and result is None) or (want is int and isinstance(result, int)) \
                or (isinstance(want, TensorType) and isinstance(result, Tensor) and result.type == want)
            if not ok:
                raise _err(fn.node, f"{fn.name}() must return {_type_name(want)}, "
                                    f"but returns {_value_type(result)}")
        return result

    def stmt(self, s, env: dict) -> None:
        self.tick(s)
        if isinstance(s, ast.Assign):
            if len(s.targets) != 1 or not isinstance(s.targets[0], ast.Name):
                raise _err(s, "assignment target must be a single name")
            env[self._target(s.targets[0])] = self.expr(s.value, env)
        elif isinstance(s, ast.AugAssign):
            if not isinstance(s.target, ast.Name):
                raise _err(s, "assignment target must be a single name")
            name = self._target(s.target)
            if name not in env:
                raise _err(s, f"name {name!r} is not defined")
            env[name] = self.binop(s.op, env[name], self.expr(s.value, env), s)
        elif isinstance(s, ast.Expr):
            v = s.value
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return  # docstring
            if not (isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "print"):
                raise _err(s, "an expression statement must be a print() call")
            if len(v.args) != 1 or v.keywords:
                raise _err(s, "print() takes exactly one argument")
            value = self.expr(v.args[0], env)
            if isinstance(value, int):
                value = self.constant(TensorType((1,)), [value])
            if not isinstance(value, Tensor):
                raise _err(s, "print() needs a tensor or an int")
            self.d.print(value)
        elif isinstance(s, ast.For):
            if s.orelse:
                raise _err(s, "for ... else is not supported")
            name = self._target(s.target)
            it = s.iter
            if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range"
                    and 1 <= len(it.args) <= 3 and not it.keywords):
                raise _err(s, "a for loop must iterate over range(...)")
            bounds = [self.int_expr(a, env) for a in it.args]
            if len(bounds) == 3 and bounds[2] == 0:
                raise _err(s, "range() step must not be zero")
            for i in range(*bounds):
                env[name] = i
                for b in s.body:
                    if isinstance(b, ast.Return):
                        raise _err(b, "return must be the last statement of a function")
                    self.stmt(b, env)
        elif isinstance(s, ast.Pass):
            pass
        elif isinstance(s, ast.Return):
            raise _err(s, "return must be the last statement of a function")
        else:
            raise _err(s, f"unsupported statement: {type(s).__name__}")

    def _target(self, node) -> str:
        if not isinstance(node, ast.Name):
            raise _err(node, "the target must be a single name")
        if node.id in BUILTINS or node.id in self.p.functions:
            raise _err(node, f"{node.id!r} is a function and cannot be assigned")
        return node.id

    # -- expressions --

    def int_expr(self, node, env: dict) -> int:
        v = self.expr(node, env)
        if not isinstance(v, int):
            raise _err(node, "expected an int")
        return v

    def expr(self, e, env: dict):
        if isinstance(e, ast.Constant):
            if type(e.value) is not int:
                raise _err(e, f"unsupported constant {e.value!r}: only integers are allowed")
            if e.value > 0xFFFFFFFF:
                raise _err(e, f"integer literal {e.value} is larger than 2^32-1")
            return to_s32(e.value)
        if isinstance(e, ast.Name):
            if e.id not in env:
                raise _err(e, f"name {e.id!r} is not defined")
            return env[e.id]
        if isinstance(e, ast.BinOp):
            return self.binop(e.op, self.expr(e.left, env), self.expr(e.right, env), e)
        if isinstance(e, ast.UnaryOp):
            v = self.expr(e.operand, env)
            if isinstance(e.op, ast.UAdd):
                return v
            if isinstance(e.op, ast.USub):
                return to_s32(-v) if isinstance(v, int) else self.elementwise("sub", 0, v, e)
            raise _err(e, "unsupported unary operator")
        if isinstance(e, ast.Attribute):
            if e.attr != "T":
                raise _err(e, f"unsupported attribute .{e.attr}")
            return self.transpose(self.expr(e.value, env), e)
        if isinstance(e, ast.Call):
            return self.call_expr(e, env)
        raise _err(e, f"unsupported expression: {type(e).__name__}")

    def call_expr(self, e: ast.Call, env: dict):
        if not isinstance(e.func, ast.Name):
            raise _err(e, "only calls of named functions are supported")
        if e.keywords:
            raise _err(e, "keyword arguments are not supported")
        name, args = e.func.id, e.args
        self.tick(e)
        if name in self.p.functions:
            result = self.call(self.p.functions[name], [self.expr(a, env) for a in args], e)
            if result is None:
                raise _err(e, f"{name}() does not return a value")
            return result

        def arity(n: int) -> None:
            if len(args) != n:
                raise _err(e, f"{name}() takes {n} argument{'s' if n != 1 else ''}")

        if name == "relu":
            arity(1)
            x = self.tensor_arg(args[0], env, name)
            return Tensor(x.type, self.d.relu(x, x.type))
        if name == "transpose":
            arity(1)
            return self.transpose(self.expr(args[0], env), e)
        if name in ("zeros", "ones", "iota"):
            arity(1)
            t = self.shape(args[0], env)
            values = list(range(t.size)) if name == "iota" else [int(name == "ones")]
            return self.constant(t, [to_s32(v) for v in values])
        if name == "full":
            arity(2)
            t = self.shape(args[0], env)
            return self.constant(t, [self.int_expr(args[1], env)])
        if name == "tensor":
            arity(1)
            return self.literal(args[0], env)
        if name in ("print", "range"):
            raise _err(e, f"{name}() cannot be used in an expression")
        raise _err(e, f"unknown function {name!r}")

    def tensor_arg(self, node, env: dict, fname: str) -> Tensor:
        v = self.expr(node, env)
        if not isinstance(v, Tensor):
            raise _err(node, f"{fname}() needs a tensor")
        return v

    def shape(self, node, env: dict) -> TensorType:
        dims = [self.int_expr(d, env) for d in node.elts] if isinstance(node, ast.Tuple) \
            else [self.int_expr(node, env)]
        if not 1 <= len(dims) <= 2 or any(d < 1 for d in dims):
            raise _err(node, "a shape must be 1 or 2 positive ints")
        return TensorType(tuple(dims))

    def literal(self, node, env: dict) -> Tensor:
        if not isinstance(node, ast.List) or not node.elts:
            raise _err(node, "tensor() needs a non-empty list literal")
        if all(isinstance(x, ast.List) for x in node.elts):
            rows = [[self.int_expr(x, env) for x in row.elts] for row in node.elts]
            if not rows[0] or any(len(r) != len(rows[0]) for r in rows):
                raise _err(node, "the rows of a tensor() literal must have the same non-zero length")
            return self.constant(TensorType((len(rows), len(rows[0]))), [v for r in rows for v in r])
        if any(isinstance(x, ast.List) for x in node.elts):
            raise _err(node, "a tensor() literal must have rank 1 or 2")
        values = [self.int_expr(x, env) for x in node.elts]
        return self.constant(TensorType((len(values),)), values)

    # -- tensor operations --

    def constant(self, t: TensorType, values: list[int]) -> Tensor:
        return Tensor(t, self.d.constant(t, values))

    def transpose(self, x, node) -> Tensor:
        if not isinstance(x, Tensor) or x.type.rank != 2:
            raise _err(node, "transpose needs a rank-2 tensor")
        t = TensorType((x.type.shape[1], x.type.shape[0]))
        return Tensor(t, self.d.transpose(x, t))

    def binop(self, op, a, b, node):
        if isinstance(op, ast.MatMult):
            if not (isinstance(a, Tensor) and isinstance(b, Tensor)
                    and a.type.rank == 2 and b.type.rank == 2):
                raise _err(node, "@ needs two rank-2 tensors")
            (m, k), (k2, n) = a.type.shape, b.type.shape
            if k != k2:
                raise _err(node, f"shapes {a.type} and {b.type} do not match for @")
            t = TensorType((m, n))
            return Tensor(t, self.d.matmul(a, b, t))
        names = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul"}
        if type(op) not in names:
            raise _err(node, f"unsupported operator {type(op).__name__}")
        return self.elementwise(names[type(op)], a, b, node)

    def elementwise(self, op: str, a, b, node):
        if isinstance(a, int) and isinstance(b, int):
            return to_s32({"add": a + b, "sub": a - b, "mul": a * b}[op])
        if isinstance(a, int):
            a = self.constant(b.type, [a])
        if isinstance(b, int):
            b = self.constant(a.type, [b])
        if a.type != b.type:
            a, b = self.broadcast(a, b, node)
        return Tensor(a.type, self.d.binary(op, a, b, a.type))

    def broadcast(self, a: Tensor, b: Tensor, node) -> tuple[Tensor, Tensor]:
        """Broadcast a rank-1 [N] operand to the rank-2 [M, N] operand (spec §8.4)."""
        if a.type.rank == 1 and b.type.rank == 2 and a.type.shape[0] == b.type.shape[1]:
            return Tensor(b.type, self.d.broadcast(a, b.type)), b
        if b.type.rank == 1 and a.type.rank == 2 and b.type.shape[0] == a.type.shape[1]:
            return a, Tensor(a.type, self.d.broadcast(b, a.type))
        raise _err(node, f"shapes {a.type} and {b.type} cannot be broadcast")


def _type_name(t) -> str:
    return "nothing" if t is None else ("int" if t is int else str(t))


def _value_type(v) -> str:
    return "nothing" if v is None else ("int" if isinstance(v, int) else str(v.type))


def run(program: Program, domain: Domain) -> None:
    """Run main() and send every tensor operation to the domain."""
    w = _Walker(program, domain)
    main = program.functions["main"]
    if w.call(main, [], main.node) is not None:
        raise _err(main.node, "main() must not return a value")
