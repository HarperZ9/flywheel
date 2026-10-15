"""background.py -- long commands that run while the agent keeps working.

`TOOL run_background {"cmd": "npm run dev"}` starts a command in the same OS
sandbox as `run`, under the same gate, denylist and permission mode (it is a
command), and returns a job id at once. `TOOL processes {"action": "list"}`
lists jobs; `{"action": "output", "id": "bg1"}` reads what a job has printed so
far; `{"action": "stop", "id": "bg1"}` stops it. A job runs for at most 30
minutes. Every start, stop and finish goes on the session ledger.

On Windows the output can be read while the job runs and `stop` ends it at
once. On Linux and macOS this release reads the output when the job ends, and
`stop` takes effect at the job's time limit; the tool says so when asked.
"""
from __future__ import annotations

import itertools
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

TIME_LIMIT = 1800
MAX_JOBS = 8
TAIL = 4000
TOOL_TEXT = ('Also available: TOOL run_background {"cmd": "<command>"} starts a long command '
             '(a dev server, a watcher) and returns a job id; TOOL processes {"action": '
             '"list" | "output" | "stop", "id": "<job id>"} checks or stops it.')


@dataclass
class Job:
    id: str
    cmd: str
    started: float
    cancel: threading.Event = field(default_factory=threading.Event)
    work: "Path | None" = None
    result: "tuple | None" = None
    stopped: bool = False

    def status(self) -> str:
        if self.result is None:
            return "stopping" if self.stopped else "running"
        return "stopped" if self.stopped else ("finished" if self.result[0] else "failed")


class JobTable:
    def __init__(self, root: str, record=None, start=None):
        self.root, self.record = root, record or (lambda *a: None)
        self.jobs: dict = {}
        self._ids = itertools.count(1)
        self._start = start or self._sandboxed

    def _sandboxed(self, job: Job) -> tuple:
        from harness.sandboxed_runner import SandboxUnavailable, sandboxed_run
        from .cli import SANDBOX_ENV

        def keep(work):
            job.work = Path(work)
        try:
            return sandboxed_run(job.cmd, self.root, scratch_home=True, extra_env=SANDBOX_ENV,
                                 timeout_seconds=TIME_LIMIT, cancel=job.cancel, work_hook=keep)
        except SandboxUnavailable as e:
            return False, f"[refused] no OS sandbox on this host ({e})"

    def start(self, cmd: str) -> "tuple[bool, str]":
        running = [j for j in self.jobs.values() if j.result is None]
        if len(running) >= MAX_JOBS:
            return False, f"[refused] {MAX_JOBS} background jobs are already running"
        job = Job(f"bg{next(self._ids)}", cmd, time.time())
        self.jobs[job.id] = job

        def body():
            job.result = self._start(job)
            self.record("finish", {"id": job.id, "status": job.status()})
        threading.Thread(target=body, name=f"flywheel-{job.id}", daemon=True).start()
        self.record("start", {"id": job.id, "cmd": cmd})
        return True, f"started {job.id}: {cmd}"

    def _live(self, job: Job) -> str:
        if job.work is None:
            return ""
        parts = []
        for name in ("stdout.txt", "stderr.txt"):
            try:
                parts.append((job.work / name).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
        return "".join(parts)

    def output(self, job_id: str) -> "tuple[bool, str]":
        job = self.jobs.get(job_id)
        if job is None:
            return False, f"[error] no job {job_id!r}"
        text = job.result[1] if job.result is not None else self._live(job)
        if job.result is None and not text and os.name != "nt":
            text = "(output is read when the job ends on this platform)"
        return True, f"[{job.id} {job.status()} | {int(time.time() - job.started)}s]\n" \
            + text[-TAIL:]

    def stop(self, job_id: str) -> "tuple[bool, str]":
        job = self.jobs.get(job_id)
        if job is None:
            return False, f"[error] no job {job_id!r}"
        if job.result is not None:
            return True, f"{job.id} already {job.status()}"
        job.stopped = True
        job.cancel.set()
        self.record("stop", {"id": job.id})
        note = "" if os.name == "nt" else " (on this platform it ends at its time limit)"
        return True, f"stopping {job.id}{note}"

    def listing(self) -> str:
        if not self.jobs:
            return "(no background jobs)"
        return "\n".join(f"{j.id} {j.status():<8} {int(time.time() - j.started)}s  {j.cmd}"
                         for j in self.jobs.values())

    def stop_all(self) -> None:
        for job in self.jobs.values():
            if job.result is None:
                job.stopped = True
                job.cancel.set()
