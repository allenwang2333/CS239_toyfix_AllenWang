"""Text assembler for T32 (spec §6).

The assembler checks only the encoding field widths (spec §2.3). Hardware
profile limits are checked by the validator.
"""

import re

from .isa import OPS, Instr, Program, encode, field_fits


class AsmError(Exception):
    pass


_LABEL = re.compile(r"^([A-Za-z_.$][\w.$]*):\s*(.*)$")
_MEM = re.compile(r"^(-?\w+)\((\w+)\)$")


def _reg(text: str, line_no: int) -> int:
    m = re.fullmatch(r"r(\d+)", text.strip().lower())
    if not m:
        raise AsmError(f"line {line_no}: expected a register, got {text!r}")
    n = int(m.group(1))
    if n > 15:
        raise AsmError(f"line {line_no}: register r{n} does not fit the encoding")
    return n


def _int(text: str, line_no: int) -> int:
    try:
        return int(text.strip(), 0)
    except ValueError:
        raise AsmError(f"line {line_no}: expected an integer, got {text!r}") from None


def _strip(line: str) -> str:
    return line.split(";", 1)[0].strip()


def assemble(source: str) -> Program:
    # Pass 1: find labels and instruction lines.
    labels: dict[str, int] = {}
    items: list[tuple[int, str]] = []
    data_words = 0
    for line_no, raw in enumerate(source.splitlines(), 1):
        text = _strip(raw)
        while True:
            m = _LABEL.match(text)
            if not m:
                break
            name = m.group(1)
            if name in labels:
                raise AsmError(f"line {line_no}: duplicate label {name!r}")
            labels[name] = len(items)
            text = m.group(2).strip()
        if not text:
            continue
        if text.startswith(".data"):
            parts = text.split()
            if len(parts) != 2:
                raise AsmError(f"line {line_no}: expected '.data N'")
            data_words = _int(parts[1], line_no)
            if data_words < 0:
                raise AsmError(f"line {line_no}: .data must not be negative")
            continue
        items.append((line_no, text))

    # Pass 2: encode.
    code: list[int] = []
    lines: list[str] = []
    for pc, (line_no, text) in enumerate(items):
        ins = _parse(text, pc, labels, line_no)
        if ins.fmt in ("I", "S", "B", "U", "J") and not field_fits(ins.imm, ins.fmt):
            raise AsmError(f"line {line_no}: immediate {ins.imm} does not fit the encoding")
        code.append(encode(ins))
        lines.append(text)
    return Program(code=code, data_words=data_words, lines=lines)


def _target(text: str, pc: int, labels: dict[str, int], line_no: int) -> int:
    text = text.strip()
    if text in labels:
        return labels[text] - pc
    if re.fullmatch(r"[+-]?(0x[0-9a-fA-F]+|\d+)", text):
        return _int(text, line_no)
    raise AsmError(f"line {line_no}: unknown label {text!r}")


def _parse(text: str, pc: int, labels: dict[str, int], line_no: int) -> Instr:
    parts = text.split(None, 1)
    op = parts[0].lower()
    if op not in OPS:
        raise AsmError(f"line {line_no}: unknown instruction {op!r}")
    args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []
    fmt = OPS[op].fmt

    def need(n: int) -> None:
        if len(args) != n:
            raise AsmError(f"line {line_no}: {op} takes {n} operands")

    if fmt == "R":
        need(3)
        return Instr(op, rd=_reg(args[0], line_no), rs1=_reg(args[1], line_no),
                     rs2=_reg(args[2], line_no))
    if op in ("lw", "sw"):
        need(2)
        m = _MEM.match(args[1].replace(" ", ""))
        if not m:
            raise AsmError(f"line {line_no}: expected imm(reg), got {args[1]!r}")
        imm, base = _int(m.group(1), line_no), _reg(m.group(2), line_no)
        if op == "lw":
            return Instr(op, rd=_reg(args[0], line_no), rs1=base, imm=imm)
        return Instr(op, rs2=_reg(args[0], line_no), rs1=base, imm=imm)
    if fmt == "I":
        need(3)
        return Instr(op, rd=_reg(args[0], line_no), rs1=_reg(args[1], line_no),
                     imm=_int(args[2], line_no))
    if fmt == "B":
        need(3)
        return Instr(op, rs1=_reg(args[0], line_no), rs2=_reg(args[1], line_no),
                     imm=_target(args[2], pc, labels, line_no))
    if fmt == "U":
        need(2)
        return Instr(op, rd=_reg(args[0], line_no), imm=_int(args[1], line_no))
    if fmt == "J":
        need(2)
        return Instr(op, rd=_reg(args[0], line_no),
                     imm=_target(args[1], pc, labels, line_no))
    if fmt == "O":
        need(1)
        return Instr(op, rs1=_reg(args[0], line_no))
    need(0)
    return Instr(op)
