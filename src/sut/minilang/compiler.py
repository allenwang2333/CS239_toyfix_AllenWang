"""MiniLang compiler driver: frontend -> ml IR -> passes -> npu IR -> assembly (spec §9).

Pipeline (each stage is verified, and can be printed with `cli.py ir`):

  frontend      the walker in parser.py builds ml ops
  canonicalize  passes.canonicalize
  fuse          passes.fuse
  bufferize     passes.bufferize
  lower-npu     lower_to_npu (tiling) below

With mm_shape = (M, K, N), the scratchpad holds four slots during a tile
computation: A (M*K words) at 0, B (K*N) after A, the accumulator C (M*N)
after B, and D (M*N) after C. Elementwise operations use C and D.
"""

from npu.machine import NpuMachine

from .ir import NPU_OPS, CompileError, Dense, Func, MemRefType, Module, Op, TensorType, print_module, verify
from .parser import Domain, ParseError, Tensor, parse, run
from .passes import bufferize, canonicalize, fuse

__all__ = ["CompileError", "STAGES", "build_ir", "compile_ir", "compile_source", "emit_asm"]



# ---- frontend: build ml IR ------------------------------------------------------

class _Builder(Domain):
    def __init__(self):
        self.func = Func("main")

    def _op(self, name: str, operands: list[Tensor], shape, attrs=None):
        op = Op(name, [x.handle for x in operands], [TensorType(tuple(shape))], attrs)
        self.func.ops.append(op)
        return op.result

    def constant(self, type, values):
        if len(set(values)) == 1:
            values = values[:1]
        return self._op("ml.constant", [], type.shape, {"value": Dense(type.shape, tuple(values))})

    def broadcast(self, x, type):
        return self._op("ml.broadcast", [x], type.shape)

    def binary(self, op, a, b, type):
        return self._op(f"ml.{op}", [a, b], type.shape)

    def matmul(self, a, b, type):
        return self._op("ml.matmul", [a, b], type.shape)

    def relu(self, x, type):
        return self._op("ml.relu", [x], type.shape)

    def transpose(self, x, type):
        return self._op("ml.transpose", [x], type.shape)

    def print(self, x):
        self.func.ops.append(Op("ml.print", [x.handle]))


def build_ir(source: str) -> Module:
    try:
        program = parse(source)
    except ParseError as e:
        raise CompileError(f"invalid program: {e}") from None
    b = _Builder()
    run(program, b)
    module = Module(b.func)
    verify(module)
    return module


# ---- lower-npu: tiling ----------------------------------------------------------

def _tiles(n: int, t: int) -> list[tuple[int, int]]:
    """(start, size) of each tile along a dimension of size n."""
    return [(i, min(t, n - i)) for i in range(0, n, t)]


