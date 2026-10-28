# Episode trajectory: fault L3 (multi mode)

- Model: `deepseek-flash`
- Outcome: **FIXED** after 1 attempt(s): verifier checks passed and the Reviewer approved
- Injected layer(s) (scoreboard only, hidden from agents): ['compiler']
- Diagnosed layers: ['compiler']
- Tool calls: 49, policy denials: 0
- Tokens: {'prompt_tokens': 328815, 'completion_tokens': 15504}

1. **Test Runner**: 23/24 visible tests pass. Failing: fusion_uses.
2. **Verifier**: FAIL: scope=ok (0 file(s) changed, all in scope); visible_tests=FAIL (23/24 passed; failing: fusion_uses); test_edits=ok (no invalid test edits); no_test_special_cases=ok (none found); hidden_valid_corpus=FAIL (27/29 valid programs accepted and correct); hidden_invalid_corpus=ok (15/15 invalid programs rejected)

## Attempt 1

3. **Diagnoser** starts (tools: list_files, read_file, search_code, read_spec, run_tests, run_program, compile_program, validate_program, trace_execution, reference_eval, minimize_failure, submit_diagnosis).
    - says: I'll start by looking at the failing test and the relevant spec sections.
    - `read_file({"path": "tests/fusion_uses.ml"})` -> tests/fusion_uses.ml (lines 1-12 of 12) /    1| # machine: npu-base /    2| # Values that are also used before the relu must not change (spec §9.4). /    3| def main(): /    4|     x = tensor([[1, -2, 3], [-4, 5, -6]]) /    5|     ...
    - `read_file({"path": "tests/fusion_uses.expected"})` -> tests/fusion_uses.expected (lines 1-8 of 8) /    1| -5 -5 /    2| 10 12 /    3| 0 0 /    4| 10 12 /    5| 0 0 /    6| 18 26 /    7| -12 -8 /    8| 18 26
    - `read_spec({"section": "9.4"})` -> 9.4. The compiler works in stages. `python3 cli.py ir FILE --stage STAGE` / prints the intermediate representation (IR) after a stage, in MLIR generic / syntax: /  / | Stage | Result | / |---|---| / | `frontend` | `ml` dialect: one  ...
    - `run_tests({})` -> 23/24 visible tests passed. /  / FAIL fusion_uses.ml (machine npu-base, stage run) /   expected: /     -5 -5 /     10 12 /     0 0 /     10 12 /     0 0 /     18 26 /     -12 -8 /     18 26 /   actual: /     0 0 /     10 12 /     0 0 /     10 12 /     0  ...
    - `reference_eval({"path": "tests/fusion_uses.ml"})` -> -5 -5 / 10 12 / 0 0 / 10 12 / 0 0 / 18 26 / -12 -8 / 18 26
    - `compile_program({"path": "tests/fusion_uses.ml", "stage": "fuse"})` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `compile_program({"path": "tests/fusion_uses.ml", "stage": "frontend"})` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `search_code({"pattern": "relu|linear|users|uses", "path": "minilang/passes.py"})` -> minilang/passes.py:4: fuse          matmul + add + relu -> ml.linear / minilang/passes.py:10: COMPUTE = {"ml.add", "ml.sub", "ml.mul", "ml.relu", "ml.matmul", "ml.linear"} / minilang/passes.py:43: if n in ("ml.relu", "ml.tra ...
    - `read_file({"path": "minilang/passes.py", "start_line": 100, "end_line": 150})` -> minilang/passes.py (lines 100-150 of 250) /  100|         for op in list(f.ops): /  101|             new = _fold(f, op) /  102|             if new is not None: /  103|                 f.replace_all_uses(op.result, new) /  104|     ...
    - `compile_program({"path": "tests/fusion_uses.ml", "stage": "asm"})` -> ; compiled for npu-base / .data 40 / .word 0, 1, -2, 3 / .word 4, -4, 5, -6 / .word 8, 2, -1 / .word 12, 1, 3 / .word 16, -2, 1 / .word 20, 1, -1 / .word 24, 2 /   load 32, 20, 2, 2, 0, 1 /   load 0, 0, 2, 3, 4, 1 /   load 16, 8, 3, 2, 4, 1 /   ...
    - `run_program({"path": "tests/fusion_uses.ml"})` -> { /  "machine": "npu-base", /  "stage": "run", /  "actual": "0 0\n10 12\n0 0\n10 12\n0 0\n18 26\n-12 -8\n18 26", /  "steps": 21, /  "dma_words": 62, /  "macs": 24, /  "detail": "" / }
    - `minimize_failure({"path": "tests/fusion_uses.ml"})` -> { /  "ok": true, /  "source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n    y = x @ w + b\n    print(y)\n    print(relu(y))\n", /  "reference" ...
    - `compile_program({"source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n    y = x @ w + b\n     ...)` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - says: The evidence is conclusive. Let me confirm the last piece — that the not-fused path (relu of a value with no other use) is handled correctly and that the merge branch is the culprit.
    - `compile_program({"stage": "fuse", "source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n    y  ...)` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `submit_diagnosis({"layer": "compiler", "files": ["minilang/passes.py"], "root_cause": "The `fuse` pass in minilang/passes.py merges a bias `ml.add` (or an `ml.linear`) with a fo ...)` -> diagnosis submitted
    - **Diagnoser** ends (finished, 15 tool calls).
```json
{
 "layer": "compiler",
 "files": [
  "minilang/passes.py"
 ],
 "root_cause": "The `fuse` pass in minilang/passes.py merges a bias `ml.add` (or an `ml.linear`) with a following `ml.relu` into a single `ml.linear {relu = true}` without checking that the pre-relu value has no other uses. Spec \u00a79.4 allows this fusion only \"when the intermediate values have no other uses\". In `fuse()`, the matmul+add branch (line 121) checks only `len(uses[mm.result]) == 1` \u2014 the matmul result \u2014 but never checks the *add* result's uses, and the `elif src.name == \"ml.linear\" and not src.attrs[\"relu\"]` branch (line 139) checks no use count at all. Consequently, when a value is printed before `relu(value)` is taken, the add result (used by the earlier `ml.print`) is replaced everywhere by the relu'd linear result, so the earlier print shows relu(y) instead of y and the printed pre-relu value is lost. This explains all 8 differing output lines in fusion_uses.ml (only the first printed tensor is wrong; the remaining lines happen to be the relu'd values, which are correct). No other visible test fails.",
 "evidence": "reference_eval tests/fusion_uses.ml returns exactly the .expected content (-5 -5 / 10 12 / 0 0 / 10 12 / 0 0 / 18 26 / -12 -8 / 18 26), so the .expected file is correct per spec \u00a79.1/\u00a79.3 and the test is not at fault.\n\nfrontend IR is correct (two uses of y: ml.print(%5) then %6 = ml.relu(%5)). After `--stage fuse` the same program becomes a single op\n  %4 = \"ml.linear\"(%0, %1, %3) {relu = true}\n  \"ml.print\"(%4)\n  \"ml.print\"(%4)\ni.e. the relu was fused into the add/linear even though %5 had two uses (print + relu), violating \u00a79.4's \"intermediate values have no other uses\" condition.\n\nMinimized repro (minimize_failure): source `x=tensor([[1,-2,3],[-4,5,-6]]); w=tensor([[2,-1],[1,3],[-2,1]]); b=tensor([1,-1]); y = x @ w + b; print(y); print(relu(y))`. Reference: \"-5 -5\\n10 12\\n0 0\\n10 12\"; actual run: \"0 0\\n10 12\\n0 0\\n10 12\" (stage run). The first print printed the relu'd value.\n\nEmitted assembly confirms the same: `mma 32,0,16,2,3,2` then immediately `vrelu 32,32,4` (in place) and then `out 28, 2, 2, 4, 1` twice, so the first `out` prints relu(y). No separate copy of the pre-relu value exists.\n\nrun_program on tests/fusion_uses.ml gives actual \"0 0\\n10 12\\n0 0\\n10 12\\n0 0\\n18 26\\n-12 -8\\n18 26\" = expected with only line 1 pair replaced by relu(y); the simulator executes mma/vrelu/out correctly (relu(y) printed as 0 0 / 10 12 matches reference), so the simulator is not at fault.\n\nControl case: for `y = relu(x @ w + b); print(y)` (add result has exactly one use) the fuse pass correctly produces one `ml.linear {relu = true}` and the result is right \u2014 so full fusion itself is legitimate; only the missing use check is wrong.",
 "spec_sections": [
  "9.4",
  "9.1",
  "9.2"
 ],
 "fix_hint": "In `fuse()` (minilang/passes.py), add the missing single-use guards: fuse matmul + bias add into 
```
4. **Coordinator** assigns layer `compiler` to the Repair Agent.
5. **Repair Agent** starts (tools: list_files, read_file, search_code, read_spec, run_tests, run_program, compile_program, validate_program, trace_execution, reference_eval, show_diff, edit_file, revert_file, check_corpus, submit_patch).
    - says: I'll start by reading the spec sections and the fuse pass.
    - `read_spec({"section": "9.4"})` -> 9.4. The compiler works in stages. `python3 cli.py ir FILE --stage STAGE` / prints the intermediate representation (IR) after a stage, in MLIR generic / syntax: /  / | Stage | Result | / |---|---| / | `frontend` | `ml` dialect: one  ...
    - `read_file({"path": "minilang/passes.py"})` -> minilang/passes.py (lines 1-250 of 250) /    1| """Middle-end passes on the ml dialect (spec §9.4). /    2|  /    3| canonicalize  fold algebraic identities and splat constants, CSE, DCE /    4| fuse          matmul + add + relu ...
    - `search_code({"pattern": "def uses|def replace_all_uses", "path": "minilang/ir.py"})` -> minilang/ir.py:102: def uses(self) -> dict[Value, list[Op]]: / minilang/ir.py:111: def replace_all_uses(self, old: Value, new: Value) -> None:
    - `read_file({"path": "tests/fusion_uses.ml"})` -> tests/fusion_uses.ml (lines 1-12 of 12) /    1| # machine: npu-base /    2| # Values that are also used before the relu must not change (spec §9.4). /    3| def main(): /    4|     x = tensor([[1, -2, 3], [-4, 5, -6]]) /    5|     ...
    - `read_file({"path": "minilang/ir.py", "start_line": 95, "end_line": 125})` -> minilang/ir.py (lines 95-125 of 266) /   95|  /   96|  /   97| @dataclass /   98| class Func: /   99|     name: str /  100|     ops: list[Op] = field(default_factory=list) /  101|  /  102|     def uses(self) -> dict[Value, list[Op]]: /  1 ...
    - `run_tests({"filter": "fusion"})` -> 0/1 visible tests passed. /  / FAIL fusion_uses.ml (machine npu-base, stage run) /   expected: /     -5 -5 /     10 12 /     0 0 /     10 12 /     0 0 /     18 26 /     -12 -8 /     18 26 /   actual: /     0 0 /     10 12 /     0 0 /     10 12 /     0 0 /  ...
    - `compile_program({"path": "tests/fusion_uses.ml", "stage": "fuse"})` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - says: Confirmed: the linear absorbed the relu despite `%4` having two uses. Applying the guard.
    - `edit_file({"path": "minilang/passes.py", "old_text": "            if mm.name == \"ml.matmul\" and len(uses[mm.result]) == 1:", "new_text": "            if (mm.name == \"m ...)` -> edited minilang/passes.py
    - `edit_file({"path": "minilang/passes.py", "old_text": "        if op.name != \"ml.relu\":\n            continue\n        src = op.operands[0].owner\n        if src.name == ...)` -> edited minilang/passes.py
    - `edit_file({"new_text": "        elif (src.name == \"ml.linear\" and not src.attrs[\"relu\"]\n                and len(uses[src.result]) == 1):", "old_text": "        elif  ...)` -> edited minilang/passes.py
    - `read_file({"path": "minilang/passes.py", "start_line": 109, "end_line": 150})` -> minilang/passes.py (lines 109-150 of 253) /  109| # ---- fuse ----------------------------------------------------------------------- /  110|  /  111| def fuse(module: Module, machine) -> None: /  112|     """Fuse a matmul with  ...
    - `compile_program({"path": "tests/fusion_uses.ml", "stage": "fuse"})` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `run_tests({})` -> 24/24 visible tests passed.
    - `check_corpus({})` -> hidden valid programs accepted and correct: 29/29 / hidden invalid programs rejected: 15/15
    - `compile_program({"stage": "fuse", "source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n    y  ...)` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `compile_program({"stage": "fuse", "source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n    y  ...)` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `show_diff({})` -> --- a/minilang/passes.py / +++ b/minilang/passes.py / @@ -118,7 +118,8 @@ /              continue /          for i in (0, 1): /              mm = op.operands[i].owner / -            if mm.name == "ml.matmul" and len(uses[mm.result]) ...
    - says: The fix is verified: 24/24 visible tests pass, hidden corpus 29/29 valid accepted+correct and 15/15 invalid rejected, and full fusion still fires when the intermediate values are single-use.
    - `submit_patch({"summary": "Fixed the `fuse` pass in minilang/passes.py so that relu folding into `ml.linear` only happens when the intermediate values have no other uses (spe ...)` -> patch submitted for verification
    - **Repair Agent** ends (finished, 18 tool calls).
```json
{
 "summary": "Fixed the `fuse` pass in minilang/passes.py so that relu folding into `ml.linear` only happens when the intermediate values have no other uses (spec \u00a79.4). Previously the matmul+add branch checked only the matmul result's use count, and the `elif src.name == \"ml.linear\"` branch checked none, so `print(y); print(relu(y))` rewrote every use of the pre-relu add result with the relu'd linear result (fusion_uses.ml printed relu(y) on the first print). Changes: (1) the matmul+bias-add branch now also requires the add result to have exactly one use; (2) the use map is recomputed per relu so counts are never stale; (3) folding a relu into an existing non-relu `ml.linear` now requires that linear's result to have exactly one use (the relu). When a value has other uses, the add/linear and the relu stay separate, so the pre-relu value remains available. No program acceptance/validity rules were changed \u2014 fusion still fires whenever the intermediates are single-use (verified: `y = x @ w + b; print(relu(y))` still becomes one `ml.linear {relu = true}`).",
 "spec_sections": [
  "9.4",
  "9.1"
 ]
}
```
6. **Verifier**: PASS: scope=ok (1 file(s) changed, all in scope); visible_tests=ok (24/24 passed); test_edits=ok (no invalid test edits); no_test_special_cases=ok (none found); hidden_valid_corpus=ok (29/29 valid programs accepted and correct); hidden_invalid_corpus=ok (15/15 invalid programs rejected)
7. **Reviewer** starts (tools: list_files, read_file, search_code, read_spec, run_tests, run_program, compile_program, validate_program, trace_execution, reference_eval, show_diff, submit_review).
    - `read_file({"path": "minilang/passes.py", "start_line": 60, "end_line": 160})` -> minilang/passes.py (lines 60-160 of 253) /   60|         # relu is idempotent; transpose is its own inverse. /   61|         src = op.operands[0] /   62|         return src if n == "ml.relu" else src.owner.operands[0] /   63|    ...
    - `read_spec({"section": "9.4"})` -> 9.4. The compiler works in stages. `python3 cli.py ir FILE --stage STAGE` / prints the intermediate representation (IR) after a stage, in MLIR generic / syntax: /  / | Stage | Result | / |---|---| / | `frontend` | `ml` dialect: one  ...
    - `run_tests({})` -> 24/24 visible tests passed.
    - `compile_program({"path": "tests/fusion_uses.ml", "stage": "fuse"})` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `run_program({"source": "x=tensor([[1,-2,3],[-4,5,-6]])\nw=tensor([[2,-1],[1,3],[-2,1]])\nb=tensor([1,-1])\ny = x @ w + b\nprint(y)\nprint(relu(y))"})` -> { /  "machine": "npu-base", /  "stage": "compile", /  "actual": "<compile error>", /  "detail": "invalid program: line 1: only function definitions are allowed at the top level" / }
    - `compile_program({"source": "x=tensor([[1,-2,3],[-4,5,-6]])\nw=tensor([[2,-1],[1,3],[-2,1]])\nb=tensor([1,-1])\ny = relu(x @ w + b)\nprint(y)", "stage": "fuse"})` -> compile error: invalid program: line 1: only function definitions are allowed at the top level
    - `read_file({"path": "tests/fusion_uses.ml"})` -> tests/fusion_uses.ml (lines 1-12 of 12) /    1| # machine: npu-base /    2| # Values that are also used before the relu must not change (spec §9.4). /    3| def main(): /    4|     x = tensor([[1, -2, 3], [-4, 5, -6]]) /    5|     ...
    - `run_program({"source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n    y = x @ w + b\n     ...)` -> { /  "machine": "npu-base", /  "stage": "run", /  "actual": "-5 -5\n10 12\n0 0\n10 12", /  "steps": 13, /  "dma_words": 36, /  "macs": 12, /  "detail": "" / }
    - `compile_program({"source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n    y = relu(x @ w + b) ...)` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `run_program({"machine": "npu-tiny", "source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n ...)` -> { /  "machine": "npu-tiny", /  "stage": "run", /  "actual": "0 0\n10 12\n-4 -4\n11 13\n-5 -5\n10 12", /  "steps": 26, /  "dma_words": 48, /  "macs": 12, /  "detail": "" / }
    - `run_program({"source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n    m = x @ w\n    prin ...)` -> { /  "machine": "npu-base", /  "stage": "run", /  "actual": "-6 -4\n9 13\n0 0\n10 12", /  "steps": 13, /  "dma_words": 36, /  "macs": 12, /  "detail": "" / }
    - `reference_eval({"source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n    y = x @ w + b\n     ...)` -> 0 0 / 10 12 / -4 -4 / 11 13 / -5 -5 / 10 12
    - `compile_program({"source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    r = relu(x @ w)\n    print(r)\n    m = x @ w ...)` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `compile_program({"source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    m = x @ w\n    print(relu(m))", "stage": "fu ...)` -> module { /   func.func @main() { /     %0 = "ml.constant"() {value = dense<[[1, -2, 3], [-4, 5, -6]]> : tensor<2x3xi32>} : () -> tensor<2x3xi32> /     %1 = "ml.constant"() {value = dense<[[2, -1], [1, 3], [-2, 1]]> : tensor<3x ...
    - `run_program({"machine": "npu-tiny", "source": "def main():\n    x = tensor([[1, -2, 3], [-4, 5, -6]])\n    w = tensor([[2, -1], [1, 3], [-2, 1]])\n    b = tensor([1, -1])\n ...)` -> { /  "machine": "npu-tiny", /  "stage": "run", /  "actual": "0 0\n10 12\n-5 -5\n10 12\n-15 -15\n30 36\n-5 -5\n20 24", /  "steps": 32, /  "dma_words": 60, /  "macs": 12, /  "detail": "" / } / [note: 5 tool calls left in your budget]
    - `submit_review({"decision": "approve", "rationale": "The diff only touches minilang/passes.py::fuse (compiler layer, which owns the bug) and adds exactly the missing single-us ...)` -> review submitted / [note: 4 tool calls left in your budget]
    - **Reviewer** ends (finished, 16 tool calls).
```json
{
 "decision": "approve",
 "rationale": "The diff only touches minilang/passes.py::fuse (compiler layer, which owns the bug) and adds exactly the missing single-use guards required by spec \u00a79.4 (\"ml.matmul followed by a bias ml.add and ml.relu becomes one ml.linear operation, when the intermediate values have no other uses\"). (1) The matmul+bias-add branch now requires len(uses[op.result]) == 1 in addition to the matmul-result check, so the add is folded into ml.linear only when its result is not needed elsewhere. (2) The matmul\u2192relu fold still guards on len(uses[src.result]) == 1. (3) Folding a relu into an existing non-relu ml.linear now requires len(uses[src.result]) == 1. The use map is recomputed inside the relu loop, so counts are not stale.\n\nVerified behaviour: `y = x@w+b; print(y); print(relu(y))` now gives \"-5 -5 / 10 12 / 0 0 / 10 12\", matching reference_eval and tests/fusion_uses.ml's .expected; the fuse IR keeps ml.add + ml.relu separate, so the pre-relu value survives. Legitimate fusion is not lost: `print(relu(x@w+b))` still becomes one `ml.linear {relu = true}`, and `print(relu(x@w))` still becomes `ml.linear {relu = true}` (\u00a79.4). Multi-use intermediates (`y` used by print, mul and add; matmul result used by print and relu) are left unfused and still produce correct values, checked against reference_eval and run successfully on npu-tiny (no new validation rejection, \u00a74.4/\u00a74.5 unaffected). No program acceptance/rejection logic changed, no new restrictions, no special-casing of tests or values, no test edits, and the patch is minimal (only the three guard conditions, plus a harmless re-computed use map). Visible tests 24/24 pass and the Verifier's hidden valid/invalid corpora pass.",
 "spec_sections": [
  "9.4",
  "9.1",
  "9.2",
  "4.4",
  "4.5"
 ]
}
```
8. **Verifier** decision: fixed=True (verifier checks passed and the Reviewer approved).

**Outcome: FIXED** (verifier checks passed and the Reviewer approved)
