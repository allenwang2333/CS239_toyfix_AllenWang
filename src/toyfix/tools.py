"""Tools that LLM agents call, with role and scope checks.

Policy checks live here, in code, so they hold even if a model ignores its
prompt: P1 (read-only roles), P2 (assigned layer), P3 (protected files),
P7 (no access outside the workspace, aggregate corpus counts only), and P9
(tool-call budget).
"""

import json
import re
from dataclasses import dataclass
from typing import Callable

from .context import EpisodeContext
from .layers import CORPUS_DIR, LAYERS, PROTECTED, is_protected, layer_of
from .workspace import PathError

MAX_RESULT_CHARS = 8000

READERS = {"diagnoser", "repair", "reviewer", "solo"}
EDITORS = {"repair", "solo"}


class ToolDenied(Exception):
    """A policy check rejected the call."""

    def __init__(self, policy: str, message: str):
        super().__init__(message)
        self.policy = policy


class ToolError(Exception):
    """The call was allowed but could not be done (bad arguments, etc.)."""


@dataclass
class Tool:
    name: str
    description: str
    params: dict
    required: list[str]
    roles: set[str]
    fn: Callable[[EpisodeContext, dict], object]
    finish: bool = False
    needs_oracle: bool = False
    needs_corpus_feedback: bool = False

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.params,
                           "required": self.required}}}


@dataclass
class ToolResult:
    ok: bool
    text: str
    data: object = None
    denied: bool = False


# ---- helpers -------------------------------------------------------------------

def _str(desc: str, enum: list[str] | None = None) -> dict:
    d = {"type": "string", "description": desc}
    if enum:
        d["enum"] = enum
    return d


def _int(desc: str) -> dict:
    return {"type": "integer", "description": desc}


def _list(desc: str) -> dict:
    return {"type": "array", "items": {"type": "string"}, "description": desc}


SOURCE_PARAMS = {
    "source": _str("Program text. Give either source or path."),
    "path": _str("Workspace-relative path of a program, e.g. tests/arith.ml."),
    "kind": _str("Program language. Default: from the path suffix, else minilang.",
                 ["minilang", "asm"]),
    "machine": _str("Hardware profile, e.g. t32-base, t32-tiny, t32-wide. "
                    "Default: the '// machine:' header, else t32-base."),
}


def _program_file(ctx: EpisodeContext, args: dict) -> tuple[str, list[str]]:
    """Return (cli file argument, extra cli args) for a source or path."""
    extra = ["--machine", args["machine"]] if args.get("machine") else []
    if args.get("path"):
        try:
            rel, path = ctx.ws.resolve(args["path"])
        except PathError as e:
            raise ToolDenied("P7", str(e)) from None
        if not path.is_file():
            raise ToolError(f"no such file: {rel}")
        if path.suffix not in (".ml", ".s"):
            raise ToolError("path must be a .ml or .s file")
        return str(path), extra
    if not args.get("source"):
        raise ToolError("give either source or path")
    kind = args.get("kind") or "minilang"
    return str(ctx.ws.scratch_file(args["source"], kind)), extra


def _sut(ctx: EpisodeContext, *cli_args: str):
    res = ctx.ws.sut(*cli_args)
    if isinstance(res, dict) and "error" in res:
        raise ToolError(res["error"])
    return res


# ---- read-only tools -----------------------------------------------------------

def list_files(ctx, args):
    want = args.get("layer")
    rows = []
    for rel in ctx.ws.files():
        layer = layer_of(rel)
        tag = "protected" if is_protected(rel) else (layer or "other")
        if want and tag != want:
            continue
        rows.append(f"{rel}  [{tag}]")
    return "\n".join(rows) or "(no files)"


