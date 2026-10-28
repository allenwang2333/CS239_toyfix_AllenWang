"""NPU instruction table and program representation (spec §2, §3)."""

from dataclasses import dataclass, field

MASK32 = 0xFFFFFFFF

# Mnemonic -> operand names, in assembly order.
OPS: dict[str, tuple[str, ...]] = {
    "load": ("spad", "dram", "rows", "cols", "rstride", "cstride"),
    "store": ("dram", "spad", "rows", "cols", "rstride"),
    "mm": ("dst", "a", "b", "m", "k", "n"),
    "mma": ("dst", "a", "b", "m", "k", "n"),
    "vadd": ("dst", "a", "b", "len"),
    "vsub": ("dst", "a", "b", "len"),
    "vmul": ("dst", "a", "b", "len"),
    "vrelu": ("dst", "a", "len"),
    "out": ("dram", "rows", "cols", "rstride", "cstride"),
}


def s32(value: int) -> int:
    """Reduce an integer modulo 2^32 to its signed 32-bit value."""
    value &= MASK32
    return value - (1 << 32) if value & 0x80000000 else value


@dataclass(frozen=True)
class Instr:
    op: str
    args: tuple[int, ...]

    def get(self, name: str) -> int:
        return self.args[OPS[self.op].index(name)]


@dataclass
class Program:
    code: list[Instr]
    data_words: int = 0
    # Initial DRAM contents: (address, values) for each .word directive.
    init: list[tuple[int, list[int]]] = field(default_factory=list)


def format_instr(ins: Instr) -> str:
    return f"{ins.op} " + ", ".join(str(a) for a in ins.args)
