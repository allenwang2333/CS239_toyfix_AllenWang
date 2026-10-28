"""NPU hardware profiles (spec §4.1)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

MACHINES_DIR = Path(__file__).resolve().parent.parent / "machines"


@dataclass(frozen=True)
class NpuMachine:
    name: str
    mm_shape: tuple[int, int, int]  # largest m, k, n of mm and mma
    vlen: int
    has_mma: bool
    stride_bits: int
    dma_align: int
    spad_words: int
    dram_words: int

    @property
    def mm_m(self) -> int:
        return self.mm_shape[0]

    @property
    def mm_k(self) -> int:
        return self.mm_shape[1]

    @property
    def mm_n(self) -> int:
        return self.mm_shape[2]


def load_npu_machine(name: str) -> NpuMachine:
    path = MACHINES_DIR / f"{name}.toml"
    if not path.is_file():
        raise ValueError(f"unknown NPU profile: {name}")
    with path.open("rb") as f:
        data = tomllib.load(f)
    data["mm_shape"] = tuple(data["mm_shape"])
    return NpuMachine(name=name, **data)


def list_npu_machines() -> list[str]:
    return sorted(p.stem for p in MACHINES_DIR.glob("npu-*.toml"))
