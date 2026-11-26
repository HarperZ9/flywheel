"""Pluggable deterministic and local-safe workstation backends with rollback snapshots."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .operator_policy import (
    AuthorityGrant,
    OperatorAction,
    WorkstationObservation,
    build_observation,
    normalize_virtual_path,
    path_within_roots,
    sha256_prefixed,
)


@dataclass(frozen=True)
class RollbackSnapshot:
    """Bit-exact pre-mutation state captured so failed writes can be undone cleanly."""

    target: str
    existed: bool
    content_bytes: bytes | None
    sha256: str | None


class WorkstationBackend(Protocol):
    """Protocol implemented by both SimulatedWorkstationBackend and LocalSafeBackend."""

    def observe(self, targets: tuple[str, ...] = ()) -> WorkstationObservation: ...

    def snapshot_target(self, target: str) -> RollbackSnapshot | None: ...

    def restore_snapshot(self, snapshot: RollbackSnapshot) -> bool: ...

    def execute(self, action: OperatorAction) -> dict[str, Any]: ...


class SimulatedWorkstationBackend:
    """Deterministic in-memory workstation backend for CI, replay, and planted controls."""

    def __init__(
        self,
        *,
        cwd: str = "/workspace",
        initial_files: dict[str, bytes | str] | None = None,
        processes: list[dict[str, Any]] | None = None,
        active_surface: dict[str, Any] | None = None,
        command_handlers: dict[str, Callable[[list[str], dict[str, bytes]], dict[str, Any]]] | None = None,
        mcp_handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
        fault_injector: Callable[[OperatorAction, dict[str, bytes]], None] | None = None,
    ) -> None:
        self.cwd = normalize_virtual_path(cwd)
        self.files: dict[str, bytes] = {}
        for path, raw in (initial_files or {}).items():
            data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
            self.files[normalize_virtual_path(path)] = data
        self.processes: list[dict[str, Any]] = [dict(p) for p in (processes or [{"pid": 100, "name": "workstation-shell", "status": "running"}])]
        self.active_surface: dict[str, Any] = dict(active_surface or {"window": "editor", "title": "workspace"})
        self._cmd_handlers = dict(command_handlers or {})
        self._mcp_handlers = dict(mcp_handlers or {})
        self._fault_injector = fault_injector

    def observe(self, targets: tuple[str, ...] = ()) -> WorkstationObservation:
        keys = [normalize_virtual_path(t) for t in targets] if targets else sorted(self.files)
        digests = {k: (sha256_prefixed(self.files[k]) if k in self.files else "missing") for k in keys}
        return build_observation(
            cwd=self.cwd,
            processes=self.processes,
            file_digests=digests,
            active_surface=self.active_surface,
        )

    def snapshot_target(self, target: str) -> RollbackSnapshot | None:
        norm = normalize_virtual_path(target)
        if not norm:
            return None
        if norm in self.files:
            raw = self.files[norm]
            return RollbackSnapshot(target=norm, existed=True, content_bytes=raw, sha256=sha256_prefixed(raw))
        return RollbackSnapshot(target=norm, existed=False, content_bytes=None, sha256=None)

    def restore_snapshot(self, snapshot: RollbackSnapshot) -> bool:
        norm = normalize_virtual_path(snapshot.target)
        if snapshot.existed and snapshot.content_bytes is not None:
            self.files[norm] = snapshot.content_bytes
            return True
        self.files.pop(norm, None)
        return True

    def execute(self, action: OperatorAction) -> dict[str, Any]:
        if action.verb == "read_file":
            return self._exec_read(action)
        if action.verb == "write_file":
            return self._exec_write(action)
        if action.verb == "run_command":
            return self._exec_command(action)
        if action.verb == "mcp_call":
            return self._exec_mcp(action)
        if action.verb == "ui_action":
            return self._exec_ui(action)
        raise ValueError(f"unsupported verb: {action.verb}")

    def _exec_read(self, action: OperatorAction) -> dict[str, Any]:
        norm = normalize_virtual_path(action.target)
        if norm not in self.files:
            return {"ok": False, "error": f"file not found: {norm}"}
        raw = self.files[norm]
        return {"ok": True, "bytes": len(raw), "sha256": sha256_prefixed(raw), "text": raw.decode("utf-8", errors="replace")}

    def _exec_write(self, action: OperatorAction) -> dict[str, Any]:
        norm = normalize_virtual_path(action.target)
        raw = action.params.get("content", "")
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        self.files[norm] = data
        if self._fault_injector is not None:
            self._fault_injector(action, self.files)
        actual = self.files[norm]
        return {"ok": True, "bytes": len(actual), "sha256": sha256_prefixed(actual)}

    def _exec_command(self, action: OperatorAction) -> dict[str, Any]:
        argv = [str(a) for a in action.params.get("argv", [])]
        prog = argv[0] if argv else ""
        if prog in self._cmd_handlers:
            return dict(self._cmd_handlers[prog](argv, self.files))
        return {"ok": True, "exit_code": 0, "stdout": f"simulated:{' '.join(argv)}", "stderr": ""}

    def _exec_mcp(self, action: OperatorAction) -> dict[str, Any]:
        if action.target in self._mcp_handlers:
            return dict(self._mcp_handlers[action.target](dict(action.params)))
        return {"ok": True, "tool": action.target, "status": "completed"}

    def _exec_ui(self, action: OperatorAction) -> dict[str, Any]:
        title = str(action.params.get("set_title", self.active_surface.get("title", "")))
        window = str(action.params.get("window", action.target or self.active_surface.get("window", "")))
        self.active_surface = {**self.active_surface, "window": window, "title": title, "last_action": str(action.params.get("action", "focus"))}
        return {"ok": True, "active_surface": dict(self.active_surface)}


class LocalSafeBackend:
    """Real filesystem and allowlisted-command backend strictly bounded by AuthorityGrant."""

    def __init__(self, cwd: str | Path, grant: AuthorityGrant, *, timeout_seconds: float = 15.0) -> None:
        self.cwd = Path(cwd).resolve()
        self.grant = grant
        self._roots = grant.normalized_roots()
        self.timeout_seconds = float(timeout_seconds)
        self.active_surface: dict[str, Any] = {"mode": "local-safe", "root": normalize_virtual_path(str(self.cwd))}

    def _resolve_in_scope(self, target: str) -> Path:
        candidate = Path(target)
        resolved = candidate.resolve() if candidate.is_absolute() else (self.cwd / candidate).resolve()
        if not path_within_roots(str(resolved), self._roots):
            raise PermissionError(f"local-safe refused path outside allowed_roots: {resolved}")
        return resolved

    def observe(self, targets: tuple[str, ...] = ()) -> WorkstationObservation:
        digests: dict[str, str] = {}
        for raw in targets:
            resolved = self._resolve_in_scope(raw)
            key = normalize_virtual_path(str(resolved))
            digests[key] = sha256_prefixed(resolved.read_bytes()) if resolved.is_file() else "missing"
        return build_observation(
            cwd=str(self.cwd),
            processes=[{"pid": 0, "name": "local-safe-operator", "status": "bounded"}],
            file_digests=digests,
            active_surface=self.active_surface,
        )

    def snapshot_target(self, target: str) -> RollbackSnapshot | None:
        if not target:
            return None
        resolved = self._resolve_in_scope(target)
        key = normalize_virtual_path(str(resolved))
        if resolved.is_file():
            raw = resolved.read_bytes()
            return RollbackSnapshot(target=key, existed=True, content_bytes=raw, sha256=sha256_prefixed(raw))
        return RollbackSnapshot(target=key, existed=False, content_bytes=None, sha256=None)

    def restore_snapshot(self, snapshot: RollbackSnapshot) -> bool:
        resolved = self._resolve_in_scope(snapshot.target)
        if snapshot.existed and snapshot.content_bytes is not None:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(snapshot.content_bytes)
            return True
        if resolved.is_file():
            resolved.unlink()
        return True

    def execute(self, action: OperatorAction) -> dict[str, Any]:
        if action.verb == "read_file":
            path = self._resolve_in_scope(action.target)
            raw = path.read_bytes()
            return {"ok": True, "bytes": len(raw), "sha256": sha256_prefixed(raw), "text": raw.decode("utf-8", errors="replace")}
        if action.verb == "write_file":
            path = self._resolve_in_scope(action.target)
            raw = action.params.get("content", "")
            data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return {"ok": True, "bytes": len(data), "sha256": sha256_prefixed(data)}
        if action.verb == "run_command":
            return self._exec_safe_command(action)
        raise PermissionError(f"local-safe backend does not execute unbridged verb: {action.verb}")

    def _exec_safe_command(self, action: OperatorAction) -> dict[str, Any]:
        argv = [str(x) for x in action.params.get("argv", [])]
        if not argv or (self.grant.allowed_commands and argv[0] not in self.grant.allowed_commands):
            raise PermissionError(f"command not allowlisted: {argv}")
        run_cwd = self._resolve_in_scope(action.target) if action.target else self.cwd
        proc = subprocess.run(argv, cwd=str(run_cwd), capture_output=True, text=True, shell=False, timeout=self.timeout_seconds)
        return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
