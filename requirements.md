# ToyFix: System Requirements

## 1. Purpose and Overview

ToyFix is a multi-agent software engineering system. The system diagnoses and repairs defects in an artificial intelligence (AI) compiler toolchain.

The primary engineering goal is:
The multi-agent system must diagnose and fix software bugs across multiple system layers without adding invalid restrictions to valid user programs and without accepting invalid programs.

The system repairs four distinct architectural layers:
1. `tests`: Visible test suites, test input programs, and expected test output files.
2. `constraints`: Hardware profile limits and validity rules checked by a static validator.
3. `compiler`: Compilation passes and lowering transformations from high-level tensor operations to accelerator instructions.
4. `simulator`: Instruction execution semantics, memory models, and functional behavior of the accelerator hardware.

## 2. System Under Test (SUT)

The system under test is a complete, self-contained neural processing unit (NPU) compiler toolchain.

### 2.1 Hardware Architecture and NPU Accelerator
The target execution platform is a tile-based NPU accelerator.
- **Memory Model**: The machine has two distinct memory spaces:
  - Dynamic Random-Access Memory (DRAM): Main system storage for input and output data.
  - Scratchpad Memory (SPAD): High-speed on-chip SRAM for tile-level compute operations.
- **Instruction Set Architecture (ISA)**: The processor supports 9 instructions:
  - `load`: Two-dimensional strided Direct Memory Access (DMA) from DRAM to scratchpad.
  - `store`: Two-dimensional strided DMA from scratchpad to DRAM.
  - `mm`: Matrix multiplication of scratchpad tiles (`dst = A @ B`).
  - `mma`: Matrix multiplication with accumulation (`dst = dst + A @ B`).
  - `vadd`: Vector element-wise addition.
  - `vsub`: Vector element-wise subtraction.
  - `vmul`: Vector element-wise multiplication.
  - `vrelu`: Vector Rectified Linear Unit activation (`max(x, 0)`).
  - `out`: Direct transfer of DRAM words to the system output log.

### 2.2 Hardware Profiles
Hardware constraints vary across hardware targets defined in profile configurations:
- `npu-tiny`: Matrix unit shape 2x2x2, vector length 2, no `mma` support, 4-bit DMA row stride limit, 2-word DMA alignment, 16-word scratchpad, 256-word DRAM.
- `npu-base`: Matrix unit shape 4x4x4, vector length 8, `mma` support enabled, 8-bit DMA row stride limit, 4-word DMA alignment, 64-word scratchpad, 4096-word DRAM.
- `npu-wide`: Matrix unit shape 8x16x4, vector length 64, `mma` support enabled, 16-bit DMA row stride limit, 4-word DMA alignment, 256-word scratchpad, 65536-word DRAM.

### 2.3 The MiniLang Tensor Language
MiniLang is a statically shaped tensor programming language with Python syntax:
- Types include scalar 32-bit integers (`int`) and rank-1 and rank-2 tensors of 32-bit signed integers (`Tensor[M, N, i32]`).
- Arithmetic operations include element-wise `+`, `-`, `*`, matrix product `@`, unary negation `-`, and `.T` transpose.
- Constructors include `tensor(...)`, `zeros(...)`, `ones(...)`, `full(...)`, and `iota(...)`.
- Functions inline at compile time. Static `for` loops unroll at compile time.

### 2.4 Compiler Pipeline
The compiler translates MiniLang source code into validated NPU assembly programs through structured passes:
1. `frontend`: Parses Python Abstract Syntax Tree (AST) into an intermediate representation (`ml` dialect).
2. `canonicalize`: Folds constants, simplifies identity arithmetic, and eliminates common subexpressions.
3. `fuse`: Identifies dense layer patterns (`matmul` + `bias` + `relu`) and combines them into `ml.linear` operations.
4. `bufferize`: Allocates physical memory buffers, calculates strided memory views, and reuses memory offsets for dead values.
5. `lower-npu`: Tiles large tensor dimensions to fit hardware matrix unit shapes and vector lengths, generates DMA transfers, and emits NPU assembly instructions.

