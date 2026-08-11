"""probe_plugin must carry the full tool spec (name + description + inputSchema),
not just a flattened name list, so a caller (the desktop) can build an args form
instead of a blind {} box. `tools` stays a sorted name list for back-compat."""
import harness.plugins as pl
import harness.mcp_client as mc
from harness.mcp_client import LaunchSpec


class _FakeClient:
    _canned = [
        {"name": "b_tool", "description": "does B",
         "inputSchema": {"type": "object",
                         "properties": {"x": {"type": "string"}},
                         "required": ["x"]}},
        {"name": "a_tool", "description": "does A",
         "inputSchema": {"type": "object", "properties": {}}},
    ]
    launch = None

    def __init__(self, launch, **kwargs):
        type(self).launch = launch

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def start(self):
        pass

    def close(self):
        pass

    def stderr_tail(self):
        return ""

    def list_tools(self):
        return list(self._canned)


def _probe(monkeypatch):
    launch = LaunchSpec(("dummy",), "/source")
    monkeypatch.setattr(pl, "LANES", {"testlane"}, raising=False)
    monkeypatch.setattr(pl, "resolve_mcp_launch", lambda name: launch)
    monkeypatch.setattr(mc, "MCPClient", _FakeClient)
    result = pl.probe_plugin("testlane")
    assert _FakeClient.launch == launch
    return result


def test_probe_keeps_sorted_names_for_back_compat(monkeypatch):
    out = _probe(monkeypatch)
    assert out["status"] == "live"
    assert out["tools"] == ["a_tool", "b_tool"]          # sorted names, unchanged contract
    assert out["n_tools"] == 2


def test_probe_carries_full_tool_specs(monkeypatch):
    out = _probe(monkeypatch)
    specs = out["tool_specs"]
    assert [s["name"] for s in specs] == ["a_tool", "b_tool"]     # sorted, same order as names
    b = next(s for s in specs if s["name"] == "b_tool")
    assert b["description"] == "does B"
    assert b["inputSchema"]["properties"]["x"]["type"] == "string"
    assert b["inputSchema"]["required"] == ["x"]                  # schema survives the boundary
