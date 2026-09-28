"""The Flywheel Verify MCP server: protocol, check_answer, packs, and no side effects.

Falsifiers first. A contract whose table disagrees must never come back PASS, a
source nobody supplied must never come back PASS, and no tool may reach a file
write, a socket, or a process, which is checked by making each of those raise.
"""
from __future__ import annotations

import builtins
import io
import json
import os
import socket
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from harness import check_mcp
from harness.check_mcp_tools import MAX_FIELDS

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = {"fields": [{"name": "rate", "authority": "TABLE", "source": "rates"}],
            "authorities": {"rates": {"kind": "table", "path": "rates.json",
                                      "key_field": "plan"}}}
SOURCES = {"rates.json": {"basic": 10, "pro": 25}}


def _answer(rate, plan="basic"):
    return {"plan": {"value": plan}, "rate": {"value": rate, "source": "rates"}}


def rpc(method, params=None, rid=1):
    req = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        req["params"] = params
    return check_mcp.handle_request(req)


def call(tool, **arguments):
    result = rpc("tools/call", {"name": tool, "arguments": arguments})["result"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result


def payload(tool, **arguments):
    result = call(tool, **arguments)
    assert not result.get("isError"), result
    return result["structuredContent"]


def refusal(tool, **arguments):
    result = call(tool, **arguments)
    assert result["isError"] is True
    return result["structuredContent"]["error"]


# --- protocol -------------------------------------------------------------

def test_initialize_negotiates_and_reports_the_package_version():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    asked = rpc("initialize", {"protocolVersion": "2025-03-26"})["result"]
    assert asked["protocolVersion"] == "2025-03-26"
    assert asked["serverInfo"] == {"name": "flywheel-check", "title": "Flywheel Verify",
                                   "version": project["project"]["version"]}
    unknown = rpc("initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert unknown["protocolVersion"] == check_mcp.PROTOCOLS[0]


def test_ping_notifications_and_unknown_methods():
    assert rpc("ping")["result"] == {}
    assert check_mcp.handle_request({"jsonrpc": "2.0",
                                     "method": "notifications/initialized"}) is None
    assert rpc("resources/list")["error"]["code"] == -32601
    assert rpc("tools/call", {"name": "rm_rf", "arguments": {}})["error"]["code"] == -32602
    assert check_mcp.handle_request([1, 2])["error"]["code"] == -32600


def test_serve_answers_a_parse_error_and_keeps_serving(capsys):
    lines = "not json\n" + json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}) + "\n"
    out = io.StringIO()
    assert check_mcp.serve(io.StringIO(lines), out) == 0
    first, second = [json.loads(line) for line in out.getvalue().splitlines()]
    assert first["error"]["code"] == -32700 and first["id"] is None
    assert second == {"jsonrpc": "2.0", "id": 7, "result": {}}
    assert "unparsable request line" in capsys.readouterr().err


