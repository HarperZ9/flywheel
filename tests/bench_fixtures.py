"""A git fixture repository and gateway traces of runs against it, for the
bench tests. The repository's test fails at its first commit; no network."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from delete_fixtures import OWNER

JOURNEY = "jrn_" + "d" * 32
GATE = f'"{sys.executable}" -c "import calc, sys; sys.exit(0 if calc.add(2, 2) == 4 else 1)"'


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=env, check=True)
    return done.stdout.strip()


def git_repo(base: Path) -> Path:
    """A repository whose test fails at its only commit."""
    repo = base / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (repo / ".gitignore").write_text(".venv/\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "a broken add")
    return repo


def plant_run(home: Path, repo: Path, *, operation: str, goal="make add work",
              test_cmd=GATE, tests_pass=False, identity=True, source_context=None) -> str:
    """A gateway trace shaped like a real agent run against `repo`."""
    from harness.gateway_agent_trace import AgentTrace, TraceLedger
    from harness.workspace_git_identity import git_identity
    (home / "state").mkdir(parents=True, exist_ok=True)
    trace = AgentTrace(home / "state", OWNER, JOURNEY, operation)
    op = {"goal": goal, **({"test_cmd": test_cmd} if test_cmd else {})}
    binding = {"endpoint": {"name": "ep-one"}, "model": {"model_id": "model-one"},
               "capabilities": {"allow_write": True, "allow_exec": True},
               "workspace": {"root": str(repo)}}
    trace.append("request", {"operation": op, "source_context": source_context,
                             "execution_binding": binding})
    found = git_identity(repo) if identity else None
    if found:
        TraceLedger(trace).append("workspace_git", json.dumps(found, sort_keys=True))
    trace.append("result", {"final": "done", "tests_pass": tests_pass})
    return trace.ref
