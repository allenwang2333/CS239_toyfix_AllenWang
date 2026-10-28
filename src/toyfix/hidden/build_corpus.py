"""Build the hidden corpus that the Verifier uses (policy P6, P7).

valid/   programs that every correct toolchain must accept and run correctly.
invalid/ programs that a validator must reject (expected "<rejected>").

MiniLang expected results come from the reference interpreter. NPU assembly
expected results are written by hand from the spec.

Run: python3 -m toyfix.hidden.build_corpus   (from src/)
"""

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUT = HERE.parent.parent / "sut"
OUT = HERE / "corpus"


def ml(machine: str, body: str) -> str:
    return f"# machine: {machine}\n{body.strip()}\n"


def npu(machine: str, body: str) -> str:
    return f"; machine: {machine}\n{body.strip()}\n"


VALID_ML = {
    "mlp_tiny": ml("npu-tiny", """
def dense(x: Tensor[3, 5, i32], w: Tensor[5, 3, i32], b: Tensor[3, i32]) -> Tensor[3, 3, i32]:
    return relu(x @ w + b)

def main():
    x = iota((3, 5)) - 6
    w1 = tensor([[1, -2, 0], [2, 1, -1], [0, 3, 1], [-1, 0, 2], [1, 1, 1]])
    h = dense(x, w1, tensor([1, -2, 3]))
    print(h)
    print(h @ tensor([[2, -1], [0, 1], [1, 3]]) + tensor([-5, 5]))
"""),
    "mlp_wide": ml("npu-wide", """
def main():
    x = iota((6, 12)) - 30
    w = iota((12, 10)) * 3 - 170
    b = iota(10) * 100 - 450
    h = relu(x @ w + b)
    print(h)
    print(h @ iota((10, 3)))
"""),
    "edge_base": ml("npu-base", """
def main():
    a = iota((5, 7)) - 17
    b = iota((7, 6)) * 2 - 41
    print(a @ b)
    print(a * 3 + iota((5, 7)))
"""),
    "matmul_k_tiny": ml("npu-tiny", """
def main():
    a = tensor([[1, 2, 3, 4, 5, 6, 7]])
    b = tensor([[1], [-1], [2], [-2], [3], [-3], [4]])
    print(a @ b)
    print(b @ a)
"""),
    "large_matmul": ml("npu-base", """
def main():
    a = iota((16, 16)) - 100
    b = iota((16, 16)) * -1 + 128
    print(a @ b)
"""),
    "transpose_mix": ml("npu-tiny", """
def main():
    x = tensor([[1, -2, 3, 4, 0], [5, 6, -7, 8, 1], [2, 0, 1, -1, 3]])
    print(x.T @ x)
    print((x * 2 + tensor([1, 2, 3, 4, 5])).T)
    print(transpose(x @ x.T - 1))
"""),
    "transpose_wide": ml("npu-wide", """
def main():
    a = iota((3, 11)) - 9
    print(a.T)
    print(a.T @ a - transpose(a).T.T @ a)
    print(a @ a.T)
"""),
    "broadcast_rect": ml("npu-base", """
def main():
    m = iota((3, 6)) - 4
    v = tensor([10, -20, 30, -40, 50, -60])
    print(m + v)
    print(v - m)
    print(m * v + 1)
"""),
    "broadcast_tiny": ml("npu-tiny", """
def main():
    m = iota((5, 3))
    b = tensor([1, 10, 100])
    print(relu(m @ tensor([[1, -1, 0], [0, 1, -1], [-1, 0, 1]]) + b))
"""),
    "reuse_chain_tiny": ml("npu-tiny", """
def main():
    y = iota((4, 4)) - 7
    w = tensor([[1, 0, 0, 1], [0, 2, 1, 0], [0, 1, -1, 1], [1, 0, 0, -1]])
    for i in range(3):
        y = relu(y @ w) - 3
    print(y)
"""),
    "reuse_base": ml("npu-base", """
def main():
    x = iota((8, 8)) - 30
    w = iota((8, 8)) - 32
    for i in range(3):
        x = x @ w - 7
        print(x)
"""),
    "fusion_shared": ml("npu-wide", """
def main():
    x = iota((4, 9)) - 20
    w = iota((9, 4)) - 18
    y = x @ w + tensor([5, -500, 50, -5])
    r = relu(y)
    print(y)
    print(r)
"""),
    "fusion_shared_tiny": ml("npu-tiny", """
def main():
    x = tensor([[2, -3, 1], [-1, 4, -2], [0, -1, 5]])
    y = x @ x + 1
    print(relu(y))
    print(y - relu(y))
"""),
    "wrap_mix": ml("npu-base", """
def main():
    a = full((2, 3), 1073741824)
    print(a + a)
    print(a * 4)
    m = tensor([[46341, 46341], [-46341, 46341]])
    print(m @ m)
    print(-full(2, -2147483648) - 1)
"""),
    "scalars_tiny": ml("npu-tiny", """
def bump(x: Tensor[5, i32], k: int) -> Tensor[5, i32]:
    return x * k + k

def main():
    v = tensor([3, -1, 4, -1, 5])
    s = 0
    for k in range(1, 6):
        v = bump(v, k) - 7 * k
        s += k * k
    print(v)
    print(s)
    print(-v)
    print(ones(5) - v * 0)
"""),
    "identity_folds": ml("npu-base", """
def main():
    x = iota((3, 5)) - 7
    print(x + 0)
    print(x * 1 - 0)
    print(x * 0)
    print(relu(relu(x)))
    print(x.T.T)
    print(relu(full((2, 2), -3)) + full((2, 2), 4) * 2)
    print(x @ zeros((5, 2)) + x @ ones((5, 2)))
"""),
    "print_views": ml("npu-base", """
def main():
    v = tensor([7, 8, 9])
    print(zeros((2, 3)) + v)
    print(tensor([[1, 2], [3, 4], [5, 6]]).T)
    print(full(4, -9))
    print(123)
"""),
    "big_data_tiny": ml("npu-tiny", """
def main():
    a = iota((10, 12))
    print(a + a)
"""),
    "long_rows_tiny": ml("npu-tiny", """
def main():
    a = iota((2, 24))
    print(a + relu(a))
    x = iota((2, 18))
    print(x @ x.T)
"""),
    "long_rows_base": ml("npu-base", """
def main():
    a = iota((2, 260))
    print(relu(a - 300))
"""),
    "wide_k_wide": ml("npu-wide", """
def main():
    x = iota((5, 40)) - 77
    w = iota((40, 7)) - 140
    print(relu(x @ w + iota(7) * 1000))
    print(transpose(x) @ (x @ w))
"""),
    "acc_tiny": ml("npu-tiny", """
def main():
    x = tensor([[-4, 3, -2, 1, 0, -1, 2], [5, -6, 7, -8, 9, -1, 0], [1, 1, -1, 1, -1, 1, 1]])
    w = iota((7, 3)) - 10
    print(x @ w + tensor([1, 2, 3]))
    print(relu(x @ (w * 2)))
"""),
}