### 2.5 Reference Interpreter Oracle
The toolchain includes a high-level reference interpreter (`reference.py`). The reference interpreter directly executes the Python AST and produces correct mathematical results. The agents use the reference interpreter as an authoritative execution oracle for MiniLang programs.

## 3. Multi-Agent System Architecture

ToyFix uses a team of specialized agents. Each agent has an assigned role, dedicated toolset, and strict operational boundaries.

```
       +-------------------------------------------------------------+
       |                        Coordinator                          |
       |  - Orchestrates lifecycle steps                             |
       |  - Enforces attempt budgets                                 |
       |  - Isolates ground truth and manages rollbacks              |
       +------------------------------+------------------------------+
                                      |
         +----------------------------+----------------------------+
         |                            |                            |
         v                            v                            v
+------------------+         +------------------+        +-------------------+
|  Fault Injector  |         |   Test Runner    |        |     Diagnoser     |
|  - Injects bug   |         |  - Runs visible  |        |  - Read-only      |
|  - Hides metadata|         |    test suite    |        |  - Finds root     |
+------------------+         +------------------+        |    cause layer    |
                                                         +---------+---------+
                                                                   |
                                                                   v
+------------------+         +------------------+        +-------------------+
|     Reviewer     |         |     Verifier     |        |   Repair Agent    |
|  - Read-only     |         |  - Objective     |        |  - Mutates only   |
|  - Checks diff   |<--------|    gatekeeper    |<-------|    assigned layer |
|  - Validates spec|         |  - Hidden corpus |        |  - Submits patch  |
+------------------+         +------------------+        +-------------------+
```

### 3.1 Coordinator
- **Role**: Central coordinator and state machine controller.
- **Implementation**: Deterministic script (non-LLM).
- **Functions**:
  - Initializes episode workspaces from clean toolchain sources.
  - Controls attempt iterations (up to 4 attempts per fault).
  - Routes structured messages between agents.
  - Assigns exactly one layer to the Repair Agent per attempt.
  - Automatically reverts workspace edits when verification fails or when policies are broken.

### 3.2 Fault Injector
- **Role**: Generates reproducible defect scenarios in isolated workspaces.
- **Implementation**: Deterministic script (non-LLM).
- **Functions**:
  - Maintains a catalog of 22 realistic software defects across all 4 system layers.
  - Creates workspace copies and executes precise text substitutions.
  - Stores fault ground-truth metadata in isolated files outside the reach of LLM agents.

### 3.3 Test Runner
- **Role**: Test harness execution and failure reporting.
- **Implementation**: Deterministic script (non-LLM).
- **Functions**:
  - Executes visible test cases (24 test programs covering assembly and MiniLang).
  - Collects pass/fail status, expected outputs, actual outputs, and failure stage details.
  - Formats diagnostic failure reports for the Coordinator and Diagnoser.

### 3.4 Diagnoser
- **Role**: Root cause investigation and fault localization.
- **Implementation**: LLM agent (`deepseek-flash` by default).
- **Functions**:
  - Analyzes test failure logs.
  - Explores workspace files, reads hardware specifications, and runs test programs with diagnostic tools.
  - Probes hardware boundaries using assembly inputs.
  - Submits a structured diagnosis identifying the faulty layer, failing files, root cause explanation, tool evidence, and specification citations.

### 3.5 Repair Agent
- **Role**: Code patch generation.
- **Implementation**: LLM agent (`deepseek-flash` by default).
- **Functions**:
  - Receives the assigned layer and root cause diagnosis from the Coordinator.
  - Reproduces the target failure with local tests.
  - Performs edits on files within the assigned layer.
  - Verifies that modified visible tests pass.
  - Submits a final patch description citing justification from the specification.

