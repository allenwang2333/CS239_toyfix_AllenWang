# Episode 3: one fault hides another (fault X3 = C3 + L2)

**Type:** real run (`python3 -m toyfix bench --faults all --modes multi,solo`,
model `deepseek-flash`, multi-agent mode). Log:
`runs/bench-20261027-203041-full/20261027-203323-X3-multi-full/`.

## Initial inputs

- **Fault Injector** injects two faults:
  - C3 (constraints): `t32/validator.py` says the last register (r7 on
    `t32-tiny`, r15 on `t32-base`) does not exist (`r >= num_regs - 1`).
  - L2 (compiler): `minilang/compiler.py` puts every nested spill in the same
    memory slot (`slot = self.spill_base`).
- C3 hides L2: the compiler uses the last register as its scratch register,
  so `deep_expr.ml` is rejected by the validator before the wrong spill code
  can run.

## Trajectory

**Attempt 1**

1. **Test Runner**: 18/22 pass. `deep_expr`, `large_array`, `mul_soft`, and
   `reg_max` all fail at stage `validate` with "register r7/r15 does not
   exist". Baseline corpus: 32/38 valid.
2. **Diagnoser** (16 calls): validates the failing programs and reads §4.1 and
   §4.4(b). It submits layer `constraints`. It claims the one off-by-one
   "explains all four failures" and that "no failure remains unexplained".
   This is wrong, but the agent could not see the second fault yet.
3. **Coordinator** assigns `constraints` (P2).
4. **Repair Agent** (16 calls): changes `num_regs - 1` to `num_regs`. It
   checks that r7 and r15 are accepted and that r8 on `t32-tiny` is still
   rejected. `run_tests` shows 21/22, with `deep_expr` still failing (61/4
   instead of 55/5). `check_corpus` shows 36/38. It does **not** edit the
   compiler, which is outside its assigned layer. Its summary says: "the
   remaining ... failure ... is a compiler-layer defect: the generated code
   spills every nested temporary to the same slot".
5. **Verifier**: FAIL (visible 21/22, valid 36/38). No count went down, so
   the **Coordinator keeps the change** as partial progress, records the
   feedback, and reruns the Test Runner: only `deep_expr` fails now.

**Attempt 2**

6. **Diagnoser** (17 calls): compares `run_program` (61/4) with
   `reference_eval` (55/5), reads the generated assembly
   (`compile_program`), runs `minimize_failure`, and checks the spill
   pattern with two small hand-written assembly programs. It finds that
   `slot = self.spill_base` ignores `spill_level`, while the space reserved
   (`spill_base + max_spill`) shows that one slot per level was intended. It
   submits layer `compiler`.
7. **Coordinator** assigns `compiler`. This is a new diagnosis, so it is a
   new layer assignment (P2).
8. **Repair Agent** (19 calls): sets the slot to
   `self.spill_base + self.spill_level` (taken before the increment). It
   tests extra deeply nested programs, gets 22/22 visible, and `check_corpus`
   gives 38/38 and 15/15. Its summary states that the fix "imposes no new
   restriction on expression depth".
9. **Verifier**: PASS. Both changed files are in layers assigned during the
   episode (`scope` uses the episode's set of assigned layers).
10. **Reviewer** (20 calls): reviews both one-line changes against §4.1,
    §4.4(b), §4.5, and §9.2. It probes r7 and r8 on `t32-tiny`, and r15
    and r16 on `t32-base`, then approves.
11. **Verifier**: **FIXED** after 2 attempts.

## Expected outcome

- FIXED in 2 attempts. Each fault is fixed in its own layer, and the result
  equals the clean toolchain.
- The scope rule (P2) forced the system to repair the masked fault through a
  second diagnosis, not by a Repair Agent editing outside its layer.
- Wrong fixes that would be prevented: making the compiler stop using the
  last register (rejected by P2 in attempt 1, and it would not fix
  `reg_max.s`); rejecting deep expressions (visible `deep_expr` and the
  hidden `deep_base`/`deep_tiny` programs would fail, P6).

## Policy connection

P2 (one layer per attempt; a new diagnosis is needed for the second layer),
P6 (partial progress is kept only because no count went down), P7 (the Repair
Agent learned only "36/38", not which programs failed), P8, P9 (two of four
attempts used).
