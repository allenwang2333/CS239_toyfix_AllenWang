"""Instruction-level T32 simulator (spec §1, §3, §5)."""

from dataclasses import dataclass, field

from .isa import MASK32, Program, decode, format_instr


@dataclass
class RunResult:
    output: list[int]
    trap: str | None
    steps: int
    regs: list[int]
    trace: list[dict] = field(default_factory=list)


class _Trap(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def s32(value: int) -> int:
    """Signed view of a 32-bit register value."""
    return value - (1 << 32) if value >= 0x80000000 else value


def _div_trunc(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q


def run(program: Program, max_steps: int = 200000, trace_start: int = 0,
        trace_limit: int = 0) -> RunResult:
    """Run the program. Trace entries are kept for steps
    trace_start .. trace_start + trace_limit - 1."""
    code = [decode(w) for w in program.code]
    regs = [0] * 16
    mem = [0] * program.data_words
    output: list[int] = []
    trace: list[dict] = []
    pc = 0
    steps = 0
    trap = None

    def write(rd: int, value: int) -> None:
        if rd != 0:
            regs[rd] = value

    def addr_of(base: int, imm: int) -> int:
        addr = (base + imm) & MASK32
        if addr >= program.data_words:
            raise _Trap("mem_out_of_range")
        return addr

    try:
        while True:
            if not 0 <= pc < len(code):
                raise _Trap("pc_out_of_range")
            if steps >= max_steps:
                raise _Trap("step_limit")
            ins = code[pc]
            if ins is None:
                raise _Trap("illegal_instruction")
            tracing = trace_start <= steps < trace_start + trace_limit
            if tracing:
                before = list(regs)
                entry = {"step": steps, "pc": pc, "asm": format_instr(ins)}
            steps += 1
            op = ins.op
            a, b, imm = regs[ins.rs1], regs[ins.rs2], ins.imm
            next_pc = pc + 1
            if op == "add":
                write(ins.rd, (a + b) & MASK32)
            elif op == "sub":
                write(ins.rd, (a - b) & MASK32)
            elif op == "and":
                write(ins.rd, a & b)
            elif op == "or":
                write(ins.rd, a | b)
            elif op == "xor":
                write(ins.rd, a ^ b)
            elif op == "sll":
                write(ins.rd, (a << (b & 31)) & MASK32)
            elif op == "srl":
                write(ins.rd, a >> (b & 31))
            elif op == "sra":
                write(ins.rd, (s32(a) >> (b & 31)) & MASK32)
            elif op == "slt":
                write(ins.rd, int(s32(a) < s32(b)))
            elif op == "sltu":
                write(ins.rd, int(a < b))
            elif op == "mul":
                write(ins.rd, (a * b) & MASK32)
            elif op in ("div", "rem"):
                sa, sb = s32(a), s32(b)
                if sb == 0:
                    raise _Trap("div_by_zero")
                q = _div_trunc(sa, sb)
                write(ins.rd, (q if op == "div" else sa - sb * q) & MASK32)
            elif op == "addi":
                write(ins.rd, (a + imm) & MASK32)
            elif op == "andi":
                write(ins.rd, a & (imm & MASK32))
            elif op == "ori":
                write(ins.rd, a | (imm & MASK32))
            elif op == "xori":
                write(ins.rd, a ^ (imm & MASK32))
            elif op == "slti":
                write(ins.rd, int(s32(a) < imm))
            elif op == "sltiu":
                write(ins.rd, int(a < (imm & MASK32)))
            elif op == "lw":
                write(ins.rd, mem[addr_of(a, imm)])
            elif op == "sw":
                mem[addr_of(a, imm)] = b
                if tracing:
                    entry["mem"] = f"mem[{addr_of(a, imm)}]={s32(b)}"
            elif op == "jalr":
                target = (a + imm) & MASK32
                write(ins.rd, pc + 1)
                next_pc = target
            elif op == "beq":
                if a == b:
                    next_pc = pc + imm
            elif op == "bne":
                if a != b:
                    next_pc = pc + imm
            elif op == "blt":
                if s32(a) < s32(b):
                    next_pc = pc + imm
            elif op == "bge":
                if s32(a) >= s32(b):
                    next_pc = pc + imm
            elif op == "lui":
                write(ins.rd, (imm << 12) & MASK32)
            elif op == "jal":
                write(ins.rd, pc + 1)
                next_pc = pc + imm
            elif op == "out":
                output.append(s32(a))
            elif op == "halt":
                if tracing:
                    trace.append(entry)
                break
            if tracing:
                changed = [f"r{i}={s32(v)}" for i, v in enumerate(regs) if v != before[i]]
                if changed:
                    entry["regs"] = ", ".join(changed)
                trace.append(entry)
            pc = next_pc
    except _Trap as t:
        trap = t.reason
    return RunResult(output=output, trap=trap, steps=steps,
                     regs=[s32(r) for r in regs], trace=trace)
