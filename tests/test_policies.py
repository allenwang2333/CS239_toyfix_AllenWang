"""Policy enforcement in the tool layer (P1, P2, P3, P5, P7, P9)."""

import unittest

from toyfix.agents.verifier import Check, VerifierReport, may_mark_fixed
from toyfix.context import Flags
from toyfix.tools import call_tool, tools_for

from tests.test_faults import FaultWorkspace


class ToolPolicyTest(unittest.TestCase):
    def setUp(self):
        self.fw = FaultWorkspace("C2")
        self.ctx = self.fw.ctx

    def tearDown(self):
        self.fw.close()

    def call(self, role, name, **args):
        return call_tool(self.ctx, role, role, name, args)

    def test_p1_read_only_roles_cannot_edit(self):
        for role in ("diagnoser", "reviewer"):
            names = {t.name for t in tools_for(role, self.ctx)}
            self.assertNotIn("edit_file", names)
            r = self.call(role, "edit_file", path="t32/validator.py", old_text="a", new_text="b")
            self.assertTrue(r.denied)
            self.assertIn("P1", r.text)
        self.assertEqual(self.ctx.ws.changes(self.ctx.ws.baseline), {})

    def test_p2_repair_edits_only_the_assigned_layer(self):
        self.ctx.assigned_layers = {"compiler"}
        r = self.call("repair", "edit_file", path="t32/validator.py",
                      old_text="if program.data_words >= machine.mem_words:",
                      new_text="if program.data_words > machine.mem_words:")
        self.assertTrue(r.denied)
        self.assertIn("P2", r.text)
        self.ctx.assigned_layers = {"constraints"}
        r = self.call("repair", "edit_file", path="t32/validator.py",
                      old_text="if program.data_words >= machine.mem_words:",
                      new_text="if program.data_words > machine.mem_words:")
        self.assertTrue(r.ok, r.text)
        self.assertEqual(self.ctx.ws.changes(self.ctx.ws.baseline), {"t32/validator.py": "modified"})

    def test_p3_protected_files(self):
        self.ctx.assigned_layers = {"tests", "constraints", "compiler", "simulator"}
        for path in ("spec.md", "machines/t32-tiny.toml", "minilang/reference.py", "cli.py"):
            r = self.call("repair", "edit_file", path=path, old_text="a", new_text="b")
            self.assertTrue(r.denied, path)
            self.assertIn("P3", r.text)

    def test_p5_no_new_files(self):
        self.ctx.assigned_layers = {"tests"}
        r = self.call("repair", "edit_file", path="tests/new.expected", old_text="x", new_text="y")
        self.assertTrue(r.denied)

    def test_p7_paths_stay_inside_the_workspace(self):
        for path in ("../baseline/t32/validator.py", "/etc/passwd",
                     "../../toyfix/hidden/corpus/valid/imm_min.s", "../scoreboard/fault.json"):
            r = self.call("diagnoser", "read_file", path=path)
            self.assertTrue(r.denied, path)
            self.assertIn("P7", r.text)

    def test_p7_corpus_feedback_is_aggregate_only(self):
        r = self.call("repair", "check_corpus")
        self.assertTrue(r.ok)
        self.assertRegex(r.text, r"^hidden valid programs accepted and correct: \d+/\d+\n"
                                 r"hidden invalid programs rejected: \d+/\d+$")

    def test_p9_tool_budget(self):
        self.ctx.agent_tool_budget = 2
        self.assertTrue(self.call("diagnoser", "read_spec", section="4.4").ok)
        self.assertTrue(self.call("diagnoser", "read_spec", section="4.2").ok)
        r = self.call("diagnoser", "read_spec", section="4.3")
        self.assertTrue(r.denied)
        self.assertIn("P9", r.text)
        # The finish tool still works so the agent can submit.
        r = self.call("diagnoser", "submit_diagnosis", layer="constraints", root_cause="x",
                      evidence="y")
        self.assertTrue(r.ok)

    def test_ablation_flags_remove_tools(self):
        self.ctx.flags = Flags(oracle=False, corpus_feedback=False)
        names = {t.name for t in tools_for("repair", self.ctx)}
        self.assertNotIn("reference_eval", names)
        self.assertNotIn("check_corpus", names)

    def test_read_and_run_tools(self):
        self.assertIn("4.4. A program is **valid**", self.call("diagnoser", "read_spec", section="4.4").text)
        r = self.call("diagnoser", "run_tests", filter="full_memory")
        self.assertIn("0/1 visible tests passed", r.text)
        r = self.call("diagnoser", "validate_program", path="tests/full_memory.s")
        self.assertIn("data_words=256", r.text)
        r = self.call("diagnoser", "run_program", source="print 2 + 3;")
        self.assertIn('"actual": "5"', r.text)
        r = self.call("diagnoser", "trace_execution", source="addi r1, r0, 4\nout r1\nhalt",
                      kind="asm", limit=5)
        self.assertIn("r1=4", r.text)
        r = self.call("diagnoser", "reference_eval", source="print -7 / 2;")
        self.assertEqual(r.text.strip(), "-3")
        r = self.call("diagnoser", "search_code", pattern="mem_words")
        self.assertIn("t32/validator.py", r.text)

    def test_submit_validation(self):
        r = self.call("diagnoser", "submit_diagnosis", layer="spec", root_cause="x", evidence="y")
        self.assertFalse(r.ok)
        self.ctx.assigned_layers = {"constraints"}
        r = self.call("repair", "submit_patch", summary="nothing")
        self.assertFalse(r.ok)  # no change and no disagreement


class FinalDecisionTest(unittest.TestCase):
    def report(self, passed=True, changed=None):
        return VerifierReport(checks=[Check("x", "P8", passed)], changed_files=changed or {})

    def test_p8_needs_verifier_and_review(self):
        approve = {"decision": "approve", "rationale": "ok", "spec_sections": ["4.4"]}
        self.assertTrue(may_mark_fixed(self.report(), approve)[0])
        self.assertFalse(may_mark_fixed(self.report(False), approve)[0])
        self.assertFalse(may_mark_fixed(self.report(), {"decision": "reject"})[0])
        self.assertFalse(may_mark_fixed(self.report(), None)[0])

    def test_p4_test_change_needs_spec_citation(self):
        rep = self.report(changed={"tests/division.expected": "modified"})
        self.assertFalse(may_mark_fixed(rep, {"decision": "approve", "rationale": "ok"})[0])
        self.assertTrue(may_mark_fixed(rep, {"decision": "approve", "rationale": "ok",
                                             "spec_sections": ["8.3"]})[0])


if __name__ == "__main__":
    unittest.main()
