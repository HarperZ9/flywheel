"""HTTP route adapter for Projects Index map and workspace-map jobs."""
from __future__ import annotations

from pathlib import Path

from .index_bridge import index_summary, index_view
from .index_jobs import (
    start_workspace_map,
    workspace_map_cancel,
    workspace_map_result,
    workspace_map_resume,
    workspace_map_status,
)

_JOB_ACTIONS = {
    "status": workspace_map_status,
    "result": workspace_map_result,
    "cancel": workspace_map_cancel,
    "resume": workspace_map_resume,
}


def _body_root(req: dict, default_root: Path, resolve_root) -> tuple[Path | None, dict | None]:
    root, err = resolve_root(req.get("root"), default_root)
    if err:
        return None, {"error": err}
    return root, None


def _start(root: Path, req: dict, run_root) -> tuple[dict, int]:
    max_docs = req.get("max_docs", 500)
    no_cache = req.get("no_cache", False)
    if type(max_docs) is not int or max_docs < 0:
        return {"error": "max_docs must be a non-negative integer"}, 400
    if type(no_cache) is not bool:
        return {"error": "no_cache must be a boolean"}, 400
    return start_workspace_map(
        root, run_root=run_root, max_docs=max_docs, no_cache=no_cache), 200


def handle_index_post(path: str, req: dict, *, default_root: Path,
                      run_root, resolve_root) -> tuple[dict, int]:
    root, fault = _body_root(req, default_root, resolve_root)
    if fault:
        return fault, 400
    assert root is not None
    if path in {"/api/index", "/api/index/summary"}:
        view = (req.get("view") or "summary").strip()
        if path == "/api/index/summary" or view == "summary":
            return index_summary(str(root)), 200
        out = index_view(str(root), view)
        return out, 400 if "error" in out else 200
    prefix = "/api/index/workspace-map/"
    if not path.startswith(prefix):
        return {"error": "not found"}, 404
    action = path[len(prefix):]
    if action == "start":
        return _start(root, req, run_root)
    fn = _JOB_ACTIONS.get(action)
    if fn is None:
        return {"error": "not found"}, 404
    job_id = req.get("job_id")
    if job_id is not None and type(job_id) is not str:
        return {"error": "job_id must be a string"}, 400
    return fn(root, run_root=run_root, job_id=job_id or None), 200
