"""run.py -- run one scenario on one build and capture its five streams.

A build is a Flywheel source tree. Each run gets a fresh folder holding its own
home, workspace, temp folder and FLYWHEEL_HOME, and its own scripted model. The
session is pinned to that model: `--backend codex --providers codex` with
CODEX_BASE_URL pointing at the stub, every other provider key and base URL
removed from the environment, so the local-first ladder never reaches a real
model server.

Streams captured: (1) model request bodies, (2) stream-json events, (3) the
sha256 of every file in the workspace after the run, (4) the exit code, (5) the
sequence of ledger entry kinds.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .model import MODEL_ID, ScriptedModel

TIMEOUT = 300
STUB_KEY = "behavior-check-stub-not-a-key"
_DROP_SUFFIXES = ("_API_KEY", "_BASE_URL", "_MODEL", "_TOKEN", "_KEY", "_SECRET",
                  "_PORT", "_PROVIDER_ID", "_USERNAME", "_PASSWORD")
_DROP_PREFIXES = ("FLYWHEEL_", "OLLAMA", "PYTHON", "AWS_", "AZURE_", "VERTEX_",
                  "BEDROCK", "OPENCODE", "OPEN_CODE", "ANTHROPIC", "OPENAI", "GEMINI",
                  "VIRTUAL_ENV", "PIP_", "CONDA")
_BOOT = ("import sys; sys.path.insert(0, sys.argv[1]); "
         "from harness.cli_entry import main; raise SystemExit(main(sys.argv[2:]))")


def scenarios_path() -> Path:
    return Path(__file__).with_name("scenarios.json")


def load_scenarios(path: "str | Path | None" = None) -> list:
    data = json.loads(Path(path or scenarios_path()).read_text(encoding="utf-8"))
    return data["scenarios"]


def clean_env(base: "dict | None" = None) -> dict:
    """The caller's environment without provider settings or Flywheel settings."""
    env = {}
    for key, value in (base if base is not None else os.environ).items():
        up = key.upper()
        if up.endswith(_DROP_SUFFIXES) or up.startswith(_DROP_PREFIXES):
            continue
        env[key] = value
    return env


def _layout(work: Path) -> dict:
    run = Path(tempfile.mkdtemp(prefix="bc-", dir=str(work)))
    dirs = {"run": run, "home": run / "home", "workspace": run / "home" / "ws",
            "flywheel_home": run / "fwhome", "temp": run / "tmp"}
    for key in ("workspace", "flywheel_home", "temp"):
        dirs[key].mkdir(parents=True)
    return dirs


def _write_files(root: Path, files: dict, python: str) -> None:
    for rel, content in sorted(files.items()):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not isinstance(content, str):
            content = json.dumps(content, indent=1, sort_keys=True)
        content = content.replace("{python}", python.replace("\\", "/"))
        target.write_bytes(content.encode("utf-8"))


def _env(dirs: dict, base_url: str, env_base: "dict | None") -> dict:
    env = clean_env(env_base)
    home, temp = str(dirs["home"]), str(dirs["temp"])
    env.update({"FLYWHEEL_HOME": str(dirs["flywheel_home"]), "HOME": home,
                "USERPROFILE": home, "TEMP": temp, "TMP": temp, "TMPDIR": temp,
                "OPENAI_API_KEY": STUB_KEY, "CODEX_BASE_URL": base_url,
                "CODEX_MODEL": MODEL_ID, "FLYWHEEL_ALLOW_UNSANDBOXED": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
                "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    return env


def command(tree: str, scenario: dict, python: str) -> list:
    argv = ["code", "-p", scenario["prompt"], "--output-format", "stream-json",
            "--backend", "codex", "--providers", "codex",
            "--mode", scenario.get("mode", "edit"), *scenario.get("args", [])]
    return [python, "-c", _BOOT, str(Path(tree).resolve()), *argv]


def _file_hashes(root: Path) -> list:
    out = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            out.append([rel, hashlib.sha256(path.read_bytes()).hexdigest()])
    return out


def _ledger_kinds(home: Path) -> list:
    kinds = []
    for ledger in sorted((home / "sessions").glob("*/ledger.jsonl")):
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                kinds.append(json.loads(line).get("kind"))
    return kinds


def _events(stdout: str) -> list:
    out = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({"raw_line": line})
    return out


def run_scenario(tree: str, scenario: dict, work: "str | Path", *,
                 python: str = sys.executable, env_base: "dict | None" = None,
                 keep: bool = False) -> dict:
    """Run one scenario on one build; returns its raw streams and the paths to mask."""
    dirs = _layout(Path(work))
    _write_files(dirs["workspace"], scenario.get("files", {}), python)
    with ScriptedModel(scenario["replies"]) as model:
        try:
            proc = subprocess.run(command(tree, scenario, python), cwd=str(dirs["workspace"]),
                                  env=_env(dirs, model.base_url, env_base),
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=TIMEOUT)
            exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            exit_code, stdout, stderr = "timeout", "", ""
        requests = model.requests
    streams = {"requests": requests, "events": _events(stdout),
               "files": _file_hashes(dirs["workspace"]), "exit": exit_code,
               "ledger": _ledger_kinds(dirs["flywheel_home"])}
    masks = {k: str(v) for k, v in dirs.items()}
    result = {"scenario": scenario["name"], "streams": streams, "masks": masks,
              "stderr_tail": stderr[-2000:]}
    if not keep:
        shutil.rmtree(dirs["run"], ignore_errors=True)
    return result
