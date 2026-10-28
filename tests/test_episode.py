"""End-to-end episodes with a scripted LLM client (no network).

These tests check the Coordinator's control flow: layer assignment, the
Verifier and Reviewer gates, reverts, the attempt budget, and that fault
metadata never reaches an agent.
"""

import json
import tempfile
import unittest
from pathlib import Path

from toyfix.episode import run_episode
from toyfix.faults import CATALOG
from toyfix.llm import ScriptedClient

FIX_C2 = {"path": "t32/validator.py",
          "old_text": "if program.data_words >= machine.mem_words:",
          "new_text": "if program.data_words > machine.mem_words:"}


def episode(fault: str, script: list, **kw):
    tmp = tempfile.TemporaryDirectory()
    client = ScriptedClient(script)
    result = run_episode(fault, Path(tmp.name), {"default": client}, echo=False, **kw)
    return result, client, tmp


def files_equal(a: Path, b: Path) -> bool:
    fa = {p.relative_to(a): p.read_bytes() for p in a.rglob("*")
          if p.is_file() and "__pycache__" not in p.parts and ".scratch" not in p.parts}
    fb = {p.relative_to(b): p.read_bytes() for p in b.rglob("*")
          if p.is_file() and "__pycache__" not in p.parts and ".scratch" not in p.parts}
    return fa == fb


class EpisodeTest(unittest.TestCase):
    def test_fixed_episode(self):
        script = [
            # Diagnoser
            [("run_tests", {"filter": "full_memory"})],
            [("edit_file", FIX_C2)],  # denied: P1
            [("submit_diagnosis", {"layer": "constraints", "files": ["t32/validator.py"],
                                   "root_cause": "data_words equal to mem_words is rejected",
                                   "evidence": "full_memory.s is rejected", "spec_sections": ["4.4"]})],
            # Repair Agent
            [("edit_file", FIX_C2)],
            [("run_tests", {})],
            [("submit_patch", {"summary": "use > as in spec 4.4(g)", "spec_sections": ["4.4"]})],
            # Reviewer
            [("show_diff", {})],
            [("submit_review", {"decision": "approve", "rationale": "matches 4.4(g)",
                                "spec_sections": ["4.4"]})],
        ]
        result, client, tmp = episode("C2", script)
        with tmp:
            self.assertEqual(result["status"], "FIXED")
            self.assertEqual(result["attempts"], 1)
            self.assertTrue(result["first_diagnosis_correct"])
            self.assertTrue(result["fixed_in_injected_layers"])
            self.assertEqual(list(result["final_valid_corpus"]), [38, 38])
            self.assertEqual([d["policy"] for d in result["policy_denials"]], ["P1"])
            ep = Path(result["episode_dir"])
            self.assertIn("data_words > machine.mem_words",
                          (ep / "workspace/t32/validator.py").read_text())
            self.assertIn("FIXED", (ep / "trajectory.md").read_text())

            # P7: no fault metadata in anything an agent saw.
            seen = json.dumps(client.seen)
            fault = CATALOG["C2"]
            for secret in (fault.title, fault.tempting_fix, "scoreboard", "hidden/corpus"):
                self.assertNotIn(secret, seen)

    def test_wrong_layer_loosening_is_reverted_and_episode_unresolved(self):
        script = [
            [("submit_diagnosis", {"layer": "constraints", "root_cause": "validator rejects "
                                   "long branches", "evidence": "long_loop is rejected"})],
            # Repair Agent: tries the compiler first (denied), then loosens the validator.
            [("edit_file", {"path": "minilang/compiler.py", "old_text": "x", "new_text": "y"})],
            [("edit_file", {"path": "t32/validator.py",
                            "old_text": "if not _fits(ins.imm, machine.branch_bits):",
                            "new_text": "if not _fits(ins.imm, machine.imm_bits):"})],
            [("submit_patch", {"summary": "accept longer branches"})],
        ]
        result, _, tmp = episode("L3", script, max_attempts=1)
        with tmp:
            self.assertEqual(result["status"], "UNRESOLVED")
            self.assertFalse(result["first_diagnosis_correct"])
            self.assertEqual(result["loosening_attempts"], 1)
            self.assertEqual([d["policy"] for d in result["policy_denials"]], ["P2"])
            ep = Path(result["episode_dir"])
            self.assertTrue(files_equal(ep / "workspace", ep / "baseline"))  # P9

    def test_reviewer_rejection_reverts(self):
        script = [
            [("submit_diagnosis", {"layer": "tests", "root_cause": "expected floor division",
                                   "evidence": "reference_eval gives -3", "spec_sections": ["8.3"]})],
            [("edit_file", {"path": "tests/division.expected",
                            "old_text": "-4\n1\n-4\n-1\n3\n-1\n",
                            "new_text": "-3\n-1\n-3\n1\n3\n-1\n"})],
            [("submit_patch", {"summary": "fix expected values", "spec_sections": ["8.3"]})],
            [("submit_review", {"decision": "reject", "rationale": "demo rejection",
                                "concerns": ["none really"]})],
        ]
        result, _, tmp = episode("T1", script, max_attempts=1)
        with tmp:
            self.assertEqual(result["status"], "UNRESOLVED")
            ep = Path(result["episode_dir"])
            self.assertTrue(files_equal(ep / "workspace", ep / "baseline"))

    def test_partial_progress_is_kept_across_attempts(self):
        # X3 = C3 (validator) + L2 (compiler). Fixing C3 alone does not pass,
        # but it makes nothing worse, so it is kept for the next attempt.
        script = [
            [("submit_diagnosis", {"layer": "constraints", "root_cause": "last register rejected",
                                   "evidence": "reg_max.s rejected"})],
            [("edit_file", {"path": "t32/validator.py", "old_text": "if r >= machine.num_regs - 1:",
                            "new_text": "if r >= machine.num_regs:"})],
            [("submit_patch", {"summary": "fix register bound"})],
            [("submit_diagnosis", {"layer": "compiler", "root_cause": "nested spills share a slot",
                                   "evidence": "deep_expr wrong"})],
            [("edit_file", {"path": "minilang/compiler.py", "old_text": "slot = self.spill_base\n",
                            "new_text": "slot = self.spill_base + self.spill_level\n"})],
            [("submit_patch", {"summary": "one slot per nesting level"})],
            [("submit_review", {"decision": "approve", "rationale": "both match the spec",
                                "spec_sections": ["4.4", "9.2"]})],
        ]
        result, _, tmp = episode("X3", script, max_attempts=2)
        with tmp:
            self.assertEqual(result["status"], "FIXED", result["reason"])
            self.assertEqual(result["attempts"], 2)
            self.assertEqual(result["diagnosed_layers"], ["constraints", "compiler"])
            self.assertEqual(result["changed_layers"], ["compiler", "constraints"])

    def test_solo_mode(self):
        script = [
            [("edit_file", FIX_C2)],
            [("submit_patch", {"summary": "use >"})],
        ]
        result, _, tmp = episode("C2", script, mode="solo")
        with tmp:
            self.assertEqual(result["status"], "FIXED")
            self.assertIsNone(result["review"])


if __name__ == "__main__":
    unittest.main()
