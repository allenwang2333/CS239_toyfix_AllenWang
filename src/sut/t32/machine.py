"""Hardware profiles (spec §4.1)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

MACHINES_DIR = Path(__file__).resolve().parent.parent / "machines"


@dataclass(frozen=True)
class Machine:
    name: str
    num_regs: int
    imm_bits: int
    branch_bits: int
    jump_bits: int
    mem_words: int
    has_mul: bool


def load_machine(name: str) -> Machine:
    path = MACHINES_DIR / f"{name}.toml"
    if not path.is_file():
        raise ValueError(f"unknown machine profile: {name}")
    with path.open("rb") as f:
        data = tomllib.load(f)
    return Machine(name=name, **data)


def list_machines() -> list[str]:
    return sorted(p.stem for p in MACHINES_DIR.glob("*.toml"))
