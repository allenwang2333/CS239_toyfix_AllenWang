"""ToyFix command line.

  python3 -m toyfix list-faults
  python3 -m toyfix check
  python3 -m toyfix episode FAULT [--mode multi|solo] [--no-oracle] [--no-corpus-feedback]
  python3 -m toyfix bench [--faults all|S1,C1,...] [--modes multi,solo] [--jobs N]
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .context import Flags
from .episode import run_episode
from .faults import CATALOG
from .llm import DeepSeekClient, load_dotenv

DEFAULT_OUT = Path(__file__).resolve().parent.parent.parent / "runs"


def cmd_list_faults(_args) -> None:
    for f in CATALOG.values():
        print(f"{f.id:3s} {'+'.join(f.layers):22s} {f.title}")


def cmd_check(_args) -> None:
    """Offline self-check: clean toolchain passes everything; every fault
    breaks at least one visible test."""
    import tempfile
    from .context import EpisodeContext, EventLog
    from .agents.verifier import verify
    from .faults import make_workspace
    from .workspace import Workspace

    ok = True
    with tempfile.TemporaryDirectory() as d:
        for fid in [None, *CATALOG]:
            ws = Workspace(Path(d) / (fid or "clean"))
            make_workspace(ws.dir, CATALOG[fid] if fid else None)
            ws.snapshot(ws.baseline)
            rep = verify(EpisodeContext(ws=ws, log=EventLog()))
            fails = rep.failing_tests
            good = rep.passed if fid is None else bool(fails)
            ok &= good
            print(f"{fid or 'clean':5s} {'ok ' if good else 'BAD'} visible {rep.visible[0]}/{rep.visible[1]} "
                  f"valid {rep.valid} invalid {rep.invalid} failing={fails}")
    sys.exit(0 if ok else 1)


def _flags(args) -> Flags:
    return Flags(oracle=not args.no_oracle, corpus_feedback=not args.no_corpus_feedback)


def _clients(args) -> dict:
    load_dotenv(Path(__file__).resolve().parent)
    return {"default": DeepSeekClient(model=args.model, base_url=getattr(args, "base_url", None))}


def cmd_episode(args) -> None:
    result = run_episode(args.fault, Path(args.out), _clients(args), mode=args.mode,
                         flags=_flags(args), max_attempts=args.attempts, echo=not args.quiet,
                         tag=args.tag)
    print(json.dumps({k: result[k] for k in (
        "fault", "status", "attempts", "diagnosed_layers", "changed_layers",
        "final_valid_corpus", "final_invalid_corpus", "restricting_attempts",
        "tool_calls", "tokens", "seconds", "episode_dir")}, indent=1))


def cmd_bench(args) -> None:
    faults = list(CATALOG) if args.faults == "all" else args.faults.split(",")
    modes = args.modes.split(",")
    clients = _clients(args)
    out = Path(args.out) / f"bench-{time.strftime('%Y%m%d-%H%M%S')}{'-' + args.tag if args.tag else ''}"
    out.mkdir(parents=True)
    jobs = [(f, m) for m in modes for f in faults]

    def one(job):
        f, m = job
        try:
            r = run_episode(f, out, clients, mode=m, flags=_flags(args),
                            max_attempts=args.attempts, echo=False, tag=args.tag)
        except Exception as e:  # Keep the benchmark going; record the error.
            r = {"fault": f, "mode": m, "status": "ERROR", "reason": repr(e)}
        print(f"{r['fault']:3s} {m:5s} {r['status']:10s} attempts={r.get('attempts')} "
              f"diag={r.get('diagnosed_layers')} changed={r.get('changed_layers')} "
              f"valid={r.get('final_valid_corpus')} restrict={r.get('restricting_attempts')}",
              flush=True)
        return r

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(one, jobs))
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "summary.md").write_text(summarize(results))
    print(summarize(results))


def summarize(results: list[dict]) -> str:
    lines = ["| mode | episodes | fixed | first diagnosis correct | fixed in injected layer "
             "| restricting attempts | loosening attempts | mean tool calls | tokens (in/out) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for mode in sorted({r["mode"] for r in results}):
        rs = [r for r in results if r["mode"] == mode and r["status"] != "ERROR"]
        if not rs:
            continue
        n = len(rs)
        fixed = sum(r["status"] == "FIXED" for r in rs)
        diag = sum(bool(r.get("first_diagnosis_correct")) for r in rs)
        inlayer = sum(bool(r.get("fixed_in_injected_layers")) for r in rs)
        restrict = sum(r.get("restricting_attempts", 0) for r in rs)
        loosen = sum(r.get("loosening_attempts", 0) for r in rs)
        calls = sum(r.get("tool_calls", 0) for r in rs) / n
        tin = sum(r["tokens"]["prompt_tokens"] for r in rs)
        tout = sum(r["tokens"]["completion_tokens"] for r in rs)
        lines.append(f"| {mode} | {n} | {fixed} | {diag} | {inlayer} | {restrict} | {loosen} "
                     f"| {calls:.1f} | {tin}/{tout} |")
    lines += ["", "| fault | mode | status | attempts | diagnosed | changed | valid | invalid |",
              "|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['fault']} | {r['mode']} | {r['status']} | {r.get('attempts')} "
                     f"| {r.get('diagnosed_layers')} | {r.get('changed_layers')} "
                     f"| {r.get('final_valid_corpus')} | {r.get('final_invalid_corpus')} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(prog="toyfix")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-faults").set_defaults(fn=cmd_list_faults)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    for name, fn in (("episode", cmd_episode), ("bench", cmd_bench)):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        if name == "episode":
            p.add_argument("fault", choices=sorted(CATALOG))
            p.add_argument("--mode", choices=["multi", "solo"], default="multi")
            p.add_argument("--quiet", action="store_true")
        else:
            p.add_argument("--faults", default="all")
            p.add_argument("--modes", default="multi")
            p.add_argument("--jobs", type=int, default=4)
        p.add_argument("--model", default=None, help="default: $TOYFIX_MODEL or deepseek-flash")
        p.add_argument("--base-url", default=None, help="default: $TOYFIX_BASE_URL")
        p.add_argument("--attempts", type=int, default=4)
        p.add_argument("--no-oracle", action="store_true")
        p.add_argument("--no-corpus-feedback", action="store_true")
        p.add_argument("--out", default=str(DEFAULT_OUT))
        p.add_argument("--tag", default="")
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