VALID_NPU = {
    "npu_spad_end_base": (npu("npu-base", """
.data 32
.word 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
  load 48, 0, 4, 4, 4, 1
  load 32, 0, 4, 4, 4, 1
  vadd 48, 48, 32, 8
  vadd 56, 56, 40, 8
  store 16, 48, 4, 4, 4
  out 16, 1, 16, 0, 1
"""), " ".join(str(2 * i) for i in range(1, 17))),
    "npu_full_dram_tiny": (npu("npu-tiny", """
.data 256
.word 255, 77
  load 0, 254, 1, 2, 0, 1
  store 0, 0, 1, 2, 0
  out 0, 1, 2, 0, 1
  out 254, 1, 2, 0, 1
"""), "0 77\n0 77"),
    "npu_mm_max_base": (npu("npu-base", """
.data 16
.word 0, 3
  load 0, 0, 4, 4, 0, 0
  load 16, 0, 4, 4, 0, 0
  mm 32, 0, 16, 4, 4, 4
  mma 32, 0, 16, 4, 4, 4
  vadd 32, 32, 0, 8
  store 0, 32, 4, 4, 4
  out 0, 4, 4, 4, 1
"""), "75 75 75 75\n75 75 75 75\n72 72 72 72\n72 72 72 72"),
    "npu_stride_max_base": (npu("npu-base", """
.data 260
.word 0, 5
.word 255, 9
  load 0, 0, 2, 1, 255, 0
  vmul 0, 0, 0, 2
  store 4, 0, 2, 1, 252
  out 4, 2, 1, 252, 0
"""), "25\n81"),
    "npu_wide_shape": (npu("npu-wide", """
.data 48
.word 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
.word 16, 1
  load 0, 0, 8, 16, 0, 1
  load 128, 16, 16, 4, 0, 0
  mm 192, 0, 128, 8, 16, 4
  vadd 192, 192, 192, 32
  store 16, 192, 8, 4, 4
  out 16, 1, 4, 0, 1
  out 44, 1, 4, 0, 1
"""), "272 272 272 272\n272 272 272 272"),
    "npu_wrap": (npu("npu-base", """
.data 8
.word 0, 2147483647, 65536, -2147483648
.word 4, 65536
  load 0, 0, 1, 3, 0, 1
  vadd 0, 0, 0, 3
  store 0, 0, 1, 3, 0
  out 0, 1, 3, 0, 1
  load 0, 4, 1, 1, 0, 0
  mm 4, 0, 0, 1, 1, 1
  store 4, 4, 1, 1, 0
  out 4, 1, 1, 0, 0
"""), "-2 131072 0\n0"),
    "npu_align_tiny": (npu("npu-tiny", """
.data 4
.word 2, 5, -6
  load 1, 2, 1, 2, 0, 1
  vrelu 3, 1, 2
  store 0, 3, 1, 2, 0
  out 1, 1, 3, 0, 1
"""), "0 5 -6"),
}

