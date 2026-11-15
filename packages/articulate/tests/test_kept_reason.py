"""When fix or polish returns the original text, the result says why.

The CLI prints `kept the original: <reason>`. An MCP host cannot read stdout, so
the same reason is a result field, `kept_original_reason`, on every surface:
the local-only MCP path, the default MCP path and run_edit.
"""
import pytest

from articulate import editing, mcp_server

CLEAN = "The build runs at night. The cache clears each week."
EDITABLE = "Moreover, the cache clears each week. The build runs at night."


@pytest.fixture(autouse=True)
def no_backend(monkeypatch):
    monkeypatch.delenv("ARTICULATE_BACKEND", raising=False)


@pytest.mark.parametrize("local_only", [True, False])
@pytest.mark.parametrize("tool", [mcp_server.do_fix, mcp_server.do_polish])
def test_mcp_result_names_why_it_kept_the_original(monkeypatch, tool, local_only):
    if local_only:
        monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", "1")
    else:
        monkeypatch.delenv("ARTICULATE_LOCAL_ONLY", raising=False)
    result = tool(CLEAN, backend="none")
    assert result["text"] == CLEAN
    assert isinstance(result["kept_original_reason"], str) and result["kept_original_reason"]


def test_a_changed_result_carries_no_kept_reason():
    result = mcp_server.do_fix(EDITABLE, backend="none")
    assert result["text"] != EDITABLE
    assert "kept_original_reason" not in result


def test_a_refused_rewrite_names_the_refusal():
    result = editing.run_edit(CLEAN, "fix", backend="none")
    result = dict(result, refused=[{"paragraph": 0, "reasons": ["number protected spans changed"]}])
    from articulate.edit_notes import kept_reason
    assert "number protected spans changed" in kept_reason(result)


def test_run_edit_and_the_cli_reason_agree():
    from articulate import editor
    result = editing.run_edit(CLEAN, "polish", backend="none")
    assert result["kept_original_reason"] == editor._kept_reason(result)
