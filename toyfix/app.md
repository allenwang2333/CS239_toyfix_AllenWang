# ToyFix

## Purpose

ToyFix is a multi-agent application that repairs a broken compiler toolchain.
It is built to answer one research question:

> Can LLM agents correctly diagnose and repair failures across tests, hardware
> constraints, compiler lowering, and simulator implementation, without adding
> unnecessary restrictions on valid programs?

The system under repair is a small but complete toolchain that we wrote for
this project:

- **NPU**, a small tile-based AI accelerator (9 instructions: strided DMA
  `load`/`store`, a matrix unit `mm`/`mma`, vector `vadd`/`vsub`/`vmul`/`vrelu`,
  and `out`), with an assembler and a simulator.
- **Hardware profiles** (`npu-tiny`, `npu-base`, `npu-wide`) that set the
  shape of the matrix unit (`mm_shape`, for example 8 x 16 x 4), the vector
  length, the presence of `mma`, the width of the DMA row stride, the DMA
  address alignment, and the scratchpad and DRAM sizes. A validator checks
  programs against a profile.
- **MiniLang**, a small tensor language with Python syntax, with a compiler to
  the NPU. The compiler has an MLIR-style middle end (an `ml` tensor dialect,
  canonicalization, matmul + bias + relu fusion, bufferization to strided
  views with buffer reuse, and tiling into an `npu` dialect). It must obey
  every profile limit: it splits vector work into `vlen` pieces, accumulates
  with `mm` and `vadd` when there is no `mma`, splits DMA transfers whose row
  stride is too long, and pads rows to `dma_align`. It must also handle
  shapes that are not multiples of the matrix unit, large matrix products,
  transposed and broadcast operands, and values with more than one use.
- A **reference interpreter** for MiniLang, used as the oracle.
- A **specification** (`spec.md`) that defines all behavior, including which
  programs are valid and which programs the compiler must accept.

A Fault Injector puts one or two bugs into a copy of the toolchain. The bugs
come from a catalog of 22 faults in four layers: wrong test expectations,
wrong hardware-constraint checks, wrong compiler lowering, and wrong simulator
semantics. Each fault has a "tempting" wrong fix. Examples: rejecting
shapes that are not multiples of the matrix unit instead of fixing the edge tiles,
or editing a test instead of fixing the simulator.

The agents then work like a small engineering team. A Test Runner reports the
failures. A Diagnoser finds the faulty layer. The Coordinator assigns that
layer to a Repair Agent, which can edit only that layer. A rule-based Verifier
checks the patch against the visible tests and a hidden corpus of valid and
invalid programs. The hidden corpus is the key to the research question: a
patch that rejects valid programs, or that accepts invalid ones, fails the
Verifier even when every visible test passes. A Reviewer checks the diff
against the spec. Only then can the Verifier mark the episode FIXED.

## Supported tasks

1. **Repair episode** (`python3 -m toyfix episode FAULT`): inject one fault
   (or a two-fault combination) and run the full multi-agent repair loop. The
   output is a scored result, a JSONL event log, and a Markdown trajectory.
2. **Benchmark** (`python3 -m toyfix bench`): run many episodes in parallel
   and report the fix rate, first-diagnosis accuracy, whether the fix stayed
   in the injected layer, and the number of attempts that restricted valid
   programs or loosened checks.
3. **Ablations**: a single-agent baseline (`--mode solo`), no oracle tools
   (`--no-oracle`), and no corpus feedback for the Repair Agent
   (`--no-corpus-feedback`).
4. **Self-check** (`python3 -m toyfix check`): with no LLM, confirm that the
   clean toolchain passes everything and that every fault is detectable.

## Agents

| Agent | Kind | Role |
|---|---|---|
| Coordinator | scripted | Runs the attempt loop, assigns layers, reverts bad attempts, enforces budgets |
| Fault Injector | scripted | Copies the toolchain and injects a catalog fault; writes metadata only to the scoreboard |
| Test Runner | scripted | Runs the visible tests and builds the failure report |
| Diagnoser | LLM | Finds the faulty layer with evidence; read-only |
| Repair Agent | LLM | Edits only the assigned layer |
| Verifier | rule-based | Objective checks and the only agent that may mark FIXED |
| Reviewer | LLM | Reviews the diff against the spec; read-only |
| Solo Agent | LLM | Single-agent ablation baseline only |

The coordination is centralized (the Coordinator) and the interaction pattern
is fixed per attempt, with dynamic retries. There is one entry point: the
command line.
