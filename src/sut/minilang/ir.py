"""MLIR-style IR for the MiniLang middle end (spec §9.4).

The IR has values, operations, one function per module, and attributes. The
printer writes MLIR generic syntax, so the output can be read by mlir-opt
with --allow-unregistered-dialect. The verifier checks every operation
against its dialect definition.

Dialects:
- ml:  tensor operations on value-semantic tensors (frontend output).
- npu: one operation per NPU instruction (spec §3), plus npu.data for
       initial DRAM contents.
"""

from dataclasses import dataclass, field


class CompileError(Exception):
    pass


class IRError(CompileError):
    """The IR is malformed. This is always a compiler bug."""


# ---- types -------------------------------------------------------------------

@dataclass(frozen=True)
class TensorType:
    shape: tuple[int, ...]

    def __str__(self) -> str:
        return f"tensor<{'x'.join(map(str, self.shape))}xi32>"


@dataclass(frozen=True)
class MemRefType:
    """A strided view of DRAM: element (i, j) is at offset + i*strides[0] + j*strides[1]."""
    shape: tuple[int, ...]
    offset: int
    strides: tuple[int, ...]

    def __str__(self) -> str:
        return (f"memref<{'x'.join(map(str, self.shape))}xi32, "
                f"strided<[{', '.join(map(str, self.strides))}], offset: {self.offset}>>")

    def view2d(self) -> tuple[int, int, int, int, int]:
        """(base, rows, cols, rstride, cstride). A rank-1 view is one row."""
        if len(self.shape) == 1:
            return self.offset, 1, self.shape[0], 0, self.strides[0]
        return self.offset, self.shape[0], self.shape[1], self.strides[0], self.strides[1]


@dataclass(frozen=True)
class Dense:
    """A dense elements attribute. One value means a splat."""
    shape: tuple[int, ...]
    values: tuple[int, ...]

    @property
    def splat(self) -> bool:
        return len(self.values) == 1

    def expanded(self) -> list[int]:
        return list(self.values) * _size(self.shape) if self.splat else list(self.values)


def _size(shape: tuple[int, ...]) -> int:
    n = 1
    for d in shape:
        n *= d
    return n


# ---- values and operations -----------------------------------------------------

class Value:
    def __init__(self, type, owner: "Op"):
        self.type = type
        self.owner = owner


class Op:
    def __init__(self, name: str, operands=(), result_types=(), attrs: dict | None = None):
        self.name = name
        self.operands: list[Value] = list(operands)
        self.results: list[Value] = [Value(t, self) for t in result_types]
        self.attrs: dict = dict(attrs or {})

    @property
    def result(self) -> Value:
        return self.results[0]

    def __repr__(self) -> str:
        return f"<Op {self.name}>"


@dataclass
class Func:
    name: str
    ops: list[Op] = field(default_factory=list)

    def uses(self) -> dict[Value, list[Op]]:
        out: dict[Value, list[Op]] = {}
        for op in self.ops:
            for v in op.results:
                out.setdefault(v, [])
            for v in op.operands:
                out.setdefault(v, []).append(op)
        return out

    def replace_all_uses(self, old: Value, new: Value) -> None:
        for op in self.ops:
            op.operands = [new if v is old else v for v in op.operands]


@dataclass
class Module:
    func: Func
    attrs: dict = field(default_factory=dict)


# Ops without side effects. Canonicalization may erase or merge them.
PURE = {"ml.constant", "ml.broadcast", "ml.add", "ml.sub", "ml.mul", "ml.matmul",
        "ml.linear", "ml.relu", "ml.transpose"}


# ---- printer -----------------------------------------------------------------

def _attr(v, elide: int | None) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return f"{v} : i64"
    if isinstance(v, Dense):
        t = TensorType(v.shape)
        if v.splat:
            return f"dense<{v.values[0]}> : {t}"
        if elide is not None and len(v.values) > elide:
            return f"dense_resource<__elided__> : {t}"
        if len(v.shape) == 2:
            n = v.shape[1]
            rows = [v.values[i:i + n] for i in range(0, len(v.values), n)]
            body = "[" + ", ".join("[" + ", ".join(map(str, r)) + "]" for r in rows) + "]"
        else:
            body = "[" + ", ".join(map(str, v.values)) + "]"
        return f"dense<{body}> : {t}"
    raise IRError(f"cannot print attribute {v!r}")