INVALID_NPU = {
    "npu_len_base": npu("npu-base", "  vadd 0, 0, 16, 9"),
    "npu_len_wide": npu("npu-wide", "  vrelu 0, 0, 65"),
    "npu_spad_tiny": npu("npu-tiny", "  mm 13, 0, 4, 2, 2, 2"),
    "npu_k_wide": npu("npu-wide", "  mm 0, 0, 0, 1, 17, 1"),
    "npu_m_base": npu("npu-base", "  mm 0, 0, 0, 5, 1, 1"),
    "npu_mma_tiny": npu("npu-tiny", "  mma 0, 0, 0, 1, 1, 1"),
    "npu_stride_base": npu("npu-base", ".data 600\n  load 0, 0, 2, 1, 256, 0"),
    "npu_stride_store_tiny": npu("npu-tiny", ".data 64\n  store 0, 0, 2, 1, 16"),
    "npu_align_store_tiny": npu("npu-tiny", ".data 4\n  store 1, 0, 1, 1, 0"),
    "npu_align_wide": npu("npu-wide", ".data 8\n  load 0, 6, 1, 1, 0, 0"),
    "npu_rows_zero": npu("npu-base", ".data 4\n  load 0, 0, 0, 1, 1, 1"),
    "npu_dram_read": npu("npu-base", ".data 8\n  load 0, 0, 2, 2, 4, 4"),
    "npu_out_range": npu("npu-wide", ".data 6\n  out 0, 3, 2, 3, 1"),
    "npu_dram_size": npu("npu-tiny", ".data 257"),
    "npu_word_outside": npu("npu-base", ".data 10\n.word 8, 1, 2, 3"),
}


def main() -> None:
    sys.path.insert(0, str(SUT))
    from cli import execute, kind_of, normalize, reference_text  # noqa: E402

    if OUT.exists():
        shutil.rmtree(OUT)
    valid, invalid = OUT / "valid", OUT / "invalid"
    valid.mkdir(parents=True)
    invalid.mkdir(parents=True)

    for name, src in VALID_ML.items():
        ref = reference_text(src)
        assert ref["ok"], (name, ref)
        (valid / f"{name}.ml").write_text(src)
        (valid / f"{name}.expected").write_text(ref["result"] + "\n")
    for name, (src, expected) in VALID_NPU.items():
        (valid / f"{name}.npu").write_text(src)
        (valid / f"{name}.expected").write_text(expected + "\n")
    for name, src in INVALID_NPU.items():
        (invalid / f"{name}.npu").write_text(src)
        (invalid / f"{name}.expected").write_text("<rejected>\n")

    # The clean toolchain must pass the whole corpus.
    bad = []
    for d in (valid, invalid):
        for src in sorted(d.iterdir()):
            if src.suffix not in (".ml", ".npu"):
                continue
            text = src.read_text()
            machine = text.splitlines()[0].split("machine:")[1].strip()
            res = execute(text, kind_of(src), machine)
            want = src.with_suffix(".expected").read_text()
            if normalize(res["actual"]) != normalize(want):
                bad.append((src.name, res["actual"][:80], want[:80], res.get("detail", "")[:120]))
    for b in bad:
        print("MISMATCH", *b)
    n_valid = len(list(valid.glob("*.expected")))
    n_invalid = len(list(invalid.glob("*.expected")))
    print(f"corpus: {n_valid} valid, {n_invalid} invalid, {len(bad)} mismatches")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
