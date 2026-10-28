"""T32 encoding, assembler, and simulator semantics (spec §2, §3, §5)."""

import unittest

from t32.assembler import AsmError, assemble
from t32.isa import OPS, Instr, decode, encode
from t32.simulator import run


def outputs(src: str, **kw):
    r = run(assemble(src), **kw)
    return r.output, r.trap


class EncodingTest(unittest.TestCase):
    def test_roundtrip_every_opcode(self):
        for name, info in OPS.items():
            if info.fmt == "R":
                ins = Instr(name, rd=3, rs1=15, rs2=7)
            elif info.fmt == "I":
                ins = Instr(name, rd=1, rs1=2, imm=-131072)
            elif info.fmt == "S":
                ins = Instr(name, rs1=4, rs2=5, imm=131071)
            elif info.fmt == "B":
                ins = Instr(name, rs1=6, rs2=7, imm=-5)
            elif info.fmt == "U":
                ins = Instr(name, rd=8, imm=(1 << 22) - 1)
            elif info.fmt == "J":
                ins = Instr(name, rd=9, imm=-(1 << 21))
            elif info.fmt == "O":
                ins = Instr(name, rs1=10)
            else:
                ins = Instr(name)
            self.assertEqual(decode(encode(ins)), ins, name)

    def test_undefined_opcode_decodes_to_none(self):
        self.assertIsNone(decode(0x3D << 26))


class AssemblerTest(unittest.TestCase):
    def test_register_outside_encoding(self):
        with self.assertRaises(AsmError):
            assemble("addi r16, r0, 1")

    def test_immediate_outside_encoding(self):
        with self.assertRaises(AsmError):
            assemble("addi r1, r0, 131072")

    def test_unknown_label(self):
        with self.assertRaises(AsmError):
            assemble("beq r0, r0, nowhere")

    def test_labels_and_data(self):
        p = assemble(".data 7\nstart: addi r1, r0, 1\n  beq r0, r0, start\n")
        self.assertEqual(p.data_words, 7)
        self.assertEqual(decode(p.code[1]).imm, -1)


class SemanticsTest(unittest.TestCase):
    def test_spec_examples(self):  # spec §3.5
        out, trap = outputs("""
            addi r1, r0, -7
            addi r2, r0, 2
            div r3, r1, r2
            out r3
            rem r3, r1, r2
            out r3
            addi r1, r0, -8
            addi r2, r0, 1
            sra r3, r1, r2
            out r3
            srl r3, r1, r2
            out r3
            halt""")
        self.assertEqual(out, [-3, -1, -4, 2147483644])
        self.assertIsNone(trap)

    def test_wraparound(self):
        out, _ = outputs("""
            lui r1, 0x80000
            addi r2, r0, -1
            add r3, r1, r2
            out r3
            sub r3, r1, r2
            out r3
            mul r3, r1, r2
            out r3
            div r3, r1, r2
            out r3
            rem r3, r1, r2
            out r3
            halt""")
        self.assertEqual(out, [2147483647, -2147483647, -2147483648, -2147483648, 0])

    def test_r0_is_always_zero(self):
        out, _ = outputs("addi r0, r0, 5\nout r0\njal r0, 1\nout r0\nhalt")
        self.assertEqual(out, [0, 0])

    def test_shift_amount_uses_low_five_bits(self):
        out, _ = outputs("addi r1, r0, 1\naddi r2, r0, 33\nsll r3, r1, r2\nout r3\nhalt")
        self.assertEqual(out, [2])

    def test_signed_and_unsigned_compare(self):
        out, _ = outputs("""
            addi r1, r0, -1
            addi r2, r0, 1
            slt r3, r1, r2
            out r3
            sltu r3, r1, r2
            out r3
            slti r3, r1, 0
            out r3
            sltiu r3, r2, -1
            out r3
            halt""")
        self.assertEqual(out, [1, 0, 1, 1])

    def test_branches_are_signed(self):
        out, _ = outputs("""
            addi r1, r0, -1
            blt r1, r0, a
            out r0
            a: addi r2, r0, 1
            bge r0, r1, b
            out r0
            b: out r2
            halt""")
        self.assertEqual(out, [1])

    def test_jal_and_jalr_link(self):
        out, _ = outputs("jal r5, f\nout r5\nhalt\nf: jalr r6, r5, 0")
        self.assertEqual(out, [1])

    def test_lui_and_immediates(self):
        out, _ = outputs("lui r1, 0xfffff\nout r1\nandi r2, r1, -2048\nout r2\n"
                         "xori r3, r0, -1\nout r3\nori r4, r0, 5\nout r4\nhalt")
        self.assertEqual(out, [-4096, -4096, -1, 5])

    def test_memory(self):
        out, trap = outputs(".data 3\naddi r1, r0, 9\nsw r1, 2(r0)\nlw r2, 2(r0)\nout r2\n"
                            "addi r3, r0, 3\nlw r4, -1(r3)\nout r4\nhalt")
        self.assertEqual((out, trap), ([9, 9], None))

    def test_traps(self):
        self.assertEqual(outputs("addi r1, r0, 1\nout r1\ndiv r2, r1, r0\nhalt"),
                         ([1], "div_by_zero"))
        self.assertEqual(outputs(".data 1\nlw r1, 1(r0)\nhalt")[1], "mem_out_of_range")
        self.assertEqual(outputs("addi r1, r0, 1")[1], "pc_out_of_range")
        self.assertEqual(outputs("l: beq r0, r0, l", max_steps=50)[1], "step_limit")
        p = assemble("halt")
        p.code[0] = 0x3D << 26
        self.assertEqual(run(p).trap, "illegal_instruction")

    def test_trace(self):
        r = run(assemble("addi r1, r0, 4\nout r1\nhalt"), trace_limit=10)
        self.assertEqual([e["pc"] for e in r.trace], [0, 1, 2])
        self.assertEqual(r.trace[0]["regs"], "r1=4")


if __name__ == "__main__":
    unittest.main()
