"""Truthful cancellation for supervisor-owned Journey check process trees."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Protocol

from .journey_checks import JourneyCheckService, OPERATION_REF_PATTERN
from .operation_grants import GrantError, GrantRequest


MAX_CANCEL_TIMEOUT_S = 30.0


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
        replay = self.check_service._cancel_replay(
            journey_ref=journey_ref, expected_event_head=expected_event_head,
            client_request_id=client_request_id, operation_ref=operation_ref,
            timeout_s=timeout_s,
        )
        if replay is not None:
            ack, state = replay
            return (self._unavailable(operation_ref) if state == "cancel_requested"
                    else self._result(operation_ref, state, ack))
        owned = self._owned.get(operation_ref)
        if (owned is None or owned.owner_ref != owner_ref
                or owned.journey_ref != journey_ref):
            return self._unavailable(operation_ref)
        body = {
            "client_request_id": client_request_id,
            "operation_ref": operation_ref, "timeout_s": timeout_s,
        }
        request = self._resolve_request(grant_ref)
        self.check_service.journey._require_binding(
            request, tool="journey.cancel", journey_ref=journey_ref,
            expected_event_head=expected_event_head,
            operation="cancel", body=body,
        )
        self.check_service.journey.grants.consume(
            grant_ref, request, now=self.check_service.journey.clock(),
        )
        self.check_service._request_cancel(
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
