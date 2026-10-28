# ToyFix: System Policies

This document defines what the multi-agent system and its individual agents **must never do**.

The policies enforce strict boundaries across five categories:
1. Permission Boundaries
2. Capability Boundaries
3. Lifecycle Boundaries (Ordering and Prerequisites)
4. Information Flow Boundaries
5. Information Isolation Boundaries

The formal system policies (P1 through P9) implement these boundaries.

---

## 1. Permission Boundaries

Permission boundaries govern which agents have authorization to call specific tools and access specific system resources.

### 1.1 Tool Access Matrix

| Tool | Coordinator | Fault Injector | Test Runner | Diagnoser | Repair Agent | Verifier | Reviewer | Solo Agent |
|---|---|---|---|---|---|---|---|---|
| `list_files` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `read_file` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `search_code` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `read_spec` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `run_tests` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `run_program` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `compile_program` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `validate_program` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `trace_execution` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `reference_eval` | No | No | No | **Yes** | **Yes** | No | **Yes** | **Yes** |
| `minimize_failure` | No | No | No | **Yes** | No | No | No | **Yes** |
| `show_diff` | No | No | No | No | **Yes** | No | **Yes** | **Yes** |
| `edit_file` | No | No | No | **DENIED** | **Assigned Layer Only** | No | **DENIED** | **All Layers** |
| `revert_file` | No | No | No | **DENIED** | **Assigned Layer Only** | No | **DENIED** | **All Layers** |
| `check_corpus` | No | No | No | **DENIED** | **Yes** | No | **DENIED** | **Yes** |
| `submit_diagnosis`| No | No | No | **Yes** | **DENIED** | No | **DENIED** | **DENIED** |
| `submit_patch` | No | No | No | **DENIED** | **Yes** | No | **DENIED** | **Yes** |
| `submit_review` | No | No | No | **DENIED** | **DENIED** | No | **Yes** | **DENIED** |
| `make_workspace` | No | **Yes** | No | **DENIED** | **DENIED** | No | **DENIED** | **DENIED** |
| `run_visible_tests`| **Yes** | No | **Yes** | **DENIED** | **DENIED** | **Yes** | **DENIED** | **DENIED** |
| `verify` | **Yes** | No | No | **DENIED** | **DENIED** | **Yes** | **DENIED** | **DENIED** |
| `may_mark_fixed` | **Yes** | No | No | **DENIED** | **DENIED** | **Yes** | **DENIED** | **DENIED** |

### 1.2 Prohibited Permission Operations
- **Read-Only Agent Mutation Prohibition (P1)**: The Diagnoser and the Reviewer must never call file modification tools (`edit_file`, `revert_file`). They must never modify workspace contents. Any call to mutation tools by read-only agents must be denied immediately.
- **Role-Specific Submission Tool Exclusivity (P1)**:
  - Only the Diagnoser may call `submit_diagnosis`.
  - Only the Repair Agent (or Solo Agent) may call `submit_patch`.
  - Only the Reviewer may call `submit_review`.
  - Only the Verifier may execute `may_mark_fixed`.
  - Agents must never call submission tools designated for other roles.
- **Unassigned Layer Mutation Prohibition (P2)**: The Repair Agent must never modify any file that belongs outside the single layer assigned by the Coordinator for the current attempt. Attempts to edit files in unassigned layers must be rejected with policy denial errors.
- **Protected File Immutability (P3)**: No agent, regardless of assigned layer or role, may modify protected system files:
  - `spec.md` (the ground-truth specification)
  - `machines/*.toml` (hardware profile definitions)
  - `minilang/parser.py` (frontend syntax parser)
  - `minilang/reference.py` (reference interpreter oracle)
  - `cli.py` (toolchain command-line harness)
  - `npu/machine.py` (hardware machine profile dataclass)
