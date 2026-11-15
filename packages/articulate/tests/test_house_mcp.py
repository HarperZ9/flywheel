"""The house tools and the CLI pipe: house_brief, house_transform and
`articulate house apply -`."""
import io
import json
import sys

import pytest

from articulate import cli, house, local_mcp, tool_meta, tool_text
from house_fixtures import RESIDUE_CLEAN, RESIDUE_REPLY

HOUSE_TOOLS = ["house_brief", "house_transform"]
VOICE_TOOLS = ["voice_apply_plan"]


def _call(name, args):
    r = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": name, "arguments": args}})
    return r["result"]


def _payload(result):
    return json.loads(result["content"][0]["text"])


@pytest.mark.parametrize("environ", [{"ARTICULATE_MCP_TOOLS": "local", "ARTICULATE_LOCAL_ONLY": "1"}, {}])
def test_tools_are_listed_read_only(environ):
    listed = {t["name"]: t for t in local_mcp.listed_tools(environ)}
    for name in HOUSE_TOOLS + VOICE_TOOLS:
        hints = listed[name]["annotations"]
        assert hints["readOnlyHint"] is True and hints["openWorldHint"] is False
        assert name in tool_meta.TITLES and name in tool_text.TOOLS
        assert "edits none of your files" in listed[name]["description"]


def test_house_brief_tool(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path))
    out = _payload(_call("house_brief", {}))
    assert out["brief"] == house.brief() and out["version"] == "house/2"
    assert out["fingerprint"].startswith("sha256:")


def test_house_transform_tool(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path))
    out = _payload(_call("house_transform", {"text": RESIDUE_REPLY}))
    assert out["text"] == RESIDUE_CLEAN
    assert out["receipt"]["schema"] == "articulate/house-receipt/v2"


def test_house_false_per_call_returns_the_text_unchanged(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path))
    out = _payload(_call("house_transform", {"text": RESIDUE_REPLY, "house": False}))
    assert out["text"] == RESIDUE_REPLY and out["receipt"]["mode"] == "off"


def test_bad_settings_are_a_tool_error():
    assert _call("house_transform", {"text": "x", "settings": {"length": "huge"}})["isError"] is True
    assert _call("house_transform", {})["isError"] is True


def test_cli_house_apply_pipes_stdin_to_stdout(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(RESIDUE_REPLY.encode("utf-8")),
                                                       encoding="utf-8"))
    assert cli.main(["house", "apply", "-"]) == 0
    assert capsys.readouterr().out == RESIDUE_CLEAN


def test_cli_house_apply_writes_a_receipt_only_when_asked(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path / "cfg"))
    src = tmp_path / "reply.md"
    src.write_text(RESIDUE_REPLY, encoding="utf-8")
    rec = tmp_path / "r.json"
    assert cli.main(["house", "apply", str(src), "--receipt", str(rec)]) == 0
    assert src.read_text(encoding="utf-8") == RESIDUE_REPLY
    assert json.loads(rec.read_text(encoding="utf-8"))["schema"] == "articulate/house-receipt/v2"
    capsys.readouterr()
    assert cli.main(["verify", str(rec), str(src)]) == 0
    assert "Match" in capsys.readouterr().out


def test_cli_brief_agents_form(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path))
    assert cli.main(["house", "brief", "--agents"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("## Articulate house voice") and house.brief() in out
