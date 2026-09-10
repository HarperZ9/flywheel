import json

import harness.gateway as gateway
from harness.desktop_status import desktop_status


NOW = "2026-09-10T12:00:00Z"
OWNER = "owner_" + "f" * 32


def test_gateway_startup_reports_malformed_export_transaction_without_state_change(
        tmp_path, monkeypatch):
    """Malformed export transaction state must not abort desktop startup."""
    fake_home = tmp_path / "home"
    state_root = fake_home / ".flywheel" / "state"
    tx_dir = state_root / "journey-exports" / "v2" / "owners" / OWNER
    tx_dir.mkdir(parents=True)
    corrupt = tx_dir / "bad.json"
    original = "{not json"
    corrupt.write_text(original, encoding="utf-8")
    monkeypatch.delenv("FLYWHEEL_HOME", raising=False)
    monkeypatch.setattr(gateway.Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setattr(gateway, "_serve_all", lambda servers: None)

    exit_code = gateway.main(["--port", "0", "--root", str(tmp_path)])

    ref = corrupt.relative_to(state_root).as_posix()
    recovery = gateway._Handler.startup_recovery["journeys"]
    status = desktop_status({"n_lanes": 0, "by_status": {"live": 0}},
                            startup_recovery=gateway._Handler.startup_recovery)
    assert exit_code == 0
    assert recovery["completed"] == 0
    assert ref in recovery["diagnostic_refs"]
    assert "recovery_limited" not in recovery
    assert status["startup_recovery"]["journeys"]["diagnostic_count"] == 1
    assert "X:/private-state/secret" not in json.dumps(recovery)
    assert corrupt.read_text(encoding="utf-8") == original
