from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
import threading
from typing import Iterator
from urllib.parse import parse_qs
from .evidence_json import canonical_bytes, canonical_sha256
from .gateway_operation import AuthorizedOperation, GatewayOperationError
from .journey_types import SHA256_PATTERN
_OPERATION_PATH = re.compile(
    r"/api/operations/(op_[0-9a-f]{32})(?:/(events|result))?\Z")
_MAX_LINE_BYTES = 262_144
_MAX_BUFFER_BYTES = 1_048_576
_MAX_GATEWAY_BUFFER_BYTES = 8_388_608
def operation_ref_for(owner_ref: str, journey_ref: str,
                      client_request_id: str) -> str:
    digest = canonical_sha256({"owner_ref": owner_ref,
                               "journey_ref": journey_ref,
                                "client_request_id": client_request_id})
    return f"op_{digest[:32]}"
def authorization_sha256(authorized: AuthorizedOperation) -> str:
    plan = getattr(authorized.execution_plan, "digest", None)
    if type(plan) is not str or SHA256_PATTERN.fullmatch(plan) is None:
        raise GatewayOperationError("PERMISSION_DENIED")
    return canonical_sha256({
        "owner_ref": authorized.owner_ref, "journey_ref": authorized.journey_ref,
        "expected_event_head": authorized.expected_event_head,
        "client_request_id": authorized.client_request_id,
        "grant_ref": authorized.grant_ref,
        "proposal_nonce": authorized.grant_ref.removeprefix("gnt_"),
        "expires_at": authorized.expires_at, "action": authorized.action,
        "tool": authorized.tool, "destination": dict(authorized.destination),
        "operation_sha256": authorized.operation_sha256,
        "arguments_sha256": authorized.arguments_sha256,
        "scopes": list(authorized.scopes), "data_refs": list(authorized.data_refs),
        "credential_refs": list(authorized.credential_refs),
        "execution_plan_sha256": plan,
    })
def replay_authorization_sha256(envelope, owner_ref: str,
                                state_root: Path) -> str:
    """Reconstruct one prior grant authorization without consuming it."""
    try:
        from .evidence_json import strict_load_json
        from .gateway_grant_route import _validate_record
        from .gateway_operation import thaw_operation
        from .gateway_provider_adapter import freeze_execution_plan
        from .operation_grants import OWNER_REF_PATTERN
        if OWNER_REF_PATTERN.fullmatch(owner_ref) is None:
            raise ValueError
        proposal_ref = "prp_" + envelope.grant_ref.removeprefix("gnt_")
        owner_dir = (Path(state_root) / "gateway-grant-proposals" / owner_ref)
        path = owner_dir / f"{canonical_sha256(proposal_ref)}.json"
        record = _validate_record(strict_load_json(path.read_bytes()), owner_ref)
        operation, plan = envelope.operation, freeze_execution_plan(
            envelope.operation)
        if (record["state"] != "approved" or record["action"] != envelope.action
                or record["journey_ref"] != envelope.journey_ref
                or record["expected_event_head"] != envelope.expected_event_head
                or record["client_request_id"] != envelope.client_request_id
                or record["operation"] != thaw_operation(operation.operation)
                or record["execution_plan_sha256"] != plan.digest
                or record["planned_grant_ref"] != envelope.grant_ref):
            raise ValueError
        authorized = AuthorizedOperation(
            operation.action, operation.tool, operation.destination,
            operation.operation, operation.operation_sha256,
            operation.arguments_sha256, operation.scopes, operation.data_refs,
            operation.credential_refs, owner_ref, record["journey_ref"],
            record["expected_event_head"], record["client_request_id"],
            record["planned_grant_ref"], record["expires_at"], plan)
        return authorization_sha256(authorized)
    except Exception:
        raise GatewayOperationError("IDEMPOTENCY_MISMATCH") from None
def queued_payload(authorized: AuthorizedOperation) -> dict:
    return {
        "operation_ref": operation_ref_for(
            authorized.owner_ref, authorized.journey_ref,
            authorized.client_request_id),
        "client_request_id": authorized.client_request_id,
        "action": authorized.action, "tool": authorized.tool,
        "authorization_sha256": authorization_sha256(authorized),
        "operation_sha256": authorized.operation_sha256,
        "arguments_sha256": authorized.arguments_sha256,
        "grant_ref_sha256": canonical_sha256(authorized.grant_ref),
        "execution_plan_sha256": authorized.execution_plan.digest,
    }