def test_tool_list_is_the_three_read_only_tools():
    tools = rpc("tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == ["check_answer", "domain_packs", "verify_bundle"]
    assert all(t["annotations"]["readOnlyHint"] is True for t in tools)
    assert all(t["annotations"]["openWorldHint"] is False for t in tools)


# --- check_answer ---------------------------------------------------------

def test_an_answer_that_matches_its_table_passes_and_releases():
    out = payload("check_answer", contract=CONTRACT, answer=_answer(10), sources=SOURCES)
    assert (out["verdict"], out["release"], out["blocking"]) == ("PASS", "RELEASE", [])
    assert "fields" not in out and out["next"] == []
    assert any("does not show that the source is right" in s for s in out["does_not_prove"])


def test_a_contract_whose_table_disagrees_never_comes_back_pass():
    out = payload("check_answer", contract=CONTRACT, answer=_answer(12), sources=SOURCES)
    assert out["verdict"] == "FAIL"
    assert out["next"][0]["code"] == "DISAGREES"
    assert "10" not in out["next"][0]["do"]    # the fix points at the source, not the value


def test_a_critical_field_that_fails_blocks_release():
    contract = {**CONTRACT, "fields": [{**CONTRACT["fields"][0], "criticality": "critical"}]}
    out = payload("check_answer", contract=contract, answer=_answer(12), sources=SOURCES)
    assert (out["release"], out["blocking"]) == ("HOLD", ["rate"])


def test_a_source_nobody_supplied_is_unverifiable_not_pass():
    out = payload("check_answer", contract=CONTRACT, answer=_answer(10), sources={},
                  detail="full")
    assert out["verdict"] == "UNVERIFIABLE"
    assert out["fields"][0]["code"] == "AUTHORITY_UNAVAILABLE"


def test_command_authorities_are_never_run(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("a command authority reached subprocess")
    monkeypatch.setattr(subprocess, "run", refuse)
    contract = {"fields": [{"name": "tax", "authority": "TABLE", "source": "irs"}],
                "authorities": {"irs": {"kind": "command", "argv": ["python", "tax.py"]}}}
    out = payload("check_answer", contract=contract,
                  answer={"tax": {"value": 4169, "source": "irs"}})
    assert out["verdict"] == "UNVERIFIABLE"
    assert out["commands_not_run"] == ["irs"]
    assert "--allow-commands" in out["commands_note"]


def test_a_pack_name_is_never_read_as_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evil.json").write_text("{}", encoding="utf-8")
    error = refusal("check_answer", contract={**CONTRACT, "pack": "evil.json"},
                    answer=_answer(10), sources=SOURCES)
    assert error["code"] == "UNKNOWN_PACK"


def test_a_shipped_pack_supplies_the_method_the_domain_mandates():
    contract = {"pack": "finance",
                "fields": [{"use": "statutory_amount", "name": "tax", "source": "irs"}],
                "authorities": {"irs": {"kind": "table", "path": "tax.json",
                                        "key_field": "income"}}}
    tax = {"value": 4169, "source": "irs"}
    args = dict(contract=contract, sources={"tax.json": {"36700": 4169}})
    unstated = payload("check_answer", answer={"income": {"value": 36700}, "tax": tax},
                       **args)
    assert (unstated["verdict"], unstated["next"][0]["code"]) == (
        "UNVERIFIABLE", "METHOD_UNSTATED")
    stated = payload("check_answer", **args, answer={
        "income": {"value": 36700}, "tax": {**tax, "method": "table-lookup"}})
    assert (stated["verdict"], stated["release"]) == ("PASS", "RELEASE")


@pytest.mark.parametrize("arguments,code", [
    ({"answer": {}}, "INVALID_ARGUMENTS"),
    ({"contract": CONTRACT, "answer": []}, "INVALID_ARGUMENTS"),
    ({"contract": {"fields": []}, "answer": {}}, "INVALID_CONTRACT"),
    ({"contract": {"fields": CONTRACT["fields"], "authorities": []}, "answer": {}},
     "INVALID_CONTRACT"),
    ({"contract": {**CONTRACT, "fields": [{"name": "x", "authority": "GUESS",
                                           "source": "rates"}]}, "answer": {}},
     "INVALID_CONTRACT"),
    ({"contract": CONTRACT, "answer": {}, "detail": "everything"}, "INVALID_ARGUMENTS"),
    ({"contract": CONTRACT, "answer": {}, "sources": {"rates.json": 5}}, "INVALID_SOURCES"),
    ({"contract": {**CONTRACT, "fields": CONTRACT["fields"] * (MAX_FIELDS + 1)},
      "answer": {}}, "TOO_LARGE"),
    ({"contract": CONTRACT, "answer": {"blob": {"value": "x" * 300_000}}}, "TOO_LARGE"),
])
def test_bad_requests_are_refused_with_an_actionable_code(arguments, code):
    error = refusal("check_answer", **arguments)
    assert error["code"] == code
    assert len(error["message"]) > 20


def test_caller_strings_are_clipped_in_the_reply():
    name = "f" * 10_000
    contract = {"fields": [{"name": name, "authority": "TABLE", "source": "rates"}],
                "authorities": CONTRACT["authorities"]}
    out = payload("check_answer", contract=contract, answer={}, detail="full")
    assert max(len(s) for s in out["unresolved"] + [out["next"][0]["reason"]]) < 320


# --- domain_packs -----------------------------------------------------------

def test_domain_packs_lists_and_describes_without_data():
    listed = payload("domain_packs")
    assert [p["name"] for p in listed["packs"]] == ["finance", "law", "medicine"]
    medicine = payload("domain_packs", name="medicine")
    assert "not a clinical authority" in medicine["caution"]
    assert {f["use"] for f in medicine["fields"]} >= {"dose", "maximum", "route"}
    assert all("value" not in f for f in medicine["fields"])
    assert refusal("domain_packs", name="astrology")["code"] == "UNKNOWN_PACK"


# --- no side effects ------------------------------------------------------------

def test_no_tool_writes_a_file_opens_a_socket_or_starts_a_process(tmp_path, monkeypatch):
    real_open = builtins.open
    touched = []

    def guarded_open(file, mode="r", *a, **k):
        if any(flag in mode for flag in "wax+"):
            touched.append(("open", str(file), mode))
            raise AssertionError(f"write-mode open of {file}")
        return real_open(file, mode, *a, **k)

    def forbidden(label):
        def fail(*_a, **_k):
            touched.append((label,))
            raise AssertionError(label)
        return fail

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(subprocess, "Popen", forbidden("Popen"))
    monkeypatch.setattr(socket, "socket", forbidden("socket"))
    monkeypatch.setattr(Path, "write_text", forbidden("write_text"))
    monkeypatch.setattr(Path, "write_bytes", forbidden("write_bytes"))
    monkeypatch.setattr(Path, "mkdir", forbidden("mkdir"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload("check_answer", contract=CONTRACT, answer=_answer(12), sources=SOURCES,
            detail="full")
    payload("domain_packs", name="law")
    payload("verify_bundle", path="nowhere")
    assert touched == []

    # The control: the guard does catch a write when one happens.
    with pytest.raises(AssertionError):
        open(tmp_path / "x.txt", "w")
    assert touched and touched[-1][0] == "open"


# --- UTF-8 over a real pipe ---------------------------------------------------
# A Windows pipe decodes stdin with the console code page. A plain echo hides
# that, because the wrong decode round-trips byte for byte, so this request makes
# the server work on characters: the table key arrives as a JSON escape (plain
# ASCII bytes) and the same key in the answer arrives as raw UTF-8. Only a UTF-8
# read makes them equal. The second field's name is outside cp1252, so writing
# it back also needs a UTF-8 stdout.
KEY = "Árbol"              # A-acute: its UTF-8 holds a byte cp1252 lacks
FAR = "日本 → x"     # CJK and an arrow: no cp1252 mapping at all


def _mixed_line() -> bytes:
    contract = {"fields": [CONTRACT["fields"][0],
                           {"name": FAR, "authority": "CITED", "source": "handbook"}],
                "authorities": {**CONTRACT["authorities"], "handbook": {"kind": "citation"}}}
    escaped = json.dumps({"contract": contract, "sources": {"rates.json": {KEY: 10}}})
    raw = json.dumps({"plan": {"value": KEY}, "rate": {"value": 10, "source": "rates"}},
                     ensure_ascii=False)
    args = escaped[:-1] + ', "answer": ' + raw + "}"
    line = ('{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": '
            '{"name": "check_answer", "arguments": ' + args + "}}\n")
    return line.encode("utf-8")


def _spawn(argv) -> tuple[int, dict | None, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONUTF8", "PYTHONIOENCODING", "PYTHONPATH")}
    done = subprocess.run(argv, input=_mixed_line(), capture_output=True, cwd=ROOT,
                          env=env, timeout=60, check=False)
    try:
        reply = json.loads(done.stdout.decode("utf-8"))["result"]["structuredContent"]
    except (ValueError, KeyError, TypeError):
        reply = None
    return done.returncode, reply, done.stderr.decode("utf-8", "replace")


def _round_tripped(reply) -> bool:
    return bool(reply) and reply["passed"] == 1 and reply["unresolved"] == [FAR]


def test_non_ascii_requests_round_trip_over_a_pipe():
    code, reply, err = _spawn([sys.executable, "-m", "harness.check_mcp"])
    assert code == 0, err
    assert _round_tripped(reply), reply


@pytest.mark.skipif(os.name != "nt", reason="the code-page decode happens on Windows pipes")
def test_the_pipe_check_catches_the_server_without_its_utf8_setup():
    without = ("import harness.check_mcp as m\n"
               "m._utf8 = lambda stream: None\n"
               "raise SystemExit(m.serve())\n")
    code, reply, _err = _spawn([sys.executable, "-c", without])
    assert code != 0 or not _round_tripped(reply)
