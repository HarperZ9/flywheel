"""index_bridge.py -- drive the `index` flagship over a project root.

The index engine (index-graph) maps a repository or a whole monorepo: an
inventory map (repos, file and class counts), a dependency/knowledge graph
(relations, roles, salience, cycles), and symbol listings. This bridge
shells the installed `index` CLI over a caller-named root and returns its
JSON verbatim, so the desktop reads the engine's own answer, never a
reconstruction. A missing CLI or a bad root is a named error; nothing is
indexed until a view asks."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

_VIEWS = {
    "map": ["map", "--json"],          # monorepo inventory / catalog
    "graph": ["graph", "--json"],      # dependency + knowledge graph
    "symbols": ["symbols", "--json"],  # symbol inventory
}
_TIMEOUT = 90
_SUMMARY_TIMEOUT = 20


def _index_argv() -> "list | None":
    """The argv that runs the index CLI: the console script if on PATH, else
    `python -m index_graph.cli` if the module is importable. None otherwise."""
    exe = shutil.which("index")
    if exe:
        return [exe]
    try:
        import importlib.util
        if importlib.util.find_spec("index_graph") is not None:
            return [sys.executable, "-m", "index_graph.cli"]
    except Exception:
        pass
    return None


def index_available() -> bool:
    return _index_argv() is not None


def index_view(root: str, view: str, *, timeout: int = _TIMEOUT) -> dict:
    """Run one index view over `root`. Returns the engine's JSON under
    `result`, or a named error."""
    view = (view or "map").strip()
    if view not in _VIEWS:
        return {"error": f"unknown view '{view}'; use one of "
                         f"{sorted(_VIEWS)}"}
    if not Path(root).is_dir():
        return {"error": f"root is not an existing directory: {root}"}
    argv = _index_argv()
    if argv is None:
        return {"error": "the index engine is not installed; "
                         "pip install index-graph"}
    cmd = argv + _VIEWS[view] + ["--root", str(root)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"index {view} timed out after {timeout}s"}
    except (OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        return {"error": f"index {view} failed (rc {proc.returncode}): {tail}"}
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        return {"error": f"index {view} did not emit JSON"}
    return {"schema": "flywheel.index-view/v1", "view": view,
            "root": str(root), "result": result}


def index_summary(root: str) -> dict:
    """A compact catalog summary for a project card: map stats only.

    Full graph/router context is a durable workspace-map job, not part of the
    synchronous summary path.
    """
    out = {"schema": "flywheel.index-summary/v1", "root": str(root),
           "errors": {}}
    m = index_view(root, "map", timeout=_SUMMARY_TIMEOUT)
    if "error" in m:
        out["errors"]["map"] = m["error"]
    else:
        res = m["result"]
        repos = res.get("repositories", [])
        out["repo_count"] = res.get("repo_count", len(repos)
                                    if isinstance(repos, list) else 0)
        out["dirty_count"] = res.get("dirty_count", 0)
        cc = res.get("class_counts", {})
        out["class_total"] = sum(cc.values()) if isinstance(cc, dict) else 0
        out["root_sha256_prefix"] = res.get("root_sha256_prefix", "")
    return out
