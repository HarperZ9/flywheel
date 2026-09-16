import shutil

import harness.endpoints
import scripts.run_endpoint_auth_status as endpoint_status


def test_build_status_does_not_resolve_credentials_or_construct_backends(monkeypatch):
    """Presence status must not read keychains or build dispatch backends."""

    def forbidden(*_args, **_kwargs):
        raise AssertionError("credential resolver or backend construction was invoked")

    monkeypatch.setattr(harness.endpoints, "_k", forbidden)
    if hasattr(endpoint_status, "build_endpoints"):
        monkeypatch.setattr(endpoint_status, "build_endpoints", forbidden)
    monkeypatch.setattr(shutil, "which", lambda name: f"C:/tools/{name}" if name in {"claude.exe", "codex.cmd"} else None)
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CURSOR_CLI", "CLAUDE_CLI", "CODEX_CLI"):
        monkeypatch.delenv(name, raising=False)

    status = endpoint_status.build_status()

    assert status["summary"] == {"lanes": 5, "configured_lanes": 2, "missing_lanes": 3, "all_configured": False}
    routes = {row["lane_id"]: row for row in status["endpoint_ladder"]}
    assert routes["claude_subscription"]["configured"] is True
    assert routes["claude_api"]["configured"] is False
    assert routes["codex_subscription"]["configured"] is True
    assert routes["codex_api"]["configured"] is False
    assert routes["cursor_subscription"]["configured"] is False
    assert all(row["backends"] == [] and row["backend_count"] == 0 for row in routes.values())
