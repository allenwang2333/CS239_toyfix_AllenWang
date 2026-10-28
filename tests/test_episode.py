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

FIX_C2 = {"path": "npu/validator.py",
          "old_text": "if v >= stride_limit - 1:",
          "new_text": "if v >= stride_limit:"}


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
            [("run_tests", {"filter": "npu_stride_max"})],
            [("edit_file", FIX_C2)],  # denied: P1
            [("submit_diagnosis", {"layer": "constraints", "files": ["npu/validator.py"],
                                   "root_cause": "rstride = 2^stride_bits - 1 is rejected",
                                   "evidence": "npu_stride_max.npu is rejected",
                                   "spec_sections": ["4.2", "4.4"]})],
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
            self.assertEqual(list(result["final_valid_corpus"]), [29, 29])
            self.assertEqual([d["policy"] for d in result["policy_denials"]], ["P1"])
            ep = Path(result["episode_dir"])
            self.assertIn("if v >= stride_limit:",
                          (ep / "workspace/npu/validator.py").read_text())
            self.assertIn("FIXED", (ep / "trajectory.md").read_text())

            # P7: no fault metadata in anything an agent saw.
            seen = json.dumps(client.seen)
            fault = CATALOG["C2"]
            for secret in (fault.title, fault.tempting_fix, "scoreboard", "hidden/corpus"):
                self.assertNotIn(secret, seen)

    def test_wrong_layer_loosening_is_reverted_and_episode_unresolved(self):
        script = [
            [("submit_diagnosis", {"layer": "constraints", "root_cause": "validator rejects "
                                   "valid programs", "evidence": "fusion_uses is wrong"})],
            # Repair Agent: tries the compiler first (denied), then loosens the validator.
            [("edit_file", {"path": "minilang/compiler.py", "old_text": "x", "new_text": "y"})],
            [("edit_file", {"path": "npu/validator.py",
                            "old_text": "if v >= stride_limit:",
                            "new_text": "if v >= stride_limit * 2:"})],
            [("submit_patch", {"summary": "accept longer strides"})],
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
            [("submit_diagnosis", {"layer": "tests", "root_cause": "expected relu before bias",
                                   "evidence": "reference_eval differs", "spec_sections": ["8.5"]})],
            [("edit_file", {"path": "tests/dense_layer.expected",
                            "old_text": "3 -20 0 7 -1\n3 -20 0 7 -1\n",
                            "new_text": "0 0 0 0 0\n1 0 0 3 0\n"})],
            [("submit_patch", {"summary": "fix expected values", "spec_sections": ["8.5"]})],
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
            [("submit_diagnosis", {"layer": "constraints", "root_cause": "alignment checked on spad",
                                   "evidence": "npu_align.npu rejected"})],
            [("edit_file", {"path": "npu/validator.py",
                            "old_text": 'if get("spad") % machine.dma_align != 0:',
                            "new_text": 'if get("dram") % machine.dma_align != 0:'})],
            [("submit_patch", {"summary": "check alignment on the DRAM address"})],
            [("submit_diagnosis", {"layer": "compiler", "root_cause": "a result overlaps a "
                                   "dying operand", "evidence": "reuse wrong"})],
            [("edit_file", {"path": "minilang/passes.py",
                            "old_text": "            for r in dict.fromkeys(root[v] for v in op.operands):\n"
                                        "                if last[r] == i and r in region:\n"
                                        "                    alloc.free(*region.pop(r))\n"
                                        "            shape = op.result.type.shape\n",
                            "new_text": "            shape = op.result.type.shape\n"})],
            [("submit_patch", {"summary": "free operands after the result is allocated"})],
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
