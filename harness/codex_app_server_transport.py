"""Process and JSONL transport helpers for Codex app-server."""
from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

TIMEOUT = 12.0
MAX_RESPONSE_BYTES = 1_000_000
SAFE_ENV = {
    "APPDATA", "CODEX_HOME", "COMSPEC", "HOME", "LOCALAPPDATA", "PATH",
    "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "WINDIR",
}


def identity(argv_prefix: list[str]) -> str:
    return executable_identity(argv_prefix)[0]


def executable_identity(argv_prefix: list[str]) -> tuple[str, list[dict]]:
    h = hashlib.sha256()
    records = []
    for item in argv_prefix:
        p = Path(item).resolve()
        data = p.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        records.append({"path": str(p), "basename": p.name, "sha256": digest})
        h.update(str(p).encode("utf-8", "replace"))
        h.update(b"\0")
        h.update(digest.encode())
        h.update(b"\0")
    return h.hexdigest(), records


def _is_windows(value=None) -> bool:
    return os.name == "nt" if value is None else bool(value)


def _which(name: str, search_path: str | None):
    try:
        return shutil.which(name, path=search_path)
    except TypeError:
        return shutil.which(name)


def subprocess_run(argv, timeout, *, env=None, cwd=None):
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
              "stdin": subprocess.DEVNULL, "text": True, "check": False,
              "timeout": timeout, "env": env, "cwd": cwd}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(argv, **kwargs)


def _run(runner, argv, timeout, *, env=None, cwd=None):
    try:
        return runner(argv, timeout, env=env, cwd=cwd)
    except TypeError:
        return runner(argv, timeout)


def run_version(argv_prefix: list[str], *, runner=None, env=None, cwd=None,
                timeout: float = TIMEOUT) -> str:
    runner = runner or subprocess_run
    try:
        proc = _run(runner, [*argv_prefix, "--version"], timeout, env=env, cwd=cwd)
    except Exception:
        return ""
    if getattr(proc, "returncode", 1) != 0:
        return ""
    return str(getattr(proc, "stdout", "") or "").strip().splitlines()[0][:120]


def npm_wrapper_prefix(path: Path, *, which) -> list[str] | None:
    basedir = path.parent
    script = basedir / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    if not script.is_file():
        return None
    node = basedir / ("node.exe" if os.name == "nt" else "node")
    if not node.is_file():
        found = which("node.exe") or which("node")
        node = Path(found) if found else node
    return [str(node), str(script)] if node.is_file() else None


def prefix_for_path(path: str, *, which, is_windows=None) -> list[str] | None:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in {".cmd", ".ps1"}:
        return npm_wrapper_prefix(p, which=which)
    if suffix == ".js":
        node = which("node.exe") or which("node")
        return [node, str(p)] if node else None
    if p.is_file() or shutil.which(path):
        return [str(p)]
    return None


def resolve_codex_cli(*, which=None, env=None, is_windows=None,
                      version_runner=None, cwd=None) -> dict:
    raw_env = env or os.environ
    child_env = app_server_env(raw_env)
    search_path = raw_env.get("PATH") or os.environ.get("PATH")
    which = which or (lambda name: _which(name, search_path))
    configured = (raw_env.get("FLYWHEEL_CODEX_APP_SERVER_CLI")
                  or raw_env.get("CODEX_APP_SERVER_CLI") or "").strip()
    candidates = [configured] if configured else []
    candidates += ([which("codex.exe") or "", which("codex") or ""]
                   if _is_windows(is_windows) else [which("codex") or ""])
    unsupported = False
    for cand in candidates:
        if not cand:
            continue
        prefix = prefix_for_path(cand, which=which, is_windows=is_windows)
        if not prefix:
            unsupported = True
            continue
        try:
            exact_identity, file_hashes = executable_identity(prefix)
        except OSError:
            return {"ok": False, "state": "identity_unreadable",
                    "cli_present": True, "argv_prefix": [], "executable": "",
                    "note": "Codex executable identity could not be read"}
        child_cwd = str(Path(cwd).resolve()) if cwd else str(Path.cwd())
        version = run_version(
            prefix, runner=version_runner, env=child_env, cwd=child_cwd)
        return {"ok": True, "state": "available", "cli_present": True,
                "argv_prefix": prefix, "executable": Path(prefix[0]).name,
                "identity": exact_identity, "identity_digest": exact_identity[:16],
                "file_hashes": file_hashes, "version": version,
                "env": child_env, "cwd": child_cwd,
                "env_fingerprint": env_fingerprint(child_env),
                "codex_home": child_env.get("CODEX_HOME", ""),
                "source": "codex-app-server"}
    state = "wrapper_unsupported" if unsupported else "cli_absent"
    note = ("Codex CLI wrapper unsupported"
            if unsupported else "Codex CLI was not found")
    return {"ok": False, "state": state, "cli_present": False,
            "argv_prefix": [], "executable": "", "note": note}


def app_server_env(base_env=None) -> dict:
    src = base_env or os.environ
    return {k: v for k, v in src.items() if k in SAFE_ENV}


def env_fingerprint(env: dict) -> str:
    clean = {str(k): str(v) for k, v in (env or {}).items()}
    blob = json.dumps(clean, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _same_path(left: str, right: str) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return str(left) == str(right)


class JsonlAppServerClient:
    def __init__(self, argv_prefix: list[str], *, popen=None, env=None, cwd=None,
                 timeout: float = TIMEOUT):
        self.argv = [*argv_prefix, "app-server", "--stdio"]
        self.popen = popen or subprocess.Popen
        self.env = app_server_env(env)
        self.cwd = cwd
        self.timeout = timeout
        self.proc = None
        self._id = 0
        self._queue: queue.Queue = queue.Queue()
        self.notifications = []
        self.initialize_result = {}
        self.codex_home = ""

    def __enter__(self):
        kwargs = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
                  "stderr": subprocess.DEVNULL, "text": True,
                  "encoding": "utf-8", "errors": "replace",
                  "env": self.env, "cwd": self.cwd}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = self.popen(self.argv, **kwargs)
            threading.Thread(target=self._reader, daemon=True).start()
            self.initialize_result = self.request("initialize", {"clientInfo": {
                "name": "flywheel", "title": "Flywheel", "version": "0.6.2"}})
            self.codex_home = str(self.initialize_result.get("codexHome") or "")
            expected = self.env.get("CODEX_HOME", "")
            if expected and (not self.codex_home or not _same_path(expected, self.codex_home)):
                raise RuntimeError("app-server Codex home mismatch")
            self.notify("initialized", {})
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, *_):
        self.close()

    def close(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait(timeout=1)
        except Exception:
            pass

    def _reader(self):
        while True:
            try:
                line = self.proc.stdout.readline()
            except Exception:
                return
            if not line:
                return
            self._queue.put(line)

    def _send(self, obj: dict) -> None:
        self.proc.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict) -> None:
        self._send({"method": method, "params": params})

    def request(self, method: str, params: dict) -> dict:
        self._id += 1
        req_id = self._id
        self._send({"id": req_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        seen = 0
        while time.monotonic() < deadline and seen <= MAX_RESPONSE_BYTES:
            try:
                line = self._queue.get(
                    timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            seen += len(line)
            if seen > MAX_RESPONSE_BYTES:
                raise TimeoutError("app-server response exceeded byte limit")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == req_id:
                if "error" in msg:
                    err = msg.get("error") or {}
                    raise RuntimeError(err.get("message") or "app-server error")
                return msg.get("result") if isinstance(msg.get("result"), dict) else {}
            if "method" in msg:
                self.notifications.append(msg)
        raise TimeoutError("app-server response timed out")
