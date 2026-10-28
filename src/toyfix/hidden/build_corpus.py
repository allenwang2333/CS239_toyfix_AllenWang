"""Build the hidden corpus that the Verifier uses (policy P6, P7).

valid/   programs that every correct toolchain must accept and run correctly.
invalid/ programs that the validator must reject (expected "<rejected>").

MiniLang expected results come from the reference interpreter. Assembly
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
    return f"// machine: {machine}\n{body.strip()}\n"


def asm(machine: str, body: str) -> str:
    return f"; machine: {machine}\n{body.strip()}\n"


def nops(n: int) -> str:
    return "\n".join("  addi r0, r0, 0" for _ in range(n))


VALID_ML = {
    "const_edges": ml("t32-base", """
print 2048; print 6144; print -2048; print -4096; print 4095; print 4096;
print 2147481600; print -2147483648; print 1048576; print 3221225472;
"""),
    "const_tiny": ml("t32-tiny", """
var a = 2048; var b = 3000; var c = -70000;
print a; print b; print c; print a + b + c; print 1000000007;
"""),
    "const_wide": ml("t32-wide", """
print 32767; print 32768; print -32768; print -32769; print 100000; print 34816;
"""),
    "div_mix": ml("t32-base", """
var m = -2147483648;
print m / -1; print m % -1; print 100 / 7; print -100 / 7; print 100 % -7;
print -1 / 2; print 1 / -2; print -9 % 3; print 9 / 9;
"""),
    "div_tiny": ml("t32-tiny", """
var x = -45; print x / 4; print x % 4; print x / -4; print 45 % -4;
"""),
    "div_zero": ml("t32-base", """
var z = 0; print 5; print 1 / z; print 6;
"""),
    "shift_mix": ml("t32-base", """
var n = -1000; print n >> 3; print n >> 31; print n >> 32; print n << 4;
print 7 << 28; print 2147483647 >> 30; print -2147483648 >> 1;
"""),
    "deep_base": ml("t32-base", """
var a = 3;
print a+(a+(a+(a+(a+(a+(a+(a+(a+(a+(a+(a+(a+(a+(a+(a+(a+(a+(a+1))))))))))))))))));
print ((1-(2-(3-(4-(5-(6-(7-(8-(9-(10-(11-(12-(13-(14-(15-(16-17))))))))))))))))) * 2;
"""),
    "deep_tiny": ml("t32-tiny", """
array v[4];
v[0] = 5; v[1] = -6; v[2] = 7; v[3] = 9;
var k = 2;
print v[0] + (v[1] * (v[2] - (v[3] + (k * (k + (k - (1 + (2 + 3))))))));
print (k == (2 + (0 * (1 + (2 + (3 + (4 + 5))))))) + (k < (1 + (1 + (1 + (1 + 1)))));
"""),
    "mul_neg": ml("t32-tiny", """
var a = -12345; var b = 678;
print a * b; print b * a; print a * a; print -1 * -1; print 65537 * 65537;
print -2147483648 * -1; print 3 * 0 * a;
"""),
    "mul_base": ml("t32-base", """
var a = -12345; var b = 678; print a * b; print 65537 * 65537; print -7 * -7;
"""),
    "long_if": ml("t32-tiny", """
var x = 1; var s = 0;
if (x) {
""" + "\n".join(f"  s = s + {i % 7};" for i in range(60)) + """
} else {
""" + "\n".join(f"  s = s - {i % 5};" for i in range(60)) + """
}
print s;
x = 0;
if (x) { s = 0; } else {
""" + "\n".join(f"  s = s + {i % 3};" for i in range(70)) + """
}
print s;
"""),
    "long_base": ml("t32-base", """
var i = 0; var s = 0;
while (i < 2) {
""" + "\n".join(f"  s = s + {i % 11};" for i in range(560)) + """
  i = i + 1;
}
print s;
"""),
    "nested_long_tiny": ml("t32-tiny", """
var i = 0; var j = 0; var s = 0;
while (i < 3) {
  j = 0;
  while (j < 2) {
""" + "\n".join(f"    s = s + {i % 4};" for i in range(45)) + """
    j = j + 1;
  }
  i = i + 1;
}
print s;
"""),
    "big_data_base": ml("t32-base", """
array big[4000];
var t = 0;
big[3999] = 17; big[2048] = 3; big[2047] = 4;
t = big[3999] * big[2048] + big[2047];
print t;
"""),
    "full_tiny": ml("t32-tiny", """
