"""Synthetic process controls; no browser or external runtime is started."""
import hashlib
import json
from dataclasses import replace

import pytest

from harness.cross_harness_process import ProcessOutcome
from harness.telos_browser_config import BrowserConfig, ConfigError
from harness.telos_browser_adapter import TelosBrowserAdapter, AdapterUnknown
from harness.telos_browser_registration import configure_telos_browser


@pytest.fixture
def config(tmp_path, monkeypatch):
    node = tmp_path / "node.exe"
    module = tmp_path / "cdp.mjs"
    node.write_bytes(b"synthetic executable, never run")
    module.write_bytes(b"synthetic module, never imported")
    monkeypatch.setattr("harness.telos_browser_config.SUPPORTED_CDP_SHA256",
                        hashlib.sha256(module.read_bytes()).hexdigest())
    return BrowserConfig.from_dict({
        "schema": "flywheel.telos-browser-config/v1", "node_path": str(node),
        "cdp_module": str(module),
        "cdp_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "port": 9229, "browser_instance": "/devtools/browser/browser-123",
        "target_id": "target-123", "allowed_origin": "https://example.test",
    })


class FakeProcess:
    def __init__(self, row=None, *, overflow=False, timeout=False):
        self.row = row or {"ok": True, "performed": True, "code": "read",
                           "observation": "owned synthetic text"}
        self.overflow, self.timeout = overflow, timeout
        self.killed = self.closed = False

    def resume(self): return True
    def capture_overflow(self): return self.overflow
    def wait(self, seconds):
        if self.timeout: return None
        return ProcessOutcome(0, json.dumps(self.row), "", 1, False)
    def signal_tree(self): self.killed = True; return True
    def close(self): self.closed = True


def action(**changes):
    return dict(kind="read", origin="https://example.test", run_id="fixture",
                request_id="fixture-1", field="", selector="", url="", **changes)


def test_frozen_binding_and_missing_config_are_explicit(config):
    assert len(config.binding_sha256) == 64
    assert replace(config, target_id="another").binding_sha256 != config.binding_sha256
    seen = []
    assert configure_telos_browser(None, register=lambda *a, **k: seen.append(a),
                                  unregister=lambda name: None)["available"] is False
    assert seen == []


@pytest.mark.parametrize("field,value", [("port", True), ("port", 0),
    ("target_id", ""), ("target_id", "../other"),
    ("allowed_origin", "https://name:secret@example.test"),
    ("allowed_origin", "https://example.test/path"),
    ("browser_instance", "/devtools/page/other")])
def test_invalid_descriptor_refused(config, field, value):
    raw = config.as_dict(); raw[field] = value
    with pytest.raises(ConfigError): BrowserConfig.from_dict(raw)


def test_injected_executor_never_claims_real_performance(config):
    process = FakeProcess(); launches = []
    def launch(*args, **kwargs): launches.append((args, kwargs)); return process
    adapter = TelosBrowserAdapter(config, launcher=launch)
    result = adapter(action())
    assert result["performed"] is False and result["code"] == "fixture_only"
    assert len(launches) == 1 and process.closed
    assert launches[0][1]["hide_window"] is True
    assert "NODE_OPTIONS" not in launches[0][1]["env"]


@pytest.mark.parametrize("change", [{"kind": "type"}, {"kind": "click"},
    {"origin": "https://other.test"}, {"kind": "navigate", "url": "file:///a"}])
def test_unsupported_or_wrong_origin_never_launches(config, change):
    seen = []
    adapter = TelosBrowserAdapter(config, launcher=lambda *a, **k: seen.append(a))
    wanted = action(); wanted.update(change)
    assert adapter(wanted)["performed"] is False
    assert seen == []


def test_runtime_drift_fails_before_launch(config):
    from pathlib import Path
    Path(config.cdp_module).write_text("changed", encoding="utf-8")
    seen = []; adapter = TelosBrowserAdapter(config, launcher=lambda *a, **k: seen.append(a))
    assert adapter(action())["performed"] is False
    assert not seen


