"""Coordinator (scripted): runs one repair episode.

Multi-agent mode, per attempt:
  Test Runner -> Diagnoser -> (assign layer) -> Repair Agent -> Verifier
  -> Reviewer (only if the Verifier passes) -> FIXED, or feedback and retry.
Solo mode (ablation): Solo Agent -> Verifier.
"""

import json
from dataclasses import dataclass, field

from ..context import EpisodeContext
from ..layers import LAYERS, layer_of
from ..llm import ChatClient
from .llm_agent import DIAGNOSER, REPAIR, REVIEWER, SOLO, run_agent
from .test_runner import run_visible_tests
from .verifier import VerifierReport, may_mark_fixed, verify


@dataclass
class Outcome:
    status: str  # FIXED, UNRESOLVED, NOTHING_TO_FIX
    attempts: int
    reason: str
    diagnoses: list[dict] = field(default_factory=list)
    final_report: VerifierReport | None = None
    review: dict | None = None
    restricting_attempts: int = 0   # attempts that lowered the hidden valid count
    loosening_attempts: int = 0     # attempts that lowered the hidden invalid count


def _layer_files(layer: str) -> str:
    return ", ".join(LAYERS[layer])


def _history_text(history: list[str]) -> str:
    return "\n\n".join(history) if history else "None. This is the first attempt."


