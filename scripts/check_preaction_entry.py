"""check_preaction_entry.py -- the single-entry gate for the pre-action monitor.

Property: ToolExecutor._execute_inner is reachable only from ToolExecutor.execute,
and the builtin tool methods (_t_<name>) only from inside local_tools.py, so no
call path skips the monitor. This walks the AST of every file under harness/
and fails if any code names `_execute_inner` anywhere but a method called
`execute` in local_tools.py, or names a `_t_` tool method outside
local_tools.py. A new caller is a monitor bypass and fails CI.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ALLOWED_FILES = {"local_tools.py"}
NEEDLE = "_execute_inner"


def _walk(node, func, out, path, home):
    for child in ast.iter_child_nodes(node):
        inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
        if isinstance(child, ast.Attribute):
            if child.attr == NEEDLE and not (home and func == "execute"):
                out.append(f"{path}:{child.lineno}: references {NEEDLE} outside execute()")
            elif child.attr.startswith("_t_") and not home:
                out.append(f"{path}:{child.lineno}: calls builtin tool {child.attr} directly")
        _walk(child, inner, out, path, home)


def offenders(root: Path) -> list:
    out = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            out.append(f"{path}: cannot parse ({type(exc).__name__}); not checked")
            continue
        _walk(tree, "", out, path, path.name in ALLOWED_FILES)
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