- **Tool-Call Budget Limits (P9)**:
  - The Diagnoser must not exceed 25 tool calls per attempt.
  - The Repair Agent must not exceed 30 tool calls per attempt.
  - The Reviewer must not exceed 20 tool calls per attempt.
  - When an agent exhausts its call budget, the tool layer must reject all further operational tool calls and permit only the agent's finishing submission tool.

---

## 2. Capability Boundaries

Capability boundaries define what actions agents are functionally capable of taking and what operations are strictly forbidden.

### 2.1 File System Manipulation Prohibitions (P5)
- Agents must never create new files in the workspace.
- Agents must never delete existing files in the workspace.
- Agents must never rename or move files in the workspace.
- Agents must never alter directory structures.

### 2.2 Test Suite Modification Boundaries (P4, P5)
- Agents must never delete, rename, or skip test cases.
- In test program files (`tests/*.ml`, `tests/*.npu`), agents may modify **only comment lines**. Agents must never change executable instructions, tensor initializations, or assertions.
- Agents may modify test expected output files (`tests/*.expected`) if and only if all of the following conditions are met:
  1. The Coordinator assigned the `tests` layer to the Repair Agent.
  2. For a MiniLang test, the new expected output exactly matches the execution output of the reference interpreter oracle (`reference_eval`).
  3. The Reviewer provides explicit justification citing at least one specific paragraph in `spec.md` that proves the previous expected output was incorrect.

### 2.3 Anti-Cheating and Hardcoding Restrictions (P5)
- Added lines in production compiler, validator, and simulator code must never contain special-case logic for tests.
- Toolchain code must never contain references to `tests/`, `.expected` file extensions, or specific test case names (e.g., `dense_layer`, `npu_mma`).

### 2.4 Semantic Correctness and Soundness Boundaries (P6)
- **No Over-Restriction (Soundness on Valid Programs)**: A patch must never cause the toolchain to reject, miscompile, or incorrectly execute any program in the hidden valid test corpus. Agents must never restrict valid language constructs (e.g., forbidding matrix shapes not divisible by tile sizes, restricting valid loop depths, or narrowing immediate ranges).
- **No Over-Loosening (Completeness on Invalid Programs)**: A patch must never cause the validator or compiler to accept any program in the hidden invalid test corpus. Agents must never widen hardware profile limits beyond the specification.

---

## 3. Lifecycle Boundaries (Ordering and Prerequisites)

Lifecycle boundaries govern the state machine, operational sequence, and prerequisite conditions for agent activation.

### 3.1 Strict Execution State Machine

```
[Start Episode]
       |
       v
[Phase 0: Workspace Creation & Fault Injection]
       |
       v
[Phase 1: Initial Test Baseline & Verifier Baseline]
       |
       v
[Phase 2: Diagnoser Execution]
       |
       v
[Phase 3: Coordinator Diagnosis Evaluation & Layer Assignment]
       |
       v
[Phase 4: Repair Agent Execution]
       |
       v
[Phase 5: Verifier Objective Evaluation]
       |
       +---> [Failed Verifier Checks] ---> [Coordinator Attempt Revert]
       |                                                |
       | (All checks pass)                              v
       v                                       (Attempts < 4) ---> [Next Attempt: Return to Phase 2]
[Phase 6: Reviewer Audit]                               |
       |                                                | (Attempts exhausted)
       +---> [Reviewer Rejection] ----------------------+---> [Final Baseline Revert -> UNRESOLVED]
       |
       | (Reviewer Approves)
       v
[Phase 7: Verifier may_mark_fixed -> FIXED]
```

### 3.2 Ordering and Prerequisite Rules
1. **Diagnosis Precedes Repair (P2)**:
   - The Repair Agent must never run without a completed diagnosis from the Diagnoser in the current attempt.
   - The Coordinator must never assign a layer without an evidence-based diagnosis.
   - A layer assignment expires when the Repair Agent finishes its attempt. A subsequent attempt requires a fresh diagnosis before repair can commence.
