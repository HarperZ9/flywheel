"""CLI identity fields for attempt receipts: version, resolved path, effort.

Every attempt receipt records which CLI binary actually ran: its version
string, the absolute path invoked, and the effective reasoning-effort
setting. Values are observed or empty; nothing here fabricates a value.
The future ClaudeCodeAdapter fills the same three fields through the same
helpers, and validate_executable_path is the shared check that a resolved
path is a real native binary rather than a shim script on PATH.
"""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Callable

from .cross_harness_process import run_process

REASONING_EFFORT_UNSPECIFIED = "unspecified"
_EXECUTABLE_MAGIC = (b"MZ", b"\x7fELF")
# Shim scripts on PATH re-enter a wrapper instead of the harness under test.
# The magic-byte check in validate_executable_path is the real gate; this
# suffix list keeps a resolver from picking a shim when a binary sits beside it.
_SHIM_SUFFIXES = (".ps1", ".cmd", ".bat")
_VERSION_TIMEOUT_SECONDS = 30.0
_version_cache: dict[str, str] = {}


def resolve_binary(candidates: tuple[str, ...]) -> str:
    """First candidate on PATH that is not a shim script, else "".

    Every CLI adapter resolves through here, so one rule covers all of them:
    name the native binary first, and never accept a wrapper that happens to
    sit earlier on PATH. Returning "" is a real answer, and the caller records
    an unavailable arm rather than measuring something else.
    """
    for name in candidates:
        found = shutil.which(name)
        if found and not found.lower().endswith(_SHIM_SUFFIXES): return found
    return ""


def codex_cli_version(executable: str, *, runner: Callable = run_process) -> str:
    """Capture the CLI version with one local ``--version`` invocation.

    Memoized per executable path so adapter init pays the subprocess cost
    once per interpreter. Returns "" whenever a version cannot be observed
    honestly: empty path, path is not an existing file (no subprocess is
    spawned, which keeps fake resolver paths in tests inert), probe failure,
    timeout, or empty stdout. "" is recorded verbatim, never replaced.
    """
    if not executable: return ""
    if executable in _version_cache: return _version_cache[executable]
    path, version = Path(executable), ""
    if path.is_file():
        try:
            outcome = runner([executable, "--version"], cwd=path.parent, stdin_text="", timeout_seconds=_VERSION_TIMEOUT_SECONDS)
            lines = outcome.stdout.strip().splitlines()
            if outcome.returncode == 0 and not outcome.timed_out and lines: version = lines[0].strip()
        except OSError: version = ""
    _version_cache[executable] = version
    return version


def cli_identity_fields(version: str, resolved_binary_path: str,
                        reasoning_effort: str = REASONING_EFFORT_UNSPECIFIED) -> dict[str, str]:
    """The three CLI identity fields every attempt receipt carries.

    reasoning_effort defaults to "unspecified": the codex adapters set no
    effort flag and cannot observe an effective value, so recording anything
    else would be fabrication. An adapter that does control effort passes
    the effective setting explicitly.
    """
    return {"cli_version": str(version), "resolved_binary_path": str(resolved_binary_path),
            "reasoning_effort": str(reasoning_effort)}


def validate_executable_path(path: str) -> str:
    """Return "" when path names a real executable binary, else a refusal.

    The file must exist at an absolute path and start with a native
    executable magic (PE "MZ" or ELF). A shim script is a text file, so it
    fails the magic check; that matters for claude, where plain ``claude``
    on PATH resolves to a contaminating wrapper rather than the binary.
    """
    if not path: return "EXECUTABLE_PATH_EMPTY: no resolved binary path"
    candidate = Path(path)
    if not candidate.is_absolute(): return f"EXECUTABLE_PATH_NOT_ABSOLUTE: {path}"
    if not candidate.is_file(): return f"EXECUTABLE_PATH_MISSING: {path}"
    try:
        with candidate.open("rb") as handle: head = handle.read(4)
    except OSError as exc: return f"EXECUTABLE_PATH_UNREADABLE: {path}: {type(exc).__name__}"
    if not any(head.startswith(magic) for magic in _EXECUTABLE_MAGIC):
        return f"EXECUTABLE_PATH_NOT_BINARY: {path} lacks a native executable magic; shim scripts are text"
    return ""
