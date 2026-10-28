"""T32 instruction table and binary encoding (spec §2, §3)."""

from dataclasses import dataclass, field

MASK32 = 0xFFFFFFFF


@dataclass(frozen=True)
class OpInfo:
    name: str
    opcode: int
    fmt: str


_TABLE = [
    ("add", 0x01, "R"), ("sub", 0x02, "R"), ("and", 0x03, "R"),
    ("or", 0x04, "R"), ("xor", 0x05, "R"), ("sll", 0x06, "R"),
    ("srl", 0x07, "R"), ("sra", 0x08, "R"), ("slt", 0x09, "R"),
    ("sltu", 0x0A, "R"), ("mul", 0x0B, "R"), ("div", 0x0C, "R"),
    ("rem", 0x0D, "R"),
    ("addi", 0x10, "I"), ("andi", 0x11, "I"), ("ori", 0x12, "I"),
    ("xori", 0x13, "I"), ("slti", 0x14, "I"), ("sltiu", 0x15, "I"),
    ("lw", 0x16, "I"), ("jalr", 0x17, "I"),
    ("sw", 0x18, "S"),
    ("beq", 0x20, "B"), ("bne", 0x21, "B"), ("blt", 0x22, "B"),
    ("bge", 0x23, "B"),
    ("lui", 0x28, "U"),
    ("jal", 0x30, "J"),
    ("out", 0x3E, "O"),
    ("halt", 0x3F, "N"),
]

OPS = {name: OpInfo(name, code, fmt) for name, code, fmt in _TABLE}
BY_OPCODE = {info.opcode: info for info in OPS.values()}

# Width of the immediate or offset field in the encoding, per format.
FIELD_BITS = {"I": 18, "S": 18, "B": 18, "U": 22, "J": 22}
UNSIGNED_FIELDS = {"U"}


@dataclass(frozen=True)
class Instr:
    op: str
    rd: int = 0
    rs1: int = 0
    rs2: int = 0
    imm: int = 0

    @property
    def fmt(self) -> str:
        return OPS[self.op].fmt


@dataclass
class Program:
    code: list[int]
    data_words: int = 0
    # Assembly text of each instruction, used for traces only.
    lines: list[str] = field(default_factory=list)


def to_signed(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def field_fits(value: int, fmt: str) -> bool:
    bits = FIELD_BITS[fmt]
    if fmt in UNSIGNED_FIELDS:
        return 0 <= value < (1 << bits)
    return -(1 << (bits - 1)) <= value < (1 << (bits - 1))


def encode(ins: Instr) -> int:
    info = OPS[ins.op]
    word = info.opcode << 26
    fmt = info.fmt
    if fmt == "R":
        word |= ins.rd << 22 | ins.rs1 << 18 | ins.rs2 << 14
    elif fmt == "I":
        word |= ins.rd << 22 | ins.rs1 << 18 | (ins.imm & 0x3FFFF)
    elif fmt == "S":
        word |= ins.rs2 << 22 | ins.rs1 << 18 | (ins.imm & 0x3FFFF)
    elif fmt == "B":
        word |= ins.rs1 << 22 | ins.rs2 << 18 | (ins.imm & 0x3FFFF)
    elif fmt in ("U", "J"):
        word |= ins.rd << 22 | (ins.imm & 0x3FFFFF)
    elif fmt == "O":
        word |= ins.rs1 << 18
    return word


def decode(word: int) -> Instr | None:
    """Return the instruction, or None if the opcode is undefined."""
    info = BY_OPCODE.get((word >> 26) & 0x3F)
    if info is None:
        return None
    a = (word >> 22) & 0xF
    b = (word >> 18) & 0xF
    c = (word >> 14) & 0xF
    fmt = info.fmt
    if fmt == "R":
        return Instr(info.name, rd=a, rs1=b, rs2=c)
    if fmt == "I":
        return Instr(info.name, rd=a, rs1=b, imm=to_signed(word, 18))
    if fmt == "S":
        return Instr(info.name, rs2=a, rs1=b, imm=to_signed(word, 18))
    if fmt == "B":
        return Instr(info.name, rs1=a, rs2=b, imm=to_signed(word, 18))
    if fmt == "U":
        return Instr(info.name, rd=a, imm=word & 0x3FFFFF)
    if fmt == "J":
        return Instr(info.name, rd=a, imm=to_signed(word, 22))
    if fmt == "O":
        return Instr(info.name, rs1=b)
    return Instr(info.name)


def regs_used(ins: Instr) -> list[int]:
    """Register fields that the instruction reads or writes."""
    fmt = ins.fmt
    if fmt == "R":
        return [ins.rd, ins.rs1, ins.rs2]
    if fmt == "I":
        return [ins.rd, ins.rs1]
    if fmt in ("S", "B"):
        return [ins.rs1, ins.rs2]
    if fmt in ("U", "J"):
        return [ins.rd]
    if fmt == "O":
        return [ins.rs1]
    return []


def format_instr(ins: Instr | None) -> str:
    if ins is None:
        return "<undefined>"
    fmt, op = ins.fmt, ins.op
    if fmt == "R":
        return f"{op} r{ins.rd}, r{ins.rs1}, r{ins.rs2}"
    if op == "lw":
        return f"lw r{ins.rd}, {ins.imm}(r{ins.rs1})"
    if fmt == "I":
        return f"{op} r{ins.rd}, r{ins.rs1}, {ins.imm}"
    if fmt == "S":
        return f"sw r{ins.rs2}, {ins.imm}(r{ins.rs1})"
    if fmt == "B":
        return f"{op} r{ins.rs1}, r{ins.rs2}, {ins.imm:+d}"
    if fmt == "U":
        return f"lui r{ins.rd}, {ins.imm:#x}"
    if fmt == "J":
        return f"jal r{ins.rd}, {ins.imm:+d}"
    if fmt == "O":
        return f"out r{ins.rs1}"
    return op