@pytest.mark.parametrize("mode", ["overflow", "timeout", "malformed"])
def test_uncertain_process_is_killed_and_never_retried(config, mode):
    process = FakeProcess(overflow=mode == "overflow", timeout=mode == "timeout")
    if mode == "malformed": process.row = {"ok": True}
    calls = []
    def launch(*a, **k): calls.append(a); return process
    adapter = TelosBrowserAdapter(config, launcher=launch, timeout_seconds=.01)
    with pytest.raises(AdapterUnknown): adapter(action())
    assert len(calls) == 1 and process.closed
    if mode != "malformed": assert process.killed


@pytest.mark.parametrize("row", [
    {"ok": False, "performed": False, "code": "read"},
    {"ok": True, "performed": True, "code": "navigation_requested"},
    {"ok": True, "performed": True, "code": "read", "observation": 7},
    {"ok": True, "performed": True, "code": "read", "observation": "text", "private_path": "hidden"},
    {"ok": True, "performed": True, "code": "read", "observation": "\u00e9" * 9000},
])
def test_wrong_or_extra_terminal_fields_cannot_acknowledge_action(config, row):
    process = FakeProcess(row)
    adapter = TelosBrowserAdapter(config, launcher=lambda *a, **k: process)
    with pytest.raises(AdapterUnknown): adapter(action())


def test_late_exit_and_cleanup_error_cannot_escape_as_success(config, monkeypatch):
    process = FakeProcess()
    times = iter([0, 0, 0, 11])
    with monkeypatch.context() as clock:
        clock.setattr("harness.telos_browser_adapter.time.monotonic", lambda: next(times))
        with pytest.raises(AdapterUnknown):
            TelosBrowserAdapter(config, launcher=lambda *a, **k: process)(action())
    def broken_close(): raise OSError("private local path must not escape")
    process.close = broken_close
    with pytest.raises(AdapterUnknown, match="^browser_delivery_unknown$"):
        TelosBrowserAdapter(config, launcher=lambda *a, **k: process)(action())


def test_registration_passes_digest_and_does_no_discovery(config, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config.as_dict()), encoding="utf-8")
    seen = []
    status = configure_telos_browser(str(path), register=lambda *a, **k: seen.append((a, k)),
                                    unregister=lambda name: None)
    assert status["available"] and status["code"] == "configured_not_runtime_verified"
    assert seen[0][0][0] == "telos-browser"
    assert seen[0][1] == {"binding_sha256": config.binding_sha256}


def test_arbitrary_configured_module_not_a_supported_runtime(config, monkeypatch):
    monkeypatch.setattr("harness.telos_browser_config.SUPPORTED_CDP_SHA256", "0" * 64)
    with pytest.raises(ConfigError, match="runtime_not_supported"):
        config.verify_runtime()


@pytest.mark.parametrize("next_config", [None, "missing-config.json"])
def test_reconfiguration_cannot_leave_old_driver_live(config, tmp_path, next_config):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config.as_dict()), encoding="utf-8")
    registry = {"another-driver": object()}
    def register(name, run, **kwargs): registry[name] = run
    def unregister(name): registry.pop(name, None)
    assert configure_telos_browser(str(path), register=register, unregister=unregister)["available"]
    assert "telos-browser" in registry
    assert not configure_telos_browser(next_config, register=register, unregister=unregister)["available"]
    assert "telos-browser" not in registry
    assert "another-driver" in registry


def test_failed_removal_reports_unknown_without_registering(config):
    seen = []
    def broken(name): raise OSError("private registry failure")
    status = configure_telos_browser(None, register=lambda *a, **k: seen.append(a), unregister=broken)
    assert status == {"available": None, "code": "registration_state_unknown", "driver": None}
    assert not seen
