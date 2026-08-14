"""Authenticated-owner Journey operations with replay-before-grant semantics."""
from __future__ import annotations

from typing import Callable
import secrets

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_store import JourneyStore, JourneyStoreError, MutationAck, MutationCommand
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