### 3.6 Verifier
- **Role**: Rule-based gatekeeper for acceptance.
- **Implementation**: Deterministic rule checker (non-LLM).
- **Functions**:
  - Evaluates every patch against strict verification criteria:
    1. Scope check: Edits must belong only to the assigned layer and touch no protected files.
    2. Visible test check: All 24 visible test cases must pass.
    3. Test edits check: Changed test expectations must match reference interpreter output. Test code can change only in comment lines.
    4. Anti-cheat check: Production code must not contain hardcoded test names or paths.
    5. Hidden valid corpus check: All 29 hidden valid programs must compile, validate, and execute correctly.
    6. Hidden invalid corpus check: All 15 hidden invalid programs must be rejected by the validator.
  - Decides whether an episode meets criteria to be marked as FIXED.

### 3.7 Reviewer
- **Role**: Independent code review and specification audit.
- **Implementation**: LLM agent (`deepseek-flash` by default).
- **Functions**:
  - Operates strictly in read-only mode after the Verifier reports an initial pass.
  - Inspects the complete unified diff against the post-injection baseline.
  - Cross-references changes against requirements in `spec.md`.
  - Verifies that edge cases and boundary conditions are preserved.
  - Submits a formal review approving or rejecting the patch with detailed rationale.

### 3.8 Solo Agent (Ablation Baseline)
- **Role**: Single-agent baseline for comparative benchmarking.
- **Implementation**: LLM agent (`deepseek-flash` by default).
- **Functions**:
  - Performs diagnosis, editing, and self-testing as a single unified worker without inter-agent handoffs or independent code review.

## 4. Supported Operations and Workflows

The application supports four primary execution workflows from the command line:

1. **Single Repair Episode (`python3 -m toyfix episode <FAULT_ID>`)**:
   - Injects a single fault or fault combination from the catalog.
   - Executes the multi-agent repair loop.
   - Generates an event log (`events.jsonl`), markdown trajectory (`trajectory.md`), baseline snapshot, and final workspace.
2. **Benchmark Execution (`python3 -m toyfix bench`)**:
   - Executes repair episodes across the entire fault catalog with parallel worker processes.
   - Computes statistical summaries: fix rate, first-diagnosis accuracy, layer adherence, tool call counts, and elapsed time.
   - Generates summary reports (`summary.md` and `results.json`).
3. **Controlled Ablations**:
   - `--mode solo`: Runs the single-agent baseline without role boundaries or Reviewer.
   - `--no-oracle`: Removes reference interpreter tools (`reference_eval`) to evaluate performance without an execution oracle.
   - `--no-corpus-feedback`: Removes hidden corpus test feedback tools (`check_corpus`) from the Repair Agent.
4. **Deterministic Self-Check (`python3 -m toyfix check`)**:
   - Executes offline verification without network calls or API keys.
   - Confirms that the clean toolchain passes all tests and that all 22 catalog faults are detectable and reversible.

## 5. Trace Capture and Observability

ToyFix provides complete visibility into multi-agent operations:
- Every execution generates a structured event log (`events.jsonl`) recording:
  - Exact UTC timestamps.
  - Agent thoughts and natural language reasoning.
  - Tool invocations and argument payloads.
  - Tool outputs, execution returns, and policy denial messages.
  - Inter-agent messages (test reports, diagnoses, layer assignments, patch submissions, review submissions).
- Every execution generates a human-readable trajectory (`trajectory.md`) capturing the chronological progression of the team.

## 6. Success and Acceptance Criteria

An episode succeeds and marks the status as **FIXED** if and only if all of the following conditions are met:
1. **Verification Soundness**:
   - All 24 visible tests pass.
   - All 29 hidden valid test cases pass without regression.
   - All 15 hidden invalid test cases are rejected by the validator.
2. **Scope Confinement**:
   - Modifications occur only in files that belong to layers assigned during the episode.
   - No protected system files are modified.
   - No tests are deleted, renamed, or skipped.
3. **Specification Compliance**:
   - The Reviewer approves the change with explicit citations to paragraphs in `spec.md`.
   - If test expectations were modified, the changes match the reference interpreter output.
