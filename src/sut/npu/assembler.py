"""Text assembler for the NPU (spec §6).

The assembler checks only the syntax. Hardware profile limits are checked by
the validator.
"""

from .isa import OPS, Instr, Program, s32


class AsmError(Exception):
    pass


def _int(text: str, line_no: int) -> int:
    try:
        return int(text.strip(), 0)
    except ValueError:
        raise AsmError(f"line {line_no}: expected an integer, got {text.strip()!r}") from None


def _operands(text: str, line_no: int) -> list[int]:
    return [_int(a, line_no) for a in text.split(",")] if text.strip() else []


def assemble(source: str) -> Program:
    prog = Program(code=[])
    for line_no, raw in enumerate(source.splitlines(), 1):
        text = raw.split(";", 1)[0].strip()
        if not text:
            continue
        parts = text.split(None, 1)
        head, rest = parts[0].lower(), parts[1] if len(parts) > 1 else ""
        if head == ".data":
            args = _operands(rest, line_no)
            if len(args) != 1 or args[0] < 0:
                raise AsmError(f"line {line_no}: expected '.data N' with N >= 0")
            prog.data_words = args[0]
        elif head == ".word":
            args = _operands(rest, line_no)
            if len(args) < 2 or args[0] < 0:
                raise AsmError(f"line {line_no}: expected '.word ADDR, V0, V1, ...'")
            for v in args[1:]:
                if not -(1 << 31) <= v <= (1 << 32) - 1:
                    raise AsmError(f"line {line_no}: value {v} is not a 32-bit integer")
            prog.init.append((args[0], [s32(v) for v in args[1:]]))
        elif head in OPS:
            args = _operands(rest, line_no)
            if len(args) != len(OPS[head]):
                raise AsmError(f"line {line_no}: {head} takes {len(OPS[head])} operands "
                               f"({', '.join(OPS[head])})")
            if any(a < 0 for a in args):
                raise AsmError(f"line {line_no}: operands must not be negative")
            prog.code.append(Instr(head, tuple(args)))
        else:
            raise AsmError(f"line {line_no}: unknown instruction {head!r}")
    return prog
