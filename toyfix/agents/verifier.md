# Verifier

**Type:** rule-based. No LLM. It cannot be persuaded: every decision is a
fixed check on files and test results.

**Implementation:** `src/toyfix/agents/verifier.py` (`verify`,
`may_mark_fixed`).

**Available tools:** `run_visible_tests` (through the workspace CLI),
`corpus_counts`, `verify`, `may_mark_fixed`.

## Checks (`verify`)

All checks compare the workspace with the post-injection baseline.

| Check | Policy | Passes when |
|---|---|---|
| `scope` | P2, P3, P5 | every changed file belongs to a layer that was assigned in the episode; no protected file changed; no test file was added or deleted |
| `visible_tests` | P8 | all 22 visible tests pass |
| `test_edits` | P4, P5 | every changed `.expected` file of a MiniLang test equals the reference interpreter output; test programs changed only in comment lines |
| `no_test_special_cases` | P5 | no added line in toolchain code contains `tests/`, `.expected`, or a test file name |
| `hidden_valid_corpus` | P6 | all 38 hidden valid programs are accepted and give the expected result |
| `hidden_invalid_corpus` | P6 | all 15 hidden invalid programs are rejected |

The hidden corpus lives in `src/toyfix/hidden/corpus`, outside every
workspace. It covers the boundaries of each rule in spec §4.4 and §9.2 (for
example `addi -2048`, `r15`, exactly `mem_words` words, branch offsets of
exactly +127/-128 on `t32-tiny`, `jal` beyond the branch range, constants with
bit 11 set, nested spills, negative software multiplies), and their invalid
neighbors (for example `addi 2048`, `r8` on `t32-tiny`, offset +128, 257
words).

The feedback text for agents (`VerifierReport.feedback`) names failing
visible tests but reports the hidden corpus only as counts (P7).

## Final decision (`may_mark_fixed`)

The Verifier marks an episode FIXED (P8) only if:

1. every check above passes, and
2. in multi-agent mode, the Reviewer's decision is `approve`, and
3. if any file under `tests/` changed, the approval cites at least one spec
   paragraph (P4).
