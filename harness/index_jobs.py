"""Durable Projects workspace-map jobs backed by Index router-job."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .index_bridge import _index_argv
from .index_job_registry import (
    DEFAULT_LOCK_TIMEOUT_S,
    IndexRegistryBusy,
    IndexRegistryCommitFailed,
    locked_registry,
)

SCHEMA = "flywheel.index-workspace-map-job/v1"
_ACTIVE = {"queued", "running", "cancellation_requested"}
_REPO = Path(__file__).resolve().parent.parent


def _job_root(run_root: Path | str) -> Path:
    return Path(run_root) / "index-router-jobs"


def _canonical(root: Path | str) -> str:
    return str(Path(root).resolve())


def _base(root: str, *, job_id: str = "", error_type: str | None = None,
          message: str | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "root": root,
        "root_sha256_prefix": "",
        "job_id": job_id,
        "status": "failed" if error_type else "running",
        "phase": "failed" if error_type else "queued",
        "completed_repos": 0,
        "total_repos": None,
        "result_available": False,
        "result_sha256": None,
        "error_type": error_type,
        "message": message,
    }


def _failure(root: str, code: str, message: str, *, job_id: str = "") -> dict:
    return _base(root, job_id=job_id, error_type=code, message=message)


def _registry_failure(root: str, code: str, *, job_id: str = "") -> dict:
    return _failure(root, code,
                    "index workspace-map registry is busy; retry shortly"
                    if code == "INDEX_REGISTRY_BUSY"
                    else "index workspace-map registry write failed",
                    job_id=job_id)


def _status_value(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    return "failed"


def _int_or_none(value: object) -> int | None:
    return value if type(value) is int else None


def _shape(root: str, receipt: dict[str, Any], *,
           row: dict[str, Any] | None = None, job_id: str = "",
           include_content: bool = False) -> dict[str, Any]:
    status_receipt = receipt.get("status_receipt")
    status = status_receipt if isinstance(status_receipt, dict) else receipt
    actual_root = status.get("root")
    actual_hash = status.get("root_sha256_prefix")
    if actual_root != root:
        return _failure(root, "ROOT_MISMATCH",
                        "Index job root does not match the requested root",
                        job_id=job_id or str(status.get("job_id") or ""))
    if row and row.get("root_sha256_prefix") and actual_hash != row.get(
            "root_sha256_prefix"):
        return _failure(root, "ROOT_MISMATCH",
                        "Index job root hash changed from the server registry",
                        job_id=job_id or str(status.get("job_id") or ""))
    out = _base(root, job_id=str(status.get("job_id") or job_id))
    out.update({
        "root_sha256_prefix": actual_hash if isinstance(actual_hash, str) else "",
        "status": _status_value(status.get("status")),
        "phase": _status_value(status.get("phase")),
        "completed_repos": _int_or_none(status.get("completed_repos")) or 0,
        "total_repos": _int_or_none(status.get("total_repos")),
        "result_available": bool(receipt.get(
            "result_available", status.get("result_available", False))),
        "result_sha256": receipt.get("result_sha256") or status.get("result_sha256"),
        "error_type": status.get("error_type"),
        "message": status.get("message"),
    })
    if include_content and out["status"] == "complete" and out[
            "result_available"] and isinstance(receipt.get("content"), str):
        out["content"] = receipt["content"]
    return out


def _remember(rows: dict[str, dict[str, Any]], root: str,
              shaped: dict[str, Any]) -> None:
    if not shaped.get("job_id") or shaped.get("error_type") == "ROOT_MISMATCH":
        return
    rows[root] = {
        "root": root,
        "job_id": shaped["job_id"],
        "root_sha256_prefix": shaped.get("root_sha256_prefix", ""),
        "status": shaped.get("status", ""),
        "phase": shaped.get("phase", ""),
    }


def _env(run_root: Path | str) -> dict[str, str]:
    env = os.environ.copy()
    env["INDEX_ROUTER_JOB_DIR"] = str(_job_root(run_root))
    return env


def _parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _module_argv() -> list[str] | None:
    try:
        import importlib.util
        if importlib.util.find_spec("index_graph") is not None:
            return [sys.executable, "-m", "index_graph.cli"]
    except Exception:
        pass
    return None


def _candidate_argvs() -> list[list[str]]:
    candidates: list[list[str]] = []
    for argv in (_index_argv(), _module_argv()):
        if argv and argv not in candidates:
            candidates.append(argv)
    return candidates


def _probe_engine(argv: list[str], root: str, run_root: Path | str) -> dict | None:
    env = _env(run_root)
    try:
        version = subprocess.run(argv + ["--version"], capture_output=True,
                                 text=True, timeout=8, env=env, cwd=str(_REPO))
        help_run = subprocess.run(argv + ["router-job", "--help"],
                                  capture_output=True, text=True, timeout=8,
                                  env=env, cwd=str(_REPO))
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return _failure(root, "INDEX_UNAVAILABLE",
                        f"index engine check failed: {type(exc).__name__}")
    found = _parse_version(version.stdout or version.stderr or "")
    if version.returncode != 0 or found is None:
        return _failure(root, "INDEX_UNAVAILABLE",
                        "index engine version could not be verified")
    if found < (2, 12, 0):
        return _failure(root, "INDEX_UNAVAILABLE",
                        f"index router-job requires index-graph>=2.12; "
                        f"found {'.'.join(str(p) for p in found)}")
    if help_run.returncode != 0:
        return _failure(root, "INDEX_UNAVAILABLE",
                        "index engine does not expose router-job")
    return None


def _engine(root: str, run_root: Path | str) -> tuple[list[str] | None, dict | None]:
    failures = []
    for argv in _candidate_argvs():
        failure = _probe_engine(argv, root, run_root)
        if failure is None:
            return argv, None
        failures.append(failure)
    if failures:
        return None, failures[-1]
    return None, _failure(root, "INDEX_UNAVAILABLE",
                          "the index engine is not installed; "
                          "pip install --upgrade index-graph>=2.12")


def _run(action: str, root: str, run_root: Path | str,
         args: list[str]) -> dict[str, Any]:
    argv, unavailable = _engine(root, run_root)
    if unavailable is not None:
        return unavailable
    try:
        proc = subprocess.run(argv + ["router-job", action, *args],
                              capture_output=True, text=True, timeout=20,
                              env=_env(run_root), cwd=str(_REPO))
    except subprocess.TimeoutExpired:
        return _failure(root, "INDEX_TIMEOUT", f"index router-job {action} timed out")
    except (OSError, ValueError) as exc:
        return _failure(root, "INDEX_RUNTIME_ERROR",
                        f"index router-job {action} failed: {type(exc).__name__}")
    try:
        doc = json.loads(proc.stdout)
    except ValueError:
        doc = None
    if isinstance(doc, dict):
        return doc
    detail = (proc.stderr or proc.stdout or "").strip()[-300:]
    return _failure(root, "INDEX_RUNTIME_ERROR",
                    f"index router-job {action} failed (rc {proc.returncode}): {detail}")


def _row_for(rows: dict[str, dict[str, Any]], root: str,
             job_id: str | None) -> tuple[str | None, dict[str, Any] | None, dict | None]:
    row = rows.get(root)
    if job_id:
        if not row or row.get("job_id") != job_id:
            return None, None, _failure(root, "UNKNOWN_JOB_FOR_ROOT",
                                        "no server registry row binds that job to this root",
                                        job_id=job_id)
        return job_id, row, None
    if not row or not row.get("job_id"):
        return None, None, _failure(root, "NO_JOB_FOR_ROOT",
                                    "no workspace map job has been started for this root")
    return str(row["job_id"]), row, None


def start_workspace_map(root: Path | str, *, run_root: Path | str,
                        max_docs: int = 500, no_cache: bool = False) -> dict:
    root_s = _canonical(root)
    try:
        with locked_registry(run_root, DEFAULT_LOCK_TIMEOUT_S) as rows:
            row = rows.get(root_s)
            if row and row.get("job_id"):
                doc = _run("status", root_s, run_root, [str(row["job_id"])])
                current = _shape(root_s, doc, row=row, job_id=str(row["job_id"]))
                _remember(rows, root_s, current)
                if current.get("status") in _ACTIVE:
                    return current
            args = [
                "--root", root_s, "--max-docs", str(max_docs), "--budget-ms", "0"
            ]
            if no_cache:
                args.append("--no-cache")
            shaped = _shape(root_s, _run("start", root_s, run_root, args))
            _remember(rows, root_s, shaped)
            return shaped
    except IndexRegistryBusy:
        return _registry_failure(root_s, "INDEX_REGISTRY_BUSY")
    except IndexRegistryCommitFailed:
        return _registry_failure(root_s, "INDEX_REGISTRY_COMMIT_FAILED")


def _workspace_map_action(action: str, root: Path | str, *, run_root: Path | str,
                          job_id: str | None = None,
                          include_content: bool = False) -> dict:
    root_s = _canonical(root)
    try:
        with locked_registry(run_root, DEFAULT_LOCK_TIMEOUT_S) as rows:
            jid, row, failure = _row_for(rows, root_s, job_id)
            if failure is not None:
                return failure
            shaped = _shape(root_s, _run(action, root_s, run_root, [jid]),
                            row=row, job_id=jid,
                            include_content=include_content)
            _remember(rows, root_s, shaped)
            return shaped
    except IndexRegistryBusy:
        return _registry_failure(root_s, "INDEX_REGISTRY_BUSY",
                                 job_id=job_id or "")
    except IndexRegistryCommitFailed:
        return _registry_failure(root_s, "INDEX_REGISTRY_COMMIT_FAILED",
                                 job_id=job_id or "")


def workspace_map_status(root: Path | str, *, run_root: Path | str,
                         job_id: str | None = None) -> dict:
    return _workspace_map_action("status", root, run_root=run_root, job_id=job_id)


def workspace_map_result(root: Path | str, *, run_root: Path | str,
                         job_id: str | None = None) -> dict:
    return _workspace_map_action(
        "result", root, run_root=run_root, job_id=job_id, include_content=True)


def workspace_map_cancel(root: Path | str, *, run_root: Path | str,
                         job_id: str | None = None) -> dict:
    return _workspace_map_action("cancel", root, run_root=run_root, job_id=job_id)


def workspace_map_resume(root: Path | str, *, run_root: Path | str,
                         job_id: str | None = None) -> dict:
    return _workspace_map_action("resume", root, run_root=run_root, job_id=job_id)
