"""Replay reproducible bench tasks in hardened clones (7.8 stage B1, FW-12b1).

Per reproducible task and endpoint: a shared clone of the recorded
workspace (`git clone --shared --no-checkout`, then a detached checkout of
the recorded commit) under
`FLYWHEEL_HOME/state/trace-bench/v1/owners/<owner>/replay/`,
with system configuration off, global configuration pointed at an empty
file, hooks and fsmonitor off, so neither the owner's configuration
(filters, credential helpers) nor repository hooks run. The clone reads the
owner's repository and writes nothing into it. Its git identity must equal
the recorded one, or the task is UNREPRODUCIBLE (CLONE_DRIFTED).

The goal runs through `run_router_agent` in the clone. The gate command then
runs there in the low-integrity sandbox with an allowlisted environment
(`PATH`, `SYSTEMROOT`, `COMSPEC`, `PATHEXT`, and `HOME`, `TEMP` and `TMP`
inside the run's scratch; no provider keys): gate commands are code from an
old commit, and the gateway's environment holds provider keys. The verdict
(PASS or FAIL) is stored encrypted with lineage to the task. The clone is
removed with the reparse-safe remover, which deletes junctions and symbolic
links as links and never follows them; a clone left by a crash is removed by
`sweep` at start. The regression report compares (task, endpoint) pairs
against each task's prior verdict.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import secrets
import subprocess

from .trace_bench_tasks import BenchTasks, ReplayResults
from . import safe_program

_log = logging.getLogger(__name__)
SCHEMA = "flywheel.trace-replay-result/v1"
GATE_TIMEOUT_S = 300
OUTPUT_CHARS = 4000


class ReplayError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def replay_root(home, owner: str) -> Path:
    return Path(home) / "state" / "trace-bench" / "v1" / "owners" / owner / "replay"


def _git(cwd: Path, *args: str) -> None:
    """A git call under an empty global config, no system config, no hooks."""
    empty = cwd / "empty.gitconfig" if cwd.name != "repo" else cwd.parent / "empty.gitconfig"
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(empty), GIT_TERMINAL_PROMPT="0",
               GIT_OPTIONAL_LOCKS="0")
    command = ["git", "-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false",
               *args]
    try:
        done = subprocess.run(safe_program.argv(command, cwd=cwd, env=env), cwd=cwd,
                              capture_output=True, env=env, timeout=300,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReplayError("CLONE_FAILED") from exc
    if done.returncode != 0:
        _log.warning("git %s failed with exit %s", args[0], done.returncode)
        raise ReplayError("CLONE_FAILED")


def _clone(workspace: str, folder: Path) -> Path:
    (folder / "empty.gitconfig").write_bytes(b"")
    _git(folder, "clone", "--quiet", "--shared", "--no-checkout", "--", workspace, "repo")
    return folder / "repo"


def _checkout(clone: Path, head: str) -> None:
    _git(clone, "checkout", "--quiet", "--detach", head)


def _same_identity(clone: Path, recorded: dict) -> bool:
    from .workspace_git_identity import git_identity
    now = git_identity(clone)
    return bool(now) and all(now.get(k) == recorded.get(k)
                             for k in ("head", "tracked_sha256", "status_sha256", "clean"))


def _run_gate(clone: Path, gate_cmd: str) -> tuple[bool | None, str]:
    """(passed, output); passed is None when no sandbox could hold the gate."""
    from .sandboxed_runner import SandboxUnavailable, sandboxed_run
    try:
        return sandboxed_run(gate_cmd, str(clone), timeout_seconds=GATE_TIMEOUT_S,
                             scratch_home=True)
    except SandboxUnavailable as exc:
        _log.warning("bench gate not run: no sandbox (%s)", exc)
        return None, "[not run: no sandbox on this host]"


def _run_goal(task: dict, endpoint: str, clone: Path, proposer) -> dict:
    from .router_agent import run_router_agent
    caps = task.get("capabilities") or {}
    out = run_router_agent(task["goal"], endpoint, root=str(clone),
                           allow_write=bool(caps.get("allow_write")),
                           allow_exec=bool(caps.get("allow_exec")), proposer=proposer)
    return {k: out.get(k) for k in ("final", "steps", "checkpoint", "verified")}


def _remove(home, owner: str, name: str) -> None:
    from .private_artifact_fs import root_identity
    from .private_artifact_remove import remove
    root = replay_root(home, owner)
    remove(root, name, expected=root_identity(root))


def _result(task: dict, endpoint: str, verdict: str, reason=None, **extra) -> dict:
    return {"schema": SCHEMA, "result_ref": "rpr_" + secrets.token_hex(16),
            "task_ref": task["task_ref"], "endpoint": endpoint, "verdict": verdict,
            "reason": reason, "gate_pass": verdict == "PASS" if verdict in ("PASS", "FAIL")
            else None, "lineage": {"task_ref": task["task_ref"],
                                   "source_trace_ref": task["trace_ref"]},
            "goal_digest": hashlib.sha256(task["goal"].encode("utf-8")).hexdigest()[:16],
            **extra}


def replay_one(home, owner: str, task: dict, endpoint: str, proposer=None) -> dict:
    """Clone, check identity, run the goal, run the gate, remove the clone."""
    name = "rpl_" + secrets.token_hex(8)
    folder = replay_root(home, owner) / name
    folder.mkdir(parents=True)
    try:
        clone = _clone(task["workspace"], folder)
        _checkout(clone, task["git"]["head"])
        if not _same_identity(clone, task["git"]):
            return _result(task, endpoint, "UNREPRODUCIBLE", "CLONE_DRIFTED")
        run = _run_goal(task, endpoint, clone, proposer)
        passed, output = _run_gate(clone, task["gate_cmd"])
        if passed is None:
            return _result(task, endpoint, "UNREPRODUCIBLE", "SANDBOX_UNAVAILABLE")
        return _result(task, endpoint, "PASS" if passed else "FAIL", run=run,
                       gate_output=output[-OUTPUT_CHARS:])
    except ReplayError as exc:
        return _result(task, endpoint, "UNREPRODUCIBLE", exc.code)
    finally:
        _remove(home, owner, name)


def _prior(tasks: list[dict], endpoints: list[str]) -> dict:
    return {"attempts": [{"task_id": t["task_ref"], "endpoint": e,
                          "gate_pass": t["prior_verdict"] == "PASS"}
                         for t in tasks if t["prior_verdict"] in ("PASS", "FAIL")
                         for e in endpoints]}


def replay_tasks(home, owner: str, endpoints: list[str], *, proposer_for=None,
                 only=None) -> dict:
    """Replay every reproducible task (or those in `only`) on each endpoint."""
    from .trace_bench import regression_report
    sweep(home, owner)
    store, results = BenchTasks(home, owner), ReplayResults(home, owner)
    classes: dict[str, int] = {}
    replayable = []
    for row in store.index():
        classes[row["class"]] = classes.get(row["class"], 0) + 1
        if row["class"] == "REPRODUCIBLE" and (only is None or row["task_ref"] in only):
            replayable.append(store.read(row["task_ref"]))
    out = []
    for task in replayable:
        for endpoint in endpoints:
            proposer = proposer_for(task, endpoint) if proposer_for else None
            result = replay_one(home, owner, task, endpoint, proposer)
            results.add(result)
            out.append({k: result[k] for k in ("result_ref", "task_ref", "endpoint", "verdict",
                                                 "reason", "goal_digest")})
    current = {"attempts": [{"task_id": r["task_ref"], "endpoint": r["endpoint"],
                             "gate_pass": r["verdict"] == "PASS"}
                            for r in out if r["verdict"] in ("PASS", "FAIL")]}
    return {"schema": "flywheel.trace-replay-report/v1", "classes": classes, "results": out,
            "regression": regression_report(_prior(replayable, endpoints), current)}


def sweep(home, owner: str) -> int:
    """Remove clones a crashed replay left; links are removed as links."""
    root = replay_root(home, owner)
    names = sorted(p.name for p in root.iterdir()) if root.is_dir() else []
    for name in names:
        _remove(home, owner, name)
    return len(names)


def sweep_all(home) -> int:
    """Gateway start: sweep every owner's replay store."""
    base = Path(home) / "state" / "trace-bench" / "v1" / "owners"
    owners = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    return sum(sweep(home, owner) for owner in owners)
