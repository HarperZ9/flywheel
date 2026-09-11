"""Private worker protocol for one owned gateway agent process tree."""
from __future__ import annotations
from dataclasses import dataclass
import os, sys, threading, time
from pathlib import Path
from typing import Callable, Mapping, Protocol
from .cross_harness_process import OwnedProcess, ProcessLaunch, ProcessOutcome, start_owned_process
from .evidence_json import canonical_bytes, strict_load_json
from .gateway_operation import AuthorizedOperation, canonicalize_operation, materialize_agent_attachment, thaw_operation
from .gateway_operation_recovery import validate_operation_value
from .gateway_secret_boundary import validate_no_raw_secrets
from .gateway_worker_env import minimal_worker_env
_PRIVATE_SCHEMA = "flywheel.gateway-operation-worker/v2"
MAX_RESULT_BYTES = 250_000
@dataclass(frozen=True)
class WorkerOutcome:
    state: str; result: dict
class OperationProcessFactory(Protocol):
    def create(self, authorized: AuthorizedOperation, progress: Callable[[dict], None]) -> object: ...
def _launch(spec: ProcessLaunch) -> OwnedProcess:
    if spec.shell or not spec.suspended:
        raise OSError("owned launch is invalid")
    return start_owned_process(spec.argv, cwd=spec.cwd, stdin_bytes=spec.stdin_bytes, env=spec.env)
class GatewayWorker:
    control_class = "windows_job_v1"
    def __init__(self, owned, progress: Callable[[dict], None], secret_values: tuple[str, ...], projection_binding=None) -> None:
        self._owned, self._progress, self._secrets = owned, progress, secret_values
        self._outcome = self._terminal = None
        self._state_lock, self._poll_lock = threading.Lock(), threading.Lock(); self._seen, self._pending = b"", bytearray()
        self._terminal_before_cancel = False
        self._cancel_requested = self._invalid = False
        self._projection_binding = projection_binding
    def resume(self) -> bool: return self._owned.resume()
    def signal_tree(self) -> bool:
        with self._poll_lock:
            self._consume_current(); confirmed = self._owned.signal_tree()
            if not confirmed: return False
            final = self._owned.wait(0); self._consume_current(final)
            with self._state_lock:
                self._invalid = self._invalid or final is None or not self._capture_valid(final)
                self._terminal_before_cancel = self._terminal is not None and not self._invalid; self._cancel_requested = True
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
            self._validate_projection(row["event"], "running")
            validate_operation_value(row["event"], self._secrets); validate_no_raw_secrets(row["event"])
            if len(canonical_bytes(row["event"])) > MAX_RESULT_BYTES: raise ValueError
            self._progress(row["event"]); return
        if (set(row) != {"type", "state", "result"}
                or row.get("type") != "terminal"
                or row.get("state") not in {"completed", "cancelled", "failed"}
                or type(row.get("result")) is not dict):
            raise ValueError
        validate_operation_value(row["result"], self._secrets); validate_no_raw_secrets(row["result"])
        self._validate_projection(row["result"], row["state"])
        if len(canonical_bytes(row["result"])) > MAX_RESULT_BYTES: raise ValueError
        self._terminal = WorkerOutcome(row["state"], row["result"])
        self._terminal_before_cancel = not self._cancel_requested
    def _validate_projection(self, value, state):
        if self._projection_binding is not None:
            if state == "failed" and value == {"reason": "EXTERNAL_ACTION_FAILED"}: return
            from .gateway_agent_projection import validate_projection
            validate_projection(value, self._projection_binding)
            if value["state"] != state: raise ValueError
    def _capture_valid(self, outcome: ProcessOutcome) -> bool:
        try: validate_no_raw_secrets({"stderr": outcome.stderr})
        except Exception: return False
        return not (outcome.malformed_output or outcome.timed_out or any(secret and secret in outcome.stderr for secret in self._secrets))
    def _finish(self, outcome: ProcessOutcome) -> WorkerOutcome:
        if self._cancel_requested:
            return (self._terminal if self._terminal_before_cancel
                    else WorkerOutcome("cancelled", {"stopped": True}))
        if self._invalid or not self._capture_valid(outcome):
            return _failed()
        if self._terminal is not None and (outcome.returncode == 0
                or outcome.returncode == 1 and self._terminal.state == "failed"):
            return self._terminal
        return _failed()
