# ToyFix: Multi-Agent AI Compiler Repair System

ToyFix is a multi-agent software engineering application that diagnoses and repairs defects in an AI compiler toolchain for a tile-based Neural Processing Unit (NPU).

The system investigates whether LLM agents can correctly identify and repair defects across tests, hardware constraints, compiler lowering passes, and simulator semantics **without over-restricting valid programs and without under-restricting invalid programs**.

---

## Deliverables Navigation

This repository contains all required deliverables for **Phase 1: Prototype**:

| Deliverable | Location | Description |
|---|---|---|
| **Requirements Document** | [`requirements.md`](requirements.md) | Specifies what the system does: NPU architecture, MiniLang compiler, agent roles, workflows, and success criteria. |
| **Policies Document** | [`policies.md`](policies.md) | Specifies what the system must never do: permission, capability, lifecycle, information flow, and isolation boundaries. |
| **Agent Traces** | [`traces/`](traces/) | Complete agentic traces (thoughts, actions, inter-agent messages, observations) in Markdown and JSONL formats. |
| **Traces Explanation** | [`traces/README.md`](traces/README.md) | Explains each scenario, failure mechanics, and specific policies triggered or enforced. |
| **Source Code** | [`src/`](src/) | Phase 1 multi-agent application code, SUT toolchain, and fault catalog. |
| **Test Suite** | [`tests/`](tests/) | 67 offline unit and regression tests covering ISA, compiler passes, policies, and scripted episodes. |

---

## System Architecture

```
                                  +-------------------+
                                  |    Coordinator    |
                                  +---------+---------+
                                            |
               +----------------------------+----------------------------+
               |                            |                            |
               v                            v                            v
     +------------------+         +------------------+         +-------------------+
     |  Fault Injector  |         |   Test Runner    |         |     Diagnoser     |
     |  - Injects bug   |         |  - Runs visible  |         |  - Read-only      |
     |  - Hides metadata|         |    test suite    |         |  - Finds root     |
     +------------------+         +------------------+         |    cause layer    |
                                                               +---------+---------+
                                                                         |
                                                                         v
     +------------------+         +------------------+         +-------------------+
     |     Reviewer     |         |     Verifier     |         |   Repair Agent    |
     |  - Read-only     |         |  - Objective     |         |  - Mutates only   |
     |  - Checks diff   |<--------|    gatekeeper    |<--------|    assigned layer |
     |  - Audits spec   |         |  - Hidden corpus |         |  - Submits patch  |
     +------------------+         +------------------+         +-------------------+
```

### Agents and Roles

- **Fault Injector** (Scripted): Copies the clean toolchain to an isolated workspace and injects one of 22 catalog bugs. Hides fault metadata in `scoreboard/`.
- **Test Runner** (Scripted): Executes visible test suites and compiles failure reports.
- **Diagnoser** (LLM, Read-Only): Investigates failures, probes hardware boundaries, and submits an evidence-backed diagnosis identifying the faulty layer.
- **Coordinator** (Scripted): Enforces lifecycle sequencing, assigns exactly one layer per attempt, manages tool budgets, and rolls back failed attempts.
- **Repair Agent** (LLM, Scoped Mutation): Edits code strictly inside the assigned layer and submits candidate patches.
- **Verifier** (Rule-Based): Objective gatekeeper checking scope, visible tests, and the hidden test corpus (29 valid, 15 invalid programs).
- **Reviewer** (LLM, Read-Only): Inspects the unified diff against `spec.md` to guarantee no valid programs are restricted and no invalid programs are admitted.

### Architectural Layers (Repair Layers)

ToyFix partitions the SUT toolchain into four repair layers. The Coordinator assigns exactly one layer to the Repair Agent per attempt (Policy P2). The Repair Agent can edit files only in that assigned layer.

```
+-----------------------------------------------------------------------------------------+
|                               Toolchain Execution Pipeline                              |
|                                                                                         |
|   MiniLang Source (.ml)                                                                 |
|         |                                                                               |
|         v                                                                               |
|   [ Compiler Layer ]       minilang/compiler.py, ir.py, passes.py                       |
|         |                  Translates AST -> IR -> optimizations -> NPU assembly        |
|         v                                                                               |
|   NPU Assembly (.npu)                                                                   |
|         |                                                                               |
|         v                                                                               |
|   [ Constraints Layer ]    npu/validator.py                                             |
|         |                  Validates assembly against hardware profiles (machines/*.toml)|
|         v                                                                               |
|   [ Simulator Layer ]      npu/isa.py, assembler.py, simulator.py                       |
|         |                  Simulates NPU instructions, scratchpad memory, and DRAM      |
|         v                                                                               |
|   Execution Output <=====  [ Tests Layer ]  tests/ (*.ml, *.npu, *.expected)            |
+-----------------------------------------------------------------------------------------+
```

