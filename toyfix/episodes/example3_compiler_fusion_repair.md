# Episode 3: compiler lowering pass repair (fault L3)

**Type:** real run (`python3 -m toyfix episode L3`, model `Qwen/Qwen3.8-27B`,
multi-agent mode). Log: `traces/scenario3_compiler_repair_L3.md`.

## Initial inputs

- **User request:** run a repair episode for catalog fault `L3`.
- **Fault Injector** modifies `minilang/passes.py` in the compiler's fusion optimization pass:
  ```python
  # Clean code:
  elif src.name == "ml.linear" and not src.attrs["relu"] and len(uses[src.result]) == 1:
  # Faulty code:
  elif src.name == "ml.linear" and not src.attrs["relu"]:
  ```
  The compiler fuses a `relu` operation into an earlier `ml.linear` operation unconditionally,
  even when the unactivated linear output is used by other operations.
- **Resources:** the faulty workspace (spec, toolchain, 24 visible tests).

## Trajectory

1. **Test Runner**: 23/24 visible tests pass. `tests/fusion_uses.ml` fails:
   actual output prints post-relu values `0 0\n10 12` where un-activated values `-5 -5\n10 12`
   were expected.
2. **Verifier** (baseline): visible tests 23/24, hidden valid corpus 27/29 pass,
   hidden invalid corpus 15/15 rejected.
3. **Diagnoser** (11 tool calls, read-only, P1):
   - Reads `tests/fusion_uses.ml` and spec §9.4.
   - Evaluates with `reference_eval("tests/fusion_uses.ml")` (the oracle).
   - Inspects compiler IR stages with `compile_program`: `canonicalize`, `fuse`, `asm`.
   - Locates `fuse` pass in `minilang/passes.py` (lines 130-142): observes that the
     `ml.linear` branch folds `ml.relu` without checking `len(uses[src.result]) == 1`.
   - Submits diagnosis for layer `compiler`.
4. **Coordinator** assigns layer `compiler` to Repair Agent (P2).
5. **Repair Agent** (10 tool calls):
   - Reads `minilang/passes.py` and reproduces failure with `run_tests(filter="fusion_uses")`.
   - Edits `minilang/passes.py` to restore `and len(uses[src.result]) == 1`.
   - Inspects post-fuse IR: confirms `ml.linear` stays un-activated when there are other uses.
   - Runs `run_tests` (24/24) and `check_corpus` (29/29 valid, 15/15 invalid).
   - Submits patch citing spec §9.4.
6. **Verifier**: PASS. Scope ok (1 file in `compiler` layer, P2/P3); visible tests 24/24;
   no test edits (P5); hidden valid 29/29 and hidden invalid 15/15 (P6).
7. **Reviewer** (12 tool calls, read-only, P1):
   - Reads diff in `minilang/passes.py`.
   - Probes edge cases: tests single-use intermediate (still fuses) and multi-use intermediate
     (does not fuse; produces exact reference results).
   - Approves patch citing spec §9.4.
8. **Verifier** (`may_mark_fixed`): Marked as **FIXED** (P8).

## Expected outcome

- FIXED in 1 attempt. Only `minilang/passes.py` changed.
- Valid multi-use tensor programs compile and execute correctly without semantic corruption.
- Total: 33 tool calls, about 148 s.

## Policy connection

P1 (Diagnoser and Reviewer read-only), P2 (layer assignment), P3 (no protected files modified),
P6 (hidden valid corpus 29/29 and hidden invalid corpus 15/15), P8 (Verifier and Reviewer gate).
