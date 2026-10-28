"""NPU assembler, validator, and simulator (spec §1 - §6)."""

import unittest

from npu.assembler import AsmError, assemble
from npu.machine import list_npu_machines, load_npu_machine
from npu.simulator import run
from npu.validator import validate


def ok(src: str, machine: str) -> bool:
    return not validate(assemble(src), load_npu_machine(machine))


def output(src: str, machine: str = "npu-base") -> list[str]:
    p = assemble(src)
    m = load_npu_machine(machine)
    assert not validate(p, m), validate(p, m)
    r = run(p, m)
    assert r.trap is None, r.trap
    return r.output


class AssemblerTest(unittest.TestCase):
    def test_errors(self):
        for bad in ["mm 0, 0, 0, 1, 1", "frob 1", "load 0, 0, 1, 1, 1, -1", ".data -1",
                    ".data", ".word 3", ".word 0, 4294967296", "vadd 0, 0, x, 1"]:
            with self.assertRaises(AsmError, msg=bad):
                assemble(bad)

    def test_program(self):
        p = assemble("; c\n.data 4\n.word 1, 4294967295, 7 ; tail\n  vrelu 0, 0, 0x1\n")
        self.assertEqual((p.data_words, p.init, len(p.code)), (4, [(1, [-1, 7])], 1))


