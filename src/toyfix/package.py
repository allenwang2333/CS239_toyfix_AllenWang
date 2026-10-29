"""Build the two submission archives.

Run from src/:  python3 -m toyfix.package --name NAME --uid UID [--out ../dist]

  {name}-toyfix-{uid}-requirements.tar.gz   toyfix/ (app.md, policy.md, tools.md, agents/, episodes/)
  {name}-toyfix-{uid}-whole.tar.gz          src/, tests/, toyfix/

Secrets (.env), run outputs, and caches are never included. The build stops if
any packaged file contains the value of an API key from the environment.
"""

import argparse
import os
import tarfile
from pathlib import Path

from .llm import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
APP = "toyfix"
SKIP_PARTS = {"__pycache__", ".scratch", ".DS_Store", ".env", "runs", "dist"}


def _files(base: Path) -> list[Path]:
    return sorted(p for p in base.rglob("*")
                  if p.is_file() and not SKIP_PARTS & set(p.relative_to(ROOT).parts))


def _secrets() -> list[str]:
    load_dotenv(ROOT)
    return [v for k, v in os.environ.items()
            if k.endswith("API_KEY") and len(v) >= 16]


def _add(tar: tarfile.TarFile, files: list[Path], base: Path, prefix: str,
         secrets: list[str]) -> int:
    for f in files:
        data = f.read_bytes()
        for s in secrets:
            if s.encode() in data:
                raise SystemExit(f"refusing to package {f}: it contains an API key")
        tar.add(f, arcname=f"{prefix}/{f.relative_to(base).as_posix()}")
    return len(files)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--uid", required=True)
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    secrets = _secrets()
    req = ROOT / APP

    path1 = out / f"{args.name}-{APP}-{args.uid}-requirements.tar.gz"
    with tarfile.open(path1, "w:gz") as tar:
        n1 = _add(tar, _files(req), req, APP, secrets)

    path2 = out / f"{args.name}-{APP}-{args.uid}-whole.tar.gz"
    with tarfile.open(path2, "w:gz") as tar:
        n2 = _add(tar, _files(ROOT / "src"), ROOT / "src", "src", secrets)
        n2 += _add(tar, _files(ROOT / "tests"), ROOT / "tests", "tests", secrets)
        n2 += _add(tar, _files(req), req, APP, secrets)
        if (ROOT / "traces").is_dir():
            n2 += _add(tar, _files(ROOT / "traces"), ROOT / "traces", "traces", secrets)
        for doc in ("README.md", "requirements.md", "policies.md"):
            p = ROOT / doc
            if p.is_file():
                tar.add(p, arcname=doc)
                n2 += 1
    print(f"{path1} ({n1} files)\n{path2} ({n2} files)")


if __name__ == "__main__":
    main()