| Layer | Files Owned | Responsibilities | Common Defect Patterns |
|---|---|---|---|
| **`tests`** | `tests/` (`*.ml`, `*.npu`, `*.expected`) | Defines visible end-to-end test cases and expected program outputs. | Stale or incorrect `.expected` files where compiler and simulator behavior is correct per `spec.md` (e.g., Fault T3). |
| **`constraints`** | `npu/validator.py` | Statically checks NPU assembly against target hardware profile limits (`machines/*.toml`): matrix multiply shapes (`mm_shape`), vector length (`vlen`), scratchpad capacity, memory alignment, and DMA stride limits. | Off-by-one boundary checks, overly tight stride limits, or wrong alignment checks that falsely reject legal programs (e.g., Faults C1–C4). |
| **`compiler`** | `minilang/compiler.py`<br>`minilang/ir.py`<br>`minilang/passes.py` | Parses Python AST into MLIR-style intermediate representation (IR), runs optimization passes (`canonicalize`, `fuse`), manages scratchpad buffer allocation (`bufferize`), tiles loops, and emits NPU assembly (`lower-npu`). | Erroneous fusion of multi-use values, premature buffer reuse that clobbers live operands, or incorrect loop tiling math (e.g., Faults L1–L4). |
| **`simulator`** | `npu/isa.py`<br>`npu/assembler.py`<br>`npu/simulator.py` | Assembles and encodes the 9 NPU instructions (`load`, `store`, `mm`, `mma`, `vadd`, `vsub`, `vmul`, `vrelu`, `out`). Simulates hardware execution and models DRAM and scratchpad memory state. | Arithmetic execution errors (e.g., inverted operand order in `vsub`, accumulator clobbering in `mma`, unhandled boundary elements in `vrelu`). |

#### Protected System Components (Policy P3)

The following components represent immutable ground truth. No agent may edit these files regardless of role or assigned layer:
- `spec.md`: The definitive system specification and ground truth.
- `machines/*.toml`: Hardware target definitions (`npu-tiny`, `npu-base`, `npu-wide`).
- `minilang/parser.py`: MiniLang frontend grammar parser.
- `minilang/reference.py`: Authoritative reference interpreter oracle.
- `cli.py` & `npu/machine.py`: Toolchain CLI interface and machine profile dataclass.

#### Why Layer Isolation Matters

A naive LLM agent often applies a "wrong-layer workaround" — such as editing a test expectation to match buggy compiler output, or loosening a hardware validator to accept illegal assembly. ToyFix prevents these unsound fixes through structural layer isolation:
1. **Evidence-based Diagnosis**: The Diagnoser must prove which layer holds the root cause.
2. **Strict Scoping (Policy P2)**: The Repair Agent cannot touch files outside its assigned layer.
3. **Dual Verification (Policy P6)**: The Verifier evaluates both hidden valid and hidden invalid test programs to ensure the patch does not over-restrict or under-restrict system behavior.
---

## Quickstart

### 1. Requirements

- Python 3.11 or newer (standard library only; no `pip install` required).
- For live LLM episodes: a DeepSeek API key (or OpenAI-compatible chat endpoint).
- Offline tests and self-checks require **no API key and no network connection**.

### 2. Configuration

Set the API key in `.env` in the repository root:

```bash
DEEPSEEK_API_KEY=sk-...
```

Optional settings:
- `TOYFIX_MODEL`: Model name (default: `deepseek-flash`).
- `TOYFIX_BASE_URL`: API base URL (default: `https://api.deepseek.com`).

### 3. Run Offline Tests (No LLM Required)

```bash
# Run all 67 offline unit tests:
python3 -m unittest discover -s tests -t . -v

# Run the fault catalog self-check (validates all 22 faults):
cd src && python3 -m toyfix check
```

### 4. Run a Live Multi-Agent Episode

```bash
cd src

# Run repair episode on hardware constraint fault C2:
python3 -m toyfix episode C2

# Run repair episode on compiler fusion fault L3:
python3 -m toyfix episode L3

# Run repair episode on test expectation fault T3:
python3 -m toyfix episode T3
```

Results are saved to `runs/<timestamp>-<fault>-multi/`:
- `events.jsonl`: Timestamped log of all thoughts, tool calls, observations, and inter-agent messages.
- `trajectory.md`: Step-by-step human-readable transcript.
- `workspace/`: Repaired toolchain code.

---

## Agentic Traces

See [`traces/README.md`](traces/README.md) for full walkthroughs:
1. **Scenario 1 (C2)**: Hardware constraint off-by-one repair in `npu/validator.py`.
2. **Scenario 2 (T3)**: Defective test expectation repair with oracle validation.
3. **Scenario 3 (L3)**: Compiler lowering pass repair in `minilang/passes.py`.
4. **Scenario 4 (P2/P6)**: Policy enforcement trace showing an out-of-layer edit denial (P2) and an invalid corpus rollback (P6).

---

## Demo & Presentation
## Demo & Presentation

For demo presentation:
- **Offline Check**: `cd src && python3 -m toyfix check` (verifies clean toolchain and all 22 catalog faults in <1s).
- **Live Episode**: `cd src && python3 -m toyfix episode C2` (demonstrates end-to-end multi-agent repair in ~90s).
- **Policy Enforcement**: Examine `traces/scenario4_policy_violation_P2_P6.md` for policy P2 denial and policy P6 rollback.

---

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE) for details.
