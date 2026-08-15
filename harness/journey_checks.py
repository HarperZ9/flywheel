"""Durable, grant-bound lifecycle control for one Journey check."""
from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
import re
from threading import RLock
from typing import Protocol
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_journey import project_journey
from .evidence_packet import run_journey_check
from .journey_service import JourneyService
from .journey_store import JourneyStoreError, MutationAck
from .operation_grants import GrantError, GrantRequest
from .oracle_registry import OracleRegistry, default_registry
from .python_execution_containment import unavailable_result
OPERATION_REF_PATTERN = re.compile(r"op_[0-9a-f]{32}\Z")
TERMINALS = frozenset(("check_completed", "check_failed", "check_cancelled"))
_LIFECYCLE = frozenset((
    "check_requested", "check_blocked", "check_started", "cancel_requested",
    *TERMINALS,
))
@dataclass(frozen=True)
class CheckCommand:
    owner_ref: str
    journey_ref: str
    expected_event_head: str
    client_request_id: str
    operation_ref: str
    grant_ref: str
    grant_request: GrantRequest
    journey: dict
    claim_id: str
    oracle_id: str
    candidate: Path
    context: dict
    artifact_root: Path | None = None
class CheckRunner(Protocol):
    def __call__(self, journey: dict, claim_id: str, oracle_id: str,
                 candidate: Path, context: dict, *,
                 artifact_root: Path | None = None) -> dict: ...
PACKET_CHECK_RUNNER: CheckRunner = run_journey_check