def lower_to_npu(module: Module, machine: NpuMachine) -> None:
    M, K, N = machine.mm_shape
    A, B = 0, M * K
    C = B + K * N
    D = C + M * N
    limit = 1 << machine.stride_bits
    data: list[Op] = []
    code: list[Op] = []
    splat_addrs: set[int] = set()

    def emit(name: str, **attrs) -> None:
        code.append(Op(f"npu.{name}", attrs=attrs))

    def vector(name: str, dst: int, a: int, b: int | None, n: int) -> None:
        """A vector operation of n words, split into pieces of at most vlen."""
        for off in range(0, n, machine.vlen):
            size = min(machine.vlen, n - off)
            if b is None:
                emit(name, dst=dst + off, a=a + off, len=size)
            else:
                emit(name, dst=dst + off, a=a + off, b=b + off, len=size)

    def load(slot: int, t: MemRefType, r0: int, c0: int, rows: int, cols: int) -> None:
        base, _, _, rs, cs = t.view2d()
        origin = base + r0 * rs + c0 * cs
        rs = rs if rows > 1 else 0
        if rs < limit:
            emit("load", spad=slot, dram=origin, rows=rows, cols=cols, rstride=rs, cstride=cs)
            return
        # The row stride does not fit stride_bits: one load per row.
        for r in range(rows):
            emit("load", spad=slot + r * cols, dram=origin + r * rs, rows=1, cols=cols,
                 rstride=0, cstride=cs)

    def store(slot: int, t: MemRefType, r0: int, c0: int, rows: int, cols: int) -> None:
        base, _, _, rs, _ = t.view2d()  # results are dense: cstride is 1
        origin = base + r0 * rs + c0
        rs = rs if rows > 1 else 0
        if rs < limit:
            emit("store", dram=origin, spad=slot, rows=rows, cols=cols, rstride=rs)
            return
        for r in range(rows):
            emit("store", dram=origin + r * rs, spad=slot + r * cols, rows=1, cols=cols,
                 rstride=0)

    for op in module.func.ops:
        n = op.name
        if n == "ml.constant":
            t, d = op.result.type, op.attrs["value"]
            if not d.splat:
                rstride = t.strides[0] if len(t.shape) == 2 else 0
                data.append(Op("npu.data", attrs={"addr": t.offset, "rstride": rstride, "value": d}))
            elif t.offset not in splat_addrs:
                splat_addrs.add(t.offset)
                data.append(Op("npu.data", attrs={"addr": t.offset, "rstride": 0,
                                                  "value": Dense((1,), d.values)}))
        elif n in ("ml.broadcast", "ml.transpose"):
            pass  # views: bufferize already folded them into the strides
        elif n == "ml.print":
            base, rows, cols, rs, cs = op.operands[0].type.view2d()
            emit("out", dram=base, rows=rows, cols=cols, rstride=rs, cstride=cs)
        elif n in ("ml.add", "ml.sub", "ml.mul", "ml.relu"):
            out = op.result.type
            _, rows, cols, _, _ = out.view2d()
            for r0, tr in _tiles(rows, M):
                for c0, tc in _tiles(cols, N):
                    load(C, op.operands[0].type, r0, c0, tr, tc)
                    if n == "ml.relu":
                        vector("vrelu", C, C, None, tr * tc)
                    else:
                        load(D, op.operands[1].type, r0, c0, tr, tc)
                        vector("v" + n[3:], C, C, D, tr * tc)
                    store(C, out, r0, c0, tr, tc)
        elif n in ("ml.matmul", "ml.linear"):
            a, b = op.operands[0].type, op.operands[1].type
            bias = op.operands[2].type if len(op.operands) == 3 else None
            relu = op.attrs.get("relu", False)
            out = op.result.type
            (m, k), nn = a.shape, b.shape[1]
            for i, tm in _tiles(m, M):
                for j, tn in _tiles(nn, N):
                    if bias is not None:
                        load(C, bias, i, j, tm, tn)
                    for step, (kk, tk) in enumerate(_tiles(k, K)):
                        load(A, a, i, kk, tm, tk)
                        load(B, b, kk, j, tk, tn)
                        # The first product overwrites C unless C holds the bias.
                        if bias is None and step == 0:
                            emit("mm", dst=C, a=A, b=B, m=tm, k=tk, n=tn)
                        elif machine.has_mma:
                            emit("mma", dst=C, a=A, b=B, m=tm, k=tk, n=tn)
                        else:
                            emit("mm", dst=D, a=A, b=B, m=tm, k=tk, n=tn)
                            vector("vadd", C, C, D, tm * tn)
                    if relu:
                        vector("vrelu", C, C, None, tm * tn)
                    store(C, out, i, j, tm, tn)
        else:
            raise CompileError(f"lower-npu: cannot lower {n}")
    module.func.ops = data + code


# ---- driver ---------------------------------------------------------------------

PIPELINE = [("canonicalize", canonicalize), ("fuse", fuse), ("bufferize", bufferize),
            ("lower-npu", lower_to_npu)]
STAGES = ["frontend"] + [name for name, _ in PIPELINE]


def _check_machine(machine: NpuMachine) -> None:
    """The profile guarantees of spec §4.6 that the compiler relies on."""
    M, K, N = machine.mm_shape
    if machine.spad_words < M * K + K * N + 2 * M * N:
        raise CompileError("the compiler needs spad_words >= M*K + K*N + 2*M*N")
    if any(d % machine.dma_align for d in machine.mm_shape):
        raise CompileError("the compiler needs mm_shape sides that are multiples of dma_align")


def compile_ir(source: str, machine: NpuMachine, dump=None) -> Module:
    """Run the pipeline. dump(stage, module), if given, is called after each stage."""
    _check_machine(machine)
    module = build_ir(source)
    if dump:
        dump("frontend", module)
    for name, fn in PIPELINE:
        fn(module, machine)
        verify(module)
        if dump:
            dump(name, module)
    return module


def emit_asm(module: Module, machine: NpuMachine) -> str:
    out = [f"; compiled for {machine.name}", f".data {module.attrs['npu.data_words']}"]
    for op in module.func.ops:
        if op.name == "npu.data":
            d = op.attrs["value"]
            values = d.expanded()
            cols = d.shape[-1] if len(d.shape) == 2 else len(values)
            for r in range(0, len(values) // cols):
                row = values[r * cols:(r + 1) * cols]
                addr = op.attrs["addr"] + r * op.attrs["rstride"]
                for i in range(0, cols, 16):
                    out.append(f".word {addr + i}, " + ", ".join(map(str, row[i:i + 16])))
        else:
            args = ", ".join(str(op.attrs[k]) for k in NPU_OPS[op.name])
            out.append(f"  {op.name[4:]} {args}")
    return "\n".join(out) + "\n"


def compile_source(source: str, machine: NpuMachine) -> str:
    """Compile MiniLang source to NPU assembly. Raises CompileError."""
    return emit_asm(compile_ir(source, machine), machine)


def compile_stages(source: str, machine: NpuMachine, elide: int | None = 16) -> dict[str, str]:
    """The printed IR after every stage, and the assembly."""
    stages: dict[str, str] = {}
    module = compile_ir(source, machine, lambda s, m: stages.__setitem__(s, print_module(m, elide)))
    stages["asm"] = emit_asm(module, machine)
    return stages
