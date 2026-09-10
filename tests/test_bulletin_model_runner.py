"""Complete supervisor wiring with fake fixtures/children, never model I/O."""
from pathlib import Path
import json

from harness.evidence_json import canonical_bytes
from tests.test_bulletin_model_campaign import Fixture, gate, invoke
from tests.test_bulletin_model_manifest import manifest
import scripts.run_bulletin_model_evaluation as runner


def test_runner_keeps_claim_phase_after_native_child_closed(monkeypatch, tmp_path):
    calls, native_instances = [], []
    class FakeFixture(Fixture):
        ready = {"base": "http://127.0.0.1:1111"}
        config = {"base_url": "http://127.0.0.1:2222"}
        config_sha = "a" * 64
        config_path = tmp_path / "private-config.json"
        @classmethod
        def start(cls, **kwargs):
            return cls()
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class FakeNative:
        review_elapsed = 0
        def __init__(self, exchange, *, launch, reviewer):
            self.launch, self.closed = launch, False
            native_instances.append(self)
        def prestart(self): pass
        def close(self): self.closed = True
        def bind_model_output(self, identity, raw):
            self.bound = (identity, raw)
        def remaining_active_seconds(self):
            raise AssertionError("native child lifetime is not the episode clock")
        def dispatch(self, action, *, reserve):
            assert json.loads(self.bound[1]) == action
            permit = reserve("a" * 64)
            self.close()
            return {"disposition": "response_received", "reservation_id": permit["reservation_id"],
                    "request_entered": True, "response_received": True, "post_id": "p"}
    def worker(request, **kwargs):
        calls.append(request)
        assert 0 < kwargs["timeout_seconds"] <= 60
        assert kwargs["reservation"]["record_name"].startswith("ledger-")
        if request["stage_id"].endswith("p3"):
            assert native_instances[-1].closed
        return invoke(**request)
    monkeypatch.setattr(runner, "OwnedBulletinFixture", FakeFixture)
    monkeypatch.setattr(runner, "NativeCoordinator", FakeNative)
    monkeypatch.setattr(runner, "supervise_generation", worker)
    monkeypatch.setattr(runner, "reconcile_generation_accounting", lambda **_: {"reconciled": True})
    monkeypatch.setattr(runner, "review_prefix", lambda *a, **kw: gate() if kw.get("continuation", True) else
                        {"status": "reviewed", "independent_review_agrees": True})
    value = manifest(tmp_path)
    value["execution_admitted"] = True
    result = runner.execute(value, canonical_bytes(value), "b" * 64, tmp_path / "run")
    assert result["failure"] is None and len(calls) == 38
    assert len(native_instances) == 12 and all(n.closed for n in native_instances)
    assert all(set(c) == {"schema_version", "run_id", "profile", "timeout_seconds", "reservation_id",
        "stage_id", "messages", "system", "max_tokens", "seed", "temperature"} for c in calls)


def test_execute_refuses_unadmitted_manifest_before_output_creation(tmp_path):
    import pytest
    value = manifest(tmp_path)
    with pytest.raises(ValueError, match="execution_not_admitted"):
        runner.execute(value, canonical_bytes(value), "a" * 64, tmp_path / "forbidden")
    assert not (tmp_path / "forbidden").exists()