class ValidatorTest(unittest.TestCase):
    def test_profiles(self):
        self.assertEqual(list_npu_machines(), ["npu-base", "npu-tiny", "npu-wide"])
        for m in list_npu_machines():  # spec §4.6
            p = load_npu_machine(m)
            M, K, N = p.mm_shape
            self.assertGreaterEqual(p.spad_words, M * K + K * N + 2 * M * N, m)
            self.assertTrue(all(d % p.dma_align == 0 for d in p.mm_shape), m)

    def test_matrix_unit_shape(self):  # §4.4(b)
        for m in list_npu_machines():
            M, K, N = load_npu_machine(m).mm_shape
            with self.subTest(machine=m):
                self.assertTrue(ok(f"mm 0, 0, 0, {M}, {K}, {N}", m))
                self.assertFalse(ok(f"mm 0, 0, 0, {M + 1}, 1, 1", m))
                self.assertFalse(ok(f"mm 0, 0, 0, 1, {K + 1}, 1", m))
                self.assertFalse(ok(f"mm 0, 0, 0, 1, 1, {N + 1}", m))
                self.assertFalse(ok("mm 0, 0, 0, 1, 0, 1", m))
        # npu-wide is not square: k may be 16 but n only 4.
        self.assertTrue(ok("mm 0, 0, 0, 1, 16, 1", "npu-wide"))
        self.assertFalse(ok("mm 0, 0, 0, 1, 1, 16", "npu-wide"))

    def test_mma(self):  # §4.4(c)
        for m in list_npu_machines():
            with self.subTest(machine=m):
                self.assertEqual(ok("mma 0, 0, 0, 1, 1, 1", m), load_npu_machine(m).has_mma)

    def test_vector_length(self):  # §4.4(d)
        for m in list_npu_machines():
            v = load_npu_machine(m).vlen
            with self.subTest(machine=m):
                self.assertTrue(ok(f"vadd 0, 0, 0, {v}", m))
                self.assertTrue(ok(f"vrelu 0, 0, {v}", m))
                self.assertFalse(ok(f"vsub 0, 0, 0, {v + 1}", m))
                self.assertFalse(ok("vmul 0, 0, 0, 0", m))

    def test_row_stride(self):  # §4.4(e), §4.3
        for m in list_npu_machines():
            s = (1 << load_npu_machine(m).stride_bits) - 1
            with self.subTest(machine=m):
                # One row, so only the stride field limits the program.
                self.assertTrue(ok(f".data 1\nload 0, 0, 1, 1, {s}, 0", m))
                self.assertFalse(ok(f".data 1\nload 0, 0, 1, 1, {s + 1}, 0", m))
                self.assertTrue(ok(f".data 1\nstore 0, 0, 1, 1, {s}", m))
                self.assertFalse(ok(f".data 1\nstore 0, 0, 1, 1, {s + 1}", m))
                # cstride and the strides of out have no limit.
                self.assertTrue(ok(f".data 1\nload 0, 0, 1, 1, 0, {s + 1}", m))
                self.assertTrue(ok(f".data 1\nout 0, 1, 1, {s + 1}, {s + 1}", m))
                self.assertFalse(ok(".data 4\nload 0, 0, 0, 1, 1, 1", m))

    def test_alignment(self):  # §4.4(f)
        for m in list_npu_machines():
            a = load_npu_machine(m).dma_align
            with self.subTest(machine=m):
                self.assertTrue(ok(f".data {2 * a}\nload 1, {a}, 1, 1, 0, 0", m))
                self.assertFalse(ok(f".data {2 * a}\nload 0, {a + 1}, 1, 1, 0, 0", m))
                self.assertFalse(ok(f".data {2 * a}\nstore {a - 1}, 0, 1, 1, 0", m))
                self.assertTrue(ok(f".data {2 * a}\nout {a + 1}, 1, 1, 0, 0", m))

    def test_scratchpad_end(self):  # §4.4(g)
        for m in list_npu_machines():
            s = load_npu_machine(m).spad_words
            with self.subTest(machine=m):
                self.assertTrue(ok(f"vrelu {s - 1}, 0, 1", m))
                self.assertFalse(ok(f"vrelu {s}, 0, 1", m))
                self.assertTrue(ok(f"mm {s - 1}, 0, {s - 1}, 1, 1, 1", m))
                self.assertFalse(ok(f"mm 0, {s - 1}, 0, 1, 2, 1", m))
                self.assertTrue(ok(f".data 1\nload {s - 1}, 0, 1, 1, 0, 0", m))
                self.assertFalse(ok(f".data 2\nload {s - 1}, 0, 1, 2, 0, 1", m))

    def test_dram_ranges(self):  # §4.4(h)
        # The last word that load reads is dram + (rows-1)*rstride + (cols-1)*cstride.
        self.assertTrue(ok(".data 8\nload 0, 0, 2, 2, 5, 2", "npu-base"))
        self.assertFalse(ok(".data 8\nload 0, 0, 2, 2, 5, 3", "npu-base"))
        # store always has cstride 1.
        self.assertTrue(ok(".data 8\nstore 4, 0, 2, 2, 2", "npu-base"))
        self.assertFalse(ok(".data 9\nstore 4, 0, 2, 2, 4", "npu-base"))
        self.assertFalse(ok(".data 8\nout 7, 1, 2, 0, 1", "npu-base"))
        self.assertTrue(ok(".data 8\nout 7, 9, 9, 0, 0", "npu-base"))

    def test_data_words(self):  # §4.4(i)
        for m in list_npu_machines():
            d = load_npu_machine(m).dram_words
            with self.subTest(machine=m):
                self.assertTrue(ok(f".data {d}", m))
                self.assertFalse(ok(f".data {d + 1}", m))
        self.assertTrue(ok(".data 3\n.word 1, 5, 6", "npu-tiny"))
        self.assertFalse(ok(".data 3\n.word 2, 5, 6", "npu-tiny"))

    def test_one_violation_per_broken_rule(self):
        errors = validate(assemble(".data 4\nmma 0, 0, 0, 3, 1, 1\nload 1, 1, 1, 1, 16, 0"),
                          load_npu_machine("npu-tiny"))
        self.assertEqual(len(errors), 4, errors)  # no mma, m > 2, rstride, alignment


