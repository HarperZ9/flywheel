"""Durable, grant-bound lifecycle control for one Journey check."""
from __future__ import annotations
from dataclasses import dataclass, replace
import os, re
from pathlib import Path, PurePosixPath, PureWindowsPath
from threading import RLock
from typing import Protocol
from .evidence_json import admit_artifact_ref, canonical_bytes, canonical_sha256, strict_load_json
from .evidence_journey import project_journey
from .evidence_packet import run_journey_check
from .journey_service import JourneyService
from .journey_store import JourneyStoreError, MutationAck
from .operation_grants import GrantError, GrantRequest, GrantStore
from .oracle_registry import OracleRegistry, default_registry
from .python_execution_containment import unavailable_result
OPERATION_REF_PATTERN = re.compile(r"op_[0-9a-f]{32}\Z")
TERMINALS = frozenset(("check_completed", "check_failed", "check_cancelled"))
_LIFECYCLE = frozenset(("check_requested", "check_blocked", "check_started", "cancel_requested", *TERMINALS))
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
    candidate_ref: str
    context: dict
    context_bytes_sha256: str
    artifact_root_ref: str
class CheckRunner(Protocol):
    def __call__(self, journey: dict, claim_id: str, oracle_id: str,
                 candidate: Path, context: dict, *, artifact_root: Path | None = None) -> dict: ...
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
        with (self.journey._owner_operation_guard(checked.operation_ref),
              self.journey._operation_guard(checked.journey_ref, "check-admission"),
              self._lock):
            return self._request_locked(checked)
    def _request_locked(self, checked: CheckCommand) -> MutationAck:
        history = self._history(checked.operation_ref, checked.journey_ref)
        if history:
            requested = [event for event in history
                         if event["event_type"] == "check_requested"]
            if (len(requested) != 1
                    or requested[0]["payload"]
                    != self._requested_payload(checked)):
                raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
            if len(history) == 1:
                return self._block(checked, requested[0]["event_sha256"],
                                   "CHECK_INTERRUPTED")
            if (history[-1]["event_type"] in ("check_started", "cancel_requested")
                    and not self._terminal(history)):
                self._commands[checked.operation_ref] = checked
            return self.journey._event_ack(history[-1], replay=True)
        requested = self.journey._append_lifecycle(
            journey_ref=checked.journey_ref,
            expected_event_head=checked.expected_event_head,
            client_request_id=checked.client_request_id,
            operation="check_requested",
            payload=self._requested_payload(checked),
        )
        self.journey._checkpoint("after_check_requested")
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
            start = self._started(history)
            if self._commands.get(operation_ref) is None or start is None:
                raise JourneyStoreError("INVALID_TRANSITION")
        with self.journey._operation_guard(
                start["journey_ref"], f"execution:{operation_ref}"):
            return self._run_claimed(operation_ref, runner)
    def _run_claimed(self, operation_ref: str, runner: CheckRunner) -> MutationAck:
        with self._lock:
            history = self._history(operation_ref)
            terminal = self._terminal(history)
            if terminal is not None:
                return self.journey._event_ack(terminal, replay=True)
            command = self._commands.get(operation_ref)
            if command is None or self._started(history) is None:
                raise JourneyStoreError("INVALID_TRANSITION")
        try:
            artifact_root, candidate = self._resolve_artifacts(
                command.artifact_root_ref, command.candidate_ref)
            raw = runner(
                command.journey, command.claim_id, command.oracle_id,
                candidate, command.context, artifact_root=artifact_root,
            )
            result = strict_load_json(canonical_bytes(raw))
            if type(result) is not dict:
                raise ValueError("runner result must be an object")
            state = "completed"
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
            if (command.grant_request.scopes != ("journey:check",)
                    or command.grant_request.data_refs != (
                        command.artifact_root_ref, command.candidate_ref)):
                raise GrantError("PERMISSION_DENIED")
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
                "operation_ref": command.operation_ref,
                "claim_id": command.claim_id, "oracle_id": command.oracle_id,
                "request_event_sha256": requested_sha,
            },
        )
    def _history(self, operation_ref: str, journey_ref: str | None = None) -> list[dict]:
        return self.journey._operation_history(operation_ref, _LIFECYCLE, journey_ref)
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
    def _arguments(command: CheckCommand) -> dict:
        return {"client_request_id": command.client_request_id,
                "operation_ref": command.operation_ref,
                "journey_sha256": canonical_sha256(command.journey),
                "claim_id": command.claim_id, "oracle_id": command.oracle_id,
                "artifact_root_ref": command.artifact_root_ref,
                "candidate_ref": command.candidate_ref,
                "context_sha256": canonical_sha256(command.context), "context_bytes_sha256": command.context_bytes_sha256}
    @staticmethod
    def _requested_payload(command: CheckCommand) -> dict:
        command_sha = canonical_sha256({
            "owner_ref": command.owner_ref, "journey_ref": command.journey_ref,
            "expected_event_head": command.expected_event_head, "client_request_id": command.client_request_id,
            "operation_ref": command.operation_ref,
            "arguments_sha256": canonical_sha256(JourneyCheckService._arguments(command)),
            "grant_request_sha256": GrantStore._request_sha(command.grant_request)})
        return {"operation_ref": command.operation_ref,
                "client_request_id": command.client_request_id,
                "command_sha256": command_sha, "claim_id": command.claim_id,
                "oracle_id": command.oracle_id}
    def _resolve_artifacts(self, root_ref: str, candidate_ref: str) -> tuple[Path, Path]:
        state = self.journey.store.state_root.resolve(strict=True)
        root = (state / root_ref).resolve(strict=True)
        try:
            contained = os.path.commonpath((os.path.normcase(str(state)),
                                            os.path.normcase(str(root)))) == os.path.normcase(str(state))
        except ValueError:
            contained = False
        if not contained or not root.is_dir():
            raise ValueError("artifact root is invalid")
        return root, admit_artifact_ref(root, candidate_ref)
    @staticmethod
    def _canonical_ref(value: object, *, allow_dot: bool) -> str:
        if type(value) is not str or not value or "\\" in value or "\x00" in value:
            raise ValueError("artifact reference is invalid")
        posix, windows = PurePosixPath(value), PureWindowsPath(value)
        if (posix.is_absolute() or windows.is_absolute() or windows.drive
                or ".." in posix.parts or value != posix.as_posix()
                or not allow_dot and value == "."):
            raise ValueError("artifact reference is invalid")
        return value
    def _snapshot(self, command: CheckCommand) -> CheckCommand:
        if not isinstance(command, CheckCommand):
            raise TypeError("command must be CheckCommand")
        if command.owner_ref != self.journey.owner_ref:
            raise GrantError("PERMISSION_DENIED")
        self.journey._validate_lifecycle_selector(
            command.journey_ref, command.expected_event_head)
        if (OPERATION_REF_PATTERN.fullmatch(command.operation_ref) is None
                or type(command.client_request_id) is not str
                or not command.client_request_id
                or type(command.claim_id) is not str or not command.claim_id
                or type(command.oracle_id) is not str or not command.oracle_id
                or not isinstance(command.grant_request, GrantRequest) or re.fullmatch(
                    r"[0-9a-f]{64}\Z", command.context_bytes_sha256 or "") is None):
            raise ValueError("check command is invalid")
        journey = strict_load_json(canonical_bytes(command.journey))
        context = strict_load_json(canonical_bytes(command.context))
        if type(journey) is not dict or type(context) is not dict:
            raise ValueError("check command is invalid")
        candidate_ref = self._canonical_ref(
            command.candidate_ref, allow_dot=False)
        root_ref = self._canonical_ref(
            command.artifact_root_ref, allow_dot=True)
        if context.get("candidate_ref") != candidate_ref:
            raise ValueError("check command is invalid")
        return replace(command, journey=journey, context=context,
                       candidate_ref=candidate_ref, artifact_root_ref=root_ref)
