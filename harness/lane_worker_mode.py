"""The frozen engine's lane worker mode, and the spawn shim that reaches it.

index runs a router job in a worker process it starts itself, with
``[sys.executable, "-m", "index_graph.router_jobs", "_worker", <job_dir>,
<token>]`` (``index_graph/router_jobs.py`` ``_spawn_worker``, index 2.13.0).
In a frozen engine ``sys.executable`` is the engine, which refuses ``-m``
(``packaging/gateway_entry.py``), so the worker exited 2 and no job ran.

Two parts close that:

``install_worker_spawn(lane)``
    Runs in the frozen index child (``--bundled-lane-mcp index`` and
    ``--bundled-lane-cli index``) before the lane serves. It gives
    ``index_graph.router_jobs`` a stand-in for its ``subprocess`` module whose
    ``Popen`` rewrites exactly that argv to ``lane_cli.lane_worker_argv``:
    ``[<engine.exe>, --bundled-lane-worker, index, <job_dir>, <token>]``. The
    other arguments index passes (log files, working directory, window flags)
    reach ``Popen`` unchanged, and any other argv passes untouched.

``dispatch_bundled_lane_worker(argv)``
    Serves that mode: exactly four tokens, a hex run token and a job folder
    that exists directly under index's own job root in this environment (the
    lane folder's ``INDEX_ROUTER_JOB_DIR`` or its scoped ``LOCALAPPDATA``).
    The lane then clears the same descriptor admission as the other lane
    modes, and index's own worker function runs the job.

Each dispatcher returns None for an argv that is not its mode, 2 for a
malformed or foreign one, and the worker's exit code otherwise.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bundled_lane_admission import admit_bundled_lane

WORKER_FLAG = "--bundled-lane-worker"
_TOKEN = re.compile(r"[0-9a-f]{32}\Z")
_JOB_NAME = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


@dataclass(frozen=True)
class WorkerSpec:
    module: str                  # the lane module that spawns and runs the worker
    marker: tuple[str, ...]      # argv[1:] prefix the lane spawns its worker with
    run: str                     # callable(job_dir, token) -> exit code
    job_root: str                # callable() -> the lane's job root in this env


WORKERS: dict[str, WorkerSpec] = {
    "index": WorkerSpec("index_graph.router_jobs", ("-m", "index_graph.router_jobs", "_worker"),
                        "run_router_job_worker", "default_job_root"),
}


class _SubprocessShim:
    """``subprocess`` for one lane module, with the worker argv rewritten."""

    def __init__(self, real: Any, lane: str, marker: tuple[str, ...],
                 executable: str | None):
        self._real, self._lane, self._marker = real, lane, marker
        self._executable = executable

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def Popen(self, args: Any, *rest: Any, **kwargs: Any) -> Any:  # noqa: N802 (subprocess API)
        if isinstance(args, (list, tuple)):
            argv = [str(a) for a in args]
            end = 1 + len(self._marker)
            if tuple(argv[1:end]) == self._marker:
                from .lane_cli import lane_worker_argv
                args = lane_worker_argv(self._lane, argv[end:],
                                        executable=self._executable or argv[0])
        return self._real.Popen(args, *rest, **kwargs)


def install_worker_spawn(lane: str, *, executable: str | None = None) -> bool:
    """Route ``lane``'s worker spawn through the engine's worker mode; False
    for a lane with no worker. Installing twice keeps one shim."""
    spec = WORKERS.get(lane)
    if spec is None:
        return False
    module = importlib.import_module(spec.module)
    if not isinstance(module.subprocess, _SubprocessShim):
        module.subprocess = _SubprocessShim(module.subprocess, lane, spec.marker, executable)
    return True


def _job_dir(spec: WorkerSpec, raw: str) -> Path | None:
    """The job folder when it is an existing folder directly under the lane's
    job root in this environment; else None."""
    path = Path(raw)
    if not path.is_absolute() or not _JOB_NAME.fullmatch(path.name):
        return None
    module = importlib.import_module(spec.module)
    try:
        root = Path(getattr(module, spec.job_root)()).resolve()
        job = path.resolve()
    except (OSError, ValueError):
        return None
    return job if job.is_dir() and job.parent == root else None


def dispatch_bundled_lane_worker(argv: list[str]) -> int | None:
    """Run ``--bundled-lane-worker <lane> <job_dir> <token>`` after admission."""
    if not argv or argv[0] != WORKER_FLAG:
        return None
    if len(argv) != 4 or argv[1] not in WORKERS or not _TOKEN.fullmatch(argv[3]):
        return 2
    spec = WORKERS[argv[1]]
    job = _job_dir(spec, argv[2])
    if job is None:
        return 2
    admission = admit_bundled_lane(argv[1], executable=sys.executable, environ=os.environ)
    if admission.blocking_codes:
        return 2
    run = getattr(importlib.import_module(spec.module), spec.run)
    return int(run(job, argv[3]) or 0)
