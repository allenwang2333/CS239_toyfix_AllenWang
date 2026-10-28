# Episode 1: an off-by-one in a hardware constraint (fault C2)

**Type:** real run (`python3 -m toyfix episode C2`, model `deepseek-flash`,
multi-agent mode). Log: `runs/20261027-202645-C2-multi-smoke/`.

## Initial inputs

- **User request:** run a repair episode for catalog fault `C2`.
- **Fault Injector** copies the clean toolchain into the episode workspace and
  changes one line in `t32/validator.py`:
  `if program.data_words > machine.mem_words:` becomes
  `if program.data_words >= machine.mem_words:`.
  The fault id, layer, and title are written only to
  `scoreboard/fault.json` (P7). No LLM agent sees them.
- **Resources:** the faulty workspace (spec, toolchain, 22 visible tests). The
  hidden corpus stays outside the workspace.

## Trajectory

1. **Test Runner**: 21/22 visible tests pass. `full_memory.s` (profile
   `t32-tiny`, `.data 256`) fails at stage `validate`. Expected `42`; actual
   `<rejected>`; detail `data_words=256 is larger than mem_words=256`.
2. **Verifier** (baseline): the hidden corpus has 36/38 valid programs passing
   and 15/15 invalid programs rejected. The Coordinator stores these counts.
3. **Diagnoser** (11 tool calls, read-only, P1): `read_spec("4")`,
   `read_file(tests/full_memory.s)`, `search_code("mem_words")`,
   `read_file(t32/validator.py)`. It then probes the boundary with
   `validate_program`: `.data 255` is valid, and `.data 256` is invalid with
   the message "256 is larger than 256", which is wrong. It submits:
   - layer `constraints`, file `t32/validator.py`;
   - root cause: the `>=` comparison rejects `data_words == mem_words`, but
     §4.4(g) says a program that uses exactly `mem_words` words is valid, and
     §4.5 forbids any other rejection. It also notes that the compiler's
     check is already correct (`compiler.py:325`), so the compiler is not the
     cause.
4. **Coordinator** assigns the layer `constraints` to the Repair Agent for
   this attempt only (P2).
5. **Repair Agent** (14 tool calls): reads the validator and spec §4.4, §4.5,
   and §1.5, reproduces the failure, and calls `edit_file(t32/validator.py)`
   to change `>=` to `>`. It then runs `run_tests` (22/22), checks
   `.data 257` (still invalid), and runs `check_corpus` ("38/38 valid, 15/15
   invalid", counts only, P7). It submits with spec sections 4.4, 4.5, and 1.5.
6. **Verifier**: PASS. scope ok (1 file, in an assigned layer, P2/P3);
   visible 22/22; no test edits; no special cases (P5); hidden valid 38/38 and
   hidden invalid 15/15 (P6).
7. **Reviewer** (20 tool calls, read-only, P1): reads the diff and the spec,
   and probes both sides of the boundary on two profiles: `t32-tiny` 256
   (valid) and 257 (invalid), `t32-base` 4096 (valid) and 4097 (invalid). It
   also checks that the visible negative test `reject_memory.s` still passes.
   One probe used invalid MiniLang syntax and failed harmlessly. It reached
   its tool budget exactly at `submit_review` (P9 lets the submit tool
   through). It approves and cites §4.4(g), §4.5, and §1.5.
8. **Verifier** (`may_mark_fixed`): all checks pass and the Reviewer approved,
   so the episode is **FIXED** (P8).

## Expected outcome

- FIXED in 1 attempt. One line changed in the injected layer. The result is
  identical to the clean toolchain.
- Hidden valid corpus 38/38 (nothing new is rejected) and hidden invalid
  corpus 15/15 (`.data 257` and `.data 4097` are still rejected).
- Total: 45 tool calls, about 62 s.

## Policy connection

P1 (Diagnoser and Reviewer only read), P2 (layer assignment), P6 (both corpus
directions checked), P7 (fault metadata and corpus contents hidden; only
counts returned), P8 (Verifier and Reviewer gate), P9 (tool budget).
