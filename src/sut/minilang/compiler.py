"""MiniLang to T32 compiler (spec §9).

Register use: r0 is zero, r1 .. r(N-2) hold expression temporaries as a
stack (depth d uses r(d+1)), and r(N-1) is the scratch register for
addresses, large constants, reloaded spills, and the multiply return link.

Data layout: multiply runtime slots (only when needed), then variables and
arrays in declaration order, then spill slots.
"""

from t32.machine import Machine

from .parser import (ArrayDecl, Assign, Binary, If, Index, IndexAssign, Num,
                     ParseError, Print, Unary, Var, VarDecl, While,
                     declarations, parse)


class CompileError(Exception):
    pass


MASK32 = 0xFFFFFFFF

# Software multiply runtime slots (spec §9.2(d)): inputs, result, saved regs.
MUL_A, MUL_B, MUL_R = 0, 1, 2
MUL_SAVE = [3, 4, 5, 6]
MUL_SLOTS = 7

_SIMPLE_OPS = {
    "+": "add", "-": "sub", "/": "div", "%": "rem",
    "&": "and", "|": "or", "^": "xor", "<<": "sll", ">>": "sra",
}


def _s32(value: int) -> int:
    value &= MASK32
    return value - (1 << 32) if value & 0x80000000 else value


def _fits(value: int, bits: int) -> bool:
    return -(1 << (bits - 1)) <= value <= (1 << (bits - 1)) - 1


def _uses_mul(node) -> bool:
    if isinstance(node, list):
        return any(_uses_mul(n) for n in node)
    if isinstance(node, Binary):
        return node.op == "*" or _uses_mul(node.left) or _uses_mul(node.right)
    for attr in ("init", "index", "value", "operand", "cond"):
        child = getattr(node, attr, None)
        if child is not None and _uses_mul(child):
            return True
    return any(_uses_mul(getattr(node, a)) for a in ("then", "orelse", "body")
               if hasattr(node, a))