def read_file(ctx, args):
    try:
        rel, path = ctx.ws.resolve(args["path"])
    except PathError as e:
        raise ToolDenied("P7", str(e)) from None
    if not path.is_file():
        raise ToolError(f"no such file: {rel}")
    lines = path.read_text().splitlines()
    start = max(1, int(args.get("start_line") or 1))
    end = min(len(lines), int(args.get("end_line") or start + 399))
    body = "\n".join(f"{i:4d}| {lines[i - 1]}" for i in range(start, end + 1))
    more = f"\n... ({len(lines) - end} more lines)" if end < len(lines) else ""
    return f"{rel} (lines {start}-{end} of {len(lines)})\n{body}{more}"


def search_code(ctx, args):
    try:
        pattern = re.compile(args["pattern"])
    except re.error as e:
        raise ToolError(f"bad regex: {e}") from None
    hits = []
    for rel in ctx.ws.files():
        if args.get("path") and not rel.startswith(args["path"]):
            continue
        try:
            text = (ctx.ws.dir / rel).read_text()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{rel}:{i}: {line.strip()}")
                if len(hits) >= 60:
                    return "\n".join(hits) + "\n... (more matches)"
    return "\n".join(hits) or "(no matches)"


def read_spec(ctx, args):
    text = (ctx.ws.dir / "spec.md").read_text()
    section = (args.get("section") or "").strip().rstrip(".")
    if not section:
        return text
    lines = text.splitlines()
    if "." in section:  # a numbered paragraph, e.g. 4.4
        start_re = re.compile(rf"^{re.escape(section)}\.\s")
        stop_re = re.compile(r"^(\d+\.\d+\.\s|## )")
    else:  # a whole section, e.g. 4
        start_re = re.compile(rf"^## {re.escape(section)}\.\s")
        stop_re = re.compile(r"^## ")
    for i, line in enumerate(lines):
        if start_re.match(line):
            j = i + 1
            while j < len(lines) and not stop_re.match(lines[j]):
                j += 1
            return "\n".join(lines[i:j]).strip()
    raise ToolError(f"no spec section {section!r}")


def run_tests(ctx, args):
    res = _sut(ctx, "test", *(["--filter", args["filter"]] if args.get("filter") else []))
    return format_test_report(res)


def format_test_report(results: list[dict]) -> str:
    failed = [t for t in results if not t["passed"]]
    lines = [f"{len(results) - len(failed)}/{len(results)} visible tests passed."]
    for t in failed:
        lines.append(f"\nFAIL {t['file']} (machine {t['machine']}, stage {t['stage']})")
        lines.append("  expected:\n" + _indent(t["expected"] or "(missing .expected file)"))
        lines.append("  actual:\n" + _indent(t["actual"]))
        if t.get("detail"):
            lines.append(f"  detail: {t['detail']}")
    return "\n".join(lines)


def _indent(text: str) -> str:
    return "\n".join("    " + l for l in (text or "").splitlines()) or "    (empty)"


def run_program(ctx, args):
    file, extra = _program_file(ctx, args)
    if args.get("max_steps"):
        extra += ["--max-steps", str(int(args["max_steps"]))]
    res = _sut(ctx, "run", file, *extra)
    return {k: v for k, v in res.items() if k != "asm"}


def compile_program(ctx, args):
    file, extra = _program_file(ctx, args | {"kind": "minilang"})
    if not file.endswith(".ml"):
        raise ToolError("compile_program needs a MiniLang program")
    res = _sut(ctx, "compile", file, *extra)
    return res["asm"] if res.get("ok") else f"compile error: {res.get('detail')}"


def validate_program(ctx, args):
    file, extra = _program_file(ctx, args)
    res = _sut(ctx, "validate", file, *extra)
    return "valid" if res["ok"] else "invalid:\n" + "\n".join(res["violations"])


def trace_execution(ctx, args):
    file, extra = _program_file(ctx, args)
    start = max(0, int(args.get("start_step") or 0))
    limit = min(200, max(1, int(args.get("limit") or 60)))
    res = _sut(ctx, "run", file, *extra, "--trace-start", str(start), "--trace-limit", str(limit))
    rows = []
    for e in res.get("trace", []):
        extra_txt = " | ".join(x for x in (e.get("regs"), e.get("mem")) if x)
        rows.append(f"{e['step']:6d} pc={e['pc']:<5d} {e['asm']:<28s} {extra_txt}")
    head = f"stage={res['stage']} actual={res['actual']!r} steps={res.get('steps')} {res.get('detail', '')}"
    return head + "\n" + ("\n".join(rows) if rows else "(no trace: the program did not run)")