class OperationEventBus:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], list[tuple[str, dict]]] = {}
        self._bytes: dict[tuple[str, str], int] = {}; self._base = {}
        self._subscribers: dict[tuple[str, str], int] = {}
        self._completed: set[tuple[str, str]] = set(); self._total_bytes = 0; self._condition = threading.Condition()
    def _drop(self, key: tuple[str, str]) -> None:
        self._total_bytes -= self._bytes.pop(key, 0); self._rows.pop(key, None)
        self._base.pop(key, None); self._completed.discard(key); self._subscribers.pop(key, None)
    def _pop_first(self, key: tuple[str, str]) -> None:
        rows, base = self._rows[key], self._base.get(key, 0)
        event, data = rows.pop(0); size = len(_frame(base + 1, event, data))
        self._base[key] = base + 1; self._bytes[key] -= size; self._total_bytes -= size
    def _evict_completed(self, needed: int, exclude) -> None:
        for key in tuple(self._completed):
            if self._total_bytes + needed <= _MAX_GATEWAY_BUFFER_BYTES: return
            if key != exclude and self._subscribers.get(key, 0) == 0:
                self._drop(key)
    def _admit(self, key: tuple[str, str], size: int, terminal: bool) -> None:
        rows = self._rows.setdefault(key, [])
        if terminal:
            while rows and self._bytes.get(key, 0) + size > _MAX_BUFFER_BYTES:
                self._pop_first(key)
        self._evict_completed(size, key)
        if terminal:
            for candidate in tuple(self._rows):
                while self._rows[candidate] and self._total_bytes + size > _MAX_GATEWAY_BUFFER_BYTES: self._pop_first(candidate)
        if (self._bytes.get(key, 0) + size > _MAX_BUFFER_BYTES
                or self._total_bytes + size > _MAX_GATEWAY_BUFFER_BYTES):
            raise GatewayOperationError("EXTERNAL_ACTION_FAILED")
    def publish(self, owner_ref: str, operation_ref: str,
                 event: str, data: dict) -> None:
        if event == "terminal": data = {"operation_ref": operation_ref}
        encoded = canonical_bytes(data)
        if len(b"data: ") + len(encoded) > _MAX_LINE_BYTES:
            raise GatewayOperationError("EXTERNAL_ACTION_FAILED")
        with self._condition:
            key = owner_ref, operation_ref
            rows = self._rows.setdefault(key, [])
            sequence = self._base.get(key, 0) + len(rows) + 1
            size = len(_frame(sequence, event, data))
            self._admit(key, size, event == "terminal")
            used = self._bytes.get(key, 0); rows.append((event, data))
            self._bytes[key] = used + size; self._total_bytes += size
            if event == "terminal":
                self._completed.add(key); self._drop(key) if self._subscribers.get(key, 0) == 0 else None
            self._condition.notify_all()
    def watch(self, service, owner_ref: str, operation_ref: str,
              after_sequence: int) -> Iterator[dict]:
        if type(after_sequence) is not int or after_sequence < 0:
            raise GatewayOperationError("INVALID_REQUEST")
        key, cursor, sent_snapshot = (owner_ref, operation_ref), after_sequence, False
        with self._condition:
            self._subscribers[key] = self._subscribers.get(key, 0) + 1
        try:
            while True:
                snapshot = service.snapshot(owner_ref, operation_ref)
                synthetic = None
                with self._condition:
                    rows, base = list(self._rows.get(key, ())), self._base.get(key, 0)
                    cursor = max(cursor, base)
                    if cursor < base + len(rows):
                        event, data = rows[cursor - base]; cursor += 1
                    elif snapshot.state in service.terminal_states:
                        synthetic = [("snapshot", snapshot.as_json()), ("terminal", self._terminal_data(service, owner_ref, operation_ref, snapshot))]
                    elif not sent_snapshot:
                        synthetic = [("snapshot", snapshot.as_json())]
                        sent_snapshot = True
                    else:
                        self._condition.wait(.25); continue
                if synthetic is not None:
                    for event, data in synthetic:
                        cursor += 1; yield {"sequence": cursor, "event": event, "data": data}
                    if snapshot.state in service.terminal_states: return
                    continue
                if event == "terminal": data = self._terminal_data(
                    service, owner_ref, operation_ref, snapshot)
                yield {"sequence": cursor, "event": event, "data": data}
        finally:
            with self._condition:
                self._subscribers[key] = max(0, self._subscribers.get(key, 1) - 1)
                if key in self._completed and self._subscribers[key] == 0:
                    self._drop(key)
                elif self._subscribers[key] == 0: self._subscribers.pop(key)
    @staticmethod
    def _terminal_data(service, owner_ref: str, operation_ref: str,
                       snapshot) -> dict:
        snapshot = service.snapshot(owner_ref, operation_ref)
        return {"snapshot": snapshot.as_json(), "result": service.result(owner_ref, operation_ref)}
    def wake(self) -> None:
        with self._condition:
            self._condition.notify_all()
@dataclass(frozen=True)
class RouteResponse:
    status: int; body: dict | None = None
    stream: Iterator[bytes] | None = None
def _frame(sequence: int, event: str, value) -> bytes:
    data = b"[DONE]" if value == "[DONE]" else canonical_bytes(value)
    if len(b"data: ") + len(data) > _MAX_LINE_BYTES:
        raise GatewayOperationError("EXTERNAL_ACTION_FAILED")
    return (f"id: {sequence}\r\nevent: {event}\r\ndata: ".encode()
            + data + b"\r\n\r\n")
