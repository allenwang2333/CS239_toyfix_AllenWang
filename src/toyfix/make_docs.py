"""Generate the parts of the requirements docs that must match the code:
tools.md and the LLM agent files (with their exact system prompts).

Run from src/:  python3 -m toyfix.make_docs
"""

from pathlib import Path

from .agents.llm_agent import DIAGNOSER, REPAIR, REVIEWER, SOLO, AgentSpec
from .context import EpisodeContext, Flags
from .tools import TOOLS, tools_for

DOCS = Path(__file__).resolve().parent.parent.parent / "toyfix"

# Tools used by the scripted agents (Python functions, not LLM tools).
INTERNAL_TOOLS = [
    ("make_workspace", "toyfix/faults.py",
     "reads the clean toolchain and a fault id; copies the toolchain into the episode "
     "workspace and applies the fault's exact text replacements; returns nothing "
     "(fault metadata is written only to scoreboard/fault.json)"),
    ("run_visible_tests", "toyfix/agents/test_runner.py",
     "reads the workspace; runs every visible test; returns per-test results "
     "(name, machine, expected, actual, stage, detail) and the failure report text"),
    ("verify", "toyfix/agents/verifier.py",
     "reads the workspace, the post-injection baseline, the assigned layers, and the hidden "
     "corpus; returns a VerifierReport with the checks scope, visible_tests, test_edits, "
     "no_test_special_cases, hidden_valid_corpus, and hidden_invalid_corpus"),
    ("corpus_counts", "toyfix/tools.py",
     "runs the hidden valid and invalid corpus on the workspace toolchain; returns only "
     "(passed, total) for each set"),
    ("may_mark_fixed", "toyfix/agents/verifier.py",
     "reads a VerifierReport and the Reviewer's submission; returns (fixed: bool, reason)"),
]

TOOL_IO = {
    "list_files": "input: optional layer; output: workspace files, each tagged with its layer or [protected]",
    "read_file": "input: path, optional start_line/end_line; output: up to 400 numbered lines of a workspace file",
    "search_code": "input: regex pattern, optional path prefix; output: matching 'file:line: text' rows (max 60)",
    "read_spec": "input: optional section ('4') or paragraph ('4.4'); output: that part of spec.md, or the whole spec",
    "run_tests": "input: optional name filter; output: pass count and, for each failing test, expected vs actual result, stage, and detail",
    "run_program": "input: source or path, kind (minilang|npu), machine, max_steps; output: JSON with stage (compile|assemble|validate|run), actual result text, steps, detail",
    "compile_program": "input: MiniLang source or path, machine, optional stage (frontend|canonicalize|fuse|bufferize|lower-npu|asm); output: NPU assembly text, the IR after that stage, or the compile error",
    "validate_program": "input: source or path, kind, machine; output: 'valid' or the list of hardware-profile violations",
    "trace_execution": "input: source or path, kind, machine, start_step, limit (<=200); output: result summary and per-step rows (pc, instruction, written words)",
    "reference_eval": "input: MiniLang source or path; output: the reference interpreter's result text (oracle)",
    "minimize_failure": "input: MiniLang source or path, machine; output: JSON with the smallest program found whose compiled result differs from the reference, both results, and the stage",
    "show_diff": "input: none; output: unified diff of the workspace against the post-injection baseline",
    "edit_file": "input: path, old_text, new_text; output: 'edited <path>' or a DENIED/ERROR message (scope-checked; old_text must occur exactly once)",
    "revert_file": "input: path; output: confirmation; restores one file to its state at the start of the attempt",
    "check_corpus": "input: none; output: two counts only: hidden valid programs accepted and correct, hidden invalid programs rejected",
    "submit_diagnosis": "input: layer, files, root_cause, evidence, spec_sections, fix_hint; output: confirmation; ends the Diagnoser run and gives the Coordinator the diagnosis",
    "submit_patch": "input: summary, spec_sections, disagree_with_diagnosis; output: confirmation; ends the Repair (or Solo) Agent run",
    "submit_review": "input: decision (approve|reject), rationale, spec_sections, concerns; output: confirmation; ends the Reviewer run",
}

ROLE_INTRO = {
    "diagnoser": "LLM-based. Finds the layer that contains the root cause of the failing "
                 "tests and proves it with tool evidence. It cannot modify files.",
    "repair": "LLM-based. Fixes the diagnosed fault by editing files of the one layer "
              "that the Coordinator assigned for the current attempt.",
    "reviewer": "LLM-based. Reviews the full diff against the spec after the Verifier "
                "passes. Its approval is required before the Verifier may mark the "
                "episode FIXED. It cannot modify files.",
    "solo": "LLM-based. Used only in the single-agent ablation (`--mode solo`). One agent "
            "diagnoses and repairs; all four layers are assigned to it; there is no "
            "Reviewer. It exists to compare against the multi-agent design.",
}

FILE_NAMES = {"diagnoser": "diagnoser.md", "repair": "repair_agent.md",
              "reviewer": "reviewer.md", "solo": "solo_agent_ablation.md"}


def tools_line(name: str) -> str:
    return f"{name}: {TOOL_IO[name]}"


def agent_doc(spec: AgentSpec) -> str:
    ctx = EpisodeContext(ws=None, log=None, flags=Flags())  # type: ignore[arg-type]
    names = [t.name for t in tools_for(spec.role, ctx)]
    ablation = [t.name for t in tools_for(spec.role, ctx)
                if TOOLS[t.name].needs_oracle or TOOLS[t.name].needs_corpus_feedback]
    return f"""# {spec.name}

**Type:** {ROLE_INTRO[spec.role]}

**Implementation:** `src/toyfix/agents/llm_agent.py` (tool-use loop),
prompt file `src/toyfix/prompts/{spec.prompt_file}` with `_system.md` inserted.
Model: DeepSeek (`deepseek-flash` by default) through the OpenAI-compatible
chat-completions API.

**Available tools:** {", ".join(f"`{n}`" for n in names)}

- Finish tool: `{spec.finish_tool}`. The run ends when it succeeds.
- Tool-call budget per run: {spec.tool_budget} (policy P9); at most {spec.max_turns} model turns.
- Removed in ablations: {", ".join(f"`{n}`" for n in ablation) or "none"}
  (`--no-oracle` removes the oracle tools, `--no-corpus-feedback` removes `check_corpus`).

## System prompt (exact text sent to the model)

````text
{spec.system_prompt.strip()}
````
"""


def main() -> None:
    (DOCS / "agents").mkdir(parents=True, exist_ok=True)
    for spec in (DIAGNOSER, REPAIR, REVIEWER, SOLO):
        (DOCS / "agents" / FILE_NAMES[spec.role]).write_text(agent_doc(spec))
    assert set(TOOL_IO) == set(TOOLS), set(TOOL_IO) ^ set(TOOLS)
    # One tool per line, "tool_name: inputs and outputs" (submission format).
    lines = [tools_line(n) + " [LLM tool, src/toyfix/tools.py]" for n in TOOLS]
    lines += [f"{name}: {desc} [scripted-agent tool, src/{path}]"
              for name, path, desc in INTERNAL_TOOLS]
    (DOCS / "tools.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {DOCS / 'tools.md'} and {len(FILE_NAMES)} LLM agent files")


if __name__ == "__main__":
    main()
