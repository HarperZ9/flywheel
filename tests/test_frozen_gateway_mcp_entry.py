import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def _load_gateway_entry():
    path = Path("packaging/gateway_entry.py")
    spec = importlib.util.spec_from_file_location("gateway_entry_mcp_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_gateway_entry_mcp_mode_delegates_to_local_agent_cli(monkeypatch):
    import harness.bundled_lane_admission as bundled
    import harness.local_agent_cli as local_agent_cli

    bundled_calls = []
    cli_calls = []
    monkeypatch.setattr(
        bundled, "dispatch_bundled_lane_mcp",
        lambda argv: bundled_calls.append(tuple(argv)) or None)
    monkeypatch.setattr(
        local_agent_cli, "main", lambda argv: cli_calls.append(tuple(argv)) or 23)
    module = _load_gateway_entry()

    argv = ["--mcp", "--root", "R", "--run-root", "RR"]
    assert module.main(argv) == 23
    assert bundled_calls == [tuple(argv)]
    assert cli_calls == [tuple(argv)]


def test_gateway_entry_rejects_ambiguous_mcp_modes(monkeypatch):
    import harness.bundled_lane_admission as bundled
    import harness.gateway as gateway
    import harness.local_agent_cli as local_agent_cli

    monkeypatch.setattr(bundled, "dispatch_bundled_lane_mcp", lambda argv: None)
    monkeypatch.setattr(gateway, "main", lambda argv: (_ for _ in ()).throw(
        AssertionError("ambiguous mcp mode reached gateway")))
    monkeypatch.setattr(local_agent_cli, "main", lambda argv: (_ for _ in ()).throw(
        AssertionError("ambiguous mcp mode reached local agent cli")))
    module = _load_gateway_entry()

    cases = [
        ["--mcp", "--bundled-lane-mcp", "relay"],
        ["--mcp", "--health"],
        ["--root", "R", "--mcp"],
        ["--mcp", "--root"],
        ["--mcp", "--root", "R", "--root", "R2"],
    ]
    for argv in cases:
        assert module.main(argv) == 2


def test_gateway_entry_dispatches_only_exact_canon_context_child(monkeypatch):
    import harness.bundled_lane_admission as bundled
    import harness.gateway as gateway

    calls = []
    package = ModuleType("canon")
    package.__path__ = []
    child = ModuleType("canon.context_mcp")
    child.serve = lambda: calls.append("serve") or 41
    monkeypatch.setitem(sys.modules, "canon", package)
    monkeypatch.setitem(sys.modules, "canon.context_mcp", child)
    monkeypatch.setattr(bundled, "dispatch_bundled_lane_mcp", lambda argv: None)
    monkeypatch.setattr(gateway, "main", lambda argv: (_ for _ in ()).throw(
        AssertionError("canon context child reached gateway")))
    module = _load_gateway_entry()

    assert module.main(["--canon-context-mcp"]) == 41
    assert calls == ["serve"]


def test_gateway_entry_rejects_canon_context_selector_args(monkeypatch):
    import harness.bundled_lane_admission as bundled
    import harness.gateway as gateway

    monkeypatch.setattr(bundled, "dispatch_bundled_lane_mcp", lambda argv: None)
    monkeypatch.setattr(gateway, "main", lambda argv: (_ for _ in ()).throw(
        AssertionError("malformed canon context child reached gateway")))
    module = _load_gateway_entry()

    for argv in (
        ["--canon-context-mcp", "--module", "os"],
        ["--canon-context-mcp", "-m", "canon.context_mcp"],
        ["-m", "canon.context_mcp"],
        ["--mcp", "--canon-context-mcp"],
    ):
        assert module.main(argv) == 2


def test_gateway_entry_preserves_normal_gateway_mode(monkeypatch):
    import harness.bundled_lane_admission as bundled
    import harness.gateway as gateway

    gateway_calls = []
    monkeypatch.setattr(bundled, "dispatch_bundled_lane_mcp", lambda argv: None)
    monkeypatch.setattr(gateway, "main",
                        lambda argv: gateway_calls.append(tuple(argv)) or 31)
    module = _load_gateway_entry()

    assert module.main(["--port", "0"]) == 31
    assert gateway_calls == [("--port", "0")]


def test_pyinstaller_spec_statically_includes_flywheel_mcp_modules():
    spec = Path("packaging/flywheel-gateway.spec").read_text(encoding="utf-8")

    assert 'find_spec("harness.local_mcp")' in spec
    assert "frozen MCP import shadowed outside harness" in spec
    assert '"harness.local_agent_cli"' in spec
    assert '"harness.local_mcp"' in spec
    assert '"harness.receipt_operations"' in spec