class SimulatorTest(unittest.TestCase):
    def test_strided_dma(self):
        src = ".data 16\n.word 0, 1, 2, 3\n.word 4, 4, 5, 6\n" \
              "load 0, 0, 3, 2, 1, 4\nstore 8, 0, 3, 2, 2\nout 8, 3, 2, 2, 1\nout 0, 2, 2, 0, 1\n"
        self.assertEqual(output(src), ["1 4", "2 5", "3 6", "1 2", "1 2"])

    def test_matrix_unit(self):
        src = ".data 8\n.word 0, 1, 2, 3, 4\n.word 4, 5, 6, 7, 8\n" \
              "load 0, 0, 2, 2, 2, 1\nload 4, 4, 2, 2, 2, 1\nmm 8, 0, 4, 2, 2, 2\n" \
              "mma 8, 0, 4, 2, 1, 2\nstore 0, 8, 2, 2, 2\nout 0, 2, 2, 2, 1\n"
        # A @ B = [[19, 22], [43, 50]]. Then mma adds the 2x1 matrix at 0
        # (1, 2) times the 1x2 matrix at 4 (5, 6).
        self.assertEqual(output(src), ["24 28", "53 62"])

    def test_non_square_matrix_unit(self):
        src = ".data 40\n.word 0, 1\n.word 4, 2\nload 0, 0, 8, 16, 0, 0\n" \
              "load 128, 4, 16, 4, 0, 1\nmm 192, 0, 128, 8, 16, 4\nstore 8, 192, 8, 4, 4\n" \
              "out 8, 1, 4, 0, 1\n"
        # B rows are dram[4..7] = 2 0 0 0 (cstride 1), so column 0 is 16 * 2.
        self.assertEqual(output(src, "npu-wide"), ["32 0 0 0"])

    def test_vector_unit_and_wraparound(self):
        src = ".data 4\n.word 0, 2147483647, -5, 3\n" \
              "load 0, 0, 1, 3, 0, 1\nvadd 4, 0, 0, 3\nvsub 8, 0, 4, 3\nvmul 12, 0, 0, 3\n" \
              "vrelu 0, 0, 3\n" \
              "store 0, 4, 1, 3, 0\nout 0, 1, 3, 0, 1\nstore 0, 8, 1, 3, 0\nout 0, 1, 3, 0, 1\n" \
              "store 0, 12, 1, 3, 0\nout 0, 1, 3, 0, 1\n" \
              "store 0, 0, 1, 3, 0\nout 0, 1, 3, 0, 1\n"
        self.assertEqual(output(src), ["-2 -10 6", "-2147483647 5 -3", "1 25 9", "2147483647 0 3"])

    def test_inputs_are_read_before_the_result_is_written(self):
        src = ".data 4\n.word 0, 1, 2, 3, 4\nload 0, 0, 2, 2, 2, 1\nmm 0, 0, 0, 2, 2, 2\n" \
              "store 0, 0, 2, 2, 2\nout 0, 2, 2, 2, 1\n"
        self.assertEqual(output(src), ["7 10", "15 22"])

    def test_memory_starts_as_zero_and_traps_without_validation(self):
        self.assertEqual(output(".data 2\nout 0, 1, 2, 0, 1"), ["0 0"])
        m = load_npu_machine("npu-tiny")
        self.assertEqual(run(assemble("vrelu 16, 0, 1"), m).trap, "spad_out_of_range")
        self.assertEqual(run(assemble(".data 1\nout 0, 1, 2, 0, 1"), m).trap, "dram_out_of_range")
        r = run(assemble(".data 1\nout 0, 1, 1, 0, 0\n" * 3), m, max_steps=2)
        self.assertEqual((r.output, r.trap), (["0", "0"], "step_limit"))

    def test_counters_and_trace(self):
        p = assemble(".data 4\nload 0, 0, 2, 2, 2, 1\nmm 4, 0, 0, 2, 2, 2")
        r = run(p, load_npu_machine("npu-base"), trace_limit=5)
        self.assertEqual((r.steps, r.dma_words, r.macs), (2, 4, 8))
        self.assertEqual(r.trace[1]["asm"], "mm 4, 0, 0, 2, 2, 2")
        self.assertIn("spad[4..7] = 0 0 0 0", r.trace[1]["mem"])


if __name__ == "__main__":
    unittest.main()
