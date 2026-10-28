"""Checks that a program is valid for a hardware profile (spec §4.4, §4.5)."""

from .isa import Program, decode, regs_used
from .machine import Machine

LUI_MAX = (1 << 20) - 1


def _fits(value: int, bits: int) -> bool:
    lo = -(1 << (bits - 1))
    hi = (1 << (bits - 1)) - 1
    return lo <= value <= hi


def validate(program: Program, machine: Machine) -> list[str]:
    """Return a list of violations. An empty list means the program is valid."""
    errors: list[str] = []
    size = len(program.code)
    for pc, word in enumerate(program.code):
        ins = decode(word)
        if ins is None:
            errors.append(f"pc {pc}: undefined opcode {word >> 26:#x}")
            continue
        for r in regs_used(ins):
            if r >= machine.num_regs:
                errors.append(f"pc {pc}: register r{r} does not exist on {machine.name}")
        fmt = ins.fmt
        if fmt in ("I", "S") and not _fits(ins.imm, machine.imm_bits):
            errors.append(f"pc {pc}: immediate {ins.imm} does not fit imm_bits={machine.imm_bits}")
        if fmt == "B":
            if not _fits(ins.imm, machine.branch_bits):
                errors.append(f"pc {pc}: branch offset {ins.imm} does not fit "
                              f"branch_bits={machine.branch_bits}")
            if not 0 <= pc + ins.imm < size:
                errors.append(f"pc {pc}: branch target {pc + ins.imm} is outside the program")
        if fmt == "J":
            if not _fits(ins.imm, machine.jump_bits):
                errors.append(f"pc {pc}: jump offset {ins.imm} does not fit "
                              f"jump_bits={machine.jump_bits}")
            if not 0 <= pc + ins.imm < size:
                errors.append(f"pc {pc}: jump target {pc + ins.imm} is outside the program")
        if fmt == "U" and not 0 <= ins.imm <= LUI_MAX:
            errors.append(f"pc {pc}: lui immediate {ins.imm} is larger than 20 bits")
        if ins.op == "mul" and not machine.has_mul:
            errors.append(f"pc {pc}: mul is not available on {machine.name}")
    if program.data_words > machine.mem_words:
        errors.append(f"data_words={program.data_words} is larger than "
                      f"mem_words={machine.mem_words}")
    return errors
