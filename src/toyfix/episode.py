"""Run one episode: inject a fault, run the agents, score the result."""

import json
import time
from dataclasses import asdict
from pathlib import Path

from .agents.coordinator import Coordinator, Outcome
from .context import EpisodeContext, EventLog, Flags
from .faults import CATALOG, Fault, make_workspace
from .layers import layer_of
from .llm import ChatClient
from .workspace import Workspace


def run_episode(fault_id: str, out_root: Path, clients: dict[str, ChatClient],
                mode: str = "multi", flags: Flags | None = None, max_attempts: int = 4,
                echo: bool = True, tag: str = "") -> dict:
    fault = CATALOG[fault_id]
    flags = flags or Flags()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ep_dir = out_root / f"{stamp}-{fault_id}-{mode}{'-' + tag if tag else ''}"
    n = 1
    while ep_dir.exists():
        n += 1
        ep_dir = out_root / f"{stamp}-{fault_id}-{mode}{'-' + tag if tag else ''}-{n}"
    ep_dir.mkdir(parents=True)
    ws = Workspace(ep_dir)

    # Fault Injector (scripted). Its metadata goes only to the scoreboard (P7).
    make_workspace(ws.dir, fault)
    (ws.dir / ".scratch").mkdir(exist_ok=True)
    ws.snapshot(ws.baseline)
    (ep_dir / "scoreboard").mkdir()
    (ep_dir / "scoreboard" / "fault.json").write_text(json.dumps(
        {"id": fault.id, "layers": fault.layers, "title": fault.title,
         "tempting_fix": fault.tempting_fix}, indent=1))

    log = EventLog(ep_dir / "events.jsonl", echo=echo)
    model = (clients.get("default") or next(iter(clients.values()))).model
    log.emit("episode_start", agent="Coordinator", mode=mode, model=model,
             flags=asdict(flags), max_attempts=max_attempts)
    ctx = EpisodeContext(ws=ws, log=log, flags=flags)
    started = time.time()
    outcome = Coordinator(ctx, clients, max_attempts=max_attempts, mode=mode).run()
    result = score(fault, outcome, ctx, mode, model, flags, time.time() - started)
    result["episode_dir"] = str(ep_dir)
    log.emit("outcome", agent="Coordinator", status=outcome.status, reason=outcome.reason)
    (ep_dir / "scoreboard" / "result.json").write_text(json.dumps(result, indent=1))
    (ep_dir / "trajectory.md").write_text(render_trajectory(log.events, result))
    return result


def score(fault: Fault, outcome: Outcome, ctx: EpisodeContext, mode: str, model: str,
          flags: Flags, seconds: float) -> dict:
    rep = outcome.final_report
    diag_layers = [d.get("layer") for d in outcome.diagnoses]
    changed = rep.changed_files if rep else {}
    changed_layers = sorted({layer_of(r) or "other" for r in changed})
    tokens = {"prompt_tokens": 0, "completion_tokens": 0}
    for e in ctx.log.events:
        if e["kind"] == "agent_end":
            for k in tokens:
                tokens[k] += e["usage"].get(k, 0)
    return {
        "fault": fault.id,
        "injected_layers": list(fault.layers),
        "mode": mode,
        "model": model,
        "flags": asdict(flags),
        "status": outcome.status,
        "reason": outcome.reason,
        "attempts": outcome.attempts,
        "diagnosed_layers": diag_layers,
        # Solo mode records the changed layers, comma-joined, as its diagnosis.
        "first_diagnosis_correct": bool(diag_layers) and bool(diag_layers[0])
                                   and set(diag_layers[0].split(",")) <= set(fault.layers),
        "changed_files": changed,
        "changed_layers": changed_layers,
        "fixed_in_injected_layers": outcome.status == "FIXED"
                                    and set(changed_layers) <= set(fault.layers),
        "final_valid_corpus": rep.valid if rep else None,
        "final_invalid_corpus": rep.invalid if rep else None,
        "restricting_attempts": outcome.restricting_attempts,
        "loosening_attempts": outcome.loosening_attempts,
        "review": outcome.review,
        "tool_calls": ctx.tool_calls_total,
        "policy_denials": ctx.denials,
        "tokens": tokens,
        "seconds": round(seconds, 1),
    }


def _short(text, n: int) -> str:
    text = text if isinstance(text, str) else json.dumps(text)
    text = text.strip()
    return text if len(text) <= n else text[:n] + " ..."


def render_trajectory(events: list[dict], result: dict) -> str:
    """Markdown trajectory of an episode, built from the event log."""
    out = [f"# Episode trajectory: fault {result['fault']} ({result['mode']} mode)\n",
           f"- Model: `{result['model']}`",
           f"- Outcome: **{result['status']}** after {result['attempts']} attempt(s): {result['reason']}",
           f"- Injected layer(s) (scoreboard only, hidden from agents): {result['injected_layers']}",
           f"- Diagnosed layers: {result['diagnosed_layers']}",
           f"- Tool calls: {result['tool_calls']}, policy denials: {len(result['policy_denials'])}",
           f"- Tokens: {result['tokens']}\n"]
    step = 0
    for e in events:
        k = e["kind"]
        if k == "attempt_start":
            out.append(f"\n## Attempt {e['attempt']}\n")
        elif k == "test_report":
            step += 1
            out.append(f"{step}. **Test Runner**: {e.get('passed')}/{e.get('total')} visible tests "
                       f"pass. Failing: {', '.join(e.get('failing') or []) or 'none'}.")
        elif k == "agent_start":
            step += 1
            out.append(f"{step}. **{e['agent']}** starts (tools: {', '.join(e['tools'])}).")
        elif k == "tool_call":
            mark = " **DENIED**" if e["denied"] else ""
            args = {a: v for a, v in e["args"].items()}
            out.append(f"    - `{e['tool']}({_short(json.dumps(args), 160)})`{mark} -> "
                       f"{_short(e['result'], 220).replace(chr(10), ' / ')}")
        elif k == "llm_turn" and e.get("content"):
            out.append(f"    - says: {_short(e['content'], 300).replace(chr(10), ' ')}")
        elif k == "agent_end":
            out.append(f"    - **{e['agent']}** ends ({e['stop']}, {e['tool_calls']} tool calls).")
            if e.get("result"):
                out.append("```json\n" + json.dumps(e["result"], indent=1)[:3000] + "\n```")
        elif k == "assign_layer":
            step += 1
            out.append(f"{step}. **Coordinator** assigns layer `{e['layer']}` to the Repair Agent.")
        elif k == "verifier_report":
            step += 1
            checks = "; ".join(f"{c['name']}={'ok' if c['passed'] else 'FAIL'} ({c['detail'][:120]})"
                               for c in e["checks"])
            out.append(f"{step}. **Verifier**: {'PASS' if e['passed'] else 'FAIL'}: {checks}")
        elif k == "decision":
            step += 1
            out.append(f"{step}. **Verifier** decision: fixed={e['fixed']} ({e['reason']}).")
        elif k == "revert":
            step += 1
            out.append(f"{step}. **Coordinator** reverts the {e['scope']}: {e['reason']}.")
        elif k == "outcome":
            out.append(f"\n**Outcome: {e['status']}** ({e['reason']})")
    return "\n".join(out) + "\n"
