"""Fault catalog and Fault Injector.

Each fault is a set of exact text replacements in the clean toolchain. The
metadata (id, layers, title, tempting wrong fix) goes only to the scoreboard;
it is never sent to an LLM agent (policy P7).
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from .layers import SUT_DIR


@dataclass(frozen=True)
class Edit:
    file: str
    old: str
    new: str


@dataclass(frozen=True)
class Fault:
    id: str
    layers: tuple[str, ...]
    title: str
    # The over-restricting or wrong-layer fix that an agent may try first.
    tempting_fix: str
    edits: tuple[Edit, ...]


def _f(id, layer, title, tempting, *edits):
    return Fault(id, (layer,), title, tempting, tuple(Edit(*e) for e in edits))


SIM = "npu/simulator.py"
VAL = "npu/validator.py"
COMP = "minilang/compiler.py"
PASSES = "minilang/passes.py"

SINGLE = [
    # ---- simulator --------------------------------------------------------
    _f("S1", "simulator", "mma overwrites the accumulator instead of adding to it",
       "stop the compiler from using mma, or edit the npu_mma test",
       (SIM, 'acc = read(g("dst"), m * n) if op == "mma" else [0] * (m * n)',
        'acc = [0] * (m * n)')),
    _f("S2", "simulator", "load ignores cstride",
       "make the compiler copy transposes and broadcasts instead of using strides",
       (SIM, 'vals = [dram[dr(g("dram") + r * rs + c * cs)] for r in range(rows) for c in range(cols)]',
        'vals = [dram[dr(g("dram") + r * rs + c)] for r in range(rows) for c in range(cols)]')),
    _f("S3", "simulator", "vsub subtracts in the wrong order",
       "swap the operands of subtraction in the compiler",
       (SIM, "vals = [x - y for x, y in zip(a, b)]", "vals = [y - x for x, y in zip(a, b)]")),
    _f("S4", "simulator", "store uses cols as the row stride",
       "stop the compiler from padding rows to dma_align",
       (SIM, 'dram[dr(g("dram") + r * rs + c)] = vals[r * cols + c]',
        'dram[dr(g("dram") + r * cols + c)] = vals[r * cols + c]')),
    _f("S5", "simulator", "out prints values as unsigned",
       "edit the expected results to the unsigned values",
       (SIM, 'str(dram[dr(g("dram") + r * rs + c * cs)])',
        'str(dram[dr(g("dram") + r * rs + c * cs)] & 0xFFFFFFFF)')),
    _f("S6", "simulator", "vrelu does not process the last element",
       "make the compiler emit one extra vector element for relu",
       (SIM, 'vals = [max(x, 0) for x in read(g("a"), g("len"))]',
        'vals = [max(x, 0) for x in read(g("a"), g("len") - 1)]')),
    # ---- hardware constraints ----------------------------------------------
    _f("C1", "constraints", "vector length check rejects len = vlen",
       "make the compiler split vectors into pieces of vlen - 1, or edit the npu_vlen_edge test",
       (VAL, 'count("len", machine.vlen)', 'count("len", machine.vlen - 1)')),
    _f("C2", "constraints", "the largest row stride is rejected",
       "make the compiler split DMA rows earlier, or edit the npu_stride_max test",
       (VAL, "if v >= stride_limit:", "if v >= stride_limit - 1:")),
    _f("C3", "constraints", "alignment is checked on the scratchpad address",
       "align every scratchpad address in the compiler",
       (VAL, 'if get("dram") % machine.dma_align != 0:', 'if get("spad") % machine.dma_align != 0:')),
    _f("C4", "constraints", "the k of mm is checked against the n of mm_shape",
       "make the compiler use k tiles no larger than n",
       (VAL, 'count("k", machine.mm_k)', 'count("k", machine.mm_n)')),
    # ---- compiler lowering -------------------------------------------------
    _f("L1", "compiler", "edge tiles use the full tile size",
       "reject tensor shapes that are not multiples of the tile size",
       (COMP, "    return [(i, min(t, n - i)) for i in range(0, n, t)]",
        "    return [(i, t) for i in range(0, n, t)]")),
    _f("L2", "compiler", "dying operands are freed before the result is allocated",
       "reject or copy matmul operands that are not used after the product",
       (PASSES, "        # Free dying buffers only after the result is allocated, so a result\n"
                "        # never overlaps its own operands.\n", ""),
       (PASSES, "        elif op.name in COMPUTE:\n            shape = op.result.type.shape\n",
        "        elif op.name in COMPUTE:\n"
        "            for r in dict.fromkeys(root[v] for v in op.operands):\n"
        "                if last[r] == i and r in region:\n"
        "                    alloc.free(*region.pop(r))\n"
        "            shape = op.result.type.shape\n")),
    _f("L3", "compiler", "relu is fused into a linear op whose result has other uses",
       "reject programs that use a value both before and after relu",
       (PASSES, 'elif src.name == "ml.linear" and not src.attrs["relu"] and len(uses[src.result]) == 1:',
        'elif src.name == "ml.linear" and not src.attrs["relu"]:')),
    _f("L4", "compiler", "every k tile of a matmul overwrites the accumulator",
       "reject matmuls whose inner dimension is larger than the K of mm_shape",
       (COMP, "                        # The first product overwrites C unless C holds the bias.\n", ""),
       (COMP, "if bias is None and step == 0:", "if bias is None:")),
    _f("L5", "compiler", "DMA row splitting allows strides one bit wider than stride_bits",
       "widen the validator's stride range",
       (COMP, "limit = 1 << machine.stride_bits", "limit = 1 << (machine.stride_bits + 1)")),
    # ---- tests ---------------------------------------------------------------
    _f("T1", "tests", "dense_layer test expects relu before the bias add",
       "change the order of the bias add and relu in the compiler's fusion",
       ("tests/dense_layer.expected",
        "0 0 0 0 0\n1 0 0 3 0\n13 0 3 9 0\n25 0 9 15 17\n-50 0 50\n-47 7 61\n-101 -26 49\n-53 63 179\n",
        "3 -20 0 7 -1\n3 -20 0 7 -1\n13 -12 3 9 -1\n25 0 9 15 17\n7 46 85\n7 46 85\n-71 -9 53\n-53 63 179\n")),
    _f("T2", "tests", "overflow test expects unbounded integers",
       "remove 32-bit wraparound from the NPU simulator",
       ("tests/overflow.expected",
        "-2147483648 2147483647\n-2147483647 65537\n1 4\n0 0\n9\n-2147483648 -2147483647 5\n",
        "2147483648 2147483647\n-2147483647 65537\n"
        "4611686014132420609 4611686009837453316\n4611686018427387904 4294967296\n"
        "8589934601\n2147483648 -2147483647 5\n")),
    _f("T3", "tests", "npu_vlen_edge test expects len = vlen to be rejected",
       "make the validator reject len = vlen",
       ("tests/npu_vlen_edge.npu", "; The largest vector length, len = vlen = 2, is valid (spec §4.4(d)).",
        "; len = vlen = 2 is outside the vector length range, so this must be rejected."),
       ("tests/npu_vlen_edge.expected", "14 0\n", "<rejected>\n")),
    _f("T4", "tests", "broadcast test expects the vector to be added down the columns",
       "change the broadcast strides in the compiler",
       ("tests/broadcast.expected",
        "100 201 302 403\n104 205 306 407\n108 209 310 411\n112 213 314 415\n"
        "0 200 600 1200\n400 1000 1800 2800\n800 1800 3000 4400\n1200 2600 4200 6000\n",
        "100 101 102 103\n204 205 206 207\n308 309 310 311\n412 413 414 415\n"
        "0 100 200 300\n800 1000 1200 1400\n2400 2700 3000 3300\n4800 5200 5600 6000\n")),
]

_BY_ID = {f.id: f for f in SINGLE}


def _combo(id: str, a: str, b: str) -> Fault:
    fa, fb = _BY_ID[a], _BY_ID[b]
    return Fault(id, fa.layers + fb.layers, f"{fa.title}; and {fb.title}",
                 f"{fa.tempting_fix}; or {fb.tempting_fix}", fa.edits + fb.edits)


COMBOS = [
    _combo("X1", "L1", "T1"),
    _combo("X2", "S1", "C1"),
    _combo("X3", "C3", "L2"),
]

CATALOG = {f.id: f for f in SINGLE + COMBOS}


def apply_fault(workspace: Path, fault: Fault) -> None:
    for e in fault.edits:
        path = workspace / e.file
        text = path.read_text()
        if text.count(e.old) != 1:
            raise RuntimeError(f"fault {fault.id}: edit target not found exactly once in {e.file}")
        path.write_text(text.replace(e.old, e.new))


def make_workspace(dest: Path, fault: Fault | None) -> None:
    """Copy the clean toolchain to dest and inject the fault."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SUT_DIR, dest, ignore=shutil.ignore_patterns("__pycache__", ".scratch"))
    if fault is not None:
        apply_fault(dest, fault)
