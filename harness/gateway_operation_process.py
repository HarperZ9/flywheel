"""Private worker protocol for one owned gateway agent process tree."""
from __future__ import annotations
from dataclasses import dataclass
import os, sys, threading, time
from pathlib import Path
from typing import Callable, Mapping, Protocol
from .cross_harness_process import (
    OwnedProcess, ProcessLaunch, ProcessOutcome, start_owned_process)
from .evidence_json import canonical_bytes, strict_load_json
from .gateway_operation import (AuthorizedOperation, canonicalize_operation,
    materialize_agent_attachment, thaw_operation)
from .gateway_operation_recovery import validate_operation_value
from .gateway_secret_boundary import validate_no_raw_secrets
_PRIVATE_SCHEMA = "flywheel.gateway-operation-worker/v1"
MAX_RESULT_BYTES = 250_000
_ENV_KEYS = frozenset((
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP"))
@dataclass(frozen=True)
class WorkerOutcome:
    state: str; result: dict
class OperationProcessFactory(Protocol):
    def create(self, authorized: AuthorizedOperation, progress: Callable[[dict], None]) -> object: ...
def _minimal_env(repo_root: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() in _ENV_KEYS}
    return dict(env, PYTHONPATH=str(repo_root))
def _launch(spec: ProcessLaunch) -> OwnedProcess:
    if spec.shell or not spec.suspended:
        raise OSError("owned launch is invalid")
    return start_owned_process(spec.argv, cwd=spec.cwd, stdin_bytes=spec.stdin_bytes, env=spec.env)
class GatewayWorker:
    control_class = "windows_job_v1"
    def __init__(self, owned, progress: Callable[[dict], None], secret_values: tuple[str, ...]) -> None:
        self._owned, self._progress = owned, progress
        self._secrets, self._outcome = secret_values, None
        self._state_lock, self._poll_lock = threading.Lock(), threading.Lock()
        self._seen, self._pending = b"", bytearray()
        self._terminal: WorkerOutcome | None = None
        self._terminal_before_cancel = False
        self._cancel_requested = self._invalid = False
    def resume(self) -> bool: return self._owned.resume()
    def signal_tree(self) -> bool:
        with self._poll_lock:
            self._consume_current(); confirmed = self._owned.signal_tree()
            if not confirmed: return False
            final = self._owned.wait(0); self._consume_current(final)
            with self._state_lock:
                self._terminal_before_cancel = self._terminal is not None and not self._invalid
                self._cancel_requested = True
            if self._outcome is None and final is not None: self._outcome = self._finish(final)
        return confirmed
    def wait(self, timeout_s: float) -> WorkerOutcome | None:
        deadline, first = time.monotonic() + max(0, timeout_s), True
        while first or time.monotonic() < deadline:
            first = False
            if self._outcome is not None: return self._outcome
            remaining = max(0.0, deadline - time.monotonic())
            with self._poll_lock:
                if self._outcome is not None: return self._outcome
                raw = self._owned.wait(min(.05, remaining))
                self._consume_current(raw)
                if raw is not None:
                    self._outcome = self._finish(raw)
                    return self._outcome
            if remaining <= 0: break
        return None
    def close(self) -> None: self._owned.close()
    def _consume_current(self, final: ProcessOutcome | None = None) -> None:
        try:
            if final is not None:
                raw, overflow = final.stdout.encode("utf-8", "strict"), False
            else:
                reader = getattr(self._owned, "stdout_snapshot", None)
                if not callable(reader): return
                raw, overflow = reader()
            self._consume(raw, overflow, final is not None)
        except Exception:
            with self._state_lock: self._invalid = True
    def _consume(self, raw: bytes, overflow: bool, final: bool) -> None:
        with self._state_lock:
            invalid = (self._invalid or overflow or len(raw) > 1_048_576
                       or not raw.startswith(self._seen)
                       or any(secret.encode("utf-8") in raw
                              for secret in self._secrets if secret))
            if invalid:
                self._invalid = True; return
            self._pending.extend(raw[len(self._seen):]); self._seen = raw
            while b"\n" in self._pending:
                line, _, rest = self._pending.partition(b"\n")
                self._pending = bytearray(rest)
                self._accept_row(strict_load_json(bytes(line)))
            if final and self._pending:
                line, self._pending = bytes(self._pending), bytearray()
                self._accept_row(strict_load_json(line))
    def _accept_row(self, row: dict) -> None:
        if self._terminal is not None:
            raise ValueError
        if set(row) == {"type", "event"} and row.get("type") == "progress":
            if type(row["event"]) is not dict: raise ValueError
            validate_operation_value(row["event"], self._secrets); validate_no_raw_secrets(row["event"])
            if len(canonical_bytes(row["event"])) > MAX_RESULT_BYTES: raise ValueError
            self._progress(row["event"]); return
        if (set(row) != {"type", "state", "result"}
                or row.get("type") != "terminal"
                or row.get("state") not in {"completed", "cancelled", "failed"}
                or type(row.get("result")) is not dict):
            raise ValueError
        validate_operation_value(row["result"], self._secrets); validate_no_raw_secrets(row["result"])
        if len(canonical_bytes(row["result"])) > MAX_RESULT_BYTES: raise ValueError
        self._terminal = WorkerOutcome(row["state"], row["result"])
        self._terminal_before_cancel = not self._cancel_requested
    def _finish(self, outcome: ProcessOutcome) -> WorkerOutcome:
        if self._cancel_requested:
            return (self._terminal if self._terminal_before_cancel
                    else WorkerOutcome("cancelled", {"stopped": True}))
        try:
            validate_no_raw_secrets({"stderr": outcome.stderr})
        except Exception: self._invalid = True
        if (outcome.malformed_output or outcome.timed_out or self._invalid
                or any(secret and secret in outcome.stderr for secret in self._secrets)):
            return _failed()
        if outcome.returncode == 0 and self._terminal is not None: return self._terminal
        return _failed()
class GatewayAgentProcessFactory:
    def __init__(self, *, repo_root: Path, run_root: Path, launcher: Callable[[ProcessLaunch], object] = _launch) -> None:
        self.repo_root, self.run_root = Path(repo_root), Path(run_root)
        self.launcher = launcher
    def create(self, authorized: AuthorizedOperation, progress: Callable[[dict], None]) -> GatewayWorker:
        if authorized.action != "agent.run": raise ValueError(
            "gateway worker action is invalid")
        bindings = authorized.credential_bindings
        if type(bindings) is not dict:
            try:
                bindings = dict(bindings or {})
            except (TypeError, ValueError):
                raise ValueError("gateway worker credentials are invalid") from None
        payload = {"schema": _PRIVATE_SCHEMA, "operation": thaw_operation(authorized.operation),
                   "credential_bindings": dict(bindings), "repo_root": str(self.repo_root),
                   "run_root": str(self.run_root)}
        spec = ProcessLaunch(
            (sys.executable, "-m", "harness.gateway_operation_process", "worker"),
            self.repo_root, canonical_bytes(payload), _minimal_env(self.repo_root))
        return GatewayWorker(self.launcher(spec), progress, tuple(
            value for value in bindings.values() if type(value) is str and value))
def _commit_terminal(callback: Callable[[WorkerOutcome], None], outcome: WorkerOutcome) -> None:
    """Retry the same CAS outcome; never substitute a second terminal."""
    for _ in range(2):
        try:
            callback(outcome); return
        except Exception: pass
def supervise_operation(*, authorized: AuthorizedOperation,
                        factory: OperationProcessFactory,
                        progress: Callable[[dict], None],
                        started: Callable[[str], None],
                        registered: Callable[[object], None],
                        terminal: Callable[[WorkerOutcome], None]) -> None:
    """Create suspended, durably start, register, resume, then monitor."""
    worker = None
    try:
        worker = factory.create(authorized, progress)
        control = getattr(worker, "control_class", None)
        if control != "windows_job_v1": raise ValueError
        started(control); registered(worker)
        if not worker.resume(): raise ValueError
    except Exception:
        if worker is not None:
            try: worker.close()
            except Exception: pass
        _commit_terminal(terminal, WorkerOutcome(
            "failed", {"reason": "OWNERSHIP_UNAVAILABLE"}))
        return
    try:
        outcome = None
        while outcome is None: outcome = worker.wait(60.0)
        if not isinstance(outcome, WorkerOutcome): raise ValueError
    except Exception:
        try: worker.close()
        except Exception: pass
        outcome = WorkerOutcome("failed", {"reason": "OWNERSHIP_UNAVAILABLE"})
    _commit_terminal(terminal, outcome)
def supervise_gateway_operation(service, authorized: AuthorizedOperation,
                                operation_ref: str,
                                factory: OperationProcessFactory) -> None:
    """Bind generic process supervision to durable lifecycle callbacks."""
    from .gateway_operation import GatewayOperationError
    from .gateway_operation_recovery import history_state
    owner = authorized.owner_ref
    def started(control: str) -> None:
        journey = service._journey(owner)
        with journey._owner_operation_guard(operation_ref):
            history = service._history(journey, operation_ref,
                                       authorized.journey_ref)
            if history_state(history)[0] != "queued": raise GatewayOperationError(
                "INVALID_TRANSITION")
            head = journey.resume(authorized.journey_ref)["event_head_sha256"]
            journey._append_lifecycle(
                journey_ref=authorized.journey_ref, expected_event_head=head,
                client_request_id=f"{operation_ref}:started",
                operation="operation_started", payload={
                    "operation_ref": operation_ref,
                    "queued_event_sha256": history[0]["event_sha256"],
                    "control_class": control})
    def registered(handle: object) -> None:
        service._handles[(owner, operation_ref)] = handle
        snapshot = service.snapshot(owner, operation_ref)
        service._publish(owner, operation_ref, "snapshot", snapshot.as_json())
    supervise_operation(
        authorized=authorized, factory=factory,
        progress=lambda event: service._publish(
            owner, operation_ref, "progress", event),
        started=started, registered=registered,
        terminal=lambda outcome: service._terminal(owner, operation_ref, outcome))
def _failed() -> WorkerOutcome: return WorkerOutcome("failed", {"reason": "EXTERNAL_ACTION_FAILED"})
def _emit(value: dict) -> None:
    sys.stdout.buffer.write(canonical_bytes(value) + b"\n"); sys.stdout.buffer.flush()
def _worker_request() -> tuple[dict, dict, Path, Path]:
    value = strict_load_json(sys.stdin.buffer.read(), max_bytes=1_048_576)
    if (set(value) != {"schema", "operation", "credential_bindings",
                       "repo_root", "run_root"}
            or value["schema"] != _PRIVATE_SCHEMA):
        raise ValueError
    operation = canonicalize_operation("agent.run", value["operation"])
    bindings = value["credential_bindings"]
    if (type(bindings) is not dict
            or any(type(key) is not str or type(item) is not str
                   for key, item in bindings.items())
            or type(value["repo_root"]) is not str
            or type(value["run_root"]) is not str):
        raise ValueError
    return (thaw_operation(operation.operation), bindings,
            Path(value["repo_root"]), Path(value["run_root"]))
class _SecretOutput(ValueError): pass
def _check_child_value(value: object, secrets: tuple[str, ...]) -> None:
    try:
        validate_no_raw_secrets(value); validate_operation_value(value, secrets); data = canonical_bytes(value)
    except Exception: raise _SecretOutput from None
    if any(secret.encode("utf-8") in data for secret in secrets if secret):
        raise _SecretOutput
def _persist_failed_run(run_root: Path, goal: str, endpoint: str,
                        events: list[dict], secrets: tuple[str, ...]) -> None:
    from .eval_store import save_agent_run, trim_events
    value = {"status": "FAILED", "goal_excerpt": goal[:200],
             "endpoint": endpoint, "events": trim_events(events),
             "failure": {"code": "EXTERNAL_ACTION_FAILED"}}
    _check_child_value(value, secrets)
    try: save_agent_run(run_root, value)
    except Exception: pass
def _run_agent(operation: dict, bindings: Mapping[str, str],
               repo_root: Path, run_root: Path) -> dict:
    from .gateway import _countersign_run, _resolve_workspace_root
    from .router_agent import run_router_agent
    from .scaffold import scaffold_answer, scaffold_turn
    goal, endpoint = operation["goal"], operation["endpoint"]
    root, error = _resolve_workspace_root(operation.get("root"), repo_root)
    if error: raise ValueError
    events: list[dict] = []
    secrets = tuple(value for value in bindings.values() if value)
    def progress(event: dict) -> None:
        events.append(event); _check_child_value(events, secrets)
        if type(event) is not dict or len(canonical_bytes(event)) > MAX_RESULT_BYTES: events.append(_SecretOutput()); raise ValueError
        _emit({"type": "progress", "event": event})
    try:
        result = run_router_agent(
            goal, endpoint, root=str(root), allow_write=operation["allow_write"],
            allow_exec=operation["allow_exec"], max_steps=operation["max_steps"],
            test_cmd=operation.get("test_cmd"),
            credential_bindings=dict(bindings), on_event=progress)
        _check_child_value(events, secrets); _check_child_value(result, secrets)
        if len(canonical_bytes(result)) > MAX_RESULT_BYTES: raise ValueError
        result["scaffold"] = scaffold_answer(
            str(result.get("final") or ""), scaffold_turn(goal),
            provenance={"endpoint": endpoint, "model_ref": endpoint})
        _check_child_value(result, secrets)
        result["run_receipt"] = _countersign_run(result)
        _check_child_value(result, secrets)
    except _SecretOutput: raise
    except Exception:
        _persist_failed_run(run_root, goal, endpoint, events, secrets)
        raise
    try:
        from .eval_store import save_agent_run, trim_events
        stored = dict(result, goal_excerpt=goal[:200], events=trim_events(events))
        _check_child_value(stored, secrets)
        result["run_id"] = save_agent_run(run_root, stored)["run_id"]
    except Exception: result["receipt_note"] = "authorized external action failed"
    return result
def _main() -> int:
    try:
        operation, bindings, repo_root, run_root = _worker_request()
        result = _run_agent(materialize_agent_attachment(operation), bindings,
                            repo_root, run_root)
        secrets = tuple(value for value in bindings.values() if value)
        _check_child_value(result, secrets)
        _emit({"type": "terminal", "state": "completed", "result": result})
        return 0
    except Exception:
        _emit({"type": "terminal", "state": "failed",
               "result": {"reason": "EXTERNAL_ACTION_FAILED"}})
        return 1
if __name__ == "__main__":
    raise SystemExit(_main() if sys.argv[1:] == ["worker"] else 2)
