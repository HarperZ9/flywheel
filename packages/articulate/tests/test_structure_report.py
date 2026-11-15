"""What a reader of a result sees: the texture figure, the span, the profile.

Three misreadings are held shut here, each seen on 2026-11-15.

  texture   "texture 0/100" printed beside a blocked gate with 8 HIGH
            findings, because rule-pack findings never feed the pinned
            texture score. A result with pack findings now carries their count
            and says what the texture figure covers.
  span      a multi-sentence finding printed the start of its line. It now
            prints where the span starts and ends and its first and last words.
  profile   a session read "clean" from the default rules as permission to
            send a reply. Every MCP result now names the profile and rule
            packs that ran, and the tool descriptions say to pass "chat".

The default rules and every field that existed before keep their meaning.
"""
import json

import pytest

from articulate import checkext, cli, cli_report, edit_hook, house_hook, local_mcp, mcp_server
from articulate import tool_text
from test_pack_structure import COUNTERPART, FIXTURES, SPECIMEN_B, run

B_PATH = str(FIXTURES / "specimen_b.txt")
C_PATH = str(FIXTURES / "counterpart.txt")


def _cli(capsys, *argv):
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


# --- (a) the texture score never stands alone beside pack findings ----------

def test_check_result_counts_pack_findings_apart_from_texture():
    r = run(SPECIMEN_B)
    assert r["texture_score"] == 0 and r["gate"] == "blocked"
    assert r["pack_findings"] == {"high": 8, "medium": 4, "low": 2}
    assert len(r["low"]) == 3, "one advisory is a line-rule finding, outside the pack count"
    assert "pack_findings" not in checkext.check_text(SPECIMEN_B)
    assert run(COUNTERPART)["pack_findings"] == {"high": 0, "medium": 0, "low": 0}


def test_cli_headline_names_the_pack_findings_before_the_texture_score(capsys):
    code, out = _cli(capsys, "check", B_PATH, "--profile", "chat", "--gate")
    head = out.splitlines()[0]
    assert code == 1
    assert head.endswith("8 high, 4 medium (blocked)  rule-pack findings 12, "
                         "texture 0/100 (line rules only)"), head
    code, out = _cli(capsys, "check", C_PATH, "--profile", "chat", "--gate")
    assert code == 0 and out.splitlines()[0].endswith("[chat]: clean  texture 0/100")


def test_cli_headline_without_pack_findings_is_unchanged(capsys):
    _code, out = _cli(capsys, "check", B_PATH)
    assert out.strip().endswith("[flavored]: clean  texture 0/100")


def test_cli_score_and_spans_say_what_texture_covers(capsys):
    _code, out = _cli(capsys, "score", B_PATH, "--profile", "chat")
    assert "texture 0/100 (low; line rules only, rule-pack findings 12), gate blocked" in out
    _code, out = _cli(capsys, "score", B_PATH)
    assert "texture 0/100 (low), gate ok" in out
    _code, out = _cli(capsys, "check", B_PATH, "--profile", "chat", "--spans")
    flagged = [line for line in out.splitlines() if "[FLAG]" in line]
    assert flagged and all("rule-pack findings" in line and "(line rules only)" in line
                           for line in flagged), out


def test_cli_json_carries_the_pack_count(capsys):
    _code, out = _cli(capsys, "check", B_PATH, "--profile", "chat", "--json")
    result = json.loads(out)["results"][0]
    assert result["pack_findings"]["high"] == 8 and result["texture_score"] == 0


def test_mcp_result_adds_fields_and_keeps_the_old_ones():
    chat = mcp_server.do_check(SPECIMEN_B, None, "chat")
    assert (chat["clean"], chat["verdict"], chat["texture_score"]) == (False, "flagged", 0)
    assert chat["pack_findings"]["high"] == 8 and chat["pack_findings"]["medium"] == 4
    assert "line rules only" in chat["texture_scope"]
    score = mcp_server.do_score(SPECIMEN_B, "chat")
    assert score["texture_score"] == 0 and score["gate"] == "blocked"
    assert score["pack_findings"] == chat["pack_findings"] and "texture_scope" in score


def test_hooks_print_findings_and_no_texture_figure():
    event = {"hook_event_name": "PostToolUse", "tool_name": "Write",
             "tool_input": {"file_path": "note.md", "content": SPECIMEN_B}}
    note = edit_hook.review(event) or ""
    assert "texture" not in note
    stop = house_hook._stop({"last_assistant_message": SPECIMEN_B},
                            {"mode": "revise", "level": "standard"})
    assert stop["decision"] == "block" and "texture" not in stop["reason"]
    assert "style/structure-" in stop["reason"]


