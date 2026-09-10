"""Claude Code account auth seam.

Only the official Claude Code executable owns account sign-in. This module
probes `claude auth status --json` for typed readiness and launches
`claude auth login` only after a human asks the UI to begin. It never returns
account metadata, executable paths, stdout, stderr, tokens, or provider URLs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

_STATUS_TIMEOUT = 8.0
_LOGIN_METHOD = "claude.ai"
_API_PROVIDER = "firstParty"


def _windows(flag=None) -> bool:
    return os.name == "nt" if flag is None else bool(flag)


def _identity(path: str, *, content: bool = False) -> str:
    p = Path(path)
    h = hashlib.sha256()
    try:
        resolved = p.resolve(strict=False)
    except Exception:
        resolved = p
    h.update(str(resolved).encode("utf-8", "surrogatepass"))
    try:
        st = resolved.stat()
        h.update(f"{st.st_size}:{st.st_mtime_ns}".encode("ascii"))
        if content:
            with resolved.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
    except Exception:
        h.update(b":unreadable:")
    return h.hexdigest()


def _unsupported(path: str, state: str) -> dict:
    return {"ok": False, "state": state, "cli_present": True,
            "executable": Path(path).name,
            "note": "Claude Code executable was present but not a native CLI"}


def _candidate(path: str, *, is_windows=None, content_identity=False) -> dict:
    p = Path(path)
    folded = str(p).replace("\\", "/").lower()
    if "/.warden/bin/" in folded or folded.endswith("/.warden/bin/claude"):
        return _unsupported(path, "wrapper_unsupported")
    if _windows(is_windows) and p.suffix.lower() != ".exe":
        return _unsupported(path, "wrapper_unsupported")
    return {"ok": True, "state": "available", "cli_present": True,
            "path": str(p), "executable": p.name,
            "identity": _identity(str(p), content=content_identity),
            "note": "operator-selected Claude Code executable"}


def resolve_official_cli(*, which=None, is_windows=None,
                         content_identity: bool = False) -> dict:
    """Resolve a native Claude Code CLI without treating wrappers as proof."""
    which = which or shutil.which
    names = ("claude.exe", "claude") if _windows(is_windows) else ("claude",)
    unsupported = None
    for name in names:
        found = which(name)
        if not found:
            continue
        result = _candidate(
            found, is_windows=is_windows, content_identity=content_identity)
        if result.get("ok"):
            return result
        unsupported = unsupported or result
    if unsupported is not None:
        return unsupported
    return {"ok": False, "state": "cli_absent", "cli_present": False,
            "executable": "", "note": "Claude Code CLI was not found"}


def _run_status(argv, timeout):
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
              "stdin": subprocess.DEVNULL, "text": True, "timeout": timeout,
              "check": False}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(argv, **kwargs)


def _safe(resolution: dict, *, state: str = "unknown",
          authenticated: bool = False, note: str = "") -> dict:
    return {"state": state, "authenticated": authenticated,
            "cli_present": bool(resolution.get("cli_present")),
            "executable": resolution.get("executable", ""),
            "executable_label": resolution.get("note", ""),
            "note": note or resolution.get("note", "")}


def _parse_status(resolution: dict, *, code: int, stdout) -> dict:
    try:
        data = json.loads(stdout if isinstance(stdout, str) else "")
    except (TypeError, ValueError):
        return _safe(resolution, note="Claude Code status was not valid JSON")
    if not isinstance(data, dict):
        return _safe(resolution, note="Claude Code status was not an object")
    logged = data.get("loggedIn")
    method = data.get("authMethod")
    provider = data.get("apiProvider")
    if code == 1 and logged is False:
        return _safe(resolution, state="not_authenticated",
                     note="Claude Code account not signed in")
    if (code == 0 and logged is True and method == _LOGIN_METHOD
            and provider == _API_PROVIDER):
        out = _safe(resolution, state="authenticated", authenticated=True,
                    note="Claude Code account authenticated")
        out.update({"source": "claude-code-account",
                    "auth_method": method, "api_provider": provider})
        return out
    return _safe(resolution,
                 note="Claude Code status did not prove first-party account auth")


def account_status(*, which=None, runner=None, timeout: float = _STATUS_TIMEOUT,
                   is_windows=None) -> dict:
    """Return account readiness labels only; never metadata or raw output."""
    resolution = resolve_official_cli(which=which, is_windows=is_windows)
    if not resolution.get("ok"):
        return _safe(resolution, state=resolution.get("state", "unknown"),
                     note=resolution.get("note", ""))
    return _status_for_resolution(resolution, runner=runner, timeout=timeout)


def _status_for_resolution(
        resolution: dict, *, runner=None, timeout: float = _STATUS_TIMEOUT) -> dict:
    runner = runner or _run_status
    try:
        proc = runner([resolution["path"], "auth", "status", "--json"], timeout)
    except subprocess.TimeoutExpired:
        return _safe(resolution, note="Claude Code status timed out")
    except Exception:
        return _safe(resolution, note="Claude Code status could not run")
    return _parse_status(
        resolution, code=getattr(proc, "returncode", -1),
        stdout=getattr(proc, "stdout", ""))


def authenticated_resolution(
        *, which=None, runner=None, timeout: float = _STATUS_TIMEOUT,
        is_windows=None) -> dict:
    resolution = resolve_official_cli(
        which=which, is_windows=is_windows, content_identity=True)
    if not resolution.get("ok"):
        out = _safe(resolution, state=resolution.get("state", "unknown"),
                    note=resolution.get("note", ""))
        out["ok"] = False
        return out
    status = _status_for_resolution(resolution, runner=runner, timeout=timeout)
    status["ok"] = status.get("authenticated") is True
    if status["ok"]:
        status.update({"path": resolution["path"],
                       "identity": resolution.get("identity", "")})
    return status


def verify_authenticated_identity(
        identity: str, *, path: str = "", which=None, runner=None,
        timeout: float = _STATUS_TIMEOUT, is_windows=None) -> dict:
    resolution = resolve_official_cli(
        which=which, is_windows=is_windows, content_identity=True)
    if not resolution.get("ok"):
        out = _safe(resolution, state=resolution.get("state", "unknown"),
                    note=resolution.get("note", ""))
        out["ok"] = False
        return out
    if resolution.get("identity") != identity or (path and resolution.get("path") != path):
        return {"ok": False, "state": "executable_changed",
                "authenticated": False, "cli_present": True,
                "executable": resolution.get("executable", ""),
                "note": "Claude Code executable changed before prompt execution"}
    status = _status_for_resolution(resolution, runner=runner, timeout=timeout)
    status["ok"] = status.get("authenticated") is True
    return status


def bind_authenticated_backend(backend, *, which=None, status_runner=None,
                               is_windows=None):
    auth = authenticated_resolution(
        which=which, runner=status_runner, is_windows=is_windows)
    if auth.get("ok") is not True:
        raise ValueError(status_label(auth))
    argv = list(getattr(backend, "argv", []))
    if not argv:
        raise ValueError("Claude Code command is empty")
    from .endpoints import CliBackend
    from .local_agent import BackendError

    class ClaudeCliCustodyBackend(CliBackend):
        def __init__(self, base):
            super().__init__(
                base.name, [auth["path"], *argv[1:]], base.model,
                base.runner, base.timeout)
            self._claude_identity = auth.get("identity", "")
            self._claude_path = auth["path"]

        def health(self) -> bool:
            return True

        def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
            check = verify_authenticated_identity(
                self._claude_identity, path=self._claude_path, which=which,
                runner=status_runner, is_windows=is_windows)
            if check.get("ok") is not True:
                raise BackendError(status_label(check))
            return super().chat(
                messages, system=system, max_tokens=max_tokens,
                temperature=temperature, seed=seed)

    return ClaudeCliCustodyBackend(backend)


def public_status() -> dict:
    return account_status()


def status_label(status: dict) -> str:
    state = status.get("state")
    if state == "authenticated":
        return "Claude Code account authenticated"
    if state == "not_authenticated":
        return "Claude Code account not signed in"
    if state == "cli_absent":
        return "Claude Code CLI absent"
    if state == "wrapper_unsupported":
        return "Claude Code wrapper unsupported"
    if state == "executable_changed":
        return "Claude Code executable changed before prompt execution"
    return "Claude Code account unknown"


def _launch_visible(argv):
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return subprocess.Popen(argv, **kwargs)


def begin_login(*, provider: str = "anthropic", which=None, launcher=None,
                is_windows=None) -> dict:
    """Start `claude auth login` after rechecking executable identity."""
    before = resolve_official_cli(
        which=which, is_windows=is_windows, content_identity=True)
    if not before.get("ok"):
        return {"ok": False, "provider": provider, "mode": "official-cli",
                "state": before.get("state", "unknown"),
                "error": status_label(before), "executable": before.get("executable", "")}
    after = resolve_official_cli(
        which=which, is_windows=is_windows, content_identity=True)
    if after.get("identity") != before.get("identity"):
        return {"ok": False, "provider": provider, "mode": "official-cli",
                "state": "executable_changed",
                "error": "Claude Code executable changed before sign-in started",
                "executable": after.get("executable", before.get("executable", ""))}
    launcher = launcher or _launch_visible
    try:
        launcher([after["path"], "auth", "login"])
    except Exception:
        return {"ok": False, "provider": provider, "mode": "official-cli",
                "state": "launch_failed",
                "error": "could not start Claude Code sign-in",
                "executable": after.get("executable", "")}
    return {"ok": True, "provider": provider, "mode": "official-cli",
            "state": "started", "launched": True,
            "executable": after.get("executable", ""),
            "note": "finish Claude Code sign-in, then return here and refresh"}
