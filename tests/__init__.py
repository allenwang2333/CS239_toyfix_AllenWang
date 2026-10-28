"""Offline test suite for ToyFix. No LLM or network access is needed.

Run from the repository root:  python3 -m unittest discover -s tests -t . -v
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
for p in (SRC, SRC / "sut"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
