"""Shared episode state and the event log."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .workspace import Workspace


@dataclass
class Flags:
    oracle: bool = True            # reference_eval and minimize_failure available
    corpus_feedback: bool = True   # check_corpus available to the Repair Agent


class EventLog:
    """Append-only JSONL log of everything that happens in an episode."""

    def __init__(self, path: Path | None = None, echo: bool = False):
        self.path = path
        self.echo = echo
        self.events: list[dict] = []
        self.start = time.time()

    def emit(self, kind: str, **data) -> dict:
        event = {"t": round(time.time() - self.start, 2), "kind": kind, **data}
        self.events.append(event)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(event) + "\n")
        if self.echo:
            _echo(event)
        return event


def _short(value, n: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "..."


def _echo(e: dict) -> None:
    k = e["kind"]
    if k == "tool_call":
        mark = "DENIED " if e.get("denied") else ""
        print(f"  [{e['agent']}] {mark}{e['tool']}({_short(e['args'], 100)}) -> {_short(e['result'], 120)}")
    elif k == "llm_turn" and e.get("content"):
        print(f"  [{e['agent']}] says: {_short(e['content'])}")
    elif k in ("agent_start", "agent_end"):
        print(f"[{e['agent']}] {k.replace('_', ' ')} {_short(e.get('summary', ''), 200)}")
    elif k not in ("llm_turn",):
        print(f"* {k}: {_short({x: y for x, y in e.items() if x not in ('t', 'kind')}, 220)}")


@dataclass
class EpisodeContext:
    ws: Workspace
    log: EventLog
    flags: Flags = field(default_factory=Flags)
    # Layers the Repair Agent may edit in the current attempt (policy P2).
    assigned_layers: set[str] = field(default_factory=set)
    # All layers assigned during the episode; the Verifier checks scope with it.
    all_assigned: set[str] = field(default_factory=set)
    attempt: int = 0
    tool_calls_total: int = 0
    agent_tool_calls: int = 0
    agent_tool_budget: int = 30
    denials: list[dict] = field(default_factory=list)