array a[240];
var i = 0;
while (i < 240) { a[i] = i; i = i + 1; }
print a[239] + a[0] + a[120];
"""),
    "overflow_wide": ml("t32-wide", """
var x = 2147483647; print x + x; print x * 3; print -x - 2; print 0 - (0 - 2147483648);
"""),
    "sort": ml("t32-base", """
array a[8];
a[0] = 5; a[1] = -3; a[2] = 9; a[3] = 0; a[4] = -8; a[5] = 2; a[6] = 7; a[7] = 1;
var i = 0;
while (i < 8) {
  var j = 0;
  j = 0;
  while (j < 7 - i) {
    if (a[j] > a[j + 1]) { var t = 0; t = a[j]; a[j] = a[j + 1]; a[j + 1] = t; }
    j = j + 1;
  }
  i = i + 1;
}
i = 0;
while (i < 8) { print a[i]; i = i + 1; }
"""),
    "primes_wide": ml("t32-wide", """
var n = 2; var count = 0;
while (n < 200) {
  var d = 2; var prime = 1;
  d = 2; prime = 1;
  while (d * d <= n) { if (n % d == 0) { prime = 0; } d = d + 1; }
  count = count + prime;
  n = n + 1;
}
print count;
"""),
    "gcd_tiny": ml("t32-tiny", """
var a = 1071; var b = 462;
while (b != 0) { var t = 0; t = a % b; a = b; b = t; }
print a;
"""),
    "compare_tiny": ml("t32-tiny", """
var a = -2147483648; var b = 2147483647;
print a < b; print a > b; print a <= a; print b >= a; print a == b; print a != b;
print !b; print ~b; print -a;
"""),
}

VALID_ASM = {
    "imm_min": (asm("t32-base", """
.data 4
  addi r1, r0, -2048
  out r1
  andi r2, r1, -2048
  out r2
  ori r3, r0, -2048
  out r3
  addi r4, r0, 2047
  addi r4, r4, 3
  sw r1, -2048(r4)
  lw r5, -2047(r4)
  out r5
  halt
"""), "-2048\n-2048\n-2048\n0"),
    "imm_wide": (asm("t32-wide", """
  addi r1, r0, 32767
  out r1
  addi r1, r0, -32768
  out r1
  halt
"""), "32767\n-32768"),
    "r15_base": (asm("t32-base", """
  addi r15, r0, 15
  addi r14, r15, 1
  out r15
  out r14
  halt
"""), "15\n16"),
    "r7_tiny": (asm("t32-tiny", """
  addi r7, r0, -7
  add r6, r7, r7
  out r6
  halt
"""), "-14"),
    "full_mem_base": (asm("t32-base", """
.data 4096
  lui r1, 0x1
  addi r1, r1, -1
  addi r2, r0, 99
  sw r2, 0(r1)
  lw r3, 0(r1)
  out r3
  halt
"""), "99"),
    "full_mem_tiny": (asm("t32-tiny", """
.data 256
  addi r1, r0, 31
  sw r1, 255(r0)
  sw r1, 0(r0)
  lw r2, 255(r0)
  out r2
  halt
"""), "31"),
    "branch_edges_tiny": (asm("t32-tiny", f"""
  addi r1, r0, 0
  addi r2, r0, 2
  beq r0, r0, fwd
{nops(126)}
fwd:
  addi r1, r1, 1
  out r1
  beq r1, r2, done
{nops(125)}
  bne r1, r2, -128
done:
  halt
"""), "1\n2"),
    "branch_edges_base": (asm("t32-base", f"""
  beq r0, r0, fwd
{nops(2046)}
fwd:
  addi r1, r0, 5
  out r1
  halt
"""), "5"),
    "jal_tiny": (asm("t32-tiny", f"""
  jal r0, far
{nops(1000)}
far:
  addi r1, r0, 3
  out r1
  halt
"""), "3"),
    "jal_link": (asm("t32-base", """
  addi r1, r0, 0
  jal r2, f
  out r2
  jal r2, f
  out r2
  halt
f:
  addi r1, r1, 1
  out r1
  jalr r0, r2, 0
"""), "1\n2\n2\n4"),
    "r0_zero": (asm("t32-base", """
  addi r0, r0, 5
  out r0
  jal r0, next
next:
  out r0
  lui r0, 0x1
  add r1, r0, r0
  out r1
  halt
