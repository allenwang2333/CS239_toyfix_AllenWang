"""NPU simulator (spec §1 - §3, §5)."""

from dataclasses import dataclass, field

from .isa import Program, format_instr, s32
from .machine import NpuMachine


@dataclass
class RunResult:
    output: list[str]
    trap: str | None
    steps: int
    dma_words: int = 0
    macs: int = 0
    trace: list[dict] = field(default_factory=list)


class _Trap(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def run(program: Program, machine: NpuMachine, max_steps: int = 200000, trace_start: int = 0,
        trace_limit: int = 0) -> RunResult:
    """Run the program. Trace entries are kept for steps
    trace_start .. trace_start + trace_limit - 1."""
    dram = [0] * program.data_words
    spad = [0] * machine.spad_words
    for addr, values in program.init:
        for i, v in enumerate(values):
            if addr + i < len(dram):
                dram[addr + i] = v
    output: list[str] = []
    trace: list[dict] = []
    res = RunResult(output=output, trap=None, steps=0, trace=trace)

    def sp(addr: int) -> int:
        if not 0 <= addr < len(spad):
            raise _Trap("spad_out_of_range")
        return addr

    def dr(addr: int) -> int:
        if not 0 <= addr < len(dram):
            raise _Trap("dram_out_of_range")
        return addr

    def read(base: int, n: int) -> list[int]:
        return [spad[sp(base + i)] for i in range(n)]

    def write(base: int, values: list[int]) -> None:
        for i, v in enumerate(values):
            spad[sp(base + i)] = s32(v)

    try:
        for pc, ins in enumerate(program.code):
            if res.steps >= max_steps:
                raise _Trap("step_limit")
            tracing = trace_start <= res.steps < trace_start + trace_limit
            res.steps += 1
            op, g = ins.op, ins.get
            written = None
            if op == "load":
                rows, cols, rs, cs = g("rows"), g("cols"), g("rstride"), g("cstride")
                vals = [dram[dr(g("dram") + r * rs + c * cs)] for r in range(rows) for c in range(cols)]
                write(g("spad"), vals)
                res.dma_words += rows * cols
                written = ("spad", g("spad"), vals)
            elif op == "store":
                rows, cols, rs = g("rows"), g("cols"), g("rstride")
                vals = read(g("spad"), rows * cols)
                for r in range(rows):
                    for c in range(cols):
                        dram[dr(g("dram") + r * rs + c)] = vals[r * cols + c]
                res.dma_words += rows * cols
                written = ("dram", g("dram"), vals)
            elif op in ("mm", "mma"):
                m, k, n = g("m"), g("k"), g("n")
                a, b = read(g("a"), m * k), read(g("b"), k * n)
                acc = read(g("dst"), m * n) if op == "mma" else [0] * (m * n)
                vals = [acc[i * n + j] + sum(a[i * k + t] * b[t * n + j] for t in range(k))
                        for i in range(m) for j in range(n)]
                write(g("dst"), vals)
                res.macs += m * k * n
                written = ("spad", g("dst"), [s32(v) for v in vals])
            elif op in ("vadd", "vsub", "vmul"):
                n = g("len")
                a, b = read(g("a"), n), read(g("b"), n)
                if op == "vadd":
                    vals = [x + y for x, y in zip(a, b)]
                elif op == "vsub":
                    vals = [x - y for x, y in zip(a, b)]
                else:
                    vals = [x * y for x, y in zip(a, b)]
                write(g("dst"), vals)
                written = ("spad", g("dst"), [s32(v) for v in vals])
            elif op == "vrelu":
                vals = [max(x, 0) for x in read(g("a"), g("len"))]
                write(g("dst"), vals)
                written = ("spad", g("dst"), vals)
            elif op == "out":
                rows, cols, rs, cs = g("rows"), g("cols"), g("rstride"), g("cstride")
                for r in range(rows):
                    output.append(" ".join(str(dram[dr(g("dram") + r * rs + c * cs)])
                                           for c in range(cols)))
            if tracing:
                entry = {"step": res.steps - 1, "pc": pc, "asm": format_instr(ins)}
                if written:
                    where, base, vals = written
                    shown = " ".join(str(v) for v in vals[:8]) + (" ..." if len(vals) > 8 else "")
                    entry["mem"] = f"{where}[{base}..{base + len(vals) - 1}] = {shown}"
                trace.append(entry)
    except _Trap as t:
        res.trap = t.reason
    return res
