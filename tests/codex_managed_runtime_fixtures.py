from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from harness.codex_managed_composition import (
    build_managed_codex_components,
    managed_codex_server_config,
)
from harness.codex_managed_inventory_lifecycle import CodexManagedInventoryLifecycle
from harness.codex_managed_profile import prepare_codex_profile
from harness.codex_managed_profile_auth_extension import extend_manifest_after_explicit_login
from harness.codex_managed_profile_auth_receipt import (
    CodexProfileLoginReceiptRef,
    LOGIN_RECEIPT_SCHEMA,
)
from harness.evidence_json import canonical_bytes
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_route import route_gateway_operation
from harness.gateway_operations import GatewayOperations
from harness.private_artifact_fs import open_artifact_root

from provider_session_fixtures import NOW


OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
MODEL = "gpt-5.6-sol"
VERSION = "0.144.6"


def roots(tmp_path):
    values = {
        "state": tmp_path / "state",
        "policy": tmp_path / "policy",
        "workspace": tmp_path / "workspace",
        "run": tmp_path / "run",
    }
    for path in values.values():
        path.mkdir()
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"synthetic managed codex executable")
    values["executable"] = executable
    values["digest"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    return values


def generated_home(profile):
    for name in (".personality_migration", "installation_id"):
        (profile.home / name).write_text("ok", encoding="utf-8")
    for name in (
            "goals_1.sqlite", "goals_1.sqlite-shm", "goals_1.sqlite-wal",
            "logs_2.sqlite", "logs_2.sqlite-shm", "logs_2.sqlite-wal",
            "memories_1.sqlite", "memories_1.sqlite-shm", "memories_1.sqlite-wal",
            "state_5.sqlite", "state_5.sqlite-shm", "state_5.sqlite-wal"):
        (profile.home / name).write_bytes(b"")
    system = profile.home / "skills" / ".system" / "openai-docs"
    system.mkdir(parents=True)
    (profile.home / "skills" / ".system" / ".codex-system-skills.marker").write_text(
        "system", encoding="utf-8")
    (system / "SKILL.md").write_text("builtin skill", encoding="utf-8")
    (profile.home / "tmp").mkdir()


class RuntimeClient:
    def __init__(self, session):
        self.session = session
        self.config_digest = session.config_digest
        self.transport = session.transport

    def check_configuration(self):
        return SimpleNamespace(configuration_ready=True, config_digest=self.config_digest)

    def thread_start(self, **_params):
        return {"thread": {"id": "thread-1", "sessionId": "session-1", "turns": []}}

    def turn_start(self, thread_id, input, **_params):
        self.session.input_sent = True
        self.session.turn_input = input
        assert thread_id == "thread-1"
        return {"turn": {"id": "turn-1", "status": "completed", "items": []}}

    def thread_resume(self, *_args, **_kwargs):
        raise AssertionError("resume not used")

    def thread_read(self, *_args, **_kwargs):
        raise AssertionError("read not used")


class RuntimeSession:
    def __init__(self, profile, inventory, *, close_ok=True, config_digest="cfg-runtime"):
        self.profile = profile
        self.inventory = inventory
        self.close_ok = close_ok
        self.config_digest = config_digest
        self.input_sent = False
        self.turn_input = None
        self.closed = False
        self.cleanup = None
        self.transport = SimpleNamespace(
            closed=False,
            close=lambda timeout=0: self._close_transport(),
            pop_notification=lambda timeout=0.0: None,
            pop_protocol_event=lambda timeout=0.0: None,
            notification_overflowed=lambda: False,
        )
        self.client = RuntimeClient(self)

    def _close_transport(self):
        self.transport.closed = self.close_ok
        return self.close_ok

    def close(self):
        self.cleanup = SimpleNamespace(
            exited=self.close_ok,
            job_closed=self.close_ok,
            stderr_drain_complete=self.close_ok,
        )
        self.transport.closed = self.close_ok
        self.closed = self.close_ok
        return self.close_ok


class Starter:
    def __init__(self, *, close_results=None, config_digest="cfg-runtime"):
        self.close_results = list(close_results or [])
        self.config_digest = config_digest
        self.calls = []
        self.sessions = []

    def __call__(self, profile, *, executable, executable_sha256, model, inventory=None):
        self.calls.append({"profile": profile, "inventory": inventory, "model": model})
        if inventory is None:
            generated_home(profile)
        close_ok = self.close_results.pop(0) if self.close_results else True
        session = RuntimeSession(
            profile, inventory, close_ok=close_ok,
            config_digest=self.config_digest)
        self.sessions.append(session)
        return session


def lifecycle(values, starter):
    return CodexManagedInventoryLifecycle(
        state_root=values["state"],
        policy_root=values["policy"],
        workspace=values["workspace"],
        executable=values["executable"],
        executable_sha256=values["digest"],
        configured_version=VERSION,
        version_provenance="synthetic-test",
        model=MODEL,
        start_session=starter,
    )


def components(values, managed_lifecycle):
    config = managed_codex_server_config(
        executable=values["executable"],
        executable_sha256=values["digest"],
        model=MODEL,
        codex_version=VERSION,
        version_provenance="synthetic-test",
        policy_root=values["policy"],
    )
    return build_managed_codex_components(
        repo_root=values["workspace"],
        run_root=values["run"],
        state_root=values["state"],
        clock=lambda: NOW,
        config=config,
        lifecycle=managed_lifecycle,
    )


def login_receipt(policy, profile, source_ref, executable_sha, *, login_id="login-1"):
    receipt = {
        "schema": LOGIN_RECEIPT_SCHEMA,
        "source_inventory_sha256": source_ref.sha256,
        "codex": {"version": VERSION, "executable_sha256": executable_sha},
        "bindings": {
            "home_identity": profile.home_identity.to_json_dict(),
            "workspace_identity": profile.workspace_identity.to_json_dict(),
        },
        "login": {
            "mode": "login_with_chatgpt",
            "login_id_sha256": hashlib.sha256(login_id.encode("utf-8")).hexdigest(),
        },
        "completion": {"success": True},
        "cleanup": {"exited": True, "job_closed": True, "stderr_drain_complete": True},
        "auth_entries": [{"path": "auth.json", "kind": "file", "max_bytes": 16 * 1024 * 1024}],
    }
    raw = canonical_bytes(receipt)
    digest = hashlib.sha256(raw).hexdigest()
    rel = f"codex-policy/{source_ref.sha256}/login-receipts/{digest}.json"
    with open_artifact_root(policy) as root:
        root.write_new_or_same(rel, raw)
    return CodexProfileLoginReceiptRef(path=policy / rel, sha256=digest), login_id


def accept_auth_inventory(values, managed_lifecycle):
    base_ref = managed_lifecycle.ensure_baseline_inventory(OWNER)
    profile = prepare_codex_profile(
        values["state"], workspace=values["workspace"], owner_ref=OWNER)
    (profile.home / "auth.json").write_text('{"synthetic":"metadata-only"}', encoding="utf-8")
    receipt, login_id = login_receipt(
        values["policy"], profile, base_ref, values["digest"])
    auth_ref = extend_manifest_after_explicit_login(
        profile,
        base_ref,
        executable=values["executable"],
        executable_sha256=values["digest"],
        codex_version=VERSION,
        login_receipt=receipt,
        policy_root=values["policy"],
        expected_login_id=login_id,
        expected_mode="login_with_chatgpt",
    )
    managed_lifecycle.accept_verified_inventory(OWNER, auth_ref)
    return auth_ref


def snapshot(registry, workspace_ref, *, head):
    return registry.binding_snapshot(
        owner_ref=OWNER,
        journey_ref=JOURNEY,
        expected_event_head=head,
        operation={
            "provider": "codex",
            "workspace_ref": workspace_ref,
            "model": MODEL,
            "permission_scope": {"mode": "manual"},
        },
    )


def operation(binding):
    return {
        "provider": "codex",
        "workspace_ref": binding["workspace_ref"],
        "model": MODEL,
        "config_digest": binding["config_digest"],
        "capability_digest": binding["capability_digest"],
        "provider_binding_ref": binding["provider_binding_ref"],
        "permission_scope": {"mode": "manual"},
        "input": [{"type": "input_text", "text": "hi"}],
        "stream": False,
        "resume_policy": "new_thread",
        "data_refs": [],
        "credential_refs": [],
        "timeout_s": 1,
    }


def grant_request(head: str, op: dict, *, request_id: str) -> bytes:
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": request_id,
        "operation": op,
    }, separators=(",", ":")).encode()


def authorized_raw(head: str, op: dict, grant_ref: str, *, request_id: str) -> bytes:
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": request_id,
        "grant_ref": grant_ref,
        **op,
    }, separators=(",", ":")).encode()


def prepare_approve_and_dispatch(comp, state_root, head, op, *, request_id):
    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/provider.session.turn",
        grant_request(head, op, request_id=request_id),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW,
        provider_session_registry=comp.provider_session_registry)
    assert status == 200, prepared
    approved, approved_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert approved_status == 200
    service = GatewayOperations(state_root, clock=lambda: NOW)
    response = route_gateway_operation(
        "POST", "/api/provider-sessions/turn", owner_ref=OWNER,
        service=service, process_factory=comp.operation_process_factory,
        raw=authorized_raw(head, op, approved["grant_ref"], request_id=request_id),
        content_type="application/json")
    if response.stream is not None:
        b"".join(response.stream)
    ref = next(iter(service.operation_refs(OWNER)))
    return service.result(OWNER, ref)