class GatewayAgentProcessFactory:
    def __init__(self, *, repo_root: Path, run_root: Path,
                 state_root: Path | None = None,
                 launcher: Callable[[ProcessLaunch], object] = _launch) -> None:
        self.repo_root, self.run_root, self.state_root = (
            Path(repo_root), Path(run_root), Path(state_root) if state_root is not None else None)
        self.launcher = launcher
    def create(self, authorized: AuthorizedOperation, progress: Callable[[dict], None]) -> GatewayWorker:
        if authorized.action != "agent.run": raise ValueError(
            "gateway worker action is invalid")
        bindings = authorized.credential_bindings
        if type(bindings) is not dict:
            try:
                from .credential_handles import CredentialBindings
                bindings = (bindings.child_environment({}, platform="windows")
                    if isinstance(bindings, CredentialBindings) else dict(bindings or {}))
            except (TypeError, ValueError):
                raise ValueError("gateway worker credentials are invalid") from None
        from .source_context_worker import source_context_or_failed_worker
        source_context = source_context_or_failed_worker(authorized, self.state_root)
        if getattr(source_context, "control_class", None): return source_context
        from .gateway_agent_execution import trace_context
        if self.state_root is None:
            raise ValueError("private trace custody is unavailable")
        payload = {"schema": _PRIVATE_SCHEMA, "operation": thaw_operation(authorized.operation),
                   "credential_bindings": dict(bindings), "repo_root": str(self.repo_root),
                   "run_root": str(self.run_root), "source_context": source_context,
                   "trace_context": trace_context(authorized, self.state_root)}
        spec = ProcessLaunch(
            (sys.executable, "-m", "harness.gateway_operation_process", "worker"),
            self.repo_root, canonical_bytes(payload), minimal_worker_env(
                self.repo_root, run_root=self.run_root, state_root=self.state_root))
        from .gateway_agent_execution import trace_from_request
        return GatewayWorker(self.launcher(spec), progress, tuple(
            value for value in bindings.values() if type(value) is str and value),
            trace_from_request(payload["trace_context"]).binding)
def _commit_terminal(callback: Callable[[WorkerOutcome], None], outcome: WorkerOutcome) -> None:
    """Retry the same CAS outcome; never substitute a second terminal."""
    for _ in range(2):
        try:
            callback(outcome); return
        except Exception: pass
def supervise_operation(*, authorized: AuthorizedOperation, factory: OperationProcessFactory,
                        progress: Callable[[dict], None], started: Callable[[str], None],
                        registered: Callable[[object], None], terminal: Callable[[WorkerOutcome], None]) -> None:
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
def supervise_gateway_operation(service, authorized: AuthorizedOperation, operation_ref: str,
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
    supervise_operation(authorized=authorized, factory=factory,
        progress=lambda event: service._publish(owner, operation_ref, "progress", event),
        started=started, registered=registered,
        terminal=lambda outcome: service._terminal(owner, operation_ref, outcome))
def _failed() -> WorkerOutcome: return WorkerOutcome("failed", {"reason": "EXTERNAL_ACTION_FAILED"})
def _emit(value: dict) -> None:
    sys.stdout.buffer.write(canonical_bytes(value) + b"\n"); sys.stdout.buffer.flush()
def _worker_request() -> tuple[dict, dict, Path, Path, dict | None]:
    value = strict_load_json(sys.stdin.buffer.read(), max_bytes=1_048_576)
    if (set(value) != {"schema", "operation", "credential_bindings",
                       "repo_root", "run_root", "source_context", "trace_context"}
            or value["schema"] != _PRIVATE_SCHEMA):
        raise ValueError
    operation = canonicalize_operation("agent.run", value["operation"])
    bindings = value["credential_bindings"]
    if (type(bindings) is not dict
            or any(type(key) is not str or type(item) is not str
                   for key, item in bindings.items())
            or type(value["repo_root"]) is not str
            or type(value["run_root"]) is not str
            or not (value["source_context"] is None
                    or type(value["source_context"]) is dict)):
        raise ValueError
    return (thaw_operation(operation.operation), bindings, Path(value["repo_root"]), Path(value["run_root"]), value["source_context"], value["trace_context"])
class _SecretOutput(ValueError): pass
def _check_child_value(value: object, secrets: tuple[str, ...]) -> None:
    try:
        validate_no_raw_secrets(value); validate_operation_value(value, secrets); data = canonical_bytes(value)
    except Exception: raise _SecretOutput from None
    if any(secret.encode("utf-8") in data for secret in secrets if secret):
        raise _SecretOutput
def _run_agent(operation: dict, bindings: Mapping[str, str],
               repo_root: Path, run_root: Path, source_context=None, *, trace=None) -> dict:
    from .gateway_agent_execution import run_private_agent
    if trace is None:
        raise ValueError("private trace custody is unavailable")
    return run_private_agent(operation, dict(bindings), repo_root, trace, source_context, _emit)

def _main() -> int:
    trace = None
    try:
        request = _worker_request(); operation, bindings, repo_root, run_root = request[:4]
        source_context = request[4] if len(request) > 4 else None
        from .gateway_agent_execution import trace_from_request
        trace = trace_from_request(request[5], tuple(v for v in bindings.values() if v))
        result = _run_agent(materialize_agent_attachment(operation), bindings,
                            repo_root, run_root, source_context, trace=trace)
        secrets = tuple(value for value in bindings.values() if value)
        _check_child_value(result, secrets)
        _emit({"type": "terminal", "state": "completed", "result": result})
        return 0
    except Exception:
        result = {"reason": "EXTERNAL_ACTION_FAILED"}
        if trace is not None and trace.count:
            result = trace.projection("failed", reason="EXTERNAL_ACTION_FAILED")
        _emit({"type": "terminal", "state": "failed", "result": result})
        return 1
if __name__ == "__main__":
    raise SystemExit(_main() if sys.argv[1:] == ["worker"] else 2)
