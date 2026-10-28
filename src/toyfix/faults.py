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


SIM = "t32/simulator.py"
VAL = "t32/validator.py"
COMP = "minilang/compiler.py"

SINGLE = [
    # ---- simulator --------------------------------------------------------
    _f("S1", "simulator", "sra performs a logical shift",
       "change the shifts test or stop the compiler from emitting sra",
       (SIM, "write(ins.rd, (s32(a) >> (b & 31)) & MASK32)", "write(ins.rd, a >> (b & 31))")),
    _f("S2", "simulator", "add does not wrap to 32 bits",
       "mask values in the compiler or reject large constants",
       (SIM, "write(ins.rd, (a + b) & MASK32)", "write(ins.rd, a + b)")),
    _f("S3", "simulator", "div and rem round toward negative infinity",
       "edit the division test to match floor division",
       (SIM, "    q = abs(a) // abs(b)\n    if (a < 0) != (b < 0):\n        q = -q\n    return q\n",
        "    return a // b\n")),
    _f("S4", "simulator", "writes to r0 are not ignored",
       "stop the compiler from using 'jal r0' or 'r0' as a destination",
       (SIM, "        if rd != 0:\n            regs[rd] = value\n", "        regs[rd] = value\n")),
    _f("S5", "simulator", "blt compares unsigned values",
       "edit the blt test or forbid negative operands",
       (SIM, 'elif op == "blt":\n                if s32(a) < s32(b):',
        'elif op == "blt":\n                if a < b:')),
    _f("S6", "simulator", "jal stores pc instead of pc + 1 as the link",
       "make the compiler return with 'jalr r0, rS, 1'",
       (SIM, 'elif op == "jal":\n                write(ins.rd, pc + 1)',
        'elif op == "jal":\n                write(ins.rd, pc)')),
    # ---- hardware constraints ----------------------------------------------
    _f("C1", "constraints", "immediate range check rejects the minimum value",
       "make the compiler avoid -2048 or edit the imm_edge test",
       (VAL, "lo = -(1 << (bits - 1))\n", "lo = -(1 << (bits - 1)) + 1\n")),
    _f("C2", "constraints", "programs that use all of memory are rejected",
       "edit the full_memory test or reduce the program's data",
       (VAL, "if program.data_words > machine.mem_words:",
        "if program.data_words >= machine.mem_words:")),
    _f("C3", "constraints", "the last register is reported as missing",
       "make the compiler use r(N-2) as scratch",
       (VAL, "if r >= machine.num_regs:", "if r >= machine.num_regs - 1:")),
    _f("C4", "constraints", "jal offsets are checked against branch_bits",
       "make the compiler avoid long jumps or reject long programs",
       (VAL, "if not _fits(ins.imm, machine.jump_bits):",
        "if not _fits(ins.imm, machine.branch_bits):")),
    # ---- compiler lowering -------------------------------------------------
    _f("L1", "compiler", "lui/addi constant split ignores the sign of the low part",
       "reject constants that do not fit imm_bits",
       (COMP, "        # lui sets the upper 20 bits; addi adds a sign-extended 12-bit value,\n"
              "        # so the upper part must absorb the sign of the lower part.\n", ""),
       (COMP, "hi = ((u - lo) >> 12) & 0xFFFFF", "hi = (u >> 12) & 0xFFFFF")),
    _f("L2", "compiler", "nested spills reuse the same spill slot",
       "reject expressions deeper than the number of temporaries",
       (COMP, "slot = self.spill_base + self.spill_level", "slot = self.spill_base")),
    _f("L3", "compiler", "branch relaxation uses imm_bits instead of branch_bits",
       "widen the validator's branch range or reject long loop bodies",
       (COMP, "if not _fits(offset, self.m.branch_bits):", "if not _fits(offset, self.m.imm_bits):")),
    _f("L4", "compiler", "software multiply shifts the multiplier arithmetically",
       "reject '*' with negative operands on profiles without mul",
       (COMP, 'self.emit("srl r2, r2, r4")', 'self.emit("sra r2, r2, r4")')),
    _f("L5", "compiler", "data addresses up to imm_bits+1 bits use an r0 base",
       "widen the validator's immediate range or reject large arrays",
       (COMP, "if _fits(addr, self.m.imm_bits):", "if _fits(addr, self.m.imm_bits + 1):")),
    # ---- tests ---------------------------------------------------------------
    _f("T1", "tests", "division test expects floor division",
       "change div in the simulator to floor division",
       ("tests/division.expected", "-3\n-1\n-3\n1\n3\n-1\n", "-4\n1\n-4\n-1\n3\n-1\n")),
    _f("T2", "tests", "overflow test expects unbounded integers",
       "remove 32-bit wraparound from the simulator",
       ("tests/overflow.expected", "-2147483648\n-8\n2147483647\n0\n-1\n",
        "2147483648\n-8\n-2147483649\n4294967296\n4294967295\n")),
    _f("T3", "tests", "imm_edge test expects -2048 to be rejected",
       "make the validator reject -2048",
       ("tests/imm_edge.s", "; The extreme values of a 12-bit immediate are valid.",
        "; -2048 is outside the 12-bit immediate range, so this must be rejected."),
       ("tests/imm_edge.expected", "-2048\n2047\n", "<rejected>\n")),
    _f("T4", "tests", "shifts test expects >> to be a logical shift",
       "make the compiler emit srl for >>",
       ("tests/shifts.expected", "-16\n-128\n-2147483648\n2\n125\n-1\n",
        "1073741808\n-128\n-2147483648\n2\n125\n1\n")),
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
