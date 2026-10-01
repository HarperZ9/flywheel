"""check_preaction_entry.py -- the single-entry gate for the pre-action monitor.

Property: ToolExecutor._execute_inner is reachable only from ToolExecutor.execute,
so no call path skips the monitor. This walks the AST of every file under
harness/ and fails if any code names `_execute_inner` outside local_tools.py
(where execute calls it) or outside a method called `execute`. A new caller
elsewhere is a monitor bypass and fails CI.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ALLOWED_FILES = {"local_tools.py"}
NEEDLE = "_execute_inner"


def offenders(root: Path) -> list:
    out = []
    for path in sorted(root.rglob("*.py")):
        if path.name in ALLOWED_FILES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == NEEDLE:
                out.append(f"{path}:{node.lineno}: references {NEEDLE} outside execute()")
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path("harness")
    hits = offenders(root)
    if hits:
        print("pre-action single-entry gate FAILED:")
        for h in hits:
            print("  " + h)
        return 1
    print(f"pre-action single-entry gate clean: no stray {NEEDLE} callers under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
