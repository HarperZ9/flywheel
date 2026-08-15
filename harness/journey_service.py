"""Authenticated-owner Journey operations with replay-before-grant semantics."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable
import secrets

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
from .journey_projection import reduce_events
from .journey_store import (
    REQUEST_SCHEMA, JourneyStore, JourneyStoreError, MutationAck, MutationCommand,
    _require_supported_version,
)
from .journey_types import SHA256_PATTERN
from .operation_grants import (
    GrantError, GrantRequest, GrantStore, _secure_owner_only, _validate_owner_ref,
)


class JourneyService:
    """One authenticated owner's mutation and projection boundary."""

    def __init__(self, *, owner_ref: str, store: JourneyStore, grants: GrantStore,
                 clock: Callable[[], str],
                 fault_injector: Callable[[str], None] | None = None) -> None:
        self.owner_ref = _validate_owner_ref(owner_ref)
        self.store = store
        self.grants = grants
        self.clock = clock
        self._fault_injector = fault_injector
        owners = self.store.state_root / "journeys" / "v2" / "owners"
        owners.mkdir(parents=True, exist_ok=True)
        _secure_owner_only(owners, directory=True)
        owner_dir = owners / self.owner_ref
        owner_dir.mkdir(exist_ok=True)
        _secure_owner_only(owner_dir, directory=True)

    def create(self, *, client_request_id: str, body: dict, grant_ref: str,
               grant_request: GrantRequest) -> MutationAck:
        snapshot = self._snapshot_body(body)
        template = MutationCommand(
            owner_ref=self.owner_ref, journey_ref=None,
            expected_event_head=None, client_request_id=client_request_id,
            operation="intake", body=snapshot,
        )
        replay = self._lookup_create_replay(client_request_id, snapshot)
        if replay is not None:
            return replay
        self.store.validate_command(
            template, creating=True, allow_unbound_journey=True,
        )
        self._require_binding(
            grant_request, tool="journey.create", journey_ref=None,
            expected_event_head=None, operation="intake", body=snapshot,
        )
        self.grants.consume(grant_ref, grant_request, now=self.clock())
        self._checkpoint("after_grant_burn")
        command = MutationCommand(
            owner_ref=self.owner_ref, journey_ref=self._new_journey_ref(),
            expected_event_head=None, client_request_id=client_request_id,
            operation="intake", body=snapshot,
        )
        return self.store.create(command)

    def append(self, *, journey_ref: str, expected_event_head: str,
               client_request_id: str, operation: str, body: dict,
               grant_ref: str, grant_request: GrantRequest) -> MutationAck:
        snapshot = self._snapshot_body(body)
        command = MutationCommand(
            owner_ref=self.owner_ref, journey_ref=journey_ref,
            expected_event_head=expected_event_head, client_request_id=client_request_id,
            operation=operation, body=snapshot,
        )
        self.store.validate_command(command, creating=False)
        replay = self.store.lookup_replay(command)
        if replay is not None:
            return replay
        self._require_binding(
            grant_request, tool="journey.append", journey_ref=journey_ref,
            expected_event_head=expected_event_head, operation=operation, body=snapshot,
        )
        self.grants.consume(grant_ref, grant_request, now=self.clock())
        self._checkpoint("after_grant_burn")
        return self.store.append(command)

    def list(self) -> list[dict]:
        return self.store.list(self.owner_ref)

    def resume(self, journey_ref: str) -> dict:
        return self.store.load(self.owner_ref, journey_ref)

    def _append_lifecycle(self, *, journey_ref: str, expected_event_head: str,
                          client_request_id: str, operation: str,
                          payload: dict) -> MutationAck:
        """Append one server-authored event with replay before timestamp creation."""
        snapshot = self._snapshot_body(payload)
        replay = self._lifecycle_replay(
            journey_ref, expected_event_head, client_request_id, operation, snapshot,
        )
        if replay is not None:
            return replay
        command = MutationCommand(
            owner_ref=self.owner_ref, journey_ref=journey_ref,
            expected_event_head=expected_event_head,
            client_request_id=client_request_id, operation=operation,
            body={"occurred_at": self.clock(), "payload": snapshot},
        )
        self.store.validate_command(command, creating=False)
        return self.store.append(command)

    def _events(self, journey_ref: str) -> list[dict]:
        directory = self.store._journey_dir(self.owner_ref, journey_ref)
        try:
            with ExclusiveJourneyLock.acquire(
                    directory / ".lock", self.store.lock_timeout_s):
                head = self.store._read_head(directory)
                return self.store._events_at_head(directory, head) if head else []
        except JourneyLockBusy:
            raise JourneyStoreError("STORE_BUSY") from None
        except JourneyStoreError:
            raise
        except (OSError, TypeError, ValueError):
            raise JourneyStoreError("STORE_COMMIT_FAILED") from None

    def _event_ack(self, event: dict, *, replay: bool) -> MutationAck:
        events = self._events(event["journey_ref"])
        projection = reduce_events(events[:event["sequence"] + 1])
        return MutationAck(
            event["journey_ref"], event["event_sha256"], event["event_sha256"],
            canonical_sha256(projection), replay,
        )

    @contextmanager
    def _operation_guard(self, journey_ref: str, operation_ref: str):
        directory = self.store._journey_dir(self.owner_ref, journey_ref)
        name = f".operation-{canonical_sha256(operation_ref)}.lock"
        try:
            with ExclusiveJourneyLock.acquire(
                    directory / name, self.store.lock_timeout_s):
                yield
        except JourneyLockBusy:
            raise JourneyStoreError("STORE_BUSY") from None

    def _validate_lifecycle_selector(self, journey_ref: str,
                                     expected_event_head: str) -> None:
        self.store._validate_selector(self.owner_ref, journey_ref)
        if (type(expected_event_head) is not str
                or SHA256_PATTERN.fullmatch(expected_event_head) is None):
            raise JourneyStoreError("HEAD_CONFLICT")

    @staticmethod
    def _snapshot_body(body: dict) -> dict:
        return strict_load_json(canonical_bytes(body))

    def _lookup_create_replay(self, client_request_id: str,
                              body: dict) -> MutationAck | None:
        for projection in self.store.list(self.owner_ref):
            command = MutationCommand(
                owner_ref=self.owner_ref, journey_ref=projection["journey_ref"],
                expected_event_head=None, client_request_id=client_request_id,
                operation="intake", body=body,
            )
            replay = self.store.lookup_replay(command)
            if replay is not None:
                return replay
        return None

    def _lifecycle_replay(self, journey_ref: str, expected_head: str,
                          request_id: str, operation: str,
                          payload: dict) -> MutationAck | None:
        _require_supported_version(self.store.state_root)
        journey_dir = self.store._journey_dir(self.owner_ref, journey_ref)
        request_path = journey_dir / "requests" / (
            f"{canonical_sha256(request_id)}.json"
        )
        if not request_path.exists():
            return None
        try:
            with ExclusiveJourneyLock.acquire(
                    journey_dir / ".lock", self.store.lock_timeout_s):
                return self._read_lifecycle_replay(
                    journey_dir, request_path, expected_head, operation, payload,
                )
        except JourneyLockBusy:
            raise JourneyStoreError("STORE_BUSY") from None
        except JourneyStoreError:
            raise
        except (OSError, TypeError, ValueError):
            raise JourneyStoreError("STORE_COMMIT_FAILED") from None

    def _read_lifecycle_replay(self, journey_dir, request_path, expected_head,
                               operation, payload) -> MutationAck:
        record = self.store._read_json(request_path)
        head = self.store._read_head(journey_dir)
        events = self.store._events_at_head(journey_dir, head) if head else []
        event = next((item for item in events
                      if item["event_sha256"] == record.get("event_sha256")), None)
        expected_fields = {
            "schema", "client_request_sha256", "request_sha256", "sequence",
            "event_head_sha256", "event_sha256", "projection_sha256",
        }
        if (set(record) != expected_fields or record.get("schema") != REQUEST_SCHEMA
                or record.get("client_request_sha256") != request_path.stem
                or event is None or record.get("sequence") != event["sequence"]
                or record.get("event_head_sha256") != event["event_sha256"]
                or record.get("event_sha256") != event["event_sha256"]):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        if (event["event_type"] != operation or event["payload"] != payload
                or event["prior_event_sha256"] != expected_head):
            raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
        projection_sha = canonical_sha256(reduce_events(events[:event["sequence"] + 1]))
        request_sha = canonical_sha256({
            "owner_ref": self.owner_ref, "journey_ref": journey_dir.name,
            "expected_event_head": expected_head, "operation": operation,
            "body": {"occurred_at": event["occurred_at"], "payload": payload},
        })
        if (record.get("projection_sha256") != projection_sha
                or record.get("request_sha256") != request_sha
                or event["request_sha256"] != request_sha):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        return MutationAck(
            journey_dir.name, event["event_sha256"], event["event_sha256"],
            projection_sha, True,
        )

    def _require_binding(self, request: GrantRequest, *, tool: str,
                         journey_ref: str | None, expected_event_head: str | None,
                         operation: str, body: dict) -> None:
        operation_value = {
            "owner_ref": self.owner_ref, "journey_ref": journey_ref,
            "expected_event_head": expected_event_head,
            "operation": operation, "body": body,
        }
        expected = (
            request.owner_ref == self.owner_ref
            and request.tool == tool
            and request.journey_ref == journey_ref
            and request.expected_event_head == expected_event_head
            and request.operation_sha256 == canonical_sha256(operation_value)
            and request.arguments_sha256 == canonical_sha256(body)
        )
        if not expected:
            raise GrantError("PERMISSION_DENIED")

    def _new_journey_ref(self) -> str:
        existing = {item["journey_ref"] for item in self.store.list(self.owner_ref)}
        journey_ref = f"jrn_{secrets.token_hex(16)}"
        while journey_ref in existing:
            journey_ref = f"jrn_{secrets.token_hex(16)}"
        return journey_ref

    def _checkpoint(self, point: str) -> None:
        if self._fault_injector is not None:
            try:
                self._fault_injector(point)
            except Exception:
                raise JourneyStoreError("STORE_COMMIT_FAILED") from None