def reference_eval(ctx, args):
    file, _ = _program_file(ctx, args | {"kind": "minilang"})
    if not file.endswith(".ml"):
        raise ToolError("reference_eval needs a MiniLang program")
    res = _sut(ctx, "reference", file)
    return res["result"] if res["ok"] else res["detail"]


def minimize_failure(ctx, args):
    file, extra = _program_file(ctx, args | {"kind": "minilang"})
    if not file.endswith(".ml"):
        raise ToolError("minimize_failure needs a MiniLang program")
    return _sut(ctx, "minimize", file, *extra)


def show_diff(ctx, args):
    return ctx.ws.diff(ctx.ws.baseline) or "(no changes since the episode started)"


# ---- write tools (Repair Agent) ------------------------------------------------

def check_edit_allowed(ctx: EpisodeContext, rel: str) -> None:
    if is_protected(rel):
        raise ToolDenied("P3", f"{rel} is protected and must not be modified")
    layer = layer_of(rel)
    if layer is None:
        raise ToolDenied("P2", f"{rel} is not part of any repair layer")
    if layer not in ctx.assigned_layers:
        raise ToolDenied("P2", f"{rel} is in layer '{layer}', but the assigned layer is "
                               f"{sorted(ctx.assigned_layers) or 'none'}")


def edit_file(ctx, args):
    try:
        rel, path = ctx.ws.resolve(args["path"])
    except PathError as e:
        raise ToolDenied("P7", str(e)) from None
    check_edit_allowed(ctx, rel)
    if not path.is_file():
        raise ToolDenied("P5", f"{rel} does not exist; agents may not create files")
    old, new = args["old_text"], args["new_text"]
    if not old:
        raise ToolError("old_text must not be empty")
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise ToolError(f"old_text occurs {count} times in {rel}; it must occur exactly once")
    path.write_text(text.replace(old, new))
    return f"edited {rel}"


def revert_file(ctx, args):
    try:
        rel, _ = ctx.ws.resolve(args["path"])
    except PathError as e:
        raise ToolDenied("P7", str(e)) from None
    check_edit_allowed(ctx, rel)
    ctx.ws.restore_file(rel, ctx.ws.checkpoint)
    return f"restored {rel} to its state at the start of this attempt"


def corpus_counts(ctx: EpisodeContext) -> dict:
    """Aggregate hidden-corpus results. Individual programs never leave this
    function (policy P7)."""
    out = {}
    for kind in ("valid", "invalid"):
        res = ctx.ws.sut("corpus", str(CORPUS_DIR / kind))
        if isinstance(res, dict):
            out[kind] = None
        else:
            out[kind] = (sum(t["passed"] for t in res), len(res))
    return out


def check_corpus(ctx, args):
    c = corpus_counts(ctx)
    if c["valid"] is None or c["invalid"] is None:
        return "the toolchain crashed while running the hidden corpus"
    (vp, vn), (ip, inn) = c["valid"], c["invalid"]
    return (f"hidden valid programs accepted and correct: {vp}/{vn}\n"
            f"hidden invalid programs rejected: {ip}/{inn}")


# ---- finish tools ----------------------------------------------------------------

def submit_diagnosis(ctx, args):
    if args.get("layer") not in LAYERS:
        raise ToolError(f"layer must be one of {sorted(LAYERS)}")
    for key in ("root_cause", "evidence"):
        if not str(args.get(key, "")).strip():
            raise ToolError(f"{key} must not be empty")
    return "diagnosis submitted"