def print_module(module: Module, elide: int | None = 16) -> str:
    """Print in MLIR generic syntax. Dense attributes with more than `elide`
    values are elided, as mlir-opt --mlir-elide-elementsattrs-if-larger does."""
    names: dict[Value, str] = {}
    lines = []
    head = "module"
    if module.attrs:
        head += " attributes {" + ", ".join(f"{k} = {_attr(v, elide)}"
                                           for k, v in sorted(module.attrs.items())) + "}"
    lines.append(head + " {")
    lines.append(f"  func.func @{module.func.name}() {{")
    for op in module.func.ops:
        for v in op.results:
            names[v] = f"%{len(names)}"
        lhs = ", ".join(names[v] for v in op.results)
        args = ", ".join(names.get(v, "%<undefined>") for v in op.operands)
        attrs = ""
        if op.attrs:
            attrs = " {" + ", ".join(f"{k} = {_attr(v, elide)}" for k, v in sorted(op.attrs.items())) + "}"
        ins = ", ".join(str(v.type) for v in op.operands)
        outs = ", ".join(str(v.type) for v in op.results)
        if len(op.results) != 1:
            outs = f"({outs})"
        text = f'"{op.name}"({args}){attrs} : ({ins}) -> {outs}'
        lines.append(f"    {lhs + ' = ' if lhs else ''}{text}")
    lines.append("    func.return")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


# ---- verifier ----------------------------------------------------------------

NPU_OPS = {
    "npu.load": ("spad", "dram", "rows", "cols", "rstride", "cstride"),
    "npu.store": ("dram", "spad", "rows", "cols", "rstride"),
    "npu.mm": ("dst", "a", "b", "m", "k", "n"),
    "npu.mma": ("dst", "a", "b", "m", "k", "n"),
    "npu.vadd": ("dst", "a", "b", "len"),
    "npu.vsub": ("dst", "a", "b", "len"),
    "npu.vmul": ("dst", "a", "b", "len"),
    "npu.vrelu": ("dst", "a", "len"),
    "npu.out": ("dram", "rows", "cols", "rstride", "cstride"),
}


def _verify_ml(op: Op) -> str | None:
    """Return an error message, or None if the op is well formed."""
    shapes = [v.type.shape for v in op.operands]
    res = [v.type.shape for v in op.results]
    n = op.name

    def arity(operands: int | tuple, results: int) -> str | None:
        ok = len(shapes) in (operands if isinstance(operands, tuple) else (operands,))
        return None if ok and len(res) == results else "wrong number of operands or results"

    if n == "ml.constant":
        d = op.attrs.get("value")
        if not isinstance(d, Dense) or d.shape != res[0] or len(d.values) not in (1, _size(d.shape)):
            return "value attribute does not match the result type"
        return arity(0, 1)
    if n == "ml.print":
        return arity(1, 0)
    err = arity((1, 2, 3), 1)
    if err:
        return err
    out = res[0]
    if n in ("ml.add", "ml.sub", "ml.mul"):
        return None if len(shapes) == 2 and shapes[0] == shapes[1] == out else "operand shapes differ"
    if n == "ml.relu":
        return None if shapes == [out] else "operand and result shapes differ"
    if n == "ml.transpose":
        return None if len(shapes) == 1 and len(out) == 2 and shapes[0] == out[::-1] else "bad shapes"
    if n == "ml.broadcast":
        return None if len(shapes) == 1 and len(shapes[0]) == 1 and len(out) == 2 \
            and shapes[0][0] == out[1] else "bad shapes"
    if n in ("ml.matmul", "ml.linear"):
        if len(shapes) < 2 or len(shapes[0]) != 2 or len(shapes[1]) != 2:
            return "operands must be rank 2"
        (m, k), (k2, nn) = shapes[0], shapes[1]
        if k != k2 or out != (m, nn):
            return "shapes do not match"
        if n == "ml.matmul" and len(shapes) != 2:
            return "ml.matmul takes 2 operands"
        if n == "ml.linear":
            if len(shapes) == 3 and shapes[2] != out:
                return "bias shape differs from the result"
            if not isinstance(op.attrs.get("relu"), bool):
                return "missing relu attribute"
        return None
    return "unknown ml operation"


def verify(module: Module) -> None:
    """Raise IRError if the module is malformed."""
    defined: set[Value] = set()
    for i, op in enumerate(module.func.ops):
        where = f"op {i} ({op.name})"
        for v in op.operands:
            if v not in defined:
                raise IRError(f"{where}: operand is not defined before its use")
        if op.name.startswith("ml."):
            err = _verify_ml(op)
        elif op.name in NPU_OPS:
            want = set(NPU_OPS[op.name])
            ok = set(op.attrs) == want and all(isinstance(op.attrs[k], int) and op.attrs[k] >= 0
                                              for k in want)
            err = None if ok and not op.operands and not op.results else "bad attributes"
        elif op.name == "npu.data":
            ok = isinstance(op.attrs.get("addr"), int) and isinstance(op.attrs.get("rstride"), int) \
                and isinstance(op.attrs.get("value"), Dense)
            err = None if ok and not op.operands and not op.results else "bad attributes"
        else:
            err = "unknown operation"
        if err:
            raise IRError(f"{where}: {err}")
        defined.update(op.results)
