"""`fix --backend none` applies the closed list of phrase edits.

Each edit is exact, stays out of protected spans, passes the meaning guard on
its own, and is listed in the result and the receipt. Anything else is left
for a model edit.
"""
import json
import subprocess
import sys

import pytest

from articulate import host_edit, local_mcp

SLOP = ("It is crucial to note that the build runs at night. Moreover, the cache "
        "clears each week. The team ships on Friday.\n")
CLEAN = "The build runs at night. The cache clears each week. The team ships on Friday.\n"


def test_backend_none_removes_closed_list_phrases():
    out = host_edit.deterministic_edit(SLOP, goal="fix")
    assert out["text"] == CLEAN
    rules = [(e["rule"], e["old"]) for e in out["edits"]]
    assert rules == [("phrase", "It is crucial to note that t"), ("phrase", "Moreover, t")]
    assert out["receipt"]["edits"] == out["edits"]
    assert all(e["line"] == 1 for e in out["edits"])


@pytest.mark.parametrize("opener", ["Furthermore,", "Additionally,", "In addition,",
                                    "It is important to note that", "It is worth noting that"])
def test_each_listed_opener_goes(opener):
    out = host_edit.deterministic_edit(f"The run ended. {opener} the log stays.\n", goal="fix")
    assert out["text"] == "The run ended. The log stays.\n"


@pytest.mark.parametrize("text", [
    'He wrote "Moreover, the cache clears." in the log.\n',
    "Run `Moreover, the cache` in the shell.\n",
    "The cache clears, moreover, each week.\n",
    "It is crucial to back up the data.\n",
])
def test_protected_or_unlisted_text_stays(text):
    out = host_edit.deterministic_edit(text, goal="fix")
    assert out["text"] == text
    assert out["edits"] == []


def test_an_edit_the_meaning_guard_refuses_is_dropped(monkeypatch):
    real = host_edit.guard_rewrite

    def refuse_moreover(original, rewrite, *args, **kwargs):
        if "Moreover" in original and "Moreover" not in rewrite:
            return {"text": original, "refused": [{"paragraph": 0, "reasons": ["planted"]}]}
        return real(original, rewrite, *args, **kwargs)

    from articulate import phrase_pass
    monkeypatch.setattr(phrase_pass, "guard_rewrite", refuse_moreover)
    monkeypatch.setattr(host_edit, "guard_rewrite", refuse_moreover)
    out = host_edit.deterministic_edit(SLOP, goal="fix")
    assert "Moreover, the cache" in out["text"]
    assert [e["old"] for e in out["edits"]] == ["It is crucial to note that t"]
    assert any("planted" in r["reasons"] for r in out["refused"])


def test_cli_fix_backend_none_edits(tmp_path):
    path = tmp_path / "slop.md"
    path.write_text(SLOP, encoding="utf-8")
    run = subprocess.run([sys.executable, "-m", "articulate.cli", "fix", str(path), "--backend", "none"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["text"] == CLEAN and len(result["edits"]) == 2


def test_mcp_fix_backend_none_edits():
    response = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "fix", "arguments": {"text": SLOP, "backend": "none"}}})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["text"] == CLEAN
    assert len(payload["receipt"]["edits"]) == 2
