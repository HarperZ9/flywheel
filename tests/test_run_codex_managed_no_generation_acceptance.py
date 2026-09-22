from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from harness.evidence_json import canonical_sha256
from harness.private_artifact_fs import root_identity


OWNER = "owner_acceptance"
MODEL = "gpt-5.6-sol"
SECRET = "owner-secret@example.invalid"


def _runner():
    from scripts import run_codex_managed_no_generation_acceptance as runner
    return runner


def _profile_home(state: Path, workspace: Path, owner: str = OWNER) -> Path:
    identity = root_identity(workspace).to_json_dict()
    key = canonical_sha256({"owner": owner, "workspace": str(workspace.absolute()).lower(),
                            "identity": identity})
    return state / "codex-managed" / key


def _exe(tmp_path: Path) -> tuple[Path, str]:
    exe = tmp_path / "codex.exe"
    exe.write_bytes(b"synthetic codex")
    return exe, hashlib.sha256(exe.read_bytes()).hexdigest()


def _config(tmp_path: Path, runner, *, profile_home: Path | None = None):
    state, policy, workspace = tmp_path / "state", tmp_path / "policy", tmp_path / "workspace"
    for root in (state, policy, workspace):
        root.mkdir(exist_ok=True)
    exe, digest = _exe(tmp_path)
    return runner.AcceptanceConfig(
        owner_ref=OWNER, state_root=state, policy_root=policy, workspace=workspace,
        profile_home=profile_home or _profile_home(state, workspace),
        executable=exe, executable_sha256=digest, codex_version="0.144.6",
        version_provenance="test", model=MODEL, out=tmp_path / "receipt.json")


class FakeLifecycle:
    instances: list["FakeLifecycle"] = []
    account_response = {"account": {"type": "chatgpt", "email": SECRET,
                                    "planType": "plus"},
                        "accessToken": "secret-token"}
    model_response = {"data": [{"id": MODEL}]}
    close_ok = True

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.sessions: list[FakeSession] = []
        FakeLifecycle.instances.append(self)

    def runtime_session_for_owner(self, *, owner_ref):
        session = FakeSession("cfg-runtime", account_response=self.account_response,
                              model_response=self.model_response, close_ok=self.close_ok)
        self.sessions.append(session)
        inventory = SimpleNamespace(sha256="a" * 64)
        manifest = {"auth_extension": {"schema": "flywheel.codex-managed-profile-auth-extension/v1"}}
        profile = SimpleNamespace(home=Path(self.kwargs["state_root"]) / "profile")
        return session, profile, inventory, manifest

    def shutdown(self):
        return True


class NoAuthExtensionLifecycle(FakeLifecycle):
    def runtime_session_for_owner(self, *, owner_ref):
        session, profile, inventory, _manifest = super().runtime_session_for_owner(
            owner_ref=owner_ref)
        return session, profile, inventory, {}


class FirstProbeLifecycleError(FakeLifecycle):
    def runtime_session_for_owner(self, *, owner_ref):
        from harness.codex_managed_inventory_lifecycle import CodexManagedInventoryLifecycleError
        raise CodexManagedInventoryLifecycleError("BASELINE_ACCEPTED_INVENTORY_REQUIRED")


class FakeSession:
    def __init__(self, config_digest: str, *, account_response, model_response,
                 close_ok=True):
        self.client = FakeClient(config_digest)
        self.transport = FakeTransport(account_response, model_response)
        self.closed = False
        self.cleanup = None
        self.close_ok = close_ok

    def close(self):
        self.closed = self.close_ok
        self.transport.closed = self.close_ok
        self.cleanup = SimpleNamespace(exited=self.close_ok, job_closed=self.close_ok,
                                       stderr_drain_complete=self.close_ok)
        return self.close_ok


class FakeClient:
    def __init__(self, config_digest: str):
        self.config_digest = config_digest

    def check_configuration(self):
        return SimpleNamespace(as_result=lambda: {
            "schema": "flywheel.codex-config-inspection/v1",
            "configuration_ready": True,
            "config_digest": self.config_digest,
            "issues": [],
        })


