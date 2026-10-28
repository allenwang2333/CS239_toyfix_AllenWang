"""MiniLang frontend, reference interpreter, IR, passes, and compiler (spec §7-§9).

The compiler is checked by differential testing against the reference
interpreter on every NPU profile, including random programs.
"""

import random
import unittest

from cli import execute, normalize, reference_text
from minilang.compiler import CompileError, build_ir, compile_ir, compile_source
from minilang.ir import IRError, Op, TensorType, print_module, verify
from minilang.parser import Domain, ParseError, parse, run
from minilang.reference import evaluate
from npu.machine import list_npu_machines, load_npu_machine

from tests import SRC

SUT = SRC / "sut"
CORPUS = SRC / "toyfix" / "hidden" / "corpus"


def main(body: str) -> str:
    return "def main():\n" + "".join(f"    {line}\n" for line in body.strip().splitlines())


class _Size(Domain):
    """Counts S of spec §9.3: the padded size of every tensor the program computes."""

    def __init__(self, align: int):
        self.align = align
        self.total = 0

    def _add(self, type):
        cols = -(-type.shape[-1] // self.align) * self.align
        self.total += cols * (type.shape[0] if type.rank == 2 else 1)

    def constant(self, type, values):
        self._add(type)

    def broadcast(self, x, type):
        self._add(type)

    def binary(self, op, a, b, type):
        self._add(type)

    def matmul(self, a, b, type):
        self._add(type)

    def relu(self, x, type):
        self._add(type)

    def transpose(self, x, type):
        self._add(type)


def size_bound(source: str, machine: str) -> int:
    d = _Size(load_npu_machine(machine).dma_align)
    run(parse(source), d)
    return d.total


def compiled_result(source: str, machine: str) -> str:
    return normalize(execute(source, "ml", machine)["actual"])


def reference_result(source: str) -> str:
    return normalize(reference_text(source)["result"])


class ParserTest(unittest.TestCase):
    def test_errors(self):
        bad = [
            "x = 1\ndef main():\n    pass",                      # top-level statement
            "def f():\n    pass",                                 # no main
            "def main(x: int):\n    pass",                        # main with parameters
            main("print(x)"),                                     # undefined name
            main("print(1.5)"),                                   # not an integer
            main("print(4294967296)"),                            # literal too large
            main("print(zeros((2, 3)) + zeros((3, 2)))"),         # shapes do not broadcast
            main("print(zeros(3) @ zeros(3))"),                   # @ needs rank 2
            main("print(zeros((2, 3)) @ zeros((2, 3)))"),         # inner dims differ
            main("print(tensor([[1, 2], [3]]))"),                 # ragged literal
            main("print(zeros((2, 2, 2)))"),                      # rank 3
            main("print(zeros(0))"),                              # empty shape
            main("x = 1\nx()"),                                   # call of a non-function
            main("relu(zeros(2))"),                               # expression statement
            main("print(1, 2)"),                                  # print arity
            main("for i in zeros(3):\n    pass"),                 # loop over a tensor
            main("for i in range(10, 0, 0):\n    pass"),          # zero step
            main("for i in range(200000):\n    pass"),            # too many operations
            main("print(zeros(2) / 2)"),                          # unsupported operator
            main("print(zeros(2).shape)"),                        # unsupported attribute
            main("return 1"),                                     # main returns a value
            main("if 1:\n    pass"),                              # no if statement
            main("print(f(1))") + "def f(n: int) -> int:\n    return f(n)\n",  # recursion
            main("print(f(zeros(2)))") + "def f(x: Tensor[3, i32]) -> Tensor[3, i32]:\n    return x\n",
            main("print(f(zeros(3)))") + "def f(x: Tensor[3, i32]) -> Tensor[2, i32]:\n    return x\n",
            main("print(f(1))") + "def f(n):\n    return n\n",  # missing annotation
            "def main(:\n",                                       # Python syntax error
        ]
        for src in bad:
            with self.assertRaises(ParseError, msg=src):
                parse(src)

    def test_errors_have_line_numbers(self):
        with self.assertRaisesRegex(ParseError, r"^line 3: name 'y' is not defined"):
            parse(main("x = 1\nprint(y)"))


class ReferenceTest(unittest.TestCase):
    def test_semantics(self):  # hand-computed from spec §8
        src = main("""
a = tensor([[1, 2, 3], [4, 5, 6]])
print(a @ a.T)
print(a + tensor([10, 20, 30]))
print(relu(a - 3) * 2)
print(-a + 1)
print(2147483647 + 1)
print(full(2, 2147483647) * 2)
print(iota((2, 2)))
n = 0
for i in range(1, 10, 4):
    n += i
print(n)
""")
        self.assertEqual(evaluate(src), [
            "14 32", "32 77",
            "11 22 33", "14 25 36",
            "0 0 0", "2 4 6",
            "0 -1 -2", "-3 -4 -5",
            "-2147483648",
            "-2 -2",
            "0 1", "2 3",
            "15",
        ])

    def test_functions_inline_and_rebind(self):
        src = main("x = twice(tensor([1, -1]), 3)\nprint(x)\nx = 5\nprint(x)") + \
            "def twice(v: Tensor[2, i32], k: int) -> Tensor[2, i32]:\n    v = v * k\n    return v + v\n"
        self.assertEqual(evaluate(src), ["6 -6", "5"])


class IRTest(unittest.TestCase):
    SRC = main("x = tensor([[1, 2], [3, 4]])\nprint(relu(x @ x + 1))")

    def test_frontend_prints_mlir_generic_syntax(self):
        self.assertEqual(print_module(build_ir(self.SRC)), """\
module {
  func.func @main() {
    %0 = "ml.constant"() {value = dense<[[1, 2], [3, 4]]> : tensor<2x2xi32>} : () -> tensor<2x2xi32>
    %1 = "ml.matmul"(%0, %0) : (tensor<2x2xi32>, tensor<2x2xi32>) -> tensor<2x2xi32>
    %2 = "ml.constant"() {value = dense<1> : tensor<2x2xi32>} : () -> tensor<2x2xi32>
    %3 = "ml.add"(%1, %2) : (tensor<2x2xi32>, tensor<2x2xi32>) -> tensor<2x2xi32>
    %4 = "ml.relu"(%3) : (tensor<2x2xi32>) -> tensor<2x2xi32>
    "ml.print"(%4) : (tensor<2x2xi32>) -> ()
    func.return
  }
}
""")

    def stage(self, src: str, stop: str, machine: str = "npu-base") -> str:
        out = {}
        compile_ir(src, load_npu_machine(machine), lambda s, m: out.setdefault(s, print_module(m)))
        return out[stop]

    def test_fuse_makes_one_linear_op(self):
        text = self.stage(self.SRC, "fuse")
        self.assertIn('"ml.linear"(%0, %0, %1) {relu = true}', text)
        self.assertNotIn('"ml.matmul"', text)
        self.assertNotIn('"ml.relu"', text)

    def test_no_fusion_when_a_value_has_other_uses(self):
        src = main("x = iota((2, 2))\ny = x @ x + 1\nprint(y)\nprint(relu(y))\nm = x @ (x * 2)\n"
                   "print(m)\nprint(relu(m))")
        text = self.stage(src, "fuse")
        self.assertIn("{relu = false}", text)
        self.assertNotIn("{relu = true}", text)
        self.assertEqual(text.count('"ml.relu"'), 2)

    def test_canonicalize_folds_identities_and_cse(self):
        src = main("x = iota((2, 3)) - 1\nprint(x + 0)\nprint(x * 1)\nprint(relu(relu(x)))\n"
                   "print(x.T.T)\nprint(iota((2, 3)) - 1)\nprint(full(2, 3) * full(2, 4))")
        text = self.stage(src, "canonicalize")
        self.assertEqual(text.count('"ml.sub"'), 1)      # CSE of the two iota - 1
        self.assertEqual(text.count('"ml.relu"'), 1)
        self.assertNotIn('"ml.transpose"', text)
        self.assertNotIn('"ml.add"', text)
        self.assertNotIn('"ml.mul"', text)
        self.assertIn("dense<12> : tensor<2xi32>", text)  # splat folding

    def test_bufferize_views_and_reuse(self):
        src = main("a = iota((2, 3)) + 1\nprint(a.T)\nprint(tensor([5, 6, 7]) + a)")
        text = self.stage(src, "bufferize")
        self.assertIn("memref<2x3xi32, strided<[4, 1], offset:", text)   # rows padded to 4
        self.assertIn("memref<3x2xi32, strided<[1, 4], offset:", text)   # transpose view
        self.assertIn("memref<2x3xi32, strided<[0, 1], offset:", text)   # broadcast view
        self.assertIn("memref<2x3xi32, strided<[0, 0], offset:", text)   # splat
        # iota is dead after a = iota + 1, so the last result reuses its buffer.
        chain = main("x = iota(64) + 1\nx = x * 3\nx = x - 2\nx = x * 5\nprint(x)")
        module = compile_ir(chain, load_npu_machine("npu-base"))
        self.assertLess(module.attrs["npu.data_words"], 64 * 3)

    def test_verifier_rejects_malformed_ir(self):
        m = build_ir(self.SRC)
        m.func.ops.reverse()
        with self.assertRaisesRegex(IRError, "not defined"):
            verify(m)
        m = build_ir(self.SRC)
        m.func.ops.insert(1, Op("ml.add", [m.func.ops[0].result, m.func.ops[0].result],
                                [TensorType((3, 3))]))
        with self.assertRaisesRegex(IRError, "shapes"):
            verify(m)


class CompilerTest(unittest.TestCase):
    def check(self, src: str, label: str) -> None:
        want = reference_result(src)
        for m in list_npu_machines():
            with self.subTest(program=label, machine=m):
                got = compiled_result(src, m)
                if got == "<compile error>":
                    # Only a program above the memory bound may be rejected (spec §9.3).
                    self.assertGreater(size_bound(src, m), load_npu_machine(m).dram_words, label)
                    with self.assertRaisesRegex(CompileError, "DRAM words"):
                        compile_source(src, load_npu_machine(m))
                    continue
                self.assertEqual(got, want, label)

    def test_visible_and_corpus_programs_on_every_profile(self):
        files = sorted((SUT / "tests").glob("*.ml")) + sorted((CORPUS / "valid").glob("*.ml"))
        self.assertGreater(len(files), 25)
        for f in files:
            self.check(f.read_text(), f.name)

    def test_test_programs_are_within_the_memory_bound(self):
        # Tests and corpus programs must be programs that the spec requires
        # the compiler to accept on their own profile.
        files = sorted((SUT / "tests").glob("*.ml")) + sorted((CORPUS / "valid").glob("*.ml"))
        for f in files:
            src = f.read_text()
            machine = src.splitlines()[0].split("machine:")[1].strip()
            with self.subTest(file=f.name):
                self.assertLessEqual(size_bound(src, machine), load_npu_machine(machine).dram_words)

    def test_random_programs(self):
        rng = random.Random(239)

        def leaf(shape) -> str:
            dims = ", ".join(map(str, shape))
            r = rng.random()
            if r < 0.4:
                return f"(iota(({dims},)) - {rng.randint(0, 40)})"
            if r < 0.6:
                return f"full(({dims},), {rng.randint(-9, 9)})"
            vals = [rng.randint(-2**31, 2**31 - 1) if rng.random() < 0.1 else rng.randint(-20, 20)
                    for _ in range(shape[0] * (shape[1] if len(shape) == 2 else 1))]
            if len(shape) == 1:
                return f"tensor({vals})"
            rows = [vals[i:i + shape[1]] for i in range(0, len(vals), shape[1])]
            return f"tensor({rows})"

        def expr(shape, depth: int) -> str:
            if depth == 0 or rng.random() < 0.2:
                return leaf(shape)
            r = rng.random()
            if len(shape) == 2 and r < 0.25:
                k = rng.randint(1, 9)
                return f"({expr((shape[0], k), depth - 1)} @ {expr((k, shape[1]), depth - 1)})"
            if len(shape) == 2 and r < 0.35:
                return f"{expr((shape[1], shape[0]), depth - 1)}.T"
            if len(shape) == 2 and r < 0.45:
                return f"({expr(shape, depth - 1)} + {expr((shape[1],), depth - 1)})"
            if r < 0.55:
                return f"relu({expr(shape, depth - 1)})"
            if r < 0.65:
                return f"({rng.randint(-5, 5)} - {expr(shape, depth - 1)} * {rng.randint(-3, 3)})"
            if r < 0.7:
                return f"-{expr(shape, depth - 1)}"
            op = rng.choice(["+", "-", "*"])
            return f"({expr(shape, depth - 1)} {op} {expr(shape, depth - 1)})"

        for i in range(60):
            lines = []
            for j in range(3):
                shape = tuple(rng.randint(1, 9) for _ in range(rng.choice([1, 2, 2])))
                lines.append(f"v{j} = {expr(shape, rng.randint(1, 4))}")
                lines.append(f"print(v{j})")
            self.check(main("\n".join(lines)), f"random {i}:\n" + "\n".join(lines))

    def test_memory_bound(self):  # spec §9.3
        tiny = load_npu_machine("npu-tiny")
        # S = 256 = dram_words: must compile and use every DRAM word.
        asm = compile_source(main("print(iota((16, 16)))"), tiny)
        self.assertIn(".data 256\n", asm)
        with self.assertRaisesRegex(CompileError, "DRAM words"):
            compile_source(main("print(iota((16, 16)) + 1)"), tiny)
        # 16 rows of 15 are padded to 16 rows of 16 (dma_align = 2): S = 256.
        self.assertIn(".data 256\n", compile_source(main("print(iota((16, 15)))"), tiny))

    def test_compiled_code_obeys_every_profile_limit(self):
        # Each profile limit changes the code: no mma on npu-tiny, vlen
        # pieces, one DMA per row for long rows, and aligned DMA addresses.
        src = main("x = iota((3, 20)) - 9\nprint(relu(x @ x.T + 1))\nprint(x * 2)")
        asm = compile_source(src, load_npu_machine("npu-tiny"))
        lines = [l.split(None, 1) for l in asm.splitlines() if l.startswith("  ")]
        args = [(op, [int(a) for a in rest.split(",")]) for op, rest in lines]
        self.assertNotIn("mma", [op for op, _ in args])
        self.assertTrue(all(a[-1] <= 2 for op, a in args if op.startswith("v")))
        self.assertTrue(all(a[4] < 16 for op, a in args if op in ("load", "store")))
        self.assertTrue(all(a[1 if op == "load" else 0] % 2 == 0
                            for op, a in args if op in ("load", "store")))
        self.assertIn("mm", [op for op, _ in args])

    def test_invalid_program_is_a_compile_error(self):
        with self.assertRaisesRegex(CompileError, "invalid program: line 2"):
            compile_source(main("print(nope)"), load_npu_machine("npu-base"))


if __name__ == "__main__":
    unittest.main()