2. **Repair Precedes Verification**:
   - The Verifier must never evaluate an attempt until the Repair Agent explicitly calls `submit_patch`.
3. **Verification Precedes Review (P8)**:
   - The Reviewer must never be invoked if any Verifier check fails. The Reviewer executes only when all objective verification checks (scope, visible tests, test edits, hidden valid corpus, hidden invalid corpus) report a pass.
4. **Independent Review Approval Precedes FIXED Status (P8)**:
   - The Verifier must never mark an episode as `FIXED` without explicit approval from the Reviewer.
   - If the Reviewer rejects the patch, the episode must not be marked as fixed, and the attempt must be reverted.
5. **Attempt Budget Limit (P9)**:
   - An episode must allow a maximum of 4 attempts.
   - If the system does not reach a passing verification and approval after 4 attempts, the episode must terminate with status `UNRESOLVED`.

### 3.3 State Recovery and Rollback Semantics (P6, P9)
- **Failed Attempt Rollback (P6)**: During an attempt, if the Repair Agent's patch lowers the visible pass count, lowers the hidden valid corpus pass count, lowers the hidden invalid corpus rejection count, or violates scope policies (P2, P3, P4, P5), the Coordinator must immediately roll back all workspace files to the checkpoint saved before the attempt.
- **Unresolved Episode Baseline Restoration (P9)**: When an episode terminates as `UNRESOLVED`, the Coordinator must completely restore the workspace to the post-injection baseline. No partial, unverified, or unapproved code changes may remain in the final workspace.

---

## 4. Information Flow Boundaries

Information flow boundaries specify authorized communication channels and structured message payloads between agents.

### 4.1 Permitted Inter-Agent Message Channels

1. **Test Runner -> Coordinator & Diagnoser**:
   - Payload: Pass count, total count, list of failing test names, expected output, actual output, failure stage (`compile`, `assemble`, `validate`, `run`), and diagnostic failure detail.
2. **Diagnoser -> Coordinator**:
   - Payload: Structured diagnosis consisting of:
     - `layer`: The single localized defect layer (`tests`, `constraints`, `compiler`, or `simulator`).
     - `files`: Workspace paths containing the defect.
     - `root_cause`: Detailed technical explanation of the failure mechanism.
     - `evidence`: Empirical proof collected from tool outputs.
     - `spec_sections`: Paragraph citations from `spec.md`.
     - `fix_hint`: Proposed repair approach that avoids adding restrictions.
3. **Coordinator -> Repair Agent**:
   - Payload: Scoped assignment consisting of `assigned_layer` and the structured diagnosis summary from the Diagnoser.
4. **Repair Agent -> Verifier & Reviewer**:
   - Payload: Structured patch submission consisting of:
     - `summary`: Explanation of code changes.
     - `spec_sections`: Justifying citations from `spec.md`.
     - `disagree_with_diagnosis`: Optional explanation if the agent disagrees with the Diagnoser.
5. **Verifier -> Coordinator & Reviewer**:
   - Payload: Structured verification report detailing pass/fail status for `scope`, `visible_tests`, `test_edits`, `no_test_special_cases`, `hidden_valid_corpus`, and `hidden_invalid_corpus`.
6. **Reviewer -> Verifier & Coordinator**:
   - Payload: Structured review decision consisting of:
     - `decision`: Explicit `approve` or `reject`.
     - `rationale`: Technical evaluation of the patch against `spec.md`.
     - `spec_sections`: Paragraph citations verifying correctness.
     - `concerns`: Actionable issues if the patch is rejected.

### 4.2 Prohibited Information Flow Channels
- **Direct Agent Bypass**: The Diagnoser must never communicate directly with the Repair Agent without Coordinator mediation.
- **Reviewer Prompt Injection**: The Repair Agent must never modify Reviewer prompts or inject unmonitored guidance into the Reviewer's context window.
- **Unstructured Backchannels**: Agents must never pass information through temporary scratch files or environmental variables outside monitored tool parameters.

