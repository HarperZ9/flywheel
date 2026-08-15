"""Truthful cancellation for supervisor-owned Journey check process trees."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Protocol

from .journey_checks import (
    JourneyCheckService, OPERATION_REF_PATTERN, TERMINALS,
)
from .journey_store import JourneyStoreError
from .journey_types import SHA256_PATTERN
from .operation_grants import GrantError, GrantRequest


MAX_CANCEL_TIMEOUT_S = 30.0


def _valid_recovery_start(events: list[dict], start: dict) -> bool:
    payload = start["payload"]
    if set(payload) != {
            "operation_ref", "claim_id", "oracle_id", "request_event_sha256"}:
        return False
    operation = payload.get("operation_ref")
    if (type(operation) is not str or OPERATION_REF_PATTERN.fullmatch(operation) is None
            or type(payload.get("claim_id")) is not str or not payload["claim_id"]
            or type(payload.get("oracle_id")) is not str or not payload["oracle_id"]):
        return False
    requests = [event for event in events if event["event_type"] == "check_requested"
                and event["event_sha256"] == payload["request_event_sha256"]]
    if len(requests) != 1:
        return False
    requested, value = requests[0], requests[0]["payload"]
    return (requested["sequence"] < start["sequence"]
            and requested["actor_id"] == start["actor_id"]
            and set(value) == {"operation_ref", "client_request_id",
                               "command_sha256", "claim_id", "oracle_id"}
            and value.get("operation_ref") == operation
            and value.get("claim_id") == payload["claim_id"]
            and value.get("oracle_id") == payload["oracle_id"]
            and type(value.get("client_request_id")) is str
            and bool(value["client_request_id"])
            and type(value.get("command_sha256")) is str
            and len(value["command_sha256"]) == 64
            and all(character in "0123456789abcdef"
                    for character in value["command_sha256"]))


def _valid_recovery_terminal(start: dict, terminal: list[dict]) -> bool:
    if len(terminal) != 1:
        return False
    event, payload = terminal[0], terminal[0]["payload"]
    common = {"operation_ref", "started_event_sha256"}
    if event["event_type"] == "check_failed":
        valid_payload = (set(payload) == common | {"reason"}
                         and payload.get("reason") in {
                             "CHECK_FAILED", "CHECK_INTERRUPTED"})
    else:
        digest = payload.get("result_sha256")
        valid_payload = (set(payload) == common | {"result_sha256"}
                         and type(digest) is str
                         and SHA256_PATTERN.fullmatch(digest) is not None)
    return (valid_payload and event["sequence"] > start["sequence"]
            and event["actor_id"] == start["actor_id"]
            and payload.get("operation_ref")
            == start["payload"].get("operation_ref")
            and payload.get("started_event_sha256") == start["event_sha256"])


def _valid_recovery_cancel(start: dict, cancel: dict,
                           terminal: list[dict]) -> bool:
    payload, timeout = cancel["payload"], cancel["payload"].get("timeout_s")
    return (set(payload) == {"operation_ref", "started_event_sha256", "timeout_s"}
            and payload.get("operation_ref") == start["payload"].get("operation_ref")
            and payload.get("started_event_sha256") == start["event_sha256"]
            and type(timeout) in (int, float) and not isinstance(timeout, bool)
            and 0 < timeout <= MAX_CANCEL_TIMEOUT_S
            and cancel["actor_id"] == start["actor_id"]
            and cancel["journey_ref"] == start["journey_ref"]
            and cancel["sequence"] > start["sequence"]
            and (not terminal or cancel["sequence"] < terminal[0]["sequence"]))


def _valid_recovery_grammar(events: list[dict], start: dict,
                            terminal: list[dict]) -> bool:
    operation = start["payload"].get("operation_ref")
    related = [event for event in events
               if event["payload"].get("operation_ref") == operation]
    requests = [event for event in related if event["event_type"] == "check_requested"]
    starts = [event for event in related if event["event_type"] == "check_started"]
    cancels = [event for event in related if event["event_type"] == "cancel_requested"]
    allowed = {"check_requested", "check_started", "cancel_requested"}
    if terminal:
        allowed |= TERMINALS
    return (len(requests) == 1 and starts == [start] and len(cancels) <= 1
            and all(event["event_type"] in allowed for event in related)
            and _valid_recovery_start(events, start)
            and (not cancels or _valid_recovery_cancel(start, cancels[0], terminal)))


class OwnedProcess(Protocol):
    def signal_tree(self) -> bool: ...
    def wait(self, timeout_s: float) -> str | None: ...


@dataclass(frozen=True)
class _Owned:
    owner_ref: str
    journey_ref: str
    process: OwnedProcess


class OperationSupervisor:
    """Bind cancellation to one owned handle and one durable Journey start."""

    def __init__(self, *, check_service: JourneyCheckService,
                 grant_request: Callable[[str], GrantRequest]) -> None:
        self.check_service = check_service
        self._grant_request = grant_request
        self._owned: dict[str, _Owned] = {}

    def register_owned(self, *, owner_ref: str, journey_ref: str,
                       operation_ref: str, process: OwnedProcess) -> None:
        if (owner_ref != self.check_service.journey.owner_ref
                or OPERATION_REF_PATTERN.fullmatch(operation_ref) is None
                or self.check_service.state(operation_ref) != "running"
                or not callable(getattr(process, "signal_tree", None))
                or not callable(getattr(process, "wait", None))):
            raise ValueError("owned process binding is invalid")
        existing = self._owned.get(operation_ref)
        value = _Owned(owner_ref, journey_ref, process)
        if existing is not None and existing != value:
            raise ValueError("owned process binding is invalid")
        self._owned[operation_ref] = value

    def request_cancel(self, *, owner_ref: str, journey_ref: str,
                       expected_event_head: str, client_request_id: str,
                       operation_ref: str, grant_ref: str,
                       timeout_s: float) -> dict:
        self._validate(timeout_s, client_request_id, operation_ref)
        if owner_ref != self.check_service.journey.owner_ref:
            return {
                "code": "CANCEL_UNAVAILABLE", "operation_ref": operation_ref,
                "state": "unknown",
            }
        replay = self._cancel_replay(
            journey_ref=journey_ref, expected_event_head=expected_event_head,
            client_request_id=client_request_id, operation_ref=operation_ref,
            timeout_s=timeout_s,
        )
        if replay is not None:
            ack, state = replay
            return (self._unavailable(operation_ref) if state == "cancel_requested"
                    else self._result(operation_ref, state, ack))
        history = self.check_service._history(operation_ref, journey_ref)
        if any(event["event_type"] == "cancel_requested" for event in history) and self.check_service._terminal(history) is None: return self._unavailable(operation_ref)
        owned = self._owned.get(operation_ref)
        if (owned is None or owned.owner_ref != owner_ref
                or owned.journey_ref != journey_ref):
            return self._unavailable(operation_ref)
        body = {
            "client_request_id": client_request_id,
            "operation_ref": operation_ref, "timeout_s": timeout_s,
        }
        request = self._resolve_request(grant_ref)
        if request.scopes != ("journey:cancel",) or request.data_refs:
            raise GrantError("PERMISSION_DENIED")
        self.check_service.journey._require_binding(
            request, tool="journey.cancel", journey_ref=journey_ref,
            expected_event_head=expected_event_head,
            operation="cancel", body=body,
        )
        self.check_service.journey.grants.consume(
            grant_ref, request, now=self.check_service.journey.clock(),
        )
        self._request_cancel(
            expected_event_head=expected_event_head,
            client_request_id=client_request_id, operation_ref=operation_ref,
            timeout_s=timeout_s,
        )
        terminal = self._controlled_terminal(owned.process, timeout_s)
        if terminal is None:
            return self._unavailable(operation_ref)
        ack, actual = self.check_service._commit_terminal(
            operation_ref, terminal, {"state": terminal},
        )
        return self._result(operation_ref, actual, ack)

    def _request_cancel(self, *, expected_event_head: str,
                        client_request_id: str, operation_ref: str,
                        timeout_s: float):
        service, history = self.check_service, self.check_service._history(operation_ref)
        start = service._started(history)
        if start is None:
            raise JourneyStoreError("INVALID_TRANSITION")
        with service.journey._operation_guard(start["journey_ref"], operation_ref):
            history = service._history(operation_ref)
            if service._terminal(history) is not None or not service._started(history):
                raise JourneyStoreError("INVALID_TRANSITION")
            start = service._started(history)
            return service.journey._append_lifecycle(
                journey_ref=start["journey_ref"], expected_event_head=expected_event_head,
                client_request_id=f"cancel:{client_request_id}",
                operation="cancel_requested",
                payload=self._cancel_payload(operation_ref, start, timeout_s))

    def _cancel_replay(self, *, journey_ref: str, expected_event_head: str,
                       client_request_id: str, operation_ref: str,
                       timeout_s: float):
        service = self.check_service
        with service._lock:
            history = service._history(operation_ref); start = service._started(history)
            if start is None or start["journey_ref"] != journey_ref:
                return None
            replay = service.journey._lifecycle_replay(
                journey_ref, expected_event_head, f"cancel:{client_request_id}",
                "cancel_requested", self._cancel_payload(operation_ref, start, timeout_s))
            if replay is None:
                return None
            terminal = service._terminal(service._history(operation_ref))
            if terminal is None:
                return replay, "cancel_requested"
            return (service.journey._event_ack(terminal, replay=True),
                    terminal["event_type"].removeprefix("check_"))

    @staticmethod
    def _cancel_payload(operation_ref: str, start: dict, timeout_s: float) -> dict:
        return {"operation_ref": operation_ref,
                "started_event_sha256": start["event_sha256"], "timeout_s": timeout_s}

    def _resolve_request(self, grant_ref: str) -> GrantRequest:
        try:
            request = self._grant_request(grant_ref)
        except Exception:
            raise GrantError("PERMISSION_REQUIRED") from None
        if not isinstance(request, GrantRequest):
            raise GrantError("PERMISSION_DENIED")
        return request

    @staticmethod
    def _controlled_terminal(process: OwnedProcess,
                             timeout_s: float) -> str | None:
        try:
            if process.signal_tree() is not True:
                return None
            terminal = process.wait(timeout_s)
        except Exception:
            return None
        return terminal if terminal in ("cancelled", "completed", "failed") else None

    def _unavailable(self, operation_ref: str) -> dict:
        return {
            "code": "CANCEL_UNAVAILABLE", "operation_ref": operation_ref,
            "state": self.check_service.state(operation_ref),
        }

    @staticmethod
    def _result(operation_ref: str, state: str, ack) -> dict:
        return {
            "operation_ref": operation_ref, "state": state,
            "event_head_sha256": ack.event_head_sha256,
            "terminal_event_ref": ack.event_sha256,
        }

    @staticmethod
    def _validate(timeout_s: float, client_request_id: str,
                  operation_ref: str) -> None:
        if (type(timeout_s) not in (int, float) or isinstance(timeout_s, bool)
                or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= MAX_CANCEL_TIMEOUT_S):
            raise ValueError("timeout_s is invalid")
        if (type(client_request_id) is not str or not client_request_id
                or OPERATION_REF_PATTERN.fullmatch(operation_ref) is None):
            raise ValueError("cancellation binding is invalid")