def _stream(service, owner_ref: str, operation_ref: str,
            initial=None, after: int = 0) -> Iterator[bytes]:
    sequence, terminal = after, False
    if initial is not None:
        sequence += 1
        yield _frame(sequence, "snapshot", initial.as_json())
        after = max(after, 1)
        if initial.state in service.terminal_states:
            result = service.result(owner_ref, operation_ref)
            sequence += 1
            yield _frame(sequence, "terminal", {
                "snapshot": initial.as_json(), "result": result})
            terminal = True
    if not terminal:
        for row in service.watch(owner_ref, operation_ref, after):
            sequence = max(sequence + 1, row["sequence"])
            yield _frame(sequence, row["event"], row["data"])
            if row["event"] == "terminal":
                terminal = True
                break
    if terminal:
        yield _frame(sequence + 1, "terminal", "[DONE]")
def _start_replay(service, owner_ref: str, envelope, journey):
    from .gateway_provider_adapter import freeze_execution_plan
    ref = operation_ref_for(owner_ref, envelope.journey_ref,
                            envelope.client_request_id)
    history = service._history(journey, ref)
    if not history:
        return None
    queued = history[0]["payload"]
    expected = {
        "client_request_id": envelope.client_request_id,
        "action": envelope.action, "tool": envelope.operation.tool,
        "operation_sha256": envelope.operation.operation_sha256,
        "arguments_sha256": envelope.operation.arguments_sha256,
        "grant_ref_sha256": canonical_sha256(envelope.grant_ref),
        "execution_plan_sha256": freeze_execution_plan(
            envelope.operation).digest,
    }
    if (history[0]["journey_ref"] != envelope.journey_ref
            or history[0]["prior_event_sha256"] != envelope.expected_event_head
            or any(queued.get(key) != value for key, value in expected.items())):
        raise GatewayOperationError("IDEMPOTENCY_MISMATCH")
    return service._snapshot(journey, ref, history)
def _start(raw: bytes, owner_ref: str, service, process_factory) -> RouteResponse:
    from .gateway_envelope import parse_gateway_envelope
    envelope = parse_gateway_envelope("agent.run", raw)
    ref = operation_ref_for(owner_ref, envelope.journey_ref,
                            envelope.client_request_id)
    journey = service._journey(owner_ref)
    with journey._owner_operation_guard(ref):
        replay = _start_replay(service, owner_ref, envelope, journey)
        if replay is None:
            authorized = service.authorizer(
                "agent.run", raw, owner_ref=owner_ref,
                state_root=service.state_root, clock=service.clock)
            authorized = service.credential_resolver(
                authorized, service.state_root)
            snapshot = service.start(
                authorized, process_factory, already_guarded=True)
        else:
            snapshot = replay
    if envelope.operation.operation["stream"]:
        return RouteResponse(200, stream=_stream(
            service, owner_ref, snapshot.operation_ref, snapshot))
    terminal = service.wait_terminal(owner_ref, snapshot.operation_ref, 300)
    if terminal.state != "completed":
        raise GatewayOperationError("EXTERNAL_ACTION_FAILED")
    return RouteResponse(200, service.result(
        owner_ref, snapshot.operation_ref)["result"])
def _read(method: str, path: str, query: str, owner_ref: str,
          service) -> RouteResponse:
    match = _OPERATION_PATH.fullmatch(path)
    if method != "GET" or match is None:
        raise GatewayOperationError("INVALID_REQUEST")
    ref, selector = match.groups()
    if selector == "events":
        values = parse_qs(query, keep_blank_values=True, strict_parsing=True)
        if set(values) - {"after"} or any(len(value) != 1 for value in values.values()):
            raise GatewayOperationError("INVALID_REQUEST")
        raw_after = values.get("after", ["0"])[0]
        if (len(raw_after) > 18 or not raw_after.isascii()
                or not raw_after.isdecimal()):
            raise GatewayOperationError("INVALID_REQUEST")
        return RouteResponse(200, stream=_stream(
            service, owner_ref, ref, after=int(raw_after)))
    if query:
        raise GatewayOperationError("INVALID_REQUEST")
    value = service.result(owner_ref, ref) if selector == "result" else (
        service.snapshot(owner_ref, ref).as_json())
    return RouteResponse(200, value)
def route_gateway_operation(
        method: str, path: str, *, owner_ref: str, service, process_factory,
        raw: bytes = b"", query: str = "", content_type: str = "") -> RouteResponse:
    try:
        if path == "/api/agent":
            if method != "POST" or query or content_type != "application/json":
                raise GatewayOperationError("INVALID_REQUEST")
            return _start(raw, owner_ref, service, process_factory)
        if path == "/api/operations/cancel":
            if method != "POST" or query or content_type != "application/json":
                raise GatewayOperationError("INVALID_REQUEST")
            from .gateway_operations import cancel_operation
            value = cancel_operation(action="operation.cancel", raw=raw,
                                     owner_ref=owner_ref, service=service)
            return RouteResponse(200, value.as_json())
        return _read(method, path, query, owner_ref, service)
    except Exception as exc:
        from .gateway_grant_route import gateway_error_response
        body, status = gateway_error_response(exc)
        return RouteResponse(status, body)
