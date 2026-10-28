"""Middle-end passes on the ml dialect (spec §9.4).

canonicalize  fold algebraic identities and splat constants, CSE, DCE
fuse          matmul + add + relu -> ml.linear
bufferize     give every value a DRAM layout (MemRefType); reuse dead buffers
"""

from .ir import PURE, CompileError, Dense, Func, MemRefType, Module, Op, TensorType, Value

COMPUTE = {"ml.add", "ml.sub", "ml.mul", "ml.relu", "ml.matmul", "ml.linear"}


# ---- canonicalize ---------------------------------------------------------------

def _splat(v: Value) -> int | None:
    op = v.owner
    if op.name == "ml.constant" and op.attrs["value"].splat:
        return op.attrs["value"].values[0]
    return None


def _wrap(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def _fold(f: Func, op: Op) -> Value | None:
    """Return a value that replaces op's result, or None."""
    n = op.name
    if n not in PURE or n == "ml.constant":
        return None
    splats = [_splat(v) for v in op.operands]

    def const(value: int) -> Value:
        shape = op.result.type.shape
        c = Op("ml.constant", [], [TensorType(shape)], {"value": Dense(shape, (_wrap(value),))})
        f.ops.insert(f.ops.index(op), c)
        return c.result

    if n in ("ml.add", "ml.sub", "ml.mul") and None not in splats:
        a, b = splats
        return const({"ml.add": a + b, "ml.sub": a - b, "ml.mul": a * b}[n])
    if n in ("ml.relu", "ml.transpose", "ml.broadcast") and splats[0] is not None:
        return const(max(splats[0], 0) if n == "ml.relu" else splats[0])
    if n == "ml.add":
        if splats[1] == 0:
            return op.operands[0]
        if splats[0] == 0:
            return op.operands[1]
    if n == "ml.sub" and splats[1] == 0:
        return op.operands[0]
    if n == "ml.mul":
        if splats[1] == 1:
            return op.operands[0]
        if splats[0] == 1:
            return op.operands[1]
        if 0 in splats:
            return const(0)
    if n in ("ml.relu", "ml.transpose") and op.operands[0].owner.name == n:
        # relu is idempotent; transpose is its own inverse.
        src = op.operands[0]
        return src if n == "ml.relu" else src.owner.operands[0]
    return None


def _cse(f: Func) -> bool:
    seen: dict[tuple, Value] = {}
    changed = False
    for op in list(f.ops):
        if op.name not in PURE:
            continue
        key = (op.name, tuple(id(v) for v in op.operands), tuple(sorted(op.attrs.items())),
               tuple(str(v.type) for v in op.results))
        if key in seen:
            f.replace_all_uses(op.result, seen[key])
            f.ops.remove(op)
            changed = True
        else:
            seen[key] = op.result
    return changed


def _dce(f: Func) -> bool:
    changed = False
    while True:
        uses = f.uses()
        dead = [op for op in f.ops if op.name in PURE and not any(uses[v] for v in op.results)]
        if not dead:
            return changed
        for op in dead:
            f.ops.remove(op)
        changed = True


def canonicalize(module: Module, machine) -> None:
    f = module.func
    changed = True
    while changed:
        changed = _cse(f)
        for op in list(f.ops):
            new = _fold(f, op)
            if new is not None:
                f.replace_all_uses(op.result, new)
                f.ops.remove(op)
                changed = True
        changed |= _dce(f)


# ---- fuse -----------------------------------------------------------------------

def fuse(module: Module, machine) -> None:
    """Fuse a matmul with the bias add and the relu that follow it, so the
    result stays in the scratchpad until it is final."""
    f = module.func
    uses = f.uses()
    for op in list(f.ops):
        if op.name != "ml.add":
            continue
        for i in (0, 1):
            mm = op.operands[i].owner
            if mm.name == "ml.matmul" and len(uses[mm.result]) == 1:
                lin = Op("ml.linear", [*mm.operands, op.operands[1 - i]], [op.result.type],
                         {"relu": False})
                f.ops[f.ops.index(op)] = lin
                f.replace_all_uses(op.result, lin.result)
                f.ops.remove(mm)
                break

    uses = f.uses()
    for op in list(f.ops):
        if op.name != "ml.relu":
            continue
        src = op.operands[0].owner
        if src.name == "ml.matmul" and len(uses[src.result]) == 1:
            lin = Op("ml.linear", src.operands, [src.result.type], {"relu": True})
            f.ops[f.ops.index(src)] = lin
            f.replace_all_uses(op.result, lin.result)
            f.ops.remove(op)
        elif src.name == "ml.linear" and not src.attrs["relu"] and len(uses[src.result]) == 1:
            src.attrs["relu"] = True
            f.replace_all_uses(op.result, src.result)
            f.ops.remove(op)


# ---- bufferize ------------------------------------------------------------------

class _Allocator:
    """First-fit allocator for DRAM words."""

    def __init__(self):
        self.blocks: list[tuple[int, int]] = []  # sorted (start, end)
        self.high = 0

    def alloc(self, size: int) -> int:
        start = 0
        for s, e in self.blocks:
            if start + size <= s:
                break
            start = max(start, e)
        self.blocks.append((start, start + size))
        self.blocks.sort()
        self.high = max(self.high, start + size)
        return start

    def free(self, start: int, size: int) -> None:
        self.blocks.remove((start, start + size))


def _round_up(n: int, align: int) -> int:
    return -(-n // align) * align


def padded_size(shape: tuple[int, ...], align: int) -> int:
    """DRAM words of a dense buffer: each row is padded to a multiple of align."""
    return _round_up(shape[-1], align) * (shape[0] if len(shape) == 2 else 1)


def _dense(shape: tuple[int, ...], base: int, align: int) -> MemRefType:
    if len(shape) == 2:
        return MemRefType(shape, base, (_round_up(shape[1], align), 1))
    return MemRefType(shape, base, (1,))


def bufferize(module: Module, machine) -> None:
    """Replace every tensor type with a DRAM layout. Constants are in DRAM
    when the program starts. broadcast and transpose are views: they change
    the strides and use no memory. A buffer is reused after its last use,
    including the uses of its views.

    Every buffer starts at a multiple of dma_align and every row is padded to
    a multiple of dma_align, so all buffer sizes are multiples of dma_align.
    With tile sides that are multiples of dma_align, every tile then starts
    at an aligned DRAM address (spec §4.4(f))."""
    f = module.func
    align = machine.dma_align
    root: dict[Value, Value] = {}
    for op in f.ops:
        for v in op.results:
            views = op.name in ("ml.broadcast", "ml.transpose")
            root[v] = root[op.operands[0]] if views else v
    last: dict[Value, int] = {}
    for i, op in enumerate(f.ops):
        for v in op.operands:
            last[root[v]] = i

    alloc = _Allocator()
    layout: dict[Value, MemRefType] = {}
    region: dict[Value, tuple[int, int]] = {}  # buffers that can be freed
    splat_words: dict[int, int] = {}
    for op in f.ops:
        if op.name != "ml.constant":
            continue
        d = op.attrs["value"]
        if d.splat:
            v = d.values[0]
            if v not in splat_words:
                splat_words[v] = alloc.alloc(align)
            layout[op.result] = MemRefType(d.shape, splat_words[v], (0,) * len(d.shape))
        else:
            size = padded_size(d.shape, align)
            base = alloc.alloc(size)
            layout[op.result] = _dense(d.shape, base, align)
            region[op.result] = (base, size)

    for i, op in enumerate(f.ops):
        if op.name == "ml.broadcast":
            base, _, _, _, cs = layout[op.operands[0]].view2d()
            layout[op.result] = MemRefType(op.result.type.shape, base, (0, cs))
        elif op.name == "ml.transpose":
            src = layout[op.operands[0]]
            layout[op.result] = MemRefType(op.result.type.shape, src.offset,
                                           (src.strides[1], src.strides[0]))
        elif op.name in COMPUTE:
            shape = op.result.type.shape
            size = padded_size(shape, align)
            base = alloc.alloc(size)
            layout[op.result] = _dense(shape, base, align)
            region[op.result] = (base, size)
        # Free dying buffers only after the result is allocated, so a result
        # never overlaps its own operands.
        for r in dict.fromkeys(root[v] for v in op.operands):
            if last[r] == i and r in region:
                alloc.free(*region.pop(r))

    for v, t in layout.items():
        v.type = t
    module.attrs["npu.data_words"] = alloc.high
    if alloc.high > machine.dram_words:
        raise CompileError(f"program needs {alloc.high} DRAM words, "
                           f"{machine.name} has {machine.dram_words}")
