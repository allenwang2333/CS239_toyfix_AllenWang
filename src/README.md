# ToyFix

ToyFix is a multi-agent application that diagnoses and repairs faults in a toy
compiler toolchain: a tile-based AI accelerator (NPU) with an assembler, a
validator for hardware profiles, and a simulator, and a compiler for MiniLang,
a small tensor language with Python syntax and an MLIR-style middle end. It asks whether LLM agents can fix faults in the right
layer (tests, hardware constraints, compiler lowering, or simulator) **without
adding restrictions on valid programs**.

The requirements documents (app, policies, tools, agents, episodes) are in
`toyfix/` (next to `src/`).

## Requirements

- Python 3.11 or newer (developed and tested on Python 3.15). The code uses
  only the standard library: no `pip install` is needed.
- For LLM episodes: a DeepSeek API key and network access to
  `https://api.deepseek.com`. Any other OpenAI-compatible chat-completions
  endpoint with tool calling also works (see below).
- The offline test suite and the self-check need no key and no network.

## Configuration

Put the key in a `.env` file in the repository root (the directory that
contains `src/`), or export it:

```
DEEPSEEK_API_KEY=sk-...
```

Optional environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `TOYFIX_MODEL` | `deepseek-flash` | Model for all LLM agents (`deepseek-v4-pro` also works) |
| `TOYFIX_BASE_URL` | `https://api.deepseek.com` | Any OpenAI-compatible endpoint |
| `TOYFIX_API_KEY` | (none) | Used instead of `DEEPSEEK_API_KEY` if set |

## MiniLang

MiniLang programs are Python files with a small subset of Python
(spec §7, §8). Every value is an `int` or an i32 tensor of rank 1 or 2.
Functions are inlined and `for ... in range(...)` loops are unrolled at
compile time.

```python
# machine: npu-base
def dense(x: Tensor[4, 6, i32], w: Tensor[6, 5, i32], b: Tensor[5, i32]) -> Tensor[4, 5, i32]:
    return relu(x @ w + b)

def main():
    x = iota((4, 6)) - 11
    w = full((6, 5), 2)
    print(dense(x, w, tensor([3, -20, 0, 7, -1])))
    print(x.T)
```

Operations: `+ - *` (elementwise, with int and row broadcasting), `@`,
unary `-`, `.T` / `transpose`, `relu`, and the constructors `tensor`,
`zeros`, `ones`, `full`, `iota`.

The compiler pipeline (spec §9.4) is: frontend (Python `ast` -> `ml`
dialect) -> canonicalize -> fuse (matmul + bias + relu -> `ml.linear`) ->
bufferize (strided `memref` views, buffer reuse) -> lower-npu (tiling into
`npu` dialect ops) -> NPU assembly. The IR is printed in MLIR generic syntax.

```
cd src/sut
python3 cli.py run tests/dense_layer.ml               # compile, validate, simulate
python3 cli.py run tests/dense_layer.ml --machine npu-tiny
python3 cli.py reference tests/dense_layer.ml         # reference interpreter
python3 cli.py ir tests/dense_layer.ml --stage fuse   # IR after one stage (or --stage all)
python3 cli.py compile tests/dense_layer.ml           # NPU assembly
```

The NPU (spec §1 - §6) has a DRAM, a scratchpad, and 9 instructions: `load`
and `store` (2-D strided DMA), `mm` and `mma` (tile matrix product, with
accumulate), `vadd`, `vsub`, `vmul`, `vrelu`, and `out`.

Each hardware profile (`machines/npu-*.toml`, spec §4) sets limits that the
validator checks and that the compiler must work around:

| Profile | mm_shape (M x K x N) | vlen | has_mma | stride_bits | dma_align | spad_words | dram_words |
|---|---|---|---|---|---|---|---|
| `npu-tiny` | 2 x 2 x 2 | 2 | false | 4 | 2 | 16 | 256 |
| `npu-base` | 4 x 4 x 4 | 8 | true | 8 | 4 | 64 | 4096 |
| `npu-wide` | 8 x 16 x 4 | 64 | true | 16 | 4 | 256 | 65536 |

The compiler tiles matrix products by `mm_shape`, splits vector work into
`vlen` pieces, adds partial products with `mm` + `vadd` when there is no
`mma`, splits a DMA transfer into one transfer per row when the row stride
does not fit `stride_bits`, and pads every row and buffer to `dma_align`.

## Run

ToyFix commands run from `src/`.

```
cd src
python3 -m toyfix list-faults              # the 22 catalog faults
python3 -m toyfix check                    # offline self-check (no LLM)
python3 -m toyfix episode L1               # one multi-agent repair episode
python3 -m toyfix episode T3 --mode solo   # single-agent baseline
python3 -m toyfix episode X3 --no-oracle   # ablation: no reference interpreter tools
python3 -m toyfix bench --faults all --modes multi,solo --jobs 8
```

Episode options: `--model`, `--attempts N` (default 4), `--no-oracle`,
`--no-corpus-feedback`, `--out DIR` (default `runs/` in the repository root),
`--tag TEXT`, `--quiet`.

### Example

```
$ python3 -m toyfix episode C2 --quiet
{
 "fault": "C2",
 "status": "FIXED",
 "attempts": 1,
 "diagnosed_layers": ["constraints"],
 "changed_layers": ["constraints"],
 "final_valid_corpus": [29, 29],
 "final_invalid_corpus": [15, 15],
 "restricting_attempts": 0,
 "tool_calls": 45,
 ...
 "episode_dir": ".../runs/20261027-202645-C2-multi-smoke"
}
```

Without `--quiet`, every tool call is printed while the agents work.

### Episode output

`runs/<timestamp>-<fault>-<mode>/` contains:

