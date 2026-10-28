"""Command-line harness for the T32 toolchain. Every command prints JSON.

Usage:
  python3 cli.py test [--filter TEXT]
  python3 cli.py corpus DIR
  python3 cli.py run FILE [--machine M] [--max-steps N] [--trace-start S] [--trace-limit N]
  python3 cli.py compile FILE [--machine M]
  python3 cli.py validate FILE [--machine M]
  python3 cli.py reference FILE
  python3 cli.py minimize FILE [--machine M]
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from minilang.compiler import CompileError, compile_source  # noqa: E402
from minilang.parser import ParseError  # noqa: E402
from minilang.reference import evaluate  # noqa: E402
from t32.assembler import AsmError, assemble  # noqa: E402
from t32.machine import load_machine  # noqa: E402
from t32.simulator import run  # noqa: E402
from t32.validator import validate  # noqa: E402

TEST_STEP_LIMIT = 200000
DEFAULT_MACHINE = "t32-base"


def header_machine(source: str) -> str | None:
    first = source.lstrip().splitlines()[0] if source.strip() else ""
    m = re.match(r"^(//|;)\s*machine:\s*([\w-]+)", first)
    return m.group(2) if m else None


def result_text(output: list[int], trap: str | None) -> str:
    lines = [str(v) for v in output]
    if trap:
        lines.append(f"<trap: {trap}>")
    return "\n".join(lines)


def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def execute(source: str, kind: str, machine_name: str, max_steps: int = TEST_STEP_LIMIT,
            trace_start: int = 0, trace_limit: int = 0) -> dict:
    """Compile (MiniLang only), assemble, validate, and run (spec §10.3)."""
    machine = load_machine(machine_name)
    res = {"machine": machine_name}
    asm = source
    if kind == "ml":
        try:
            asm = compile_source(source, machine)
        except CompileError as e:
            return res | {"stage": "compile", "actual": "<compile error>", "detail": str(e)}
        res["asm"] = asm
    try:
        program = assemble(asm)
    except AsmError as e:
        return res | {"stage": "assemble", "actual": "<rejected>", "detail": str(e)}
    errors = validate(program, machine)
    if errors:
        return res | {"stage": "validate", "actual": "<rejected>", "detail": "; ".join(errors[:10])}
    r = run(program, max_steps=max_steps, trace_start=trace_start, trace_limit=trace_limit)
    res |= {"stage": "run", "actual": result_text(r.output, r.trap), "steps": r.steps,
            "detail": f"trap: {r.trap}" if r.trap else ""}
    if trace_limit:
        res["trace"] = r.trace
    return res


def kind_of(path: Path) -> str:
    return "ml" if path.suffix == ".ml" else "asm"


def run_suite(directory: Path, name_filter: str | None = None) -> list[dict]:
    results = []
    for src in sorted(directory.iterdir()):
        if src.suffix not in (".ml", ".s"):
            continue
        if name_filter and name_filter not in src.stem:
            continue
        source = src.read_text()
        machine = header_machine(source) or DEFAULT_MACHINE
        exp_path = src.with_suffix(".expected")
        expected = exp_path.read_text() if exp_path.exists() else None
        try:
            res = execute(source, kind_of(src), machine)
        except Exception as e:  # A crash in the toolchain is a test failure.
            res = {"stage": "crash", "actual": "<crash>", "detail": f"{type(e).__name__}: {e}"}
        res.pop("asm", None)
        passed = expected is not None and normalize(res["actual"]) == normalize(expected)
        results.append({"name": src.stem, "file": src.name, "machine": machine,
                        "passed": passed, "expected": expected and normalize(expected),
                        "actual": res["actual"], "stage": res["stage"],
                        "detail": res.get("detail", "")})
    return results


def reference_text(source: str) -> dict:
    try:
        output, trap = evaluate(source)
    except ParseError as e:
        return {"ok": False, "detail": f"syntax error: {e}"}
    return {"ok": True, "result": result_text(output, trap)}


def minimize(source: str, machine: str) -> dict:
    """Remove lines while the compiled result still differs from the reference."""

    def failing(text: str) -> bool:
        ref = reference_text(text)
        if not ref["ok"]:
            return False
        try:
            actual = execute(text, "ml", machine)["actual"]
        except Exception:
            return True
        return normalize(actual) != normalize(ref["result"])

    if not failing(source):
        return {"ok": False, "detail": "the program does not fail: compiled result equals the reference"}
    lines = source.splitlines()
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(lines):
            candidate = lines[:i] + lines[i + 1:]
            if lines[i].strip() and failing("\n".join(candidate)):
                lines = candidate
                changed = True
            else:
                i += 1
    text = "\n".join(lines) + "\n"
    ref = reference_text(text)
    res = execute(text, "ml", machine)
    return {"ok": True, "source": text, "reference": ref["result"], "actual": res["actual"],
            "stage": res["stage"], "detail": res.get("detail", "")}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test")
    t.add_argument("--filter")
    c = sub.add_parser("corpus")
    c.add_argument("dir")
    for name in ("run", "compile", "validate", "reference", "minimize"):
        p = sub.add_parser(name)
        p.add_argument("file")
        p.add_argument("--machine")
        p.add_argument("--max-steps", type=int, default=TEST_STEP_LIMIT)
        p.add_argument("--trace-start", type=int, default=0)
        p.add_argument("--trace-limit", type=int, default=0)
    args = ap.parse_args()

    if args.cmd == "test":
        out = run_suite(ROOT / "tests", args.filter)
    elif args.cmd == "corpus":
        out = run_suite(Path(args.dir))
    else:
        path = Path(args.file)
        source = path.read_text()
        machine = args.machine or header_machine(source) or DEFAULT_MACHINE
        kind = kind_of(path)
        if args.cmd == "run":
            out = execute(source, kind, machine, args.max_steps, args.trace_start, args.trace_limit)
        elif args.cmd == "compile":
            try:
                out = {"ok": True, "asm": compile_source(source, load_machine(machine))}
            except CompileError as e:
                out = {"ok": False, "detail": str(e)}
        elif args.cmd == "validate":
            try:
                asm = compile_source(source, load_machine(machine)) if kind == "ml" else source
                errors = validate(assemble(asm), load_machine(machine))
                out = {"ok": not errors, "violations": errors}
            except (AsmError, CompileError) as e:
                out = {"ok": False, "violations": [str(e)]}
        elif args.cmd == "reference":
            out = reference_text(source)
        else:
            out = minimize(source, machine)
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
