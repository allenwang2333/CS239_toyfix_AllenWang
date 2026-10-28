# ToyFix: Demo Guide & Presentation Script

This document provides:
1. A **5-minute YouTube video script and storyboard** for the Phase 1 submission deliverable.
2. A **live demo cheat sheet** for the class presentation.

---

## Part 1: 5-Minute YouTube Video Script

### Video Outline

| Time Window | Segment | On-Screen Display | Narration / Key Points |
|---|---|---|---|
| **0:00 – 1:00** | Problem & Architecture | Slide or diagram of ToyFix architecture | Introduce ToyFix; explain the over-restriction and under-restriction problem in automated compiler repair. |
| **1:00 – 2:15** | Live Multi-Agent Execution | Terminal executing `python3 -m toyfix episode C2` | Show live collaboration between Diagnoser, Coordinator, Repair Agent, Verifier, and Reviewer. |
| **2:15 – 3:30** | Trace Deep Dive | Display `traces/scenario1_constraint_repair_C2.md` | Highlight agent thoughts, tool observations, layer assignments, and independent review audit. |
| **3:30 – 4:30** | Policy Enforcement & Soundness | Display `traces/scenario4_policy_violation_P2_P6.md` | Demonstrate policy P2 (out-of-layer edit denial) and policy P6 (hidden invalid corpus rollback on under-restriction). |
| **4:30 – 5:00** | Conclusion & Deliverables | GitHub repository view (`requirements.md`, `policies.md`) | Summarize Phase 1 deliverables and transition to Phase 2. |

---

### Minute-by-Minute Script

#### [0:00 - 1:00] Introduction: The Research Problem & System Architecture
- **Voiceover**:
  *"Hello. Welcome to the demonstration of ToyFix, our multi-agent software engineering system for compiler toolchain repair.
  When LLM agents repair code, they frequently fall into two traps:
  First, **over-restriction**: rejecting valid user programs to make a failing test pass.
  Second, **under-restriction**: loosening hardware checks so that invalid code is accepted, which causes real hardware to crash.
  ToyFix tests whether a multi-agent team can diagnose and fix defects across tests, hardware constraints, compiler passes, and simulator semantics without over-restricting or under-restricting the system.
  Our toolchain compiles MiniLang—a tensor language—down to a tile-based Neural Processing Unit with strided DMA and matrix units."*
- **Visual**: Show the architecture diagram from `README.md`.

#### [1:00 - 2:15] Live Multi-Agent Repair Episode
- **Action**: Run in terminal:
  ```bash
  cd src
  python3 -m toyfix episode C2
  ```
- **Voiceover**:
  *"Here we run a live repair episode for catalog fault C2.
  Notice the multi-agent workflow:
  1. The Test Runner identifies a failing test: npu_stride_max fails at the validation stage.
  2. The Diagnoser analyzes the error. It is read-only. It reads the specification and probes the hardware boundaries. It determines that the validator has an off-by-one check rejecting row stride 15, which specification section 4.2 defines as valid.
  3. The Coordinator reviews the diagnosis and assigns ONLY the constraints layer to the Repair Agent.
  4. The Repair Agent edits npu/validator.py, verifies that all 24 visible tests pass, and checks the hidden corpus.
  5. The Verifier runs objective checks against 29 hidden valid and 15 hidden invalid programs.
  6. Finally, the Reviewer independently audits the diff against the specification and approves it. The episode finishes as FIXED in about 60 seconds."*

#### [2:15 - 3:30] Inspecting the Agentic Trace
- **Visual**: Open `traces/scenario1_constraint_repair_C2.md`.
- **Voiceover**:
  *"Let's look at the generated trace.
  Every turn captures:
  - The agent's internal thoughts and hypotheses.
  - The exact tool actions and parameter payloads.
  - Inter-agent messages—like the structured diagnosis sent to the Coordinator.
  - Tool observations, such as boundary probe results on npu-tiny and npu-base.
  Our system records both human-readable Markdown trajectories and machine-parseable JSONL event streams.
  Notice that the Reviewer operates strictly in read-only mode, verifying that the fix relaxes an off-by-one error rather than introducing new restrictions."*

#### [3:30 - 4:30] Policy Enforcement: Denials and Rollbacks
- **Visual**: Open `traces/scenario4_policy_violation_P2_P6.md`.
- **Voiceover**:
  *"Now let's examine what happens when an agent violates policy boundaries.
  In Scenario 4, we test an adversarial scenario:
  First, the Repair Agent attempts to edit minilang/compiler.py while assigned to the constraints layer.
  The tool layer immediately triggers Policy P2: it blocks the edit and raises a policy denial error.
  Second, the agent attempts to fix the test by loosening the validator check, multiplying the stride limit by 2.
  While this makes visible tests pass, our Verifier runs the hidden invalid corpus. The rejection rate drops from 15/15 to 13/15. Two illegal programs were accepted!
  Policy P6 detects this under-restriction and the Coordinator immediately reverts the workspace to the clean checkpoint, resetting the attempt."*

#### [4:30 - 5:00] Conclusion & Phase 1 Deliverables
- **Visual**: Show `requirements.md` and `policies.md` in the GitHub repo.
- **Voiceover**:
  *"In Phase 1, we delivered:
  - A working multi-agent application.
  - requirements.md and policies.md detailing permissions, capabilities, lifecycles, information flow, and isolation boundaries.
  - Four complete agentic traces in traces/ covering all layers and policy violations.
  - An offline test suite of 67 tests and a 22-fault benchmark catalog.
  Thank you for watching!"*

---

## Part 2: Class Presentation Live Demo Cheat Sheet

Use these steps for the live demo during class.

### Step 1: Show Clean Self-Check (5 seconds)
Proves the toolchain and catalog are completely healthy:
```bash
cd src
python3 -m toyfix check
```
*Expected Output*: `clean ok  visible 24/24 valid (29, 29) invalid (15, 15) failing=[]`, followed by all 22 faults passing.

### Step 2: Run a Live Repair Episode (60 seconds)
Run a live episode with live DeepSeek API:
```bash
cd src
python3 -m toyfix episode C2
```
*Key things to point out while running*:
- The Test Runner catching the stride limit failure.
- The Diagnoser submitting its diagnosis.
- The Coordinator locking the scope to `constraints`.
- The Verifier checking both the 29 valid and 15 invalid hidden test suites.
- The Reviewer approving the diff.

### Step 3: Show Policy Denial & Rollback (30 seconds)
Open `traces/scenario4_policy_violation_P2_P6.md` or display the denial in terminal:
- Show line with `DENIED by policy P2: minilang/compiler.py is in layer 'compiler', but the assigned layer is ['constraints']`.
- Show line with `hidden_invalid_corpus=FAIL (13/15 invalid programs rejected)`.
- Show `Coordinator reverts the attempt`.

### Step 4: Show Unit Test Coverage (15 seconds)
```bash
python3 -m unittest discover -s tests -t . -v
```
*Expected Output*: `Ran 67 tests in ~16s ... OK`.
