"""MiniLang parser, reference interpreter, and compiler (spec §7-§9).

The compiler is checked by differential testing against the reference
interpreter on every profile, including random programs.
"""

import random
import unittest

from cli import execute, normalize, reference_text
from minilang.compiler import CompileError, compile_source
from minilang.parser import ParseError, parse
from minilang.reference import evaluate
from t32.machine import list_machines, load_machine

from tests import SRC

SUT = SRC / "sut"
CORPUS = SRC / "toyfix" / "hidden" / "corpus"


def compiled_result(source: str, machine: str) -> str:
    return normalize(execute(source, "ml", machine)["actual"])


def reference_result(source: str) -> str:
    return normalize(reference_text(source)["result"])


class ParserTest(unittest.TestCase):
    def test_errors(self):
        for bad in ["print x;", "var a; var a;", "var a = a;", "array a[0];",
                    "var a; a[1] = 2;", "array a[2]; a = 1;", "print 4294967296;",
                    "if (1) { print 1;", "print 1 +;"]:
            with self.assertRaises(ParseError, msg=bad):
                parse(bad)

    def test_precedence(self):
        self.assertEqual(evaluate("print 1 + 2 * 3 << 1 | 1 == 1;")[0], [15])
        self.assertEqual(evaluate("print -2 * 3 - -4;")[0], [-2])
        self.assertEqual(evaluate("print 10 - 3 - 2;")[0], [5])


class ReferenceTest(unittest.TestCase):
    def test_semantics(self):  # hand-computed from spec §8
        src = """
        print -7 / 2; print -7 % 2; print 7 % -2;
        print 2147483647 + 1; print 4294967295; print -64 >> 2; print 1 << 33;
        print 3 < 4; print !5; print ~0;
        var x; print x; array a[3]; a[2] = 9; print a[2] + a[0];
        """
        self.assertEqual(evaluate(src), ([-3, -1, 1, -2147483648, -1, -16, 2, 1, 0, -1, 0, 9],
                                         None))

    def test_traps(self):
        self.assertEqual(evaluate("print 1; print 1 / 0; print 2;"), ([1], "div_by_zero"))


class CompilerTest(unittest.TestCase):
    def test_visible_and_corpus_programs_on_every_profile(self):
        files = sorted((SUT / "tests").glob("*.ml")) + sorted((CORPUS / "valid").glob("*.ml"))
        self.assertGreater(len(files), 25)
        for f in files:
            src = f.read_text()
            want = reference_result(src)
            for m in list_machines():
                with self.subTest(file=f.name, machine=m):
                    try:
                        got = compiled_result(src, m)
                    except CompileError:
                        got = None
                    if got == "<compile error>":
                        # Only a memory overflow may be reported (spec §9.3).
                        with self.assertRaisesRegex(CompileError, "data words"):
                            compile_source(src, load_machine(m))
                        continue
                    self.assertEqual(got, want)

    def test_random_programs(self):
        rng = random.Random(239)
        consts = [0, 1, -1, 7, 2047, 2048, -2048, -2049, 4095, 4096, 32767, 32768,
                  65535, 123456789, -2147483648, 2147483647, 3000, -70000]
        ops = ["+", "-", "*", "&", "|", "^", "<<", ">>", "<", "<=", ">", ">=", "==", "!="]

        def expr(depth: int) -> str:
            if depth == 0 or rng.random() < 0.25:
                return rng.choice(["a", "b", "c", "v[1]", str(abs(rng.choice(consts)))])
            r = rng.random()
            if r < 0.1:
                return f"{rng.choice(['-', '!', '~'])}({expr(depth - 1)})"
            if r < 0.2:
                return f"({expr(depth - 1)}) {rng.choice(['/', '%'])} (({expr(depth - 1)}) | 1)"
            return f"({expr(depth - 1)}) {rng.choice(ops)} ({expr(depth - 1)})"

        for i in range(40):
            lines = [f"var a = {abs(rng.choice(consts))};", f"var b = -{abs(rng.choice(consts))};",
                     "var c = 0;", "array v[3];", f"v[1] = {rng.choice(consts) & 0xFFFF};"]
            for _ in range(4):
                lines.append(f"c = {expr(rng.randint(2, 9))};")
                lines.append("print c;")
            src = "\n".join(lines) + "\n"
            want = reference_result(src)
            for m in list_machines():
                with self.subTest(program=i, machine=m):
                    self.assertEqual(compiled_result(src, m), want, src)

    def test_too_much_data_is_a_compile_error(self):  # spec §9.3
        with self.assertRaises(CompileError):
            compile_source("array a[300];", load_machine("t32-tiny"))
        compile_source("array a[256];", load_machine("t32-tiny"))


if __name__ == "__main__":
    unittest.main()
