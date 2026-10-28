"""Checks that an NPU program is valid for a hardware profile (spec §4.4, §4.5)."""

from .isa import Program
from .machine import NpuMachine


def validate(program: Program, machine: NpuMachine) -> list[str]:
    """Return a list of violations. An empty list means the program is valid."""
    errors: list[str] = []
    stride_limit = 1 << machine.stride_bits

    for pc, ins in enumerate(program.code):
        get = ins.get
        bad_count = False

        def count(name: str, limit: int | None) -> None:
            nonlocal bad_count
            v = get(name)
            if v < 1 or (limit is not None and v > limit):
                bad_count = True
                bound = f"is not in 1 .. {limit}" if limit is not None else "is less than 1"
                errors.append(f"pc {pc}: {ins.op} {name}={v} {bound}")

        def stride(name: str) -> None:
            v = get(name)
            if v >= stride_limit:
                errors.append(f"pc {pc}: {ins.op} {name}={v} does not fit "
                              f"stride_bits={machine.stride_bits}")

        def spad(name: str, length: int) -> None:
            start = get(name)
            if start + length > machine.spad_words:
                errors.append(f"pc {pc}: {ins.op} {name} range {start} .. {start + length - 1} "
                              f"is outside spad_words={machine.spad_words}")

        def dram(rows: int, cols: int, rstride: int, cstride: int) -> None:
            base = get("dram")
            last = base + (rows - 1) * rstride + (cols - 1) * cstride
            if last >= program.data_words:
                errors.append(f"pc {pc}: {ins.op} reads or writes DRAM word {last}, "
                              f"outside data_words={program.data_words}")

        op = ins.op
        if op in ("load", "store"):
            count("rows", None)
            count("cols", None)
            stride("rstride")
            if get("dram") % machine.dma_align != 0:
                errors.append(f"pc {pc}: {op} DRAM address {get('dram')} is not a multiple "
                              f"of dma_align={machine.dma_align}")
            if not bad_count:
                rows, cols = get("rows"), get("cols")
                spad("spad", rows * cols)
                cstride = get("cstride") if op == "load" else 1
                dram(rows, cols, get("rstride"), cstride)
        elif op in ("mm", "mma"):
            if op == "mma" and not machine.has_mma:
                errors.append(f"pc {pc}: mma is not available on {machine.name}")
            count("m", machine.mm_m)
            count("k", machine.mm_k)
            count("n", machine.mm_n)
            if not bad_count:
                m, k, n = get("m"), get("k"), get("n")
                spad("dst", m * n)
                spad("a", m * k)
                spad("b", k * n)
        elif op in ("vadd", "vsub", "vmul", "vrelu"):
            count("len", machine.vlen)
            if not bad_count:
                n = get("len")
                for name in ("dst", "a", "b") if op != "vrelu" else ("dst", "a"):
                    spad(name, n)
        elif op == "out":
            count("rows", None)
            count("cols", None)
            if not bad_count:
                dram(get("rows"), get("cols"), get("rstride"), get("cstride"))

    if program.data_words > machine.dram_words:
        errors.append(f"data_words={program.data_words} is larger than "
                      f"dram_words={machine.dram_words}")
    for addr, values in program.init:
        if addr + len(values) > program.data_words:
            errors.append(f".word at {addr} with {len(values)} values is outside "
                          f"data_words={program.data_words}")
    return errors
