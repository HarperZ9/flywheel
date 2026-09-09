"""Gateway and freeze boundaries for Projects Index workspace-map jobs."""
from __future__ import annotations

import ast
import io
import json
from pathlib import Path

from harness import gateway, index_jobs, index_route


class _Headers:
    def __init__(self, length: int):
        self.length = str(length)

    def get(self, key, default=None):
        return self.length if key == "Content-Length" else default


def _fake_status(job_id: str, root: str) -> dict:
    return {
        "schema": "index.router-job-status/v1",
        "job_id": job_id,
        "root": root,
        "root_sha256_prefix": "rootabc123456789",
        "status": "running",
        "phase": "building",
        "completed_repos": 1,
        "total_repos": 2,
        "result_available": False,
        "result_sha256": None,
        "error_type": None,
        "message": None,
        "job_dir": "private-must-not-leak",
    }


def test_frozen_gateway_bundles_index_or_route_fails_actionably(
        tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parent.parent
    spec = ast.parse((repo / "packaging" / "flywheel-gateway.spec").read_text(
        encoding="utf-8"))
    hidden = {
        elt.value for node in ast.walk(spec)
        if isinstance(node, ast.keyword) and node.arg == "hiddenimports"
        for elt in node.value.elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    }
    if any(name == "index_graph" or name.startswith("index_graph.")
           for name in hidden):
        return
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(index_jobs, "_index_argv", lambda: None)
    monkeypatch.setattr(index_jobs, "_module_argv", lambda: None)

    out = index_jobs.start_workspace_map(root, run_root=tmp_path / "run")

    assert out["status"] == "failed"
    assert out["error_type"] == "INDEX_UNAVAILABLE"
    assert "index-graph>=2.12" in out["message"]


def test_gateway_routes_workspace_map_start(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    body = json.dumps({"root": str(root)}).encode()
    sent = {}
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = "/api/index/workspace-map/start"
    h.root = tmp_path
    h.run_root = tmp_path / "run"
    h.headers = _Headers(len(body))
    h.rfile = io.BytesIO(body)
    h._json = lambda value, code=200: sent.update(body=value, code=code)
    monkeypatch.setattr(index_route, "start_workspace_map",
                        lambda root, **_: _fake_status("job-r", str(root)))

    h._post()

    assert sent["code"] == 200
    assert sent["body"]["job_id"] == "job-r"
