import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_gateway_entry():
    path = Path("packaging/gateway_entry.py")
    spec = importlib.util.spec_from_file_location("gateway_entry_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_gateway_entry_dispatches_only_exact_relay_child_mode(monkeypatch):
    """Catches the frozen entrypoint ignoring the fixed child mode."""
    import harness.bundled_lane_admission as bundled

    calls = []
    monkeypatch.setattr(
        bundled, "dispatch_bundled_lane_mcp",
        lambda argv: calls.append(tuple(argv)) or 17,
    )
    module = _load_gateway_entry()

    assert module.main(["--bundled-lane-mcp", "relay"]) == 17
    assert calls == [("--bundled-lane-mcp", "relay")]


def test_gateway_entry_rejects_unknown_lane_extra_args_and_module_selectors(monkeypatch):
    """Catches arbitrary module/path dispatch from the gateway exe."""
    from harness.bundled_lane_admission import dispatch_bundled_lane_mcp

    imports = []

    def fake_import(name):
        imports.append(name)
        return SimpleNamespace(serve=lambda: 0)

    cases = [
        ["--bundled-lane-mcp", "relay", "--module", "os"],
        ["--bundled-lane-mcp", "mneme"],
        ["--bundled-lane-mcp"],
    ]
    for argv in cases:
        assert dispatch_bundled_lane_mcp(argv, import_module_fn=fake_import) == 2

    assert dispatch_bundled_lane_mcp(["-m", "relay.local_mcp"],
                                     import_module_fn=fake_import) is None
    assert imports == []
