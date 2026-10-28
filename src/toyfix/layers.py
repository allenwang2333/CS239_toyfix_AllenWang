"""Repair layers of the toolchain and the files each layer owns."""

from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
SUT_DIR = PKG_DIR.parent / "sut"
CORPUS_DIR = PKG_DIR / "hidden" / "corpus"
PROMPTS_DIR = PKG_DIR / "prompts"

# Layer name -> workspace-relative files or directory prefixes (ending in "/").
LAYERS: dict[str, list[str]] = {
    "tests": ["tests/"],
    "constraints": ["t32/validator.py"],
    "compiler": ["minilang/compiler.py"],
    "simulator": ["t32/isa.py", "t32/assembler.py", "t32/simulator.py"],
}

# Files that no agent may modify (policy P3).
PROTECTED: list[str] = [
    "spec.md", "machines/", "cli.py", "t32/machine.py", "t32/__init__.py",
    "minilang/parser.py", "minilang/reference.py", "minilang/__init__.py",
]


def _matches(rel: str, patterns: list[str]) -> bool:
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in patterns)


def layer_of(rel: str) -> str | None:
    for name, patterns in LAYERS.items():
        if _matches(rel, patterns):
            return name
    return None


def is_protected(rel: str) -> bool:
    return _matches(rel, PROTECTED)
