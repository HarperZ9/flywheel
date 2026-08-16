"""Durable lifecycle and one-use cancellation for gateway agent operations."""
from __future__ import annotations
from contextlib import nullcontext
from dataclasses import dataclass
import os, threading, time
from pathlib import Path
from typing import Callable, Iterator
from .evidence_json import canonical_bytes, canonical_sha256
from .gateway_envelope import parse_gateway_envelope
from .gateway_operation import AuthorizedOperation, GatewayOperationError, OPERATION_REF_PATTERN
from .gateway_operation_process import MAX_RESULT_BYTES, OperationProcessFactory, WorkerOutcome
from .journey_service import JourneyService
from .journey_store import JourneyStore, JourneyStoreError
from .operation_grants import GrantStore, _secure_owner_only
from .gateway_operation_recovery import (LIFECYCLE, history_state, normalize_outcome,
    seal_outcome, started_event, validate_history,
    validate_operation_value, validate_result)
from .gateway_operation_route import (OperationEventBus, authorization_sha256,
    operation_ref_for, queued_payload, replay_authorization_sha256)
SNAPSHOT_SCHEMA = "flywheel.gateway-operation-snapshot/v1"
RESULT_SCHEMA = "flywheel.gateway-operation-result/v1"
TERMINALS = frozenset(("completed", "failed", "cancelled"))
@dataclass(frozen=True)
class OperationSnapshot:
    operation_ref: str; journey_ref: str; event_head_sha256: str
    state: str; can_cancel: bool
    terminal_event_ref: str | None = None
    result_sha256: str | None = None
    def as_json(self) -> dict:
        return {
            "schema": SNAPSHOT_SCHEMA, "operation_ref": self.operation_ref,
            "journey_ref": self.journey_ref,
            "event_head_sha256": self.event_head_sha256, "state": self.state,
            "can_cancel": self.can_cancel,
            "terminal_event_ref": self.terminal_event_ref,
            "result_sha256": self.result_sha256,
        }
