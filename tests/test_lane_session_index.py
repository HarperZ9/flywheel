"""A real index router job through a lane session (WP10), in a source install.

The index child (``python -m index_graph mcp``) starts the job's worker as its
own child process. The session keeps the index child alive across the three
calls, so the worker finishes and the result call reads the finished job. The
frozen engine runs the same worker as ``--bundled-lane-worker index``; that
path is measured on a local freeze, not here.
"""
from __future__ import annotations

import sys
import time

import pytest

from harness.lane_session import LaneSessionPool
from harness.mcp_client import LaunchSpec

pytest.importorskip("index_graph.router_jobs")


@pytest.mark.timeout(120)
def test_start_status_result_return_a_finished_router_job(tmp_path):
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / "README.md").write_text("# repo\n", encoding="utf-8")
    launch = LaunchSpec((sys.executable, "-m", "index_graph", "mcp"), cwd=str(tmp_path),
                        env_overrides=(("INDEX_ROUTER_JOB_DIR", str(tmp_path / "jobs")),
                                       ("LOCALAPPDATA", str(tmp_path / "appdata"))))
    pool = LaneSessionPool(reaper=False)
    try:
        started = pool.call("index", "index.router.job.start", launch, {"root": str(repo)}, 60)
        job_id = started["job_id"]
        for _ in range(120):
            status = pool.call("index", "index.router.job.status", launch,
                               {"job_id": job_id}, 20)
            if status.get("status") in ("complete", "failed", "cancelled"):
                break
            time.sleep(0.25)
        result = pool.call("index", "index.router.job.result", launch, {"job_id": job_id}, 30)
        sessions = pool.describe()
    finally:
        pool.close_all()
    assert status["status"] == "complete", status
    assert result["job_id"] == job_id and result["status"] == "complete"
    assert result["result_available"] is True and result["content"].startswith("# Workspace map")
    assert sessions["index"]["active"] == 0   # the finished job no longer holds the child
    assert (tmp_path / "jobs" / job_id / "router.md").is_file()