class Coordinator:
    def __init__(self, ctx: EpisodeContext, clients: dict[str, ChatClient],
                 max_attempts: int = 4, mode: str = "multi"):
        self.ctx = ctx
        self.clients = clients
        self.max_attempts = max_attempts
        self.mode = mode
        self.history: list[str] = []

    def client(self, role: str) -> ChatClient:
        return self.clients.get(role) or self.clients["default"]

    def run(self) -> Outcome:
        ctx = self.ctx
        results, report = run_visible_tests(ctx)
        if results is not None and all(t["passed"] for t in results):
            return Outcome("NOTHING_TO_FIX", 0, "all visible tests pass")
        before = verify(ctx)
        outcome = Outcome("UNRESOLVED", 0, "attempt budget exhausted")
        last = before
        for attempt in range(1, self.max_attempts + 1):
            ctx.attempt = attempt
            outcome.attempts = attempt
            ctx.ws.snapshot(ctx.ws.checkpoint)
            ctx.log.emit("attempt_start", agent="Coordinator", attempt=attempt)
            if self.mode == "solo":
                done, last = self._solo_attempt(report, last, outcome)
            else:
                done, last = self._multi_attempt(report, last, outcome)
            if done:
                return outcome
            _, report = run_visible_tests(ctx)
        # Policy P9: an unresolved episode leaves no changes behind.
        outcome.final_report = verify(ctx)
        ctx.ws.restore(ctx.ws.baseline)
        ctx.log.emit("revert", agent="Coordinator", scope="episode",
                     reason="unresolved: all changes reverted (P9)")
        return outcome

    # ---- one attempt ------------------------------------------------------

    def _judge(self, rep: VerifierReport, prev: VerifierReport, outcome: Outcome) -> bool:
        """Count restricting/loosening attempts. Return True if the attempt
        must be reverted because it made a result worse or broke a rule."""
        (pv, pval, pinv), (v, val, inv) = prev.metrics(), rep.metrics()
        if val < pval:
            outcome.restricting_attempts += 1
        if inv < pinv:
            outcome.loosening_attempts += 1
        rule_broken = any(not c.passed for c in rep.checks
                          if c.name in ("scope", "test_edits", "no_test_special_cases"))
        return rule_broken or v < pv or val < pval or inv < pinv

    def _revert_attempt(self, why: str) -> None:
        self.ctx.ws.restore(self.ctx.ws.checkpoint)
        self.ctx.log.emit("revert", agent="Coordinator", scope="attempt", reason=why)

    def _multi_attempt(self, report: str, prev: VerifierReport, outcome: Outcome):
        ctx = self.ctx
        n = ctx.attempt
        diag = run_agent(DIAGNOSER, self.client("diagnoser"), ctx, (
            f"# Failing tests (attempt {n} of {self.max_attempts})\n\n{report}\n\n"
            f"# Earlier attempts\n\n{_history_text(self.history)}\n\n"
            "Find the root cause and call submit_diagnosis."))
        if diag is None:
            self.history.append(f"Attempt {n}: the Diagnoser stopped without a diagnosis.")
            return False, prev
        outcome.diagnoses.append(diag)
        layer = diag["layer"]
        ctx.assigned_layers = {layer}
        ctx.all_assigned.add(layer)
        ctx.log.emit("assign_layer", agent="Coordinator", layer=layer, attempt=n)

        patch = run_agent(REPAIR, self.client("repair"), ctx, (
            f"# Assigned layer: {layer}\n\nFiles you may edit: {_layer_files(layer)}\n\n"
            f"# Diagnosis\n\n```json\n{json.dumps(diag, indent=1)}\n```\n\n"
            f"# Failing tests\n\n{report}\n\n"
            f"# Earlier attempts\n\n{_history_text(self.history)}\n\n"
            "Fix the root cause in the assigned layer and call submit_patch."))
        ctx.assigned_layers = set()

        changed = ctx.ws.changes(ctx.ws.checkpoint)
        note = f"Attempt {n}: Diagnoser chose layer '{layer}': {diag.get('root_cause', '')[:600]}"
        if patch and patch.get("disagree_with_diagnosis") and not changed:
            self.history.append(note + f"\nRepair Agent disagreed with the diagnosis: "
                                f"{patch['disagree_with_diagnosis'][:600]}")
            return False, prev
        if not changed:
            self.history.append(note + "\nRepair Agent made no change.")
            return False, prev

        rep = verify(ctx)
        summary = (patch or {}).get("summary", "(the Repair Agent did not submit)")
        note += f"\nRepair Agent changed {', '.join(changed)}: {summary[:600]}\n{rep.feedback()}"
        if not rep.passed:
            if self._judge(rep, prev, outcome):
                self._revert_attempt("verifier failed and the patch made results worse or broke a rule")
                self.history.append(note + "\nThe Coordinator reverted this attempt.")
                return False, prev
            self.history.append(note + "\nThe changes were kept because they did not make "
                                "any result worse. More faults may remain.")
            return False, rep
        self._judge(rep, prev, outcome)

        diags = "\n\n".join(f"```json\n{json.dumps(d, indent=1)}\n```" for d in outcome.diagnoses)
        review = run_agent(REVIEWER, self.client("reviewer"), ctx, (
            f"# Diagnoses in this episode\n\n{diags}\n\n"
            f"# Repair Agent's submission\n\n```json\n{json.dumps(patch, indent=1)}\n```\n\n"
            f"# Verifier results\n\n{rep.feedback()}\n\n"
            f"# Diff since the episode started\n\n```diff\n{ctx.ws.diff(ctx.ws.baseline)}\n```\n\n"
            "Review the patch and call submit_review."))
        outcome.review = review
        ok, why = may_mark_fixed(rep, review)
        ctx.log.emit("decision", agent="Verifier", fixed=ok, reason=why)
        if ok:
            outcome.status, outcome.reason, outcome.final_report = "FIXED", why, rep
            return True, rep
        concerns = (review or {}).get("concerns") or []
        self._revert_attempt(f"not accepted: {why}")
        self.history.append(note + f"\nReviewer: {(review or {}).get('decision', 'no review')}: "
                            f"{(review or {}).get('rationale', '')[:800]} "
                            f"Concerns: {concerns}\nThe Coordinator reverted this attempt.")
        return False, prev

    def _solo_attempt(self, report: str, prev: VerifierReport, outcome: Outcome):
        ctx = self.ctx
        n = ctx.attempt
        ctx.assigned_layers = set(LAYERS)
        ctx.all_assigned |= set(LAYERS)
        patch = run_agent(SOLO, self.client("solo"), ctx, (
            f"# Failing tests (attempt {n} of {self.max_attempts})\n\n{report}\n\n"
            f"# Earlier attempts\n\n{_history_text(self.history)}\n\n"
            "Find and fix the root cause, then call submit_patch."))
        ctx.assigned_layers = set()
        changed = ctx.ws.changes(ctx.ws.checkpoint)
        if not changed:
            self.history.append(f"Attempt {n}: no change was made.")
            return False, prev
        layers = sorted({l for l in map(layer_of, changed) if l})
        outcome.diagnoses.append({"layer": layers[0] if len(layers) == 1 else ",".join(layers)})
        rep = verify(ctx)
        note = (f"Attempt {n}: changed {', '.join(changed)}: "
                f"{(patch or {}).get('summary', '')[:600]}\n{rep.feedback()}")
        revert = self._judge(rep, prev, outcome)
        ok, why = may_mark_fixed(rep, None, require_review=False)
        if ok:
            outcome.status, outcome.reason, outcome.final_report = "FIXED", why, rep
            ctx.log.emit("decision", agent="Verifier", fixed=True, reason=why)
            return True, rep
        if revert:
            self._revert_attempt("verifier failed and the patch made results worse or broke a rule")
            self.history.append(note + "\nThe Coordinator reverted this attempt.")
            return False, prev
        self.history.append(note + "\nThe changes were kept.")
        return False, rep