def submit_patch(ctx, args):
    if not str(args.get("summary", "")).strip():
        raise ToolError("summary must not be empty")
    if not ctx.ws.changes(ctx.ws.checkpoint) and not args.get("disagree_with_diagnosis"):
        raise ToolError("you have not changed any file in this attempt; change a file, or "
                        "explain in disagree_with_diagnosis why the diagnosis is wrong")
    return "patch submitted for verification"


def submit_review(ctx, args):
    if args.get("decision") not in ("approve", "reject"):
        raise ToolError("decision must be 'approve' or 'reject'")
    if not str(args.get("rationale", "")).strip():
        raise ToolError("rationale must not be empty")
    return "review submitted"


# ---- registry ------------------------------------------------------------------

_LAYER_ENUM = sorted(LAYERS)

TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("list_files", "List workspace files with their repair layer, or [protected].",
         {"layer": _str("Only list files of this layer.", _LAYER_ENUM + ["protected"])},
         [], READERS, list_files),
    Tool("read_file", "Read a workspace file with line numbers (at most 400 lines per call).",
         {"path": _str("Workspace-relative path."), "start_line": _int("First line (1-based)."),
          "end_line": _int("Last line.")}, ["path"], READERS, read_file),
    Tool("search_code", "Search workspace files with a Python regular expression.",
         {"pattern": _str("Regular expression."), "path": _str("Only files under this prefix.")},
         ["pattern"], READERS, search_code),
    Tool("read_spec", "Read spec.md, or one section ('4') or numbered paragraph ('4.4').",
         {"section": _str("Section or paragraph number. Empty for the whole spec.")},
         [], READERS, read_spec),
    Tool("run_tests", "Run the visible tests in tests/. Shows expected and actual output of failures.",
         {"filter": _str("Only run tests whose name contains this text.")}, [], READERS, run_tests),
    Tool("run_program", "Compile (MiniLang), assemble, validate, and run a program. "
         "Returns the stage reached, the result text, and details.",
         SOURCE_PARAMS | {"max_steps": _int("Step limit. Default 200000.")}, [], READERS, run_program),
    Tool("compile_program", "Compile a MiniLang program and return the T32 assembly.",
         {k: SOURCE_PARAMS[k] for k in ("source", "path", "machine")}, [], READERS, compile_program),
    Tool("validate_program", "Assemble (and compile, for MiniLang) a program and list the "
         "hardware-profile violations.", SOURCE_PARAMS, [], READERS, validate_program),
    Tool("trace_execution", "Run a program and return a per-instruction trace "
         "(pc, instruction, changed registers and memory).",
         SOURCE_PARAMS | {"start_step": _int("First step to trace. Default 0."),
                          "limit": _int("Number of steps, at most 200. Default 60.")},
         [], READERS, trace_execution),
    Tool("reference_eval", "Run a MiniLang program on the reference interpreter (the oracle "
         "for MiniLang semantics). Returns the result text.",
         {k: SOURCE_PARAMS[k] for k in ("source", "path")}, [], READERS, reference_eval,
         needs_oracle=True),
    Tool("minimize_failure", "Shrink a MiniLang program whose compiled result differs from the "
         "reference interpreter. Returns the smallest failing program found.",
         {k: SOURCE_PARAMS[k] for k in ("source", "path", "machine")}, [],
         {"diagnoser", "solo"}, minimize_failure, needs_oracle=True),
    Tool("show_diff", "Show all changes made to the workspace since the episode started.",
         {}, [], {"repair", "reviewer", "solo"}, show_diff),
    Tool("edit_file", "Replace old_text with new_text in a file of the assigned layer. "
         "old_text must occur exactly once.",
         {"path": _str("Workspace-relative path."), "old_text": _str("Exact text to replace."),
          "new_text": _str("Replacement text.")}, ["path", "old_text", "new_text"],
         EDITORS, edit_file),
    Tool("revert_file", "Undo your changes to one file in this attempt.",
         {"path": _str("Workspace-relative path.")}, ["path"], EDITORS, revert_file),
    Tool("check_corpus", "Run the hidden corpus. Returns only counts: valid programs that are "
         "accepted and correct, and invalid programs that are rejected.",
         {}, [], EDITORS, check_corpus, needs_corpus_feedback=True),
    Tool("submit_diagnosis", "Finish: report the faulty layer and the evidence.",
         {"layer": _str("The layer that contains the root cause.", _LAYER_ENUM),
          "files": _list("Files that contain the root cause."),
          "root_cause": _str("What is wrong, precisely."),
          "evidence": _str("Observations that prove it: test output, traces, reference output."),
          "spec_sections": _list("Spec paragraphs that define the correct behavior, e.g. 3.1."),
          "fix_hint": _str("What a correct fix changes, without adding restrictions.")},
         ["layer", "root_cause", "evidence"], {"diagnoser"}, submit_diagnosis, finish=True),
    Tool("submit_patch", "Finish: submit your changes for verification.",
         {"summary": _str("What you changed and why."),
          "spec_sections": _list("Spec paragraphs that justify the change."),
          "disagree_with_diagnosis": _str("Fill only if you think the diagnosed layer is wrong.")},
         ["summary"], EDITORS, submit_patch, finish=True),
    Tool("submit_review", "Finish: approve or reject the patch.",
         {"decision": _str("approve or reject", ["approve", "reject"]),
          "rationale": _str("Reasons, with spec citations."),
          "spec_sections": _list("Spec paragraphs checked."),
          "concerns": _list("Concrete problems, if any.")},
         ["decision", "rationale"], {"reviewer"}, submit_review, finish=True),
]}