"""), "0\n0\n0"),
    "sra_mix": (asm("t32-base", """
  lui r1, 0x80000
  addi r2, r0, 4
  sra r3, r1, r2
  out r3
  srl r3, r1, r2
  out r3
  addi r2, r0, 31
  sra r3, r1, r2
  out r3
  halt
"""), "-134217728\n134217728\n-1"),
    "signed_branches": (asm("t32-base", """
  lui r1, 0x80000
  addi r2, r0, 1
  blt r1, r2, a
  out r0
  halt
a:
  addi r3, r0, 1
  out r3
  bge r2, r1, b
  out r0
  halt
b:
  addi r3, r0, 2
  out r3
  sltu r4, r2, r1
  out r4
  slt r4, r2, r1
  out r4
  halt
"""), "1\n2\n1\n0"),
    "div_asm": (asm("t32-base", """
  lui r1, 0x80000
  addi r2, r0, -1
  div r3, r1, r2
  out r3
  rem r3, r1, r2
  out r3
  addi r4, r0, -9
  addi r5, r0, 4
  div r3, r4, r5
  out r3
  rem r3, r4, r5
  out r3
  halt
"""), "-2147483648\n0\n-2\n-1"),
    "add_wrap": (asm("t32-base", """
  addi r1, r0, -1
  add r2, r1, r1
  out r2
  lui r3, 0x7ffff
  addi r3, r3, 2047
  addi r3, r3, 2047
  addi r3, r3, 1
  add r4, r3, r2
  out r3
  out r4
  halt
"""), "-2\n2147483647\n2147483645"),
    "lui_max": (asm("t32-base", """
  lui r1, 0xfffff
  out r1
  halt
"""), "-4096"),
    "trap_mem": (asm("t32-base", """
.data 2
  addi r1, r0, 1
  out r1
  lw r2, 2(r0)
  out r2
  halt
"""), "1\n<trap: mem_out_of_range>"),
}

INVALID_ASM = {
    "imm_pos": asm("t32-base", "  addi r1, r0, 2048\n  halt"),
    "imm_neg": asm("t32-base", "  addi r1, r0, -2049\n  halt"),
    "imm_wide": asm("t32-wide", "  addi r1, r0, 32768\n  halt"),
    "sw_imm": asm("t32-base", ".data 4096\n  sw r1, 3000(r0)\n  halt"),
    "lui_big": asm("t32-base", "  lui r1, 0x100000\n  halt"),
    "reg_tiny": asm("t32-tiny", "  addi r8, r0, 1\n  halt"),
    "reg_base_lw": asm("t32-tiny", ".data 1\n  lw r1, 0(r9)\n  halt"),
    "mul_tiny": asm("t32-tiny", "  mul r1, r2, r3\n  halt"),
    "branch_pos_tiny": asm("t32-tiny", f"  beq r0, r0, t\n{nops(127)}\nt:\n  halt"),
    "branch_neg_tiny": asm("t32-tiny", f"b:\n{nops(129)}\n  beq r0, r0, b\n  halt"),
    "branch_base": asm("t32-base", f"  beq r0, r0, t\n{nops(2047)}\nt:\n  halt"),
    "jal_tiny": asm("t32-tiny", f"  jal r0, t\n{nops(32767)}\nt:\n  halt"),
    "target_outside": asm("t32-base", "  beq r0, r0, 5\n  halt"),
    "mem_tiny": asm("t32-tiny", ".data 257\n  halt"),
    "mem_base": asm("t32-base", ".data 4097\n  halt"),
}


def main() -> None:
    sys.path.insert(0, str(SUT))
    from cli import reference_text, execute, normalize  # noqa: E402

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
    for name, (src, expected) in VALID_ASM.items():
        (valid / f"{name}.s").write_text(src)
        (valid / f"{name}.expected").write_text(expected + "\n")
    for name, src in INVALID_ASM.items():
        (invalid / f"{name}.s").write_text(src)
        (invalid / f"{name}.expected").write_text("<rejected>\n")

    # The clean toolchain must pass the whole corpus.
    bad = []
    for d in (valid, invalid):
        for src in sorted(d.iterdir()):
            if src.suffix not in (".ml", ".s"):
                continue
            text = src.read_text()
            machine = text.splitlines()[0].split("machine:")[1].strip()
            res = execute(text, "ml" if src.suffix == ".ml" else "asm", machine)
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
