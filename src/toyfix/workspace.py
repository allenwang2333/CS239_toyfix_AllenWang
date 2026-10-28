"""Episode workspace: a private copy of the toolchain that agents repair."""

import difflib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

SKIP_DIRS = {"__pycache__", ".scratch"}
SUT_TIMEOUT = 120


class PathError(Exception):
    pass


def _files(root: Path) -> dict[str, Path]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not SKIP_DIRS & set(p.relative_to(root).parts):
            out[p.relative_to(root).as_posix()] = p
    return out


class Workspace:
    def __init__(self, episode_dir: Path):
        self.root = episode_dir
        self.dir = episode_dir / "workspace"
        self.baseline = episode_dir / "baseline"      # state after fault injection
        self.checkpoint = episode_dir / "checkpoint"  # state at the start of an attempt

    # ---- paths --------------------------------------------------------------

    def resolve(self, rel: str) -> tuple[str, Path]:
        """Return (normalized relative path, absolute path). Paths must stay
        inside the workspace (policy P7)."""
        if not rel or os.path.isabs(rel):
            raise PathError(f"path must be relative to the workspace: {rel!r}")
        path = (self.dir / rel).resolve()
        base = self.dir.resolve()
        if path != base and base not in path.parents:
            raise PathError(f"path is outside the workspace: {rel!r}")
        rel_norm = path.relative_to(base).as_posix()
        if SKIP_DIRS & set(Path(rel_norm).parts):
            raise PathError(f"path is not available: {rel!r}")
        return rel_norm, path

    def files(self) -> list[str]:
        return list(_files(self.dir))

    # ---- snapshots ----------------------------------------------------------

    def snapshot(self, dest: Path) -> None:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(self.dir, dest, ignore=shutil.ignore_patterns(*SKIP_DIRS))

    def restore(self, src: Path) -> None:
        scratch = self.dir / ".scratch"
        shutil.rmtree(self.dir)
        shutil.copytree(src, self.dir)
        scratch.mkdir(exist_ok=True)

    def restore_file(self, rel: str, src_root: Path) -> bool:
        """Restore one file from a snapshot. Return False if it is not there."""
        src = src_root / rel
        dest = self.dir / rel
        if src.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return True
        if dest.exists():
            dest.unlink()
        return False

    def changes(self, against: Path) -> dict[str, str]:
        """Changed files relative to a snapshot: rel -> modified/added/deleted."""
        old, new = _files(against), _files(self.dir)
        out = {}
        for rel in sorted(set(old) | set(new)):
            if rel not in new:
                out[rel] = "deleted"
            elif rel not in old:
                out[rel] = "added"
            elif old[rel].read_bytes() != new[rel].read_bytes():
                out[rel] = "modified"
        return out

    def diff(self, against: Path, max_chars: int = 20000) -> str:
        parts = []
        for rel, status in self.changes(against).items():
            a = (against / rel).read_text().splitlines(keepends=True) if status != "added" else []
            b = (self.dir / rel).read_text().splitlines(keepends=True) if status != "deleted" else []
            parts.append("".join(difflib.unified_diff(a, b, f"a/{rel}", f"b/{rel}")))
        text = "".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (diff truncated)\n"
        return text

    def added_lines(self, against: Path) -> dict[str, list[str]]:
        out = {}
        for rel, status in self.changes(against).items():
            if status == "deleted":
                continue
            a = (against / rel).read_text().splitlines() if status != "added" else []
            b = (self.dir / rel).read_text().splitlines()
            out[rel] = [l[1:] for l in difflib.unified_diff(a, b, lineterm="", n=0)
                        if l.startswith("+") and not l.startswith("+++")]
        return out

    # ---- running the toolchain ----------------------------------------------

    def scratch_file(self, text: str, kind: str) -> Path:
        """Write an ad-hoc program for the toolchain CLI."""
        d = self.dir / ".scratch"
        d.mkdir(exist_ok=True)
        path = d / f"{uuid.uuid4().hex[:8]}.{'ml' if kind == 'minilang' else 's'}"
        path.write_text(text)
        return path

    def sut(self, *args: str, timeout: int = SUT_TIMEOUT):
        """Run the workspace's own cli.py in a subprocess and parse its JSON.
        The workspace code may be broken by a patch, so errors are returned,
        not raised."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        try:
            proc = subprocess.run([sys.executable, "-B", "cli.py", *args], cwd=self.dir,
                                  capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return {"error": f"the toolchain did not finish within {timeout} s"}
        if proc.returncode != 0:
            return {"error": "the toolchain crashed:\n" + proc.stderr[-3000:]}
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"error": "the toolchain printed invalid JSON:\n" + proc.stdout[-2000:]}
