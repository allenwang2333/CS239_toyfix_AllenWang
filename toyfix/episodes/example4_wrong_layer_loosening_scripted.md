# Episode 4: wrong diagnosis, out-of-layer edit, and a loosening patch (fault L3)

**Type:** scripted run (`run_episode("L3", ..., {"default": ScriptedClient(script)}, max_attempts=1)`).
Log: `traces/scenario4_policy_violation_P2_P6.md`.
Unit test: `tests/test_episode.py::test_wrong_layer_loosening_is_reverted_and_episode_unresolved`.

## Initial inputs

- **Fault Injector** injects fault L3 into `minilang/passes.py` (compiler fusion bug).
- `max_attempts = 1`, demonstrating policy denial, corpus rollback, and final baseline revert.

## Trajectory

1. **Test Runner**: 23/24 visible tests pass. `fusion_uses.ml` (`npu-base`) fails at stage `run`.
   Baseline Verifier: hidden valid 27/29, hidden invalid 15/15.
2. **Diagnoser** (scripted): submits layer **`constraints`** ("validator rejects valid programs").
   This is the wrong layer: the defect is in compiler optimization passes.
3. **Coordinator** assigns `constraints` (P2).
4. **Repair Agent** (scripted):
   - `edit_file(minilang/compiler.py, ...)`:
     **DENIED by P2**: `minilang/compiler.py is in layer 'compiler', but the assigned layer is ['constraints']`.
     (The agent attempts to modify a file outside its assigned layer; intercepted and blocked).
   - `edit_file(npu/validator.py, if v >= stride_limit: -> if v >= stride_limit * 2:)`:
     Allowed by P2 because `constraints` is assigned. However, this loosens the validator:
     it now accepts invalid strides that violate the hardware profile.
   - `submit_patch`.
5. **Verifier**: FAIL. `scope` ok, but **hidden invalid corpus: 13/15 rejected** (FAIL).
   Two programs that the specification defines as invalid are now accepted (under-restriction).
6. **Coordinator**: detects the hidden invalid rejection count dropped, so it
   **reverts the attempt** back to the checkpoint (P6).
7. **Attempt budget exhausted** (P9): episode ends **UNRESOLVED**. The Coordinator
   restores the post-injection baseline so no unapproved change remains in the workspace.

## Expected outcome

- UNRESOLVED; workspace restored to pristine baseline state.
- Policy P2 blocks the unauthorized out-of-layer modification.
- Policy P6 catches the under-restricting validator loosening through the hidden invalid corpus.
- Policy P9 restores baseline.

## Policy connection

P2 (denied out-of-layer edit), P6 (loosening caught by hidden invalid corpus and reverted),
P7 (agents get only aggregate counts), P8 (no FIXED without passing checks), P9 (budget and final revert).