def tools_for(role: str, ctx: EpisodeContext) -> list[Tool]:
    out = []
    for t in TOOLS.values():
        if role not in t.roles:
            continue
        if t.needs_oracle and not ctx.flags.oracle:
            continue
        if t.needs_corpus_feedback and not ctx.flags.corpus_feedback:
            continue
        out.append(t)
    return out


def call_tool(ctx: EpisodeContext, role: str, agent: str, name: str, args: dict) -> ToolResult:
    """Run one tool call with all policy checks, and log it."""
    allowed = {t.name for t in tools_for(role, ctx)}
    ctx.tool_calls_total += 1
    ctx.agent_tool_calls += 1
    try:
        if name not in TOOLS:
            raise ToolError(f"unknown tool {name!r}")
        if name not in allowed:
            raise ToolDenied("P1", f"role {role} may not use {name}")
        if ctx.agent_tool_calls > ctx.agent_tool_budget and not TOOLS[name].finish:
            raise ToolDenied("P9", "tool-call budget exhausted; call your submit tool now")
        value = TOOLS[name].fn(ctx, args)
        text = value if isinstance(value, str) else json.dumps(value, indent=1)
        result = ToolResult(True, text, data=args if TOOLS[name].finish else None)
    except ToolDenied as e:
        result = ToolResult(False, f"DENIED by policy {e.policy}: {e}", denied=True)
        ctx.denials.append({"agent": agent, "tool": name, "policy": e.policy, "reason": str(e)})
    except (ToolError, KeyError, TypeError, ValueError) as e:
        msg = f"missing argument {e}" if isinstance(e, KeyError) else str(e)
        result = ToolResult(False, f"ERROR: {msg}")
    if len(result.text) > MAX_RESULT_CHARS:
        result.text = result.text[:MAX_RESULT_CHARS] + "\n... (output truncated)"
    left = ctx.agent_tool_budget - ctx.agent_tool_calls
    if 0 <= left <= 5:
        result.text += f"\n[note: {left} tool calls left in your budget]"
    ctx.log.emit("tool_call", agent=agent, tool=name, args=args, ok=result.ok,
                 denied=result.denied, result=result.text[:2000])
    return result


__all__ = ["TOOLS", "Tool", "ToolResult", "call_tool", "tools_for", "corpus_counts",
           "format_test_report", "check_edit_allowed", "PROTECTED"]
