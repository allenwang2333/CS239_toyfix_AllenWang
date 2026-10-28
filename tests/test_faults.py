"""Fault catalog and Verifier: every fault is detectable, and wrong fixes are caught."""

import tempfile
import unittest
from pathlib import Path

from toyfix.agents.verifier import verify
from toyfix.context import EpisodeContext, EventLog
from toyfix.faults import CATALOG, apply_fault, make_workspace
from toyfix.workspace import Workspace


class FaultWorkspace:
    """A workspace with a fault injected; edits simulate an agent's patch."""

    def __init__(self, fault_id: str | None, assigned: set[str] | None = None):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self.tmp.name))
        make_workspace(self.ws.dir, CATALOG[fault_id] if fault_id else None)
        self.ws.snapshot(self.ws.baseline)
        self.ws.snapshot(self.ws.checkpoint)
        self.ctx = EpisodeContext(ws=self.ws, log=EventLog())
        self.ctx.all_assigned = set(assigned or ())

    def edit(self, rel: str, old: str, new: str) -> None:
        p = self.ws.dir / rel
        text = p.read_text()
        assert text.count(old) == 1, (rel, old)
        p.write_text(text.replace(old, new))

    def verify(self):
        return verify(self.ctx)

    def close(self):
        self.tmp.cleanup()


class CatalogTest(unittest.TestCase):
    def test_clean_toolchain_passes_everything(self):
        fw = FaultWorkspace(None)
        rep = fw.verify()
        fw.close()
        self.assertTrue(rep.passed, rep.feedback())

    def test_every_fault_is_visible_and_reversible(self):
        for fid, fault in CATALOG.items():
            with self.subTest(fault=fid):
                fw = FaultWorkspace(fid, set(fault.layers))
                rep = fw.verify()
                self.assertTrue(rep.failing_tests, f"{fid} breaks no visible test")
                if "tests" not in fault.layers:
                    self.assertLess(rep.valid[0], rep.valid[1], f"{fid} breaks no corpus program")
                # Restoring the clean files is an accepted fix.
                make_workspace(fw.ws.dir, None)
                self.assertTrue(fw.verify().passed)
                fw.close()

    def test_fault_edits_must_match_exactly(self):
        with tempfile.TemporaryDirectory() as d:
            make_workspace(Path(d) / "ws", CATALOG["S1"])
            with self.assertRaises(RuntimeError):
                apply_fault(Path(d) / "ws", CATALOG["S1"])  # already applied


class WrongFixTest(unittest.TestCase):
    def test_over_restricting_validator_lowers_valid_count(self):
        fw = FaultWorkspace(None, {"constraints"})
        fw.edit("t32/validator.py", "lo = -(1 << (bits - 1))\n", "lo = -(1 << (bits - 1)) + 1\n")
        rep = fw.verify()
        fw.close()
        self.assertFalse(rep.passed)
        self.assertLess(rep.valid[0], rep.valid[1])

    def test_loosened_validator_is_caught_by_invalid_corpus(self):
        # Fault C4 checks jal against branch_bits. Deleting the jal range check
        # makes every visible test pass, but invalid programs are accepted.
        fw = FaultWorkspace("C4", {"constraints"})
        fw.edit("t32/validator.py",
                "if not _fits(ins.imm, machine.branch_bits):\n                errors.append(f\"pc {pc}: jump",
                "if False:\n                errors.append(f\"pc {pc}: jump")
        rep = fw.verify()
        fw.close()
        self.assertEqual(rep.failing_tests, [])
        self.assertLess(rep.invalid[0], rep.invalid[1])
        self.assertFalse(rep.passed)

    def test_wrong_layer_fix_is_caught_by_valid_corpus(self):
        # Fault T4: the shifts test wrongly expects a logical >>. Making the
        # compiler emit srl passes every visible test but breaks valid programs.
        fw = FaultWorkspace("T4", {"compiler"})
        fw.edit("minilang/compiler.py", '"<<": "sll", ">>": "sra"', '"<<": "sll", ">>": "srl"')
        rep = fw.verify()
        fw.close()
        self.assertEqual(rep.failing_tests, [])
        self.assertLess(rep.valid[0], rep.valid[1])

    def test_test_edit_must_match_reference(self):
        # Fault S3 (floor division in the simulator): editing the test to the
        # buggy output passes the visible tests but violates P4.
        fw = FaultWorkspace("S3", {"tests"})
        fw.edit("tests/division.expected", "-3\n-1\n-3\n1\n3\n-1\n", "-4\n1\n-4\n-1\n3\n-1\n")
        rep = fw.verify()
        fw.close()
        check = {c.name: c for c in rep.checks}["test_edits"]
        self.assertFalse(check.passed)
        self.assertIn("P4", check.detail)

    def test_correct_test_fix_is_accepted(self):
        fw = FaultWorkspace("T1", {"tests"})
        fw.edit("tests/division.expected", "-4\n1\n-4\n-1\n3\n-1\n", "-3\n-1\n-3\n1\n3\n-1\n")
        rep = fw.verify()
        fw.close()
        self.assertTrue(rep.passed, rep.feedback())

    def test_special_case_for_a_test_is_caught(self):
        fw = FaultWorkspace(None, {"compiler"})
        fw.edit("minilang/compiler.py", "MASK32 = 0xFFFFFFFF\n",
                "MASK32 = 0xFFFFFFFF\nSKIP = 'tests/deep_expr.ml'\n")
        rep = fw.verify()
        fw.close()
        self.assertFalse({c.name: c for c in rep.checks}["no_test_special_cases"].passed)

    def test_test_program_change_and_deletion_are_caught(self):
        fw = FaultWorkspace(None, {"tests"})
        fw.edit("tests/arith.ml", "var b = 5;", "var b = 6;")
        (fw.ws.dir / "tests" / "sra.s").unlink()
        rep = fw.verify()
        fw.close()
        checks = {c.name: c for c in rep.checks}
        self.assertFalse(checks["scope"].passed)
        self.assertIn("deleted", checks["scope"].detail)
        self.assertFalse(checks["test_edits"].passed)

    def test_unassigned_layer_and_protected_file_are_caught(self):
        fw = FaultWorkspace(None, {"compiler"})
        fw.edit("t32/simulator.py", "def s32(value: int) -> int:", "def s32(value: int) -> int:  # x")
        fw.edit("spec.md", "single source of truth", "source of truth")
        rep = fw.verify()
        fw.close()
        detail = {c.name: c for c in rep.checks}["scope"].detail
        self.assertIn("never assigned", detail)
        self.assertIn("protected", detail)


if __name__ == "__main__":
    unittest.main()
