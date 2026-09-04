"""Shared setup for the gateway operation route tests.

Two test modules drive the same route: this one builds the journey, the
authorizer, and the request bytes they both start from, so the split between
them is about what is being tested and not about who owns the fixture.
"""
import json

from harness.gateway_envelope import parse_gateway_envelope
from harness.gateway_operation import AuthorizedOperation
from harness.gateway_operations import GatewayOperations
from harness.gateway_provider_adapter import freeze_execution_plan
from harness.journey_store import JourneyStore, MutationCommand

NOW = "2026-08-16T12:00:00Z"
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
class Process:
    control_class = "windows_job_v1"
    def __init__(self, outcome):
        self.outcome, self.resume_calls = outcome, 0
    def resume(self): self.resume_calls += 1; return True
    def signal_tree(self): return True
    def wait(self, _timeout): return self.outcome
    def close(self): pass
class Factory:
    def __init__(self, process): self.process, self.calls = process, 0
    def create(self, _authorized, progress):
        self.calls += 1
        progress({"type": "assistant", "text": "bounded"})
        return self.process
def _setup(root, *, stream=True, authorize_calls=None, lock_timeout_s=2.0):
    head = JourneyStore(root).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "route", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    operation = {"goal": "inspect", "endpoint": "local", "max_steps": 2,
                 "allow_write": False, "allow_exec": False, "stream": stream,
                 "data_refs": [], "credential_refs": []}
    def authorize(action, raw, **_):
        if authorize_calls is not None: authorize_calls.append(action)
        envelope = parse_gateway_envelope(action, raw)
        canonical = envelope.operation
        return AuthorizedOperation(
            canonical.action, canonical.tool, canonical.destination,
            canonical.operation, canonical.operation_sha256,
            canonical.arguments_sha256, canonical.scopes, canonical.data_refs,
            canonical.credential_refs, OWNER, JOURNEY,
            envelope.expected_event_head, envelope.client_request_id,
            envelope.grant_ref, "2026-08-16T12:02:00Z",
            freeze_execution_plan(canonical), {})
    service = GatewayOperations(
        root, clock=lambda: NOW, authorizer=authorize,
        credential_resolver=lambda value, _root: value,
        lock_timeout_s=lock_timeout_s)
    raw = json.dumps({"schema": "flywheel.gateway-operation/v1",
                      "journey_ref": JOURNEY, "expected_event_head": head,
                      "client_request_id": "agent-1", "grant_ref": "gnt_" + "a" * 32,
                      **operation}).encode()
    return service, raw