class Compiler:
    def __init__(self, machine: Machine):
        if machine.num_regs < 4:
            raise CompileError("the compiler needs at least 4 registers")
        self.m = machine
        self.scratch = machine.num_regs - 1
        self.num_temps = machine.num_regs - 2
        # Items: ("ins", text), ("label", name), ("bz", reg, label), ("jmp", label)
        self.items: list[tuple] = []
        self.addr: dict[str, int] = {}
        self.spill_base = 0
        self.spill_level = 0
        self.max_spill = 0
        self.labels = 0
        self.soft_mul = False

    # ---- helpers ----------------------------------------------------------

    def emit(self, text: str) -> None:
        self.items.append(("ins", text))

    def new_label(self, hint: str) -> str:
        self.labels += 1
        return f"L{self.labels}_{hint}"

    def reg(self, depth: int) -> int:
        return depth + 1

    def load_const(self, rd: int, value: int) -> None:
        u = value & MASK32
        s = _s32(u)
        if _fits(s, self.m.imm_bits):
            self.emit(f"addi r{rd}, r0, {s}")
            return
        # lui sets the upper 20 bits; addi adds a sign-extended 12-bit value,
        # so the upper part must absorb the sign of the lower part.
        lo = u & 0xFFF
        if lo >= 0x800:
            lo -= 0x1000
        hi = ((u - lo) >> 12) & 0xFFFFF
        self.emit(f"lui r{rd}, {hi:#x}")
        if lo:
            self.emit(f"addi r{rd}, r{rd}, {lo}")

    def mem_op(self, op: str, reg: int, addr: int) -> None:
        if _fits(addr, self.m.imm_bits):
            self.emit(f"{op} r{reg}, {addr}(r0)")
            return
        assert not (op == "sw" and reg == self.scratch)
        self.load_const(self.scratch, addr)
        self.emit(f"{op} r{reg}, 0(r{self.scratch})")

    def add_base(self, rd: int, base: int) -> None:
        if base == 0:
            return
        if _fits(base, self.m.imm_bits):
            self.emit(f"addi r{rd}, r{rd}, {base}")
        else:
            self.load_const(self.scratch, base)
            self.emit(f"add r{rd}, r{rd}, r{self.scratch}")

    # ---- expressions ------------------------------------------------------

    def binop(self, op: str, rd: int, ra: int, rb: int) -> None:
        if op in _SIMPLE_OPS:
            self.emit(f"{_SIMPLE_OPS[op]} r{rd}, r{ra}, r{rb}")
        elif op == "*":
            if self.m.has_mul:
                self.emit(f"mul r{rd}, r{ra}, r{rb}")
            else:
                self.soft_mul = True
                self.emit(f"sw r{ra}, {MUL_A}(r0)")
                self.emit(f"sw r{rb}, {MUL_B}(r0)")
                self.emit(f"jal r{self.scratch}, __mul")
                self.emit(f"lw r{rd}, {MUL_R}(r0)")
        elif op == "<":
            self.emit(f"slt r{rd}, r{ra}, r{rb}")
        elif op == ">":
            self.emit(f"slt r{rd}, r{rb}, r{ra}")
        elif op == "<=":
            self.emit(f"slt r{rd}, r{rb}, r{ra}")
            self.emit(f"xori r{rd}, r{rd}, 1")
        elif op == ">=":
            self.emit(f"slt r{rd}, r{ra}, r{rb}")
            self.emit(f"xori r{rd}, r{rd}, 1")
        elif op == "==":
            self.emit(f"xor r{rd}, r{ra}, r{rb}")
            self.emit(f"sltiu r{rd}, r{rd}, 1")
        elif op == "!=":
            self.emit(f"xor r{rd}, r{ra}, r{rb}")
            self.emit(f"sltu r{rd}, r0, r{rd}")
        else:
            raise CompileError(f"unknown operator {op!r}")

    def gen(self, e, d: int) -> None:
        """Evaluate e into register reg(d)."""
        rd = self.reg(d)
        if isinstance(e, Num):
            self.load_const(rd, e.value)
        elif isinstance(e, Var):
            self.mem_op("lw", rd, self.addr[e.name])
        elif isinstance(e, Index):
            self.gen(e.index, d)
            self.add_base(rd, self.addr[e.name])
            self.emit(f"lw r{rd}, 0(r{rd})")
        elif isinstance(e, Unary):
            self.gen(e.operand, d)
            if e.op == "-":
                self.emit(f"sub r{rd}, r0, r{rd}")
            elif e.op == "!":
                self.emit(f"sltiu r{rd}, r{rd}, 1")
            else:
                self.emit(f"xori r{rd}, r{rd}, -1")
        elif isinstance(e, Binary):
            self.gen(e.left, d)
            if d + 1 < self.num_temps:
                self.gen(e.right, d + 1)
                self.binop(e.op, rd, rd, self.reg(d + 1))
            else:
                # Out of temporaries: spill the left value, reuse its register
                # for the right value, then reload the left into scratch.
                slot = self.spill_base + self.spill_level
                self.spill_level += 1
                self.max_spill = max(self.max_spill, self.spill_level)
                self.mem_op("sw", rd, slot)
                self.gen(e.right, d)
                self.spill_level -= 1
                self.mem_op("lw", self.scratch, slot)
                self.binop(e.op, rd, self.scratch, rd)
        else:
            raise CompileError(f"unknown expression {e!r}")

    # ---- statements -------------------------------------------------------

    def stmts(self, stmts: list) -> None:
        for s in stmts:
            self.stmt(s)

    def stmt(self, s) -> None:
        if isinstance(s, VarDecl):
            if s.init is None:
                self.mem_op("sw", 0, self.addr[s.name])
            else:
                self.gen(s.init, 0)
                self.mem_op("sw", self.reg(0), self.addr[s.name])
        elif isinstance(s, ArrayDecl):
            pass
        elif isinstance(s, Assign):
            self.gen(s.value, 0)
            self.mem_op("sw", self.reg(0), self.addr[s.name])
        elif isinstance(s, IndexAssign):
            self.gen(s.index, 0)
            self.add_base(self.reg(0), self.addr[s.name])
            self.gen(s.value, 1)
            self.emit(f"sw r{self.reg(1)}, 0(r{self.reg(0)})")
        elif isinstance(s, Print):
            self.gen(s.value, 0)
            self.emit(f"out r{self.reg(0)}")
        elif isinstance(s, If):
            else_label = self.new_label("else")
            end_label = self.new_label("endif")
            self.gen(s.cond, 0)
            self.items.append(("bz", self.reg(0), else_label))
            self.stmts(s.then)
            if s.orelse:
                self.items.append(("jmp", end_label))
            self.items.append(("label", else_label))
            if s.orelse:
                self.stmts(s.orelse)
                self.items.append(("label", end_label))
        elif isinstance(s, While):
            top = self.new_label("while")
            end = self.new_label("endwhile")
            self.items.append(("label", top))
            self.gen(s.cond, 0)
            self.items.append(("bz", self.reg(0), end))
            self.stmts(s.body)
            self.items.append(("jmp", top))
            self.items.append(("label", end))
        else:
            raise CompileError(f"unknown statement {s!r}")

    def mul_routine(self) -> None:
        """Shift-and-add multiply: mem[MUL_R] = mem[MUL_A] * mem[MUL_B].
        The return address is in the scratch register."""
        saved = [1, 2, 3, 4]
        self.items.append(("label", "__mul"))
        for r, slot in zip(saved, MUL_SAVE):
            self.emit(f"sw r{r}, {slot}(r0)")
        self.emit(f"lw r1, {MUL_A}(r0)")
        self.emit(f"lw r2, {MUL_B}(r0)")
        self.emit("addi r3, r0, 0")
        self.items.append(("label", "__mul_loop"))
        self.emit("beq r2, r0, __mul_done")
        self.emit("andi r4, r2, 1")
        self.emit("beq r4, r0, __mul_skip")
        self.emit("add r3, r3, r1")
        self.items.append(("label", "__mul_skip"))
        self.emit("addi r4, r0, 1")
        self.emit("sll r1, r1, r4")
        self.emit("srl r2, r2, r4")
        self.emit("jal r0, __mul_loop")
        self.items.append(("label", "__mul_done"))
        self.emit(f"sw r3, {MUL_R}(r0)")
        for r, slot in zip(saved, MUL_SAVE):
            self.emit(f"lw r{r}, {slot}(r0)")
        self.emit(f"jalr r0, r{self.scratch}, 0")

    # ---- branch relaxation (spec §9.2(c)) ---------------------------------

    def layout(self, long: set[int]) -> tuple[dict[str, int], list[int]]:
        labels: dict[str, int] = {}
        pcs: list[int] = []
        pc = 0
        for i, item in enumerate(self.items):
            pcs.append(pc)
            if item[0] == "label":
                labels[item[1]] = pc
            elif item[0] == "bz" and i in long:
                pc += 2
            else:
                pc += 1
        return labels, pcs

    def relax(self) -> set[int]:
        """Find the conditional branches that need the long form."""
        long: set[int] = set()
        while True:
            labels, pcs = self.layout(long)
            changed = False
            for i, item in enumerate(self.items):
                if item[0] == "bz" and i not in long:
                    offset = labels[item[2]] - pcs[i]
                    if not _fits(offset, self.m.branch_bits):
                        long.add(i)
                        changed = True
            if not changed:
                break
        labels, pcs = self.layout(long)
        for i, item in enumerate(self.items):
            target = None
            if item[0] == "jmp":
                target = item[1]
            elif item[0] == "bz" and i in long:
                target = item[2]
            if target is not None:
                jal_pc = pcs[i] + (1 if item[0] == "bz" else 0)
                if not _fits(labels[target] - jal_pc, self.m.jump_bits):
                    raise CompileError("program is too long: a jump does not fit jump_bits")
        return long

    # ---- driver -----------------------------------------------------------

    def compile(self, stmts: list) -> str:
        next_addr = 0
        if not self.m.has_mul and _uses_mul(stmts):
            next_addr = MUL_SLOTS
        for d in declarations(stmts):
            self.addr[d.name] = next_addr
            next_addr += d.size if isinstance(d, ArrayDecl) else 1
        self.spill_base = next_addr

        self.stmts(stmts)
        self.emit("halt")
        if self.soft_mul:
            self.mul_routine()

        data_words = self.spill_base + self.max_spill
        if data_words > self.m.mem_words:
            raise CompileError(f"program needs {data_words} data words, "
                               f"{self.m.name} has {self.m.mem_words}")

        long = self.relax()
        out = [f"; compiled for {self.m.name}", f".data {data_words}"]
        for i, item in enumerate(self.items):
            kind = item[0]
            if kind == "ins":
                out.append(f"  {item[1]}")
            elif kind == "label":
                out.append(f"{item[1]}:")
            elif kind == "jmp":
                out.append(f"  jal r0, {item[1]}")
            elif i in long:
                out.append(f"  bne r{item[1]}, r0, 2")
                out.append(f"  jal r0, {item[2]}")
            else:
                out.append(f"  beq r{item[1]}, r0, {item[2]}")
        return "\n".join(out) + "\n"


def compile_source(source: str, machine: Machine) -> str:
    """Compile MiniLang source to T32 assembly. Raises CompileError."""
    try:
        stmts = parse(source)
    except ParseError as e:
        raise CompileError(f"syntax error: {e}") from None
    return Compiler(machine).compile(stmts)
