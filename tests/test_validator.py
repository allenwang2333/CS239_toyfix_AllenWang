"""Validity rules at their exact boundaries on every profile (spec §4.4)."""

import unittest

from t32.assembler import assemble
from t32.machine import list_machines, load_machine
from t32.validator import validate


def nops(n: int) -> str:
    return "\n".join("addi r0, r0, 0" for _ in range(n))


def valid(src: str, machine: str) -> bool:
    return not validate(assemble(src), load_machine(machine))


class ValidatorTest(unittest.TestCase):
    def test_profiles_load(self):
        self.assertEqual(list_machines(), ["t32-base", "t32-tiny", "t32-wide"])

    def test_immediate_range(self):  # §4.2, §4.4(c)
        for m in list_machines():
            bits = load_machine(m).imm_bits
            lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
            self.assertTrue(valid(f"addi r1, r0, {lo}\nsw r1, {hi}(r0)\nhalt", m), m)
            self.assertFalse(valid(f"addi r1, r0, {lo - 1}\nhalt", m), m)
            self.assertFalse(valid(f"sw r1, {hi + 1}(r0)\nhalt", m), m)

    def test_registers(self):  # §4.4(b)
        for m in list_machines():
            n = load_machine(m).num_regs
            self.assertTrue(valid(f"addi r{n - 1}, r0, 1\nhalt", m), m)
            if n < 16:
                self.assertFalse(valid(f"addi r{n}, r0, 1\nhalt", m), m)

    def test_branch_range_tiny(self):  # §4.4(d), branch_bits = 8
        self.assertTrue(valid(f"beq r0, r0, t\n{nops(126)}\nt: halt", "t32-tiny"))
        self.assertFalse(valid(f"beq r0, r0, t\n{nops(127)}\nt: halt", "t32-tiny"))
        self.assertTrue(valid(f"b: {nops(128)}\nbeq r0, r0, b\nhalt", "t32-tiny"))
        self.assertFalse(valid(f"b: {nops(129)}\nbeq r0, r0, b\nhalt", "t32-tiny"))

    def test_jump_range_tiny(self):  # §4.4(d), jump_bits = 16
        self.assertTrue(valid(f"jal r0, t\n{nops(1000)}\nt: halt", "t32-tiny"))
        self.assertFalse(valid(f"jal r0, t\n{nops(32767)}\nt: halt", "t32-tiny"))

    def test_targets_inside_program(self):  # §4.4(e)
        self.assertFalse(valid("beq r0, r0, 2\nhalt", "t32-base"))
        self.assertFalse(valid("jal r0, -1\nhalt", "t32-base"))

    def test_lui_range(self):  # §4.3
        self.assertTrue(valid("lui r1, 0xfffff\nhalt", "t32-base"))
        self.assertFalse(valid("lui r1, 0x100000\nhalt", "t32-base"))

    def test_mul(self):  # §4.4(f)
        self.assertTrue(valid("mul r1, r1, r1\nhalt", "t32-base"))
        self.assertFalse(valid("mul r1, r1, r1\nhalt", "t32-tiny"))

    def test_memory(self):  # §4.4(g): exactly mem_words is valid
        for m in list_machines():
            words = load_machine(m).mem_words
            self.assertTrue(valid(f".data {words}\nhalt", m), m)
            self.assertFalse(valid(f".data {words + 1}\nhalt", m), m)


if __name__ == "__main__":
    unittest.main()
