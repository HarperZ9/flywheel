#!/usr/bin/env python3
"""Build one-file executables for local harness entrypoints."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "artifacts" / "exe"
WORK = ROOT / "artifacts" / ".pyinstaller"


def _build(name: str, entry: str, *, python: str, hidden: list[str] | None = None) -> None:
    cmd = [
        python,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK / name),
        "--name",
        name,
        entry,
    ]
    for h in hidden or []:
        cmd.extend(["--hidden-import", h])
    print(f"[build] {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"pyinstaller failed for {name} ({proc.returncode})")


def _py_path(raw: str | None) -> str:
    if not raw:
        return sys.executable
    explicit = str(Path(raw).expanduser().resolve())
    if not Path(explicit).exists():
        raise FileNotFoundError(f"python executable not found: {explicit}")
    return explicit


def _has_modules(python: str) -> bool:
    probe = (
        "import torch,transformers,peft,bitsandbytes; "
        "import importlib.util; "
        "print('ok')"
    )
    proc = subprocess.run([python, "-c", probe], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[warn] torch stack unavailable via {python}:")
        print(proc.stderr.strip())
        return False
    return True


def _has_pyinstaller(python: str) -> bool:
    probe = "import PyInstaller"
    proc = subprocess.run([python, "-c", probe], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[warn] PyInstaller unavailable via {python}:")
        print(proc.stderr.strip())
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-serve", action="store_true",
                    help="build only the local-agent executable")
    ap.add_argument("--serve-python", default="E:/local-model-run/venv/Scripts/python.exe",
                    help="python interpreter used for the torch-backed serve executable")
    args = ap.parse_args()

    DIST.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    serve_python = _py_path(args.serve_python)

    _build("local-agent", str(ROOT / "scripts" / "local_agent_entry.py"), python=sys.executable)
    if not args.skip_serve:
        if not _has_pyinstaller(serve_python):
            print("[warn] serve skipped: PyInstaller unavailable for serve-python interpreter")
        elif not _has_modules(serve_python):
            print("[warn] serve skipped: required serve stack not available in that interpreter")
        else:
            _build("local-serve", str(ROOT / "scripts" / "local_serve_entry.py"),
                   python=serve_python, hidden=[
                       "transformers",
                       "bitsandbytes",
                       "torch",
                       "peft",
                   ])

    print(f"[ok] executables in {DIST}")
    if not args.skip_serve:
        print("[note] local-serve bundle is intentionally heavy because it includes torch/transformers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