class FakeTransport:
    def __init__(self, account_response, model_response):
        self.calls = []
        self.closed = False
        self.account_response = account_response
        self.model_response = model_response

    def request(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "account/read":
            return self.account_response
        if method == "model/list":
            return self.model_response
        raise AssertionError(f"unexpected method {method}")


def _state(receipt, assertion_id):
    return next(row for row in receipt["assertions"] if row["id"] == assertion_id)["state"]


def _reset_fake(**kwargs):
    FakeLifecycle.instances = []
    FakeLifecycle.account_response = {"account": {"type": "chatgpt", "email": SECRET,
                                                  "planType": "plus"},
                                      "accessToken": "secret-token"}
    FakeLifecycle.model_response = {"data": [{"id": MODEL}]}
    FakeLifecycle.close_ok = True
    for key, value in kwargs.items():
        setattr(FakeLifecycle, key, value)


def test_missing_owner_supplied_profile_refuses_before_runtime_start(tmp_path):
    runner = _runner()
    _reset_fake()
    cfg = _config(tmp_path, runner)

    receipt = runner.run_acceptance(cfg, lifecycle_factory=FakeLifecycle)

    assert receipt["complete"] is False
    assert _state(receipt, "P03_owner_supplied_profile_home") == "FAIL"
    assert FakeLifecycle.instances == []


def test_profile_home_must_match_owner_workspace_identity(tmp_path):
    runner = _runner()
    _reset_fake()
    wrong = tmp_path / "state" / "codex-managed" / "wrong"
    wrong.mkdir(parents=True)
    cfg = _config(tmp_path, runner, profile_home=wrong)

    receipt = runner.run_acceptance(cfg, lifecycle_factory=FakeLifecycle)

    assert receipt["complete"] is False
    assert _state(receipt, "P03_owner_supplied_profile_home") == "FAIL"
    assert FakeLifecycle.instances == []


def test_existing_profile_runs_redacted_no_generation_restart_probe(tmp_path):
    runner = _runner()
    _reset_fake()
    cfg = _config(tmp_path, runner)
    cfg.profile_home.mkdir(parents=True)

    receipt = runner.run_acceptance(cfg, lifecycle_factory=FakeLifecycle)

    assert receipt["complete"] is True
    assert _state(receipt, "P07_first_no_generation_probe") == "PASS"
    assert _state(receipt, "P08_restart_no_generation_probe") == "PASS"
    lifecycle = FakeLifecycle.instances[0]
    assert [call[0] for session in lifecycle.sessions for call in session.transport.calls] == [
        "account/read", "model/list", "account/read", "model/list"]
    serialized = json.dumps(receipt)
    assert SECRET not in serialized
    assert "secret-token" not in serialized
    assert "account/login/start" not in serialized
    assert "turn/start" not in serialized
    assert receipt["restart"]["config_digest_match"] is True
    assert json.loads(cfg.out.read_text(encoding="utf-8")) == receipt


def test_missing_auth_extension_prevents_clean_acceptance(tmp_path):
    runner = _runner()
    cfg = _config(tmp_path, runner)
    cfg.profile_home.mkdir(parents=True)

    receipt = runner.run_acceptance(cfg, lifecycle_factory=NoAuthExtensionLifecycle)

    assert receipt["complete"] is False
    assert _state(receipt, "P07_first_no_generation_probe") == "FAIL"


def test_first_probe_lifecycle_error_preserves_redacted_probe_row(tmp_path):
    runner = _runner()
    cfg = _config(tmp_path, runner)
    cfg.profile_home.mkdir(parents=True)

    receipt = runner.run_acceptance(cfg, lifecycle_factory=FirstProbeLifecycleError)

    assert receipt["complete"] is False
    assert receipt["error"] == "probe_failed_BASELINE_ACCEPTED_INVENTORY_REQUIRED"
    assert len(receipt["probes"]) == 1
    assert receipt["probes"][0]["phase"] == "first"
    assert receipt["probes"][0]["error"] == "BASELINE_ACCEPTED_INVENTORY_REQUIRED"
    assert _state(receipt, "P07_first_no_generation_probe") == "FAIL"
    assert json.loads(cfg.out.read_text(encoding="utf-8")) == receipt


def test_absent_authenticated_account_prevents_clean_acceptance(tmp_path):
    runner = _runner()
    _reset_fake(account_response={"account": None, "requiresOpenaiAuth": True})
    cfg = _config(tmp_path, runner)
    cfg.profile_home.mkdir(parents=True)

    receipt = runner.run_acceptance(cfg, lifecycle_factory=FakeLifecycle)

    assert receipt["complete"] is False
    assert _state(receipt, "P07_first_no_generation_probe") == "FAIL"
    serialized = json.dumps(receipt)
    assert "requiresOpenaiAuth" not in serialized


def test_malformed_account_shapes_prevent_clean_acceptance(tmp_path):
    runner = _runner()
    cases = [
        {"account": {}},
        {"account": {"type": "unknown", "email": SECRET}},
    ]

    for index, response in enumerate(cases):
        case_dir = tmp_path / f"case-{index}"
        case_dir.mkdir()
        _reset_fake(account_response=response)
        cfg = _config(case_dir, runner)
        cfg.profile_home.mkdir(parents=True)

        receipt = runner.run_acceptance(cfg, lifecycle_factory=FakeLifecycle)

        assert receipt["complete"] is False
        assert _state(receipt, "P07_first_no_generation_probe") == "FAIL"
        assert receipt["error"] == "probe_failed_AGENT_NATIVE_AUTH_REQUIRED"
        assert SECRET not in json.dumps(receipt)


def test_missing_configured_model_prevents_clean_acceptance(tmp_path):
    runner = _runner()
    _reset_fake(model_response={"data": [{"id": "other-model"}]})
    cfg = _config(tmp_path, runner)
    cfg.profile_home.mkdir(parents=True)

    receipt = runner.run_acceptance(cfg, lifecycle_factory=FakeLifecycle)

    assert receipt["complete"] is False
    assert _state(receipt, "P07_first_no_generation_probe") == "FAIL"


def test_model_list_data_shape_with_configured_model_accepts(tmp_path):
    runner = _runner()
    _reset_fake(model_response={"data": [{"id": MODEL}]})
    cfg = _config(tmp_path, runner)
    cfg.profile_home.mkdir(parents=True)

    receipt = runner.run_acceptance(cfg, lifecycle_factory=FakeLifecycle)

    assert receipt["complete"] is True
    assert receipt["probes"][0]["model_list"]["configured_model_present"] is True


def test_close_failure_records_cleanup_required_and_failed_probe(tmp_path):
    runner = _runner()
    _reset_fake(account_response={"account": None}, close_ok=False)
    cfg = _config(tmp_path, runner)
    cfg.profile_home.mkdir(parents=True)

    receipt = runner.run_acceptance(cfg, lifecycle_factory=FakeLifecycle)

    assert receipt["complete"] is False
    assert _state(receipt, "P07_first_no_generation_probe") == "FAIL"
    assert _state(receipt, "P10_cleanup_complete") == "FAIL"
    assert receipt["error"] == "probe_failed_AGENT_NATIVE_AUTH_REQUIRED"
    assert receipt["cleanup"]["reason"] == "AGENT_NATIVE_CLEANUP_REQUIRED"
