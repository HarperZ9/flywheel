"""Entry-point wrapper for a one-file local serve executable."""
from __future__ import annotations

import sys
from pathlib import Path
from os import environ
import subprocess


def main() -> int:
    helper_python = environ.get("LOCAL_SERVE_PYTHON", "").strip()
    if helper_python:
        helper = Path(helper_python).expanduser().resolve()
        if helper.exists():
            repo_root = environ.get("LOCAL_SERVE_REPO", "").strip()
            if repo_root:
                repo_root = Path(repo_root)
            else:
                exe_root = Path(sys.executable).resolve()
                repo_root = exe_root.parent.parent
            serve_script = repo_root / "harness" / "serve.py"
            if serve_script.exists():
                cmd = [str(helper), str(serve_script), *sys.argv[1:]]
                result = subprocess.run(cmd)
                return int(result.returncode)

    try:
        from harness.serve import main as serve_main
    except ModuleNotFoundError as e:
        print("[error] local-serve executable requires torch/transformers in the runtime Python env")
        print(f"        missing dependency: {e}")
        return 1
    return serve_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
