# Fault Injector

**Type:** scripted. No LLM.

**Implementation:** `src/toyfix/faults.py` (`CATALOG`, `apply_fault`,
`make_workspace`), called by `src/toyfix/episode.py` before any other agent
runs.

**Available tools:** `make_workspace`.

## Decision logic

- The fault is chosen by the user on the command line (`episode FAULT`) or by
  the benchmark loop. The Fault Injector makes no random choices.
- It copies the clean toolchain (`src/sut`) into
  `runs/<episode>/workspace` and applies the fault's edits. Each edit is an
  exact text replacement; if the old text does not occur exactly once, the
  injection fails, so a catalog entry can never silently do nothing.
- It saves a snapshot of the faulty workspace as `baseline/`. The Verifier
  uses it to compute the diff, and the Coordinator restores it at the end of
  an unresolved episode.
- It writes the fault metadata (id, layers, title, tempting fix) only to
  `runs/<episode>/scoreboard/fault.json`. This directory is outside the
  workspace, so no agent can read it (policy P7).

## Catalog (22 faults)

| Id | Layer | Fault |
|---|---|---|
| S1 | simulator | `sra` performs a logical shift |
| S2 | simulator | `add` does not wrap to 32 bits |
| S3 | simulator | `div`/`rem` round toward negative infinity |
| S4 | simulator | writes to `r0` are not ignored |
| S5 | simulator | `blt` compares unsigned values |
| S6 | simulator | `jal` stores `pc` instead of `pc + 1` |
| C1 | constraints | immediate range check rejects the minimum value |
| C2 | constraints | programs that use all of memory are rejected |
| C3 | constraints | the last register is reported as missing |
| C4 | constraints | `jal` offsets are checked against `branch_bits` |
| L1 | compiler | `lui`/`addi` constant split ignores the sign of the low part |
| L2 | compiler | nested spills reuse the same spill slot |
| L3 | compiler | branch relaxation uses `imm_bits` instead of `branch_bits` |
| L4 | compiler | software multiply shifts the multiplier arithmetically |
| L5 | compiler | data addresses up to `imm_bits+1` bits use an `r0` base |
| T1 | tests | division test expects floor division |
| T2 | tests | overflow test expects unbounded integers |
| T3 | tests | `imm_edge` test expects -2048 to be rejected |
| T4 | tests | shifts test expects `>>` to be a logical shift |
| X1 | compiler + tests | L1 and T1 together |
| X2 | simulator + constraints | S1 and C1 together |
| X3 | constraints + compiler | C3 and L2 together (C3 hides L2) |