class JourneyCheckService:
    """Persist request, admission, execution, and one terminal event."""

    def __init__(self, *, journey: JourneyService,
                 registry: OracleRegistry | None = None,
                 supported_oracle_types=frozenset(("lean", "measurement"))) -> None:
        self.journey = journey
        self.registry = registry if registry is not None else default_registry()
        self.supported_oracle_types = frozenset(supported_oracle_types)
        self._commands: dict[str, CheckCommand] = {}
        self._lock = RLock()
    def request(self, command: CheckCommand) -> MutationAck:
        checked = self._snapshot(command)
        with self.journey._operation_guard(
                checked.journey_ref, checked.operation_ref), self._lock:
            return self._request_locked(checked)
    def _request_locked(self, checked: CheckCommand) -> MutationAck:
        requested = self.journey._append_lifecycle(
            journey_ref=checked.journey_ref,
            expected_event_head=checked.expected_event_head,
            client_request_id=checked.client_request_id,
            operation="check_requested", payload=self._requested_payload(checked),
        )
        history = self._history(checked.operation_ref)
        if requested.idempotent_replay and history[-1]["event_type"] != "check_requested":
            if (history[-1]["event_type"] in ("check_started", "cancel_requested")
                    and not self._terminal(history)):
                self._commands[checked.operation_ref] = checked
            return self.journey._event_ack(history[-1], replay=True)
        reason = self._consume_or_block(checked)
        if reason is not None:
            return self._block(checked, requested.event_sha256, reason)
        self._commands[checked.operation_ref] = checked
        return self._start(checked, requested.event_sha256)
    def run(self, operation_ref: str, runner: CheckRunner) -> MutationAck:
        with self._lock:
            history = self._history(operation_ref)
            terminal = self._terminal(history)
            if terminal is not None:
                return self.journey._event_ack(terminal, replay=True)
            command = self._commands.get(operation_ref)
            if command is None or not self._started(history):
                raise JourneyStoreError("INVALID_TRANSITION")
        try:
            raw = runner(
                command.journey, command.claim_id, command.oracle_id,
                command.candidate, command.context,
                artifact_root=command.artifact_root,
            )
            result = strict_load_json(canonical_bytes(raw))
            if type(result) is not dict:
                raise ValueError("runner result must be an object")
            state = result.get("state", "completed")
            if state not in ("completed", "failed", "cancelled"):
                raise ValueError("runner state is invalid")
        except Exception:
            result, state = {"state": "failed"}, "failed"
        return self._commit_terminal(operation_ref, state, result)[0]
    def state(self, operation_ref: str) -> str:
        history = self._history(operation_ref)
        terminal = self._terminal(history)
        if terminal is not None:
            return terminal["event_type"].removeprefix("check_")
        kinds = [event["event_type"] for event in history]
        if "cancel_requested" in kinds:
            return "cancel_requested"
        if "check_started" in kinds:
            return "running"
        if "check_blocked" in kinds:
            return "blocked"
        return "queued" if "check_requested" in kinds else "unknown"
    def _request_cancel(self, *, expected_event_head: str,
                        client_request_id: str, operation_ref: str,
                        timeout_s: float) -> MutationAck:
        history = self._history(operation_ref)
        start = self._started(history)
        if start is None:
            raise JourneyStoreError("INVALID_TRANSITION")
        with self.journey._operation_guard(start["journey_ref"], operation_ref):
            history = self._history(operation_ref)
            if self._terminal(history) is not None or not self._started(history):
                raise JourneyStoreError("INVALID_TRANSITION")
            start = self._started(history)
            return self.journey._append_lifecycle(
                journey_ref=start["journey_ref"],
                expected_event_head=expected_event_head,
                client_request_id=f"cancel:{client_request_id}",
                operation="cancel_requested",
                payload=self._cancel_payload(operation_ref, start, timeout_s),
            )
    def _cancel_replay(self, *, journey_ref: str, expected_event_head: str,
                       client_request_id: str, operation_ref: str,
                       timeout_s: float) -> tuple[MutationAck, str] | None:
        with self._lock:
            history = self._history(operation_ref)
            start = self._started(history)
            if start is None or start["journey_ref"] != journey_ref:
                return None
            replay = self.journey._lifecycle_replay(
                journey_ref, expected_event_head, f"cancel:{client_request_id}",
                "cancel_requested",
                self._cancel_payload(operation_ref, start, timeout_s),
            )
            if replay is None:
                return None
            terminal = self._terminal(self._history(operation_ref))
            if terminal is None:
                return replay, "cancel_requested"
            return (self.journey._event_ack(terminal, replay=True),
                    terminal["event_type"].removeprefix("check_"))
    def _commit_terminal(self, operation_ref: str, state: str,
                         result: dict | None = None) -> tuple[MutationAck, str]:
        history = self._history(operation_ref)
        start = self._started(history)
        if start is None:
            raise JourneyStoreError("INVALID_TRANSITION")
        with self.journey._operation_guard(start["journey_ref"], operation_ref):
            history = self._history(operation_ref)
            terminal = self._terminal(history)
            if terminal is not None:
                actual = terminal["event_type"].removeprefix("check_")
                return self.journey._event_ack(terminal, replay=True), actual
            start = self._started(history)
            if start is None or state not in ("completed", "failed", "cancelled"):
                raise JourneyStoreError("INVALID_TRANSITION")
            event_type = f"check_{state}"
            payload = {
                "operation_ref": operation_ref,
                "started_event_sha256": start["event_sha256"],
            }
            if state == "failed":
                payload["reason"] = "CHECK_FAILED"
            else:
                payload["result_sha256"] = canonical_sha256(result or {"state": state})
            head = self.journey._events(start["journey_ref"])[-1]["event_sha256"]
            ack = self.journey._append_lifecycle(
                journey_ref=start["journey_ref"], expected_event_head=head,
                client_request_id=f"{operation_ref}:{event_type}",
                operation=event_type, payload=payload,
            )
            return ack, state
    def _consume_or_block(self, command: CheckCommand) -> str | None:
        arguments = self._arguments(command)
        try:
            self.journey._require_binding(
                command.grant_request, tool="journey.check",
                journey_ref=command.journey_ref,
                expected_event_head=command.expected_event_head,
                operation="check", body=arguments,
            )
            self.journey.grants.consume(
                command.grant_ref, command.grant_request, now=self.journey.clock(),
            )
        except GrantError as exc:
            return exc.code
        entry = self.registry.entry(command.oracle_id)
        if entry is None:
            return "ORACLE_UNAVAILABLE"
        oracle_type = entry.oracle.oracle_type
        if oracle_type == "pytest":
            try:
                view = project_journey(command.journey, lens="verify")
                claims = {item["claim_id"]: item for item in view["detail"]["claims"]}
                verdict = claims[command.claim_id]["verdict"]
            except (KeyError, TypeError, ValueError):
                return "INVALID_JOURNEY"
            return unavailable_result(
                claim_id=command.claim_id, claim_verdict_before=verdict,
            )["unverifiable_reason"]
        if oracle_type not in self.supported_oracle_types:
            return "UNSUPPORTED_CAPABILITY"
        return None
    def _block(self, command: CheckCommand, requested_sha: str,
               reason: str) -> MutationAck:
        head = self.journey._events(command.journey_ref)[-1]["event_sha256"]
        return self.journey._append_lifecycle(
            journey_ref=command.journey_ref, expected_event_head=head,
            client_request_id=f"{command.client_request_id}:blocked",
            operation="check_blocked", payload={
                "operation_ref": command.operation_ref,
                "reason": reason, "request_event_sha256": requested_sha,
            },
        )
    def _start(self, command: CheckCommand, requested_sha: str) -> MutationAck:
        head = self.journey._events(command.journey_ref)[-1]["event_sha256"]
        return self.journey._append_lifecycle(
            journey_ref=command.journey_ref, expected_event_head=head,
            client_request_id=f"{command.client_request_id}:started",
            operation="check_started", payload={
                **self._requested_payload(command),
                "request_event_sha256": requested_sha,
            },
        )
    def _history(self, operation_ref: str) -> list[dict]:
        journeys = self.journey.list()
        for projection in journeys:
            events = self.journey._events(projection["journey_ref"])
            found = [event for event in events if event["event_type"] in _LIFECYCLE
                     and event["payload"].get("operation_ref") == operation_ref]
            if found:
                return found
        return []
    @staticmethod
    def _terminal(history: list[dict]) -> dict | None:
        values = [event for event in history if event["event_type"] in TERMINALS]
        if len(values) > 1:
            raise JourneyStoreError("INVALID_TRANSITION")
        return values[0] if values else None
    @staticmethod
    def _started(history: list[dict]) -> dict | None:
        values = [event for event in history if event["event_type"] == "check_started"]
        return values[0] if len(values) == 1 else None
    @staticmethod
    def _requested_payload(command: CheckCommand) -> dict:
        return {"operation_ref": command.operation_ref, "claim_id": command.claim_id,
                "oracle_id": command.oracle_id}
    @staticmethod
    def _cancel_payload(operation_ref: str, start: dict,
                        timeout_s: float) -> dict:
        return {
            "operation_ref": operation_ref,
            "started_event_sha256": start["event_sha256"],
            "timeout_s": timeout_s,
        }

    @staticmethod
    def _arguments(command: CheckCommand) -> dict:
        candidate_ref = command.context.get("candidate_ref", command.candidate.name)
        return {
            "journey_sha256": canonical_sha256(command.journey),
            "claim_id": command.claim_id, "oracle_id": command.oracle_id,
            "candidate_ref": candidate_ref,
            "context_sha256": canonical_sha256(command.context),
        }

    def _snapshot(self, command: CheckCommand) -> CheckCommand:
        if not isinstance(command, CheckCommand):
            raise TypeError("command must be CheckCommand")
        if command.owner_ref != self.journey.owner_ref:
            raise GrantError("PERMISSION_DENIED")
        self.journey._validate_lifecycle_selector(
            command.journey_ref, command.expected_event_head,
        )
        if (OPERATION_REF_PATTERN.fullmatch(command.operation_ref) is None
                or type(command.client_request_id) is not str
                or not command.client_request_id
                or type(command.claim_id) is not str or not command.claim_id
                or type(command.oracle_id) is not str or not command.oracle_id
                or not isinstance(command.candidate, Path)
                or command.artifact_root is not None
                and not isinstance(command.artifact_root, Path)
                or not isinstance(command.grant_request, GrantRequest)):
            raise ValueError("check command is invalid")
        journey = strict_load_json(canonical_bytes(command.journey))
        context = strict_load_json(canonical_bytes(command.context))
        if type(journey) is not dict or type(context) is not dict:
            raise ValueError("check command is invalid")
        return replace(command, journey=journey, context=context)