# --- (c) a finding prints its span -------------------------------------------

def test_cli_prints_where_a_span_starts_and_ends_and_its_edge_words(capsys):
    _code, out = _cli(capsys, "check", B_PATH, "--profile", "chat")
    line = next(row for row in out.splitlines() if "structure-anaphora" in row)
    start = SPECIMEN_B.index("One points at a line") + 1
    end = SPECIMEN_B.index("back to you.") + len("back to you.")
    assert line.startswith(f"  L1:{start}-L1:{end} [HIGH structure-anaphora]"), line
    assert line.endswith(": One points at a line ... next step back to you."), line
    assert "Those three sentences" not in line, "the start of the line is not the span"
    short = next(row for row in out.splitlines() if "The cause is mine." in row)
    assert short.startswith("  L5:1-L5:18 [MEDIUM ") and short.endswith(": The cause is mine.")


def test_a_span_across_wrapped_lines_names_both_lines():
    text = "Keys open doors. Keys rust\nin rain. Keys get lost in coats.\n"
    f, = [f for f in run(text)["high"] if f["category"] == "structure-anaphora"]
    assert cli_report.span_place(f) == "L1:1-L2:32"
    assert cli_report.finding_line(f).endswith(
        ": Keys open doors. Keys rust in rain. Keys get lost in coats.")


def test_line_rule_findings_and_content_free_output_keep_their_form(capsys, tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text("It is important to note that the plan works.\n", encoding="utf-8")
    _code, out = _cli(capsys, "check", str(doc))
    assert any(row.startswith("  L1 [") for row in out.splitlines()), out
    r = run(SPECIMEN_B)
    cli._redact(r)
    assert cli_report.finding_line(r["high"][0]).startswith("  L1 [HIGH structure-")


# --- (e) a result names the rules that ran -----------------------------------

def test_an_unprofiled_check_runs_the_default_rules_as_before():
    plain = mcp_server.do_check(SPECIMEN_B)
    assert plain["clean"] is True and plain["verdict"] == "clean" and plain["hits"] == []
    for absent in ("profile", "gate", "blocking_count", "pack_findings", "texture_scope"):
        assert absent not in plain, absent
    before = {"clean", "verdict", "texture_score", "elevated", "hits", "advisory_count", "cadence"}
    assert set(plain) == before | {"rules_run"}


def test_every_result_names_the_profile_and_packs_that_ran():
    plain = mcp_server.do_check(SPECIMEN_B)["rules_run"]
    assert plain["profile"] == "default" and plain["rule_packs"] == []
    assert plain["structure_rules"] is False and 'profile "chat"' in plain["note"]
    chat = mcp_server.do_check(SPECIMEN_B, None, "chat")["rules_run"]
    assert chat == {"profile": "chat", "rule_packs": ["structure"], "structure_rules": True}
    readme = mcp_server.do_check(SPECIMEN_B, None, "readme")["rules_run"]
    assert readme["profile"] == "readme" and readme["structure_rules"] is False
    assert 'profile "chat"' in readme["note"]
    assert mcp_server.do_score(SPECIMEN_B)["rules_run"] == plain
    assert mcp_server.do_score(SPECIMEN_B, "chat")["rules_run"] == chat


def test_a_clean_default_result_cannot_pass_for_a_clean_chat_result():
    plain = mcp_server.do_check(SPECIMEN_B)
    chat = mcp_server.do_check(COUNTERPART, None, "chat")
    assert plain["clean"] and chat["clean"]
    assert plain["rules_run"]["structure_rules"] is False
    assert chat["rules_run"]["structure_rules"] is True


@pytest.mark.parametrize("name", ["check", "score"])
def test_tool_descriptions_tell_a_model_to_pass_chat_for_its_own_reply(name):
    text = tool_text.TOOLS[name]
    assert 'own reply to a person should pass profile "chat"' in text
    assert "rules_run" in text
    tool = next(t for t in local_mcp.TOOLS if t["name"] == name)
    assert tool["description"] == text
    described = tool["inputSchema"]["properties"]["profile"]["description"]
    assert "own reply to a person" in described and "rules_run" in described


def test_the_stdio_tool_call_carries_rules_run():
    called = local_mcp._call({"name": "check", "arguments": {"text": SPECIMEN_B}})
    payload = json.loads(called["content"][0]["text"])
    assert payload["clean"] is True and payload["rules_run"]["profile"] == "default"