---

## 5. Information Isolation Boundaries

Information isolation boundaries define what information must remain strictly concealed from agents to prevent contamination, overfitting, or cheating.

### 5.1 Fault Metadata Isolation (P7)
- **Ground Truth Concealment**: Fault ground truth metadata (fault ID, injected line edits, catalog description, and tempting incorrect fix) must never be sent to any LLM agent.
- **Scoreboard Isolation**: Fault metadata must be written exclusively to `scoreboard/fault.json` outside the workspace. Agents must never have read or list permissions for the `scoreboard/` directory.

### 5.2 Hidden Corpus Isolation (P6, P7)
- **Location Isolation**: The hidden test corpus (29 valid programs and 15 invalid programs) resides in `src/toyfix/hidden/corpus`, strictly outside the episode workspace.
- **Content Concealment**: Agents must never read, search, or inspect files in the hidden corpus directory.
- **Aggregate Feedback Only**: The tool `check_corpus` must report only aggregate numerical pass counts (e.g., `29/29 valid, 15/15 invalid`). The tool must never return failing test names, source code, input values, error messages, or failure traces.

### 5.3 Filesystem Jailing (P7)
- **Workspace Confinement**: Agents are strictly confined to their isolated episode workspace (`runs/<episode>/workspace`).
- **Path Traversal Prohibition**: The tool layer must resolve all relative paths strictly within the workspace root. Any attempt to use parent directory traversal (`../`) or absolute host paths to access the clean toolchain, baseline snapshots, or other episodes must be blocked immediately with a `ToolDenied` exception.

### 5.4 Clean Baseline Isolation (P7)
- Agents must never have access to the clean reference repository (`src/sut`) during an episode.
- Agents must never inspect the post-injection baseline snapshot (`baseline/`) to bypass diagnosis.

---

## 6. Policy Index and Formal Rule Summary

The operational policies are numbered P1 through P9:

- **P1 (Role Separation and Tool Permissions)**: Agents may call only the tools assigned to their specific role. Read-only agents (Diagnoser, Reviewer) cannot edit files. Only Diagnoser can submit a diagnosis; only Repair Agent can submit a patch; only Reviewer can submit a review.
- **P2 (Scope and Layer Assignment)**: The Repair Agent may modify only files of the layer assigned by the Coordinator for the current attempt (`tests`, `constraints`, `compiler`, or `simulator`). Edits outside the assigned layer are denied.
- **P3 (Protected Files)**: Protected files (`spec.md`, `machines/*.toml`, `minilang/parser.py`, `minilang/reference.py`, `cli.py`, `npu/machine.py`) are immutable by all agents.
- **P4 (Test Modification Rules)**: Test expected results can be modified only when the `tests` layer is assigned, MiniLang modifications match the reference interpreter output, and the Reviewer cites justifying specification paragraphs.
- **P5 (Test Suite Integrity and Anti-Cheat)**: Agents must not delete, add, rename, or skip tests. Test programs can only have comments modified. Toolchain code must not contain test names or test-specific logic.
- **P6 (Hidden Corpus Soundness and Invalidation)**: Patches must not reject any hidden valid program and must not accept any hidden invalid program. Attempts that degrade corpus counts are reverted.
- **P7 (Information Isolation)**: Fault metadata, baseline snapshots, clean toolchains, and hidden corpus sources are inaccessible to agents. Paths outside the workspace are blocked. Corpus feedback is aggregate counts only.
- **P8 (Independent Verification and Approval)**: Only the Verifier can mark an episode FIXED. Verifier requires all checks to pass and requires independent Reviewer approval.
- **P9 (Budgeting and Final Rollback)**: Episodes have a 4-attempt limit and strict tool-call budgets per agent run. Unresolved episodes are reverted to the baseline state.
