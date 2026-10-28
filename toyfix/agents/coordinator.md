# Coordinator

**Type:** scripted (deterministic Python state machine). No LLM.

**Implementation:** `src/toyfix/agents/coordinator.py` (`Coordinator.run`,
`_multi_attempt`, `_solo_attempt`, `_judge`).

**Available tools:** `run_visible_tests` (through the Test Runner), `verify`,
`may_mark_fixed`, and workspace snapshots (`Workspace.snapshot`,
`Workspace.restore`). It starts the LLM agents through `run_agent`.

## Decision logic

1. Ask the Test Runner for the failure report. If every visible test passes,
   stop with `NOTHING_TO_FIX`. Run the Verifier once to record the starting
   counts (visible passes, hidden valid passes, hidden invalid rejections).
2. For attempt `n = 1 .. 4` (policy P9):
   1. Save a checkpoint of the workspace.
   2. Start the **Diagnoser** with the failure report and the history of
      earlier attempts. If it stops without `submit_diagnosis`, record that
      and go to the next attempt.
   3. **Assign** the diagnosed layer: set `assigned_layers = {layer}` for
      this attempt only (P2) and add it to the episode's `all_assigned` set.
   4. Start the **Repair Agent** with the assigned layer, the diagnosis, the
      failure report, and the history. Clear `assigned_layers` when it
      finishes.
   5. If nothing changed: record the reason (no change, or the Repair Agent's
      `disagree_with_diagnosis` text) and go to the next attempt. This is how
      a wrong diagnosis is corrected.
   6. Run the **Verifier**. If it fails:
      - if the attempt lowered the visible, hidden-valid, or hidden-invalid
        count, or broke a scope, test-edit, or special-case rule, **revert to
        the checkpoint** (P6) and record why;
      - otherwise keep the changes (partial progress, for example one of two
        injected faults is fixed) and record the Verifier feedback.
      Then rerun the Test Runner and go to the next attempt.
   7. If the Verifier passes, start the **Reviewer** with all diagnoses, the
      patch submission, the Verifier feedback, and the full diff.
   8. Ask `may_mark_fixed`. If it returns true, the episode is `FIXED`.
      Otherwise revert to the checkpoint and record the Reviewer's concerns.
3. If no attempt succeeds: run the Verifier once more for the scoreboard,
   then **restore the post-injection baseline** (P9) and end `UNRESOLVED`.

It also counts *restricting attempts* (the hidden valid count went down) and
*loosening attempts* (the hidden invalid count went down) for the scoreboard.

The feedback that it passes between agents contains Verifier check results
with visible test names and hidden-corpus **counts** only (P7).

In the single-agent ablation (`--mode solo`), each attempt runs the Solo
Agent with all four layers assigned, then the Verifier; there is no Reviewer.
