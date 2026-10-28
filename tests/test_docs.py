"""The submitted requirements docs match the code."""

import re
import unittest

from toyfix.agents.llm_agent import DIAGNOSER, REPAIR, REVIEWER, SOLO
from toyfix.make_docs import FILE_NAMES
from toyfix.tools import TOOLS

from tests import SRC

DOCS = SRC.parent / "toyfix"


class DocsTest(unittest.TestCase):
    def test_required_files(self):
        for name in ("app.md", "policy.md", "tools.md"):
            self.assertTrue((DOCS / name).is_file(), name)
        self.assertTrue(list((DOCS / "episodes").glob("*.md")))

    def test_llm_agent_docs_contain_the_exact_prompt(self):
        for spec in (DIAGNOSER, REPAIR, REVIEWER, SOLO):
            doc = (DOCS / "agents" / FILE_NAMES[spec.role]).read_text()
            self.assertIn(spec.system_prompt.strip(), doc, spec.name)

    def test_tools_md_lists_every_tool_one_per_line(self):
        lines = (DOCS / "tools.md").read_text().splitlines()
        names = [l.split(":", 1)[0] for l in lines if l.strip()]
        self.assertTrue(all(re.fullmatch(r"[\w.]+", n) for n in names), names)
        self.assertLessEqual(set(TOOLS), set(names))

    def test_policies_are_numbered_paragraphs(self):
        paras = [p for p in (DOCS / "policy.md").read_text().split("\n\n") if p.strip()]
        self.assertGreaterEqual(len(paras), 3)
        for i, p in enumerate(paras, 1):
            self.assertTrue(p.startswith(f"P{i}. "), p[:20])


if __name__ == "__main__":
    unittest.main()
