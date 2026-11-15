"""The five series and voice tools are listed locally, run sealed, and read a
stored voice profile without writing anything."""
import json

import pytest

from articulate import local_mcp, tool_meta, tool_text
from voice_fixtures import SCAFFOLD_ESSAY, VARIED, templated_docs

NEW_TOOLS = ["corpus_check", "title_workshop", "interview", "restructure_plan", "voice_compare"]
PLUGIN_ENV = {"ARTICULATE_MCP_TOOLS": "local", "ARTICULATE_LOCAL_ONLY": "1"}


def _call(name, arguments):
    response = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": name, "arguments": arguments}})
    return response["result"]


def _payload(result):
    return json.loads(result["content"][0]["text"])


@pytest.mark.parametrize("environ", [PLUGIN_ENV, {}])
def test_new_tools_are_listed_with_local_hints(environ):
    listed = {t["name"]: t for t in local_mcp.listed_tools(environ)}
    for name in NEW_TOOLS:
        hints = listed[name]["annotations"]
        assert hints["readOnlyHint"] is True and hints["openWorldHint"] is False
        assert name in tool_meta.TITLES and name in tool_text.TOOLS
        assert "edits none of your files" in listed[name]["description"]


def test_corpus_check_returns_findings_and_a_receipt():
    out = _payload(_call("corpus_check", {"documents": templated_docs()}))
    assert out["findings"] and out["receipt"]["schema"] == "articulate/corpus-receipt/v2"


def test_title_workshop_returns_families_and_questions():
    out = _payload(_call("title_workshop", {"titles": ["The Map Is Not the Road",
                                                       "The Vote Is Not the Law"]}))
    assert out["families"] and out["questions"] and out["suggestions"] == []


def test_interview_and_restructure_tools():
    qs = _payload(_call("interview", {"text": SCAFFOLD_ESSAY}))
    assert qs["questions"]
    plan = _payload(_call("restructure_plan", {"text": SCAFFOLD_ESSAY}))
    assert plan["verdict"]["ok"] and plan["proposal"] != SCAFFOLD_ESSAY


def test_voice_compare_reads_a_stored_profile(monkeypatch, tmp_path):
    from articulate import voice, voice_identity, voice_store
    voice_identity.ensure_identity(tmp_path)
    voice_store.save(voice_identity.bind(voice.build_profile([t for _, _, t in VARIED]), tmp_path),
                     "mine", tmp_path)
    monkeypatch.setenv("ARTICULATE_VOICE_DIR", str(tmp_path))
    out = _payload(_call("voice_compare", {"text": SCAFFOLD_ESSAY, "voice_name": "mine"}))
    assert out["schema"] == "articulate/voice-compare/v2" and out["features"]


def test_voice_compare_with_a_missing_profile_is_a_tool_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTICULATE_VOICE_DIR", str(tmp_path))
    result = _call("voice_compare", {"text": SCAFFOLD_ESSAY, "voice_name": "nobody"})
    assert result["isError"] is True
    assert "voice learn" in result["content"][0]["text"]


def test_no_tool_accepts_samples_to_learn_from():
    names = {t["name"] for t in local_mcp.TOOLS}
    assert "voice_learn" not in names
    for tool in local_mcp.TOOLS:
        assert "samples" not in tool["inputSchema"]["properties"], tool["name"]


@pytest.mark.parametrize("name,args", [
    ("corpus_check", {"documents": "not a list"}),
    ("corpus_check", {"documents": [{"name": "a"}]}),
    ("title_workshop", {"titles": [1, 2]}),
    ("interview", {}),
    ("restructure_plan", {"text": "x", "anchors": "bogus"}),
    ("voice_compare", {"text": "x"}),
])
def test_bad_arguments_are_tool_errors(name, args):
    assert _call(name, args)["isError"] is True


def test_doctor_lists_the_new_tools_as_local():
    doctor = _payload(_call("articulate.doctor", {}))
    assert set(NEW_TOOLS) <= set(doctor["local_only"])