class GatewayOperations:
    """One gateway-lifetime registry over durable Journey operation events."""
    def __init__(self, state_root: Path, *, clock: Callable[[], str],
                 authorizer=None, credential_resolver=None) -> None:
        self.state_root, self.clock = Path(state_root), clock
        if authorizer is None:
            from .gateway_grant_route import authorize_gateway_operation
            authorizer = authorize_gateway_operation
        if credential_resolver is None:
            from .gateway_provider_adapter import resolve_credentials
            credential_resolver = resolve_credentials
        self.authorizer, self.credential_resolver = authorizer, credential_resolver
        self._handles: dict[tuple[str, str], object] = {}
        self._secrets: dict[tuple[str, str], tuple[str, ...]] = {}
        self.events = OperationEventBus()
        self.terminal_states = TERMINALS
    def start(self, authorized: AuthorizedOperation,
              process_factory: OperationProcessFactory, *,
              already_guarded: bool = False) -> OperationSnapshot:
        ref = operation_ref_for(authorized.owner_ref, authorized.journey_ref,
                                authorized.client_request_id)
        payload = queued_payload(authorized)
        journey = self._journey(authorized.owner_ref)
        guard = (nullcontext() if already_guarded else
                 journey._owner_operation_guard(ref))
        with guard:
            history = self._history(journey, ref, authorized.journey_ref)
            if history:
                if history[0]["payload"] != payload:
                    raise GatewayOperationError("IDEMPOTENCY_MISMATCH")
                return self._snapshot(journey, ref, history)
            current = journey.resume(authorized.journey_ref)["event_head_sha256"]
            if current != authorized.expected_event_head:
                raise GatewayOperationError("HEAD_CONFLICT")
            ack = journey._append_lifecycle(
                journey_ref=authorized.journey_ref, expected_event_head=current,
                client_request_id=authorized.client_request_id,
                operation="operation_queued", payload=payload)
            queued = OperationSnapshot(ref, authorized.journey_ref,
                                       ack.event_head_sha256, "queued", False)
            self._secrets[(authorized.owner_ref, ref)] = tuple(
                value for value in authorized.credential_bindings.values() if type(value) is str and value)
        self._publish(authorized.owner_ref, ref, "snapshot", queued.as_json())
        threading.Thread(target=self._control,
                         args=(authorized, ref, process_factory), daemon=True).start()
        return queued
    def cancel(self, *, action: str, raw: bytes, owner_ref: str) -> OperationSnapshot:
        envelope = parse_gateway_envelope(action, raw); ref = envelope.operation.operation["operation_ref"]
        journey = self._journey(owner_ref)
        with journey._owner_operation_guard(ref):
            history = self._history(journey, ref)
            if not history: raise GatewayOperationError("CANCEL_UNAVAILABLE")
            snapshot = self._snapshot(journey, ref, history)
            if snapshot.state in TERMINALS: return snapshot
            prior = next((e for e in history if e["event_type"] == "cancel_requested"), None)
            if prior is not None:
                if (prior["payload"]["client_request_id"]
                        != envelope.client_request_id
                        or prior["payload"]["timeout_ms"]
                        != envelope.operation.operation["timeout_ms"]
                        or prior["journey_ref"] != envelope.journey_ref
                        or prior["prior_event_sha256"]
                        != envelope.expected_event_head):
                    raise GatewayOperationError("IDEMPOTENCY_MISMATCH")
                if (getattr(self.authorizer, "__module__", "")
                        == "harness.gateway_grant_route"
                        and prior["payload"]["authorization_sha256"] !=
                        replay_authorization_sha256(
                            envelope, owner_ref, self.state_root)):
                    raise GatewayOperationError("IDEMPOTENCY_MISMATCH")
                return snapshot
            handle = self._handles.get((owner_ref, ref))
            if (envelope.journey_ref != snapshot.journey_ref or
                    envelope.expected_event_head != snapshot.event_head_sha256
                    or snapshot.state != "running" or handle is None or getattr(
                        handle, "control_class", None) != "windows_job_v1"):
                raise GatewayOperationError("CANCEL_UNAVAILABLE")
            authorized = self.authorizer(
                action, raw, owner_ref=owner_ref, state_root=self.state_root,
                clock=self.clock)
            if (authorized.journey_ref != snapshot.journey_ref
                    or authorized.expected_event_head != snapshot.event_head_sha256
                    or authorized.operation["operation_ref"] != ref):
                raise GatewayOperationError("CANCEL_UNAVAILABLE")
            payload = {
                "operation_ref": ref,
                "started_event_sha256": started_event(history)["event_sha256"],
                "client_request_id": authorized.client_request_id,
                "authorization_sha256": authorization_sha256(authorized),
                "timeout_ms": authorized.operation["timeout_ms"],
            }
            ack = journey._append_lifecycle(
                journey_ref=snapshot.journey_ref,
                expected_event_head=snapshot.event_head_sha256,
                client_request_id=authorized.client_request_id,
                operation="cancel_requested", payload=payload)
        stopping = OperationSnapshot(ref, snapshot.journey_ref,
                                     ack.event_head_sha256, "cancel_requested", False)
        self._publish(owner_ref, ref, "snapshot", stopping.as_json())
        timeout = authorized.operation["timeout_ms"] / 1000
        if not handle.signal_tree():
            raise GatewayOperationError("CANCEL_UNAVAILABLE")
        outcome = handle.wait(timeout)
        if outcome is None:
            raise GatewayOperationError("CANCEL_UNAVAILABLE")
        return self._terminal(owner_ref, ref, outcome)
    def snapshot(self, owner_ref: str, ref: str) -> OperationSnapshot:
        if OPERATION_REF_PATTERN.fullmatch(ref) is None:
            raise GatewayOperationError("NOT_FOUND")
        journey = self._journey(owner_ref)
        history = self._history(journey, ref)
        if not history:
            raise GatewayOperationError("NOT_FOUND")
        return self._snapshot(journey, ref, history)
    def result(self, owner_ref: str, ref: str) -> dict:
        snapshot = self.snapshot(owner_ref, ref)
        if snapshot.state not in TERMINALS or snapshot.result_sha256 is None:
            raise GatewayOperationError("INVALID_TRANSITION")
        history = self._history(self._journey(owner_ref), ref)
        path = self._result_dir(owner_ref) / f"{snapshot.result_sha256}.json"
        try:
            raw = path.read_bytes()
            value = __import__("harness.evidence_json", fromlist=[
                "strict_load_json"]).strict_load_json(raw)
            if canonical_sha256(value) != snapshot.result_sha256:
                raise ValueError
            validate_result(value, ref, history[0]["payload"]["action"],
                            snapshot.state)
            return value
        except (OSError, TypeError, ValueError):
            raise GatewayOperationError("STORE_COMMIT_FAILED") from None
    def operation_refs(self, owner_ref: str) -> set[str]:
        refs = set()
        for projection in self._journey(owner_ref).list():
            for event in self._journey(owner_ref)._events(projection["journey_ref"]):
                if event["event_type"] == "operation_queued":
                    refs.add(event["payload"].get("operation_ref"))
        return {ref for ref in refs if type(ref) is str}
    def watch(self, owner_ref: str, ref: str,
              after_sequence: int) -> Iterator[dict]:
        return self.events.watch(self, owner_ref, ref, after_sequence)
    def wait_terminal(self, owner_ref: str, ref: str,
                      timeout_s: float) -> OperationSnapshot:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            snapshot = self.snapshot(owner_ref, ref)
            if snapshot.state in TERMINALS:
                return snapshot
            time.sleep(min(.05, max(0, deadline - time.monotonic())))
        raise TimeoutError("gateway operation did not become terminal")
    def shutdown(self) -> None:
        for handle in list(self._handles.values()):
            try:
                handle.signal_tree()
            except Exception:
                pass
    def _journey(self, owner_ref: str) -> JourneyService:
        try:
            return JourneyService(
                owner_ref=owner_ref, store=JourneyStore(self.state_root),
                grants=GrantStore(self.state_root, clock=self.clock),
                clock=self.clock)
        except (OSError, TypeError, ValueError) as exc:
            raise GatewayOperationError("NOT_FOUND") from exc
    @staticmethod
    def _history(journey: JourneyService, ref: str,
                 journey_ref: str | None = None) -> list[dict]:
        try:
            history = journey._operation_history(ref, LIFECYCLE, journey_ref)
            validate_history(history, ref)
            return history
        except JourneyStoreError as exc:
            raise GatewayOperationError(exc.code) from None
        except (KeyError, TypeError, ValueError):
            raise GatewayOperationError("STORE_COMMIT_FAILED") from None
    def _snapshot(self, journey: JourneyService, ref: str,
                  history: list[dict]) -> OperationSnapshot:
        state, terminal = history_state(history)
        projection = journey.resume(history[0]["journey_ref"])
        handle = self._handles.get((journey.owner_ref, ref))
        return OperationSnapshot(
            ref, history[0]["journey_ref"], projection["event_head_sha256"],
            state, state == "running" and getattr(
                handle, "control_class", None) == "windows_job_v1",
            terminal["event_sha256"] if terminal else None,
            terminal["payload"]["result_sha256"] if terminal else None)
    def _control(self, authorized: AuthorizedOperation, ref: str,
                 factory: OperationProcessFactory) -> None:
        from .gateway_operation_process import supervise_gateway_operation
        supervise_gateway_operation(self, authorized, ref, factory)
    def _terminal(self, owner_ref: str, ref: str,
                  outcome: WorkerOutcome) -> OperationSnapshot:
        journey = self._journey(owner_ref)
        with journey._owner_operation_guard(ref):
            history = self._history(journey, ref)
            current = self._snapshot(journey, ref, history)
            if current.state in TERMINALS:
                return current
            state, result = normalize_outcome(
                current.state, outcome.state, outcome.result)
            state, result, digest = seal_outcome(
                self._seal, owner_ref, ref, history[0]["payload"]["action"],
                state, result)
            event_type = f"operation_{state}"
            basis = history[-1]["event_sha256"]
            payload = {"operation_ref": ref,
                       "basis_event_sha256": basis,
                       "result_sha256": digest}
            if state == "failed":
                payload["reason"] = result["reason"]
            head = journey.resume(current.journey_ref)["event_head_sha256"]
            ack = journey._append_lifecycle(
                journey_ref=current.journey_ref, expected_event_head=head,
                client_request_id=f"{ref}:terminal", operation=event_type,
                payload=payload)
            self._handles.pop((owner_ref, ref), None)
            terminal = OperationSnapshot(
                ref, current.journey_ref, ack.event_head_sha256, state, False,
                ack.event_sha256, digest)
        try: self._publish(owner_ref, ref, "terminal", {
            "snapshot": terminal.as_json(), "result": self.result(owner_ref, ref)})
        finally: self._secrets.pop((owner_ref, ref), None)
        return terminal
    def _seal(self, owner_ref: str, ref: str, action: str,
              state: str, result: dict) -> str:
        value = {"schema": RESULT_SCHEMA, "operation_ref": ref,
                 "action": action, "state": state, "result": result}
        self._validate(owner_ref, ref, value, "STORE_COMMIT_FAILED")
        data = canonical_bytes(value)
        if len(data) > MAX_RESULT_BYTES:
            raise GatewayOperationError("STORE_COMMIT_FAILED")
        digest, directory = canonical_sha256(value), self._result_dir(owner_ref)
        path = directory / f"{digest}.json"
        try:
            with path.open("x+b") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            _secure_owner_only(path, directory=False)
        except FileExistsError:
            if path.read_bytes() != data:
                raise GatewayOperationError("STORE_COMMIT_FAILED")
        except (OSError, PermissionError):
            raise GatewayOperationError("STORE_COMMIT_FAILED") from None
        return digest
    def _result_dir(self, owner_ref: str) -> Path:
        directory = (self.state_root / "gateway-operations" / "v1" /
                     "owners" / owner_ref / "results")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            _secure_owner_only(directory, directory=True)
            return directory
        except (OSError, PermissionError):
            raise GatewayOperationError("STORE_COMMIT_FAILED") from None
    def _publish(self, owner_ref: str, ref: str, kind: str, data: dict) -> None:
        self._validate(owner_ref, ref, data, "EXTERNAL_ACTION_FAILED")
        self.events.publish(owner_ref, ref, kind, data)
    def _validate(self, owner_ref: str, ref: str, value: object, code: str) -> None:
        try: validate_operation_value(value, self._secrets.get((owner_ref, ref), ()))
        except Exception: raise GatewayOperationError(code) from None
def start_operation(*, authorized: AuthorizedOperation, service: GatewayOperations,
                    process_factory: OperationProcessFactory) -> OperationSnapshot:
    return service.start(authorized, process_factory)
def cancel_operation(*, action: str, raw: bytes, owner_ref: str, service: GatewayOperations) -> OperationSnapshot:
    return service.cancel(action=action, raw=raw, owner_ref=owner_ref)
