"""Test Runner (scripted): runs the visible tests and builds the failure report."""

from ..context import EpisodeContext
from ..tools import format_test_report


def run_visible_tests(ctx: EpisodeContext) -> tuple[list[dict] | None, str]:
    """Return (per-test results, report text). Results are None if the
    toolchain crashed before it could report."""
    res = ctx.ws.sut("test")
    if isinstance(res, dict):
        text = f"The test runner could not run: {res.get('error')}"
        ctx.log.emit("test_report", agent="Test Runner", passed=None, total=None, report=text)
        return None, text
    text = format_test_report(res)
    failing = [t["name"] for t in res if not t["passed"]]
    ctx.log.emit("test_report", agent="Test Runner", passed=len(res) - len(failing),
                 total=len(res), failing=failing, report=text)
    return res, text
