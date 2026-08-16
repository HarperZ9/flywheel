"""Private worker protocol for one owned gateway agent process tree."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import threading
from typing import Callable, Mapping, Protocol

from .cross_harness_process import (
    OwnedProcess, ProcessLaunch, ProcessOutcome, start_owned_process,
)
from .evidence_json import canonical_bytes, strict_load_json
from .gateway_operation import (
    AuthorizedOperation, canonicalize_operation, materialize_agent_attachment,
    thaw_operation,
)
from .gateway_secret_boundary import validate_no_raw_secrets

_PRIVATE_SCHEMA = "flywheel.gateway-operation-worker/v1"
_ENV_KEYS = frozenset((
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP",
))


@dataclass(frozen=True)
class WorkerOutcome:
    state: str
    result: dict


class OperationProcess(Protocol):
    control_class: str
    def resume(self) -> bool: ...
    def signal_tree(self) -> bool: ...
    def wait(self, timeout_s: float) -> WorkerOutcome | None: ...
    def close(self) -> None: ...


class OperationProcessFactory(Protocol):
    def create(self, authorized: AuthorizedOperation,
               progress: Callable[[dict], None]) -> OperationProcess: ...


def _minimal_env(repo_root: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if key.upper() in _ENV_KEYS}
    env["PYTHONPATH"] = str(repo_root)
    return env


def _launch(spec: ProcessLaunch) -> OwnedProcess:
    if spec.shell or not spec.suspended:
        raise OSError("owned launch is invalid")
    return start_owned_process(spec.argv, cwd=spec.cwd,
                               stdin_bytes=spec.stdin_bytes, env=spec.env)


class GatewayWorker:
    control_class = "windows_job_v1"

    def __init__(self, owned, progress: Callable[[dict], None],
                 secret_values: tuple[str, ...]) -> None:
        self._owned, self._progress = owned, progress
        self._secrets, self._outcome = secret_values, None
        self._wait_lock = threading.Lock()

    def resume(self) -> bool:
        return self._owned.resume()

    def signal_tree(self) -> bool:
        return self._owned.signal_tree()

    def wait(self, timeout_s: float) -> WorkerOutcome | None:
        with self._wait_lock:
            if self._outcome is not None:
                return self._outcome
            raw = self._owned.wait(timeout_s)
            if raw is None:
                return None
            self._outcome = self._decode(raw)
            return self._outcome

    def close(self) -> None:
        self._owned.close()

    def _decode(self, outcome: ProcessOutcome) -> WorkerOutcome:
        if (outcome.malformed_output or outcome.timed_out
                or any(secret and secret in outcome.stdout + outcome.stderr
                       for secret in self._secrets)):
            return _failed()
        try:
            rows = [strict_load_json(line) for line in outcome.stdout.splitlines()
                    if line]
            if outcome.returncode != 0 or not rows:
                raise ValueError
            terminals = [row for row in rows if row.get("type") == "terminal"]
            progress = [row for row in rows if row.get("type") == "progress"]
            if (len(terminals) != 1 or rows[-1] is not terminals[0]
                    or any(set(row) != {"type", "event"} for row in progress)):
                raise ValueError
            for row in progress:
                validate_no_raw_secrets(row["event"])
                self._progress(row["event"])
            terminal = terminals[0]
            if (set(terminal) != {"type", "state", "result"}
                    or terminal["state"] not in {"completed", "cancelled", "failed"}
                    or type(terminal["result"]) is not dict):
                raise ValueError
            validate_no_raw_secrets(terminal["result"])
            if len(canonical_bytes(terminal["result"])) > 1_048_576:
                raise ValueError
            return WorkerOutcome(terminal["state"], terminal["result"])
        except Exception:
            return _failed()


class GatewayAgentProcessFactory:
    def __init__(self, *, repo_root: Path, run_root: Path,
                 launcher: Callable[[ProcessLaunch], object] = _launch) -> None:
        self.repo_root, self.run_root = Path(repo_root), Path(run_root)
        self.launcher = launcher

    def create(self, authorized: AuthorizedOperation,
               progress: Callable[[dict], None]) -> GatewayWorker:
        if authorized.action != "agent.run":
            raise ValueError("gateway worker action is invalid")
        bindings = authorized.credential_bindings
        if type(bindings) is not dict:
            try:
                bindings = dict(bindings or {})
            except (TypeError, ValueError):
                raise ValueError("gateway worker credentials are invalid") from None
        payload = {
            "schema": _PRIVATE_SCHEMA,
            "operation": thaw_operation(authorized.operation),
            "credential_bindings": dict(bindings),
            "repo_root": str(self.repo_root), "run_root": str(self.run_root),
        }
        spec = ProcessLaunch(
            (sys.executable, "-m", "harness.gateway_operation_process", "worker"),
            self.repo_root, canonical_bytes(payload), _minimal_env(self.repo_root),
        )
        owned = self.launcher(spec)
        return GatewayWorker(owned, progress,
                             tuple(value for value in bindings.values()
                                   if type(value) is str and value))


def supervise_operation(*, authorized: AuthorizedOperation,
                        factory: OperationProcessFactory,
                        progress: Callable[[dict], None],
                        started: Callable[[str], None],
                        registered: Callable[[OperationProcess], None],
                        terminal: Callable[[WorkerOutcome], None]) -> None:
    """Create suspended, durably start, register, resume, then monitor."""
    worker = None
    try:
        worker = factory.create(authorized, progress)
        control = getattr(worker, "control_class", None)
        if control != "windows_job_v1":
            raise ValueError
        started(control)
        registered(worker)
        if not worker.resume():
            raise ValueError
        outcome = None
        while outcome is None:
            outcome = worker.wait(60.0)
        if not isinstance(outcome, WorkerOutcome):
            raise ValueError
        terminal(outcome)
    except Exception:
        if worker is not None:
            try:
                worker.close()
            except Exception:
                pass
        terminal(WorkerOutcome(
            "failed", {"reason": "OWNERSHIP_UNAVAILABLE"}))


def supervise_gateway_operation(service, authorized: AuthorizedOperation,
                                operation_ref: str,
                                factory: OperationProcessFactory) -> None:
    """Bind generic process supervision to durable gateway lifecycle callbacks."""
    from .gateway_operation import GatewayOperationError
    from .gateway_operation_recovery import history_state
    owner = authorized.owner_ref

    def started(control: str) -> None:
        journey = service._journey(owner)
        with journey._owner_operation_guard(operation_ref):
            history = service._history(
                journey, operation_ref, authorized.journey_ref)
            if history_state(history)[0] != "queued":
                raise GatewayOperationError("INVALID_TRANSITION")
            head = journey.resume(authorized.journey_ref)["event_head_sha256"]
            journey._append_lifecycle(
                journey_ref=authorized.journey_ref,
                expected_event_head=head,
                client_request_id=f"{operation_ref}:started",
                operation="operation_started", payload={
                    "operation_ref": operation_ref,
                    "queued_event_sha256": history[0]["event_sha256"],
                    "control_class": control})

    def registered(handle: OperationProcess) -> None:
        service._handles[(owner, operation_ref)] = handle
        snapshot = service.snapshot(owner, operation_ref)
        service._publish(owner, operation_ref, "snapshot", snapshot.as_json())

    supervise_operation(
        authorized=authorized, factory=factory,
        progress=lambda event: service._publish(
            owner, operation_ref, "progress", event),
        started=started, registered=registered,
        terminal=lambda outcome: service._terminal(owner, operation_ref, outcome))


def _failed() -> WorkerOutcome:
    return WorkerOutcome("failed", {"reason": "EXTERNAL_ACTION_FAILED"})


def _emit(value: dict) -> None:
    sys.stdout.buffer.write(canonical_bytes(value) + b"\n")
    sys.stdout.buffer.flush()


def _worker_request() -> tuple[dict, dict, Path, Path]:
    value = strict_load_json(sys.stdin.buffer.read(), max_bytes=1_048_576)
    if set(value) != {"schema", "operation", "credential_bindings",
                      "repo_root", "run_root"} or value["schema"] != _PRIVATE_SCHEMA:
        raise ValueError
    operation = canonicalize_operation("agent.run", value["operation"])
    bindings = value["credential_bindings"]
    if (type(bindings) is not dict
            or any(type(key) is not str or type(item) is not str
                   for key, item in bindings.items())
            or type(value["repo_root"]) is not str
            or type(value["run_root"]) is not str):
        raise ValueError
    return thaw_operation(operation.operation), bindings, Path(
        value["repo_root"]), Path(value["run_root"])


def _run_agent(operation: dict, bindings: Mapping[str, str],
               repo_root: Path, run_root: Path) -> dict:
    from .gateway import _countersign_run, _resolve_workspace_root
    from .router_agent import run_router_agent
    from .scaffold import scaffold_answer, scaffold_turn
    goal, endpoint = operation["goal"], operation["endpoint"]
    root, error = _resolve_workspace_root(operation.get("root"), repo_root)
    if error:
        raise ValueError
    events: list[dict] = []
    result = run_router_agent(
        goal, endpoint, root=str(root),
        allow_write=operation["allow_write"],
        allow_exec=operation["allow_exec"], max_steps=operation["max_steps"],
        test_cmd=operation.get("test_cmd"), credential_bindings=dict(bindings),
        on_event=lambda event: (events.append(event), _emit({
            "type": "progress", "event": event})),
    )
    result["scaffold"] = scaffold_answer(
        str(result.get("final") or ""), scaffold_turn(goal),
        provenance={"endpoint": endpoint, "model_ref": endpoint})
    result["run_receipt"] = _countersign_run(result)
    try:
        from .eval_store import save_agent_run, trim_events
        result["run_id"] = save_agent_run(
            run_root, dict(result, goal_excerpt=goal[:200],
                           events=trim_events(events)))["run_id"]
    except Exception:
        result["receipt_note"] = "authorized external action failed"
    return result


def _main() -> int:
    try:
        operation, bindings, repo_root, run_root = _worker_request()
        result = _run_agent(materialize_agent_attachment(operation), bindings,
                            repo_root, run_root)
        _emit({"type": "terminal", "state": "completed", "result": result})
        return 0
    except Exception:
        _emit({"type": "terminal", "state": "failed",
               "result": {"reason": "EXTERNAL_ACTION_FAILED"}})
        return 1


if __name__ == "__main__":
    raise SystemExit(_main() if sys.argv[1:] == ["worker"] else 2)