- `workspace/`: the repaired toolchain (or the faulty one, if unresolved:
  policy P9 reverts all changes),
- `baseline/`: the toolchain right after fault injection,
- `events.jsonl`: every LLM turn, tool call, policy denial, Verifier report,
  and Coordinator decision,
- `trajectory.md`: a readable step-by-step trajectory,
- `scoreboard/fault.json` and `scoreboard/result.json`: the injected fault
  and the score. Agents never see this directory.

A benchmark writes `runs/bench-<timestamp>/results.json` and `summary.md`.

## Tests

From the repository root:

```
python3 -m unittest discover -s tests -t . -v
```

The suite (no LLM, no network) covers:

- `test_npu.py`: the NPU assembler, every validity rule at its exact
  boundary on every profile, and the semantics of every NPU instruction.
- `test_minilang.py`: parser errors, hand-computed reference semantics, the
  printed IR, the passes (folding, CSE, fusion, views, buffer reuse), the
  verifier, the memory bound of spec §9.3, and differential testing of the
  compiler against the reference interpreter on every NPU profile (all test
  and corpus programs plus 60 random programs).
- `test_faults.py`: every fault is detected; restoring clean code passes;
  wrong fixes are caught (a loosened validator by the invalid corpus, a
  wrong-layer fix by the valid corpus, a test edited to match a bug by P4,
  special cases for tests, deleted tests, protected files).
- `test_policies.py`: P1, P2, P3, P5, P7, P8, P9 enforcement in the tool
  layer and the final decision.
- `test_episode.py`: full episodes with a scripted LLM client: a fixed
  episode, a wrong-layer loosening that is reverted, a Reviewer rejection,
  partial progress kept across attempts, the solo mode, and a check that no
  fault metadata reaches any agent.
- `test_docs.py`: the requirements docs match the code (exact prompts, tool
  list, policy numbering).

## Results (October 2026, `deepseek-flash`, 4 attempts per episode)

These results were measured on an earlier version of the toolchain, in which
MiniLang was a small imperative language compiled to a scalar ISA (T32). That
ISA is removed and every fault in the catalog has changed since then, so the
benchmark must be run again for the current catalog.

All 22 catalog faults, each run once per configuration:

| Configuration | Mode | Fixed | First diagnosis correct | Fix only in injected layer | Restricting / loosening attempts | Mean tool calls | Mean time |
|---|---|---|---|---|---|---|---|
| default | multi-agent | 22/22 | 22/22 | 22/22 | 0 / 0 | 49.5 | 80 s |
| default | solo | 22/22 | 22/22 | 22/22 | 0 / 0 | 18.9 | 31 s |
| `--no-oracle --no-corpus-feedback` | multi-agent | 22/22 | 22/22 | 22/22 | 0 / 0 | 49.5 | 81 s |
| `--no-oracle --no-corpus-feedback` | solo | 22/22 | 22/22 | 22/22 | 0 / 0 | 24.6 | 49 s |

Patch quality: in 78 of 95 FIXED live episodes (including a 6-episode pilot
and one smoke run), the final code equals the clean toolchain, ignoring
comments. The other 17 use different but equivalent code (for example
`hi = ((u + 0x800) >> 12) & 0xFFFFF` for the `lui` split). All of them also pass
135 extra stress programs (300+ constants and random expressions on every
profile). Two S2 patches added extra masking that has no effect; it is correct
but not minimal.

Interpretation: with this fault catalog, `deepseek-flash` localizes and
repairs every fault without adding restrictions, in both modes and without
the oracle. The benchmark is saturated for this model. The multi-agent
design does not raise the fix rate here; it adds enforced scope, an
independent review, and auditable decisions, at about twice the tool calls.
The policy checks and reverts are exercised by the offline tests and the
scripted episode in `toyfix/episodes/example4_*`.

## Repository layout

```
src/
  README.md
  sut/                    the clean toolchain (copied into each episode)
    spec.md               NPU + MiniLang specification (source of truth)
    machines/*.toml       hardware profiles (npu-*)
    npu/                  isa.py, assembler.py, simulator.py, validator.py, machine.py
    minilang/             parser.py (frontend), reference.py (oracle),
                          ir.py (MLIR-style IR), passes.py, compiler.py
    cli.py                JSON command-line harness used by the tools
    tests/                24 visible tests (*.ml, *.npu, *.expected)
  toyfix/
    __main__.py           command line
    agents/               coordinator, llm_agent (Diagnoser/Repair/Reviewer/Solo),
                          test_runner, verifier
    prompts/              system prompts of the LLM agents
    tools.py              LLM tools with policy enforcement
    faults.py             fault catalog and Fault Injector
    episode.py            episode runner, scoreboard, trajectory renderer
    llm.py                DeepSeek client and scripted client
    workspace.py          episode workspace, snapshots, diffs
    hidden/               hidden corpus (29 valid, 15 invalid) and its builder
    make_docs.py          regenerates tools.md and the LLM agent docs
    package.py            builds the submission archives
tests/                    offline unittest suite
toyfix/                   submission documents (app, policy, tools, agents, episodes)
```

## Maintenance commands

```
cd src
python3 -m toyfix.hidden.build_corpus      # rebuild the hidden corpus and check it
python3 -m toyfix.make_docs                # regenerate tools.md and LLM agent docs
python3 -m toyfix.package --name NAME --uid UID   # build both archives in dist/
```

## Notes

- Agents edit and run the toolchain code of their own episode workspace. The
  code runs in a local subprocess with a timeout, with no other sandbox. Run
  episodes only on a machine where that is acceptable.
- The hidden corpus is in `src/toyfix/hidden/corpus`. Agents cannot read it
  (policy P7), but anyone with the source can. Do not use it as a public
  training set if you want the benchmark to stay meaningful.
