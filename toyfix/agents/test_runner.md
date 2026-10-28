# Test Runner

**Type:** scripted. No LLM.

**Implementation:** `src/toyfix/agents/test_runner.py` (`run_visible_tests`),
which runs `python3 -B cli.py test` inside the episode workspace.

**Available tools:** `run_visible_tests`.

## Decision logic

- It runs every visible test in `tests/` (22 tests: 12 MiniLang, 10
  assembly) with the workspace's own, possibly faulty, toolchain. Each test
  is compiled (MiniLang only), assembled, validated against the profile named
  in its first line, and run with a 200000-step limit (spec §10.3).
- A test passes if the result text equals the `.expected` file (trailing
  whitespace is ignored). A crash of the toolchain counts as a failure with
  stage `crash`.
- It builds the failure report: the pass count, and for each failing test the
  file, profile, stage, expected result, actual result, and detail (compile
  error, validator violation, assembler error, or trap).
- The Coordinator calls it at the start of an episode and after each failed
  attempt. The report is the input of the Diagnoser and the Repair Agent.
- It runs in a subprocess with a timeout, so a patch that breaks or hangs the
  toolchain cannot stop the episode.
