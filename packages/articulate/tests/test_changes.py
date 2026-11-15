"""The change report: changed sentences, cleared and remaining findings."""
import json

from articulate import changes, cli, host_edit, local_mcp, mcp_server


def _fake_check(rules):
    """A check that reports rule ids at the offsets of marker words."""
    def check(text):
        found = []
        for word, rule in rules.items():
            pos = text.find(word)
            while pos != -1:
                found.append({"rule_id": rule, "label": rule + " label", "category": "x",
                              "start": pos})
                pos = text.find(word, pos + 1)
        return {"high": found, "medium": [], "low": []}
    return check


def test_changed_sentence_lists_gone_and_remaining_findings():
    original = "Alpha stays here. Beta has foo and bar now.\n\nGamma is untouched."
    final = "Alpha stays here. Beta has bar now.\n\nGamma is untouched."
    rep = changes.build(original, final, _fake_check({"foo": "r/foo", "bar": "r/bar"}))
    assert len(rep["sentences"]) == 1
    rec = rep["sentences"][0]
    assert rec["paragraph"] == 0 and rec["op"] == "replace" and rec["line"] == 1
    assert rec["before"] == "Beta has foo and bar now." and rec["after"] == "Beta has bar now."
    assert rec["findings_gone"] == [{"rule_id": "r/foo", "label": "r/foo label"}]
    assert rec["findings_remaining"] == [{"rule_id": "r/bar", "label": "r/bar label"}]
    assert rec["findings_added"] == []
    assert rep["schema"] == changes.SCHEMA and rep["scope"]


def test_unchanged_text_has_no_records_and_new_findings_are_added():
    text = "One sentence. Two sentence."
    assert changes.build(text, text, _fake_check({}))["sentences"] == []
    rep = changes.build("Plain words here.", "Plain foo here.", _fake_check({"foo": "r/foo"}))
    assert rep["sentences"][0]["findings_added"] == [{"rule_id": "r/foo", "label": "r/foo label"}]
    assert rep["sentences"][0]["findings_gone"] == []


def test_second_paragraph_change_is_located_in_that_paragraph():
    original = "First one.\n\nSecond foo one."
    rep = changes.build(original, "First one.\n\nSecond one.", _fake_check({"foo": "r/foo"}))
    rec = rep["sentences"][0]
    assert rec["paragraph"] == 1 and rec["line"] == 3
    assert rec["findings_gone"][0]["rule_id"] == "r/foo"


def test_refused_paragraphs_and_allowed_changes_are_reported():
    text = "We measured 14 samples on site.\n\nSee https://example.org/a for the data."
    rewrite = "We measured 15 samples on site.\n\nSee https://example.org/b for the data."
    plan = host_edit.edit_plan(text, allow_change=["number"])
    result = host_edit.edit_submit(text, rewrite, plan["plan_id"])
    rep = changes.for_result(text, result)
    assert rep["refused"] == [{"paragraph": 1, "reasons": ["url protected spans changed"]}]
    assert rep["allowed_changes"] == [{"paragraph": 0, "kind": "number"}]
    assert [r["after"] for r in rep["sentences"]] == ["We measured 15 samples on site."]
    report = changes.format_report(rep)
    assert "kept paragraph 2: url protected spans changed" in report
    assert "allowed number change in paragraph 1" in report


def test_host_plan_has_no_change_report():
    assert changes.for_result("Some text.", host_edit.edit_plan("Some text.")) is None


DASHED = "We measured 14 samples \u2014 a lot.\n\nThe second paragraph stays as written."


def _write(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(DASHED, encoding="utf-8")
    return str(path)


def test_cli_explain_json_adds_changes(tmp_path, capsys):
    assert cli.main(["fix", _write(tmp_path), "--backend", "none", "--explain"]) == 0
    result = json.loads(capsys.readouterr().out)
    rec = result["changes"]["sentences"][0]
    assert rec["before"] == "We measured 14 samples \u2014 a lot."
    assert rec["after"] == "We measured 14 samples, a lot."
    assert [f["rule_id"] for f in rec["findings_gone"]] == ["em-dash/em-dash"]


def test_cli_explain_text_prints_a_report_instead_of_json(tmp_path, capsys):
    assert cli.main(["fix", _write(tmp_path), "--backend", "none", "--explain", "text"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("[changes] ") and "gone: em-dash/em-dash" in out
    assert "Read each pair to check the meaning held." in out and not out.lstrip().startswith("{")


def test_cli_submit_takes_explain(tmp_path, capsys):
    path = _write(tmp_path)
    plan = host_edit.edit_plan(DASHED)
    rewrite = tmp_path / "rewrite.md"
    rewrite.write_text(DASHED.replace(" \u2014 a lot", ", a lot"), encoding="utf-8")
    assert cli.main(["submit", path, str(rewrite), "--plan", plan["plan_id"], "--explain"]) == 0
    assert json.loads(capsys.readouterr().out)["changes"]["summary"]["changed"] == 1


def _tool(name, args):
    resp = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": name, "arguments": args}})
    return json.loads(resp["result"]["content"][0]["text"])


def test_stdio_mcp_explain_on_fix_polish_and_edit_submit():
    schemas = {t["name"]: t["inputSchema"]["properties"] for t in local_mcp.TOOLS}
    assert all(schemas[n]["explain"]["type"] == "boolean" for n in ("fix", "polish", "edit_submit"))
    assert "changes" in _tool("fix", {"text": DASHED, "backend": "none", "explain": True})
    assert "changes" not in _tool("fix", {"text": DASHED, "backend": "none"})
    plan = host_edit.edit_plan(DASHED)
    out = _tool("edit_submit", {"text": DASHED, "rewrite": DASHED, "plan_id": plan["plan_id"],
                                "explain": True})
    assert out["changes"]["sentences"] == []
    assert "changes" in mcp_server.do_polish(DASHED, backend="none", explain=True)


def test_fastmcp_tools_take_explain():
    from test_allow_change import fastmcp_properties
    props = fastmcp_properties()
    for name in ("fix", "polish", "edit_submit"):
        assert "explain" in props[name], name
