"""Verifier (rule-based): objective acceptance checks for a patch.

Only the Verifier may mark an episode FIXED (policy P8).
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..context import EpisodeContext
from ..layers import is_protected, layer_of
from ..tools import corpus_counts


@dataclass
class Check:
    name: str
    policy: str
    passed: bool
    detail: str = ""


@dataclass
class VerifierReport:
    checks: list[Check] = field(default_factory=list)
    visible: tuple[int, int] = (0, 0)
    valid: tuple[int, int] | None = None
    invalid: tuple[int, int] | None = None
    failing_tests: list[str] = field(default_factory=list)
    changed_files: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def metrics(self) -> tuple[int, int, int]:
        return (self.visible[0], self.valid[0] if self.valid else -1,
                self.invalid[0] if self.invalid else -1)

    def feedback(self) -> str:
        """Text for agents. It names visible tests but never hidden programs (P7)."""
        lines = [f"Verifier: {'PASS' if self.passed else 'FAIL'}"]
        for c in self.checks:
            lines.append(f"- [{'ok' if c.passed else 'FAIL'}] {c.name} ({c.policy}): {c.detail}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        return d


def _comment_only(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("//") or s.startswith(";")


def verify(ctx: EpisodeContext) -> VerifierReport:
    ws = ctx.ws
    rep = VerifierReport()
    changes = ws.changes(ws.baseline)
    rep.changed_files = changes
    added = ws.added_lines(ws.baseline)

    # Scope: protected files, layer assignment, test files kept (P2, P3, P5).
    problems = []
    for rel, status in changes.items():
        layer = layer_of(rel)
        if is_protected(rel):
            problems.append(f"{rel}: protected file changed (P3)")
        elif layer is None:
            problems.append(f"{rel}: file outside every repair layer was {status}")
        elif layer not in ctx.all_assigned:
            problems.append(f"{rel}: layer '{layer}' was never assigned (P2)")
        if rel.startswith("tests/") and status != "modified":
            problems.append(f"{rel}: test file {status} (P5)")
    rep.checks.append(Check("scope", "P2/P3/P5", not problems,
                            "; ".join(problems) or f"{len(changes)} file(s) changed, all in scope"))

    # Visible tests.
    res = ws.sut("test")
    if isinstance(res, dict):
        rep.checks.append(Check("visible_tests", "P8", False, res.get("error", "")[:500]))
        test_results = []
    else:
        test_results = res
        failing = [t["name"] for t in res if not t["passed"]]
        rep.visible = (len(res) - len(failing), len(res))
        rep.failing_tests = failing
        rep.checks.append(Check("visible_tests", "P8", not failing,
                                f"{rep.visible[0]}/{rep.visible[1]} passed"
                                + (f"; failing: {', '.join(failing)}" if failing else "")))

    # Test edits: MiniLang expectations must equal the reference; test
    # programs may change only in comments (P4, P5).
    problems = []
    for rel, status in changes.items():
        if not rel.startswith("tests/") or status != "modified":
            continue
        path = Path(rel)
        if path.suffix == ".expected" and (ws.dir / path.with_suffix(".ml")).exists():
            ref = ws.sut("reference", str(ws.dir / path.with_suffix(".ml")))
            want = ref.get("result") if isinstance(ref, dict) else None
            got = (ws.dir / rel).read_text()
            if want is None or [l.rstrip() for l in got.strip().splitlines()] != \
                    [l.rstrip() for l in want.strip().splitlines()]:
                problems.append(f"{rel}: new expected result differs from the reference interpreter (P4)")
        elif path.suffix in (".ml", ".s"):
            old = (ws.baseline / rel).read_text().splitlines()
            new = (ws.dir / rel).read_text().splitlines()
            removed = [l for l in old if l not in new]
            if any(not _comment_only(l) for l in removed + added.get(rel, [])):
                problems.append(f"{rel}: test program code changed (P5)")
    rep.checks.append(Check("test_edits", "P4/P5", not problems,
                            "; ".join(problems) or "no invalid test edits"))

    # No special cases for tests in toolchain code (P5).
    names = {t["name"] for t in test_results}
    problems = []
    for rel, lines in added.items():
        if rel.startswith("tests/"):
            continue
        for line in lines:
            hits = [n for n in names if re.search(rf"\b{re.escape(n)}\.(ml|s|expected)\b", line)]
            if "tests/" in line or ".expected" in line or hits:
                problems.append(f"{rel}: '{line.strip()[:80]}'")
    rep.checks.append(Check("no_test_special_cases", "P5", not problems,
                            "; ".join(problems) or "none found"))

    # Hidden corpus (P6). Only counts are reported.
    counts = corpus_counts(ctx)
    rep.valid, rep.invalid = counts["valid"], counts["invalid"]
    for key, label in (("valid", "valid programs accepted and correct"),
                       ("invalid", "invalid programs rejected")):
        c = counts[key]
        ok = c is not None and c[0] == c[1]
        detail = "toolchain crashed" if c is None else f"{c[0]}/{c[1]} {label}"
        rep.checks.append(Check(f"hidden_{key}_corpus", "P6", ok, detail))

    ctx.log.emit("verifier_report", agent="Verifier", passed=rep.passed,
                 checks=[asdict(c) for c in rep.checks])
    return rep


def may_mark_fixed(rep: VerifierReport, review: dict | None, require_review: bool = True) -> tuple[bool, str]:
    """Final decision (P4, P8)."""
    if not rep.passed:
        return False, "verifier checks failed"
    if not require_review:
        return True, "verifier checks passed (no review in this mode)"
    if not review or review.get("decision") != "approve":
        return False, "the Reviewer did not approve"
    tests_changed = any(r.startswith("tests/") for r in rep.changed_files)
    if tests_changed and not review.get("spec_sections"):
        return False, "test files changed but the approval cites no spec paragraph (P4)"
    return True, "verifier checks passed and the Reviewer approved"
