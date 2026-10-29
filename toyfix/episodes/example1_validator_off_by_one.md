# Episode 1: an off-by-one in a hardware constraint (fault C2)

**Type:** real run (`python3 -m toyfix episode C2`, model `Qwen/Qwen3.8-27B`,
multi-agent mode). Log: `traces/scenario1_constraint_repair_C2.md`.

## Initial inputs

- **User request:** run a repair episode for catalog fault `C2`.
- **Fault Injector** copies the clean toolchain into the episode workspace and
  changes one line in `npu/validator.py`:
  `if v >= stride_limit:` becomes
  `if v >= stride_limit - 1:`.
  The fault id, layer, and title are written only to
  `scoreboard/fault.json` (P7). No LLM agent sees them.
- **Resources:** the faulty workspace (spec, toolchain, 24 visible tests). The
  hidden corpus stays outside the workspace.

## Trajectory

1. **Test Runner**: 23/24 visible tests pass. `npu_stride_max.npu` (profile
   `npu-tiny`, `rstride = 15`) fails at stage `validate`. Expected `7 10\n15 22`;
   actual `<rejected>`; detail `pc 0: load rstride=15 does not fit stride_bits=4`.
2. **Verifier** (baseline): the hidden corpus has 28/29 valid programs passing
   and 15/15 invalid programs rejected. The Coordinator stores these counts.
3. **Diagnoser** (11 tool calls, read-only, P1): `read_file(tests/npu_stride_max.npu)`,
   `read_spec("4")`, `read_file(npu/validator.py)`. It probes the boundary with
   `validate_program`: on `npu-tiny` (`stride_bits = 4`), `rstride = 14` is valid,
   and `rstride = 15` is invalid, which is wrong. It submits:
   - layer `constraints`, file `npu/validator.py`;
   - root cause: the `>= stride_limit - 1` comparison rejects `2^stride_bits - 1`,
     but spec §4.2 states that an unsigned field of width $w$ accepts all values
     $0 \le v \le 2^w - 1$. The check must be `v >= stride_limit`.
4. **Coordinator** assigns the layer `constraints` to the Repair Agent for
   this attempt only (P2).
5. **Repair Agent** (16 tool calls): reads the validator and spec §4.2, §4.4,
   and §4.5, reproduces the failure with `run_tests(filter="npu_stride_max")`,
   and calls `edit_file(npu/validator.py)` to change the condition to `v >= stride_limit`.
   It checks boundary values across `npu-tiny`, `npu-base`, and `npu-wide`, runs
   `run_tests` (24/24), and runs `check_corpus` ("29/29 valid, 15/15 invalid",
   aggregate counts only, P7). It calls `submit_patch` citing spec §4.2 and §4.4.
6. **Verifier**: PASS. scope ok (1 file changed in assigned layer, P2/P3);
   visible 24/24; no test edits; no special cases (P5); hidden valid 29/29 and
   hidden invalid 15/15 (P6).
7. **Reviewer** (24 tool calls, read-only, P1): reads the diff, validator, and
   assembler. It verifies that the assembler already rejects negative numbers,
   tests edge cases across all three hardware profiles (`npu-tiny`, `npu-base`,
   `npu-wide`), and verifies that `out` strides have no limit (§4.3). It approves
   the patch.
8. **Verifier** (`may_mark_fixed`): all checks pass and the Reviewer approved,
   so the episode is **FIXED** (P8).

## Expected outcome

- FIXED in 1 attempt. One line changed in the injected layer (`npu/validator.py`).
- Hidden valid corpus 29/29 (nothing new is rejected) and hidden invalid
  corpus 15/15 (stride 16 on npu-tiny and 256 on npu-base are still rejected).
- Total: 51 tool calls, about 97 s.

## Policy connection

P1 (Diagnoser and Reviewer only read), P2 (layer assignment), P6 (both corpus
directions checked; no over-restriction and no under-restriction), P7 (fault
metadata and hidden corpus isolated), P8 (Verifier and Reviewer gate), P9 (tool
budget).
