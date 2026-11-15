"""`articulate dialogue` on the command line and `dialogue_check` over MCP."""
import json

from articulate import cli, local_mcp

SCRIPT = "\n".join(
    ["@node quay.a", "speaker: KEEL"]
    + [f"line: The Board has counted the {n} lamps on the quay, assessor." for n in range(25)]
    + ["@node quay.b"]
    + [f"line: WENNA: She's got her eye shut, love. Stairs {n}." for n in range(25)]
    + ["line: WENNA: Mercy is a tide. Ask about the works order."]) + "\n"
SHEET = {"name": "WENNA", "register": {"level": "plain"},
         "knowledge": {"unknown": [{"terms": ["works order"], "why": "Keel's secret"}]}}


def _setup(tmp_path):
    act = tmp_path / "content" / "act1"
    act.mkdir(parents=True)
    (act / "quay.lwd").write_text(SCRIPT, encoding="utf-8")
    hidden = tmp_path / "content" / ".old"
    hidden.mkdir()
    (hidden / "quay.lwd").write_text("line: KEEL: An old draft the walk must skip.\n")
    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "wenna.json").write_text(json.dumps(SHEET), encoding="utf-8")
    return tmp_path / "content", voices


def test_cli_json_report(tmp_path, capsys):
    content, voices = _setup(tmp_path)
    assert cli.main(["dialogue", str(content), "--voices", str(voices), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["lines"] == 51                      # the hidden folder is skipped
    assert set(report["speakers"]) == {"KEEL", "WENNA"}
    assert report["checks"]["knowledge-leak"] == 1
    assert report["groups"]["act1"]["epigram_lines"] == 1
    assert report["gate"]["passed"] is False


def test_cli_table_gate_and_markdown(tmp_path, capsys):
    content, voices = _setup(tmp_path)
    md = tmp_path / "audit.md"
    code = cli.main(["dialogue", str(content), "--voices", str(voices), "--gate",
                     "--markdown", str(md)])
    out = capsys.readouterr().out
    assert code == 1 and "gate: failed" in out and "WENNA" in out
    text = md.read_text(encoding="utf-8")
    for heading in ("## Worst lines by score", "## Distinctiveness per character",
                    "## Epigram-flagged lines per group", "## Reading these numbers"):
        assert heading in text
    assert "Mercy is a tide." in text


def test_cli_gate_passes_clean_script(tmp_path):
    f = tmp_path / "plain.txt"
    f.write_text("ANNA: Kettle's on.\nBEN: Ta.\nANNA: Sugar?\nBEN: Two.\n", encoding="utf-8")
    assert cli.main(["dialogue", str(f), "--gate"]) == 0


def test_cli_reports_missing_inputs(tmp_path, capsys):
    empty = tmp_path / "empty.txt"
    empty.write_text("no speakers here\n", encoding="utf-8")
    assert cli.main(["dialogue", str(empty)]) == 2
    assert cli.main(["dialogue", str(empty), "--voices", str(tmp_path / "nope")]) == 2
    assert "voices folder not found" in capsys.readouterr().err


def _call(args):
    resp = local_mcp.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                             "params": {"name": "dialogue_check", "arguments": args}})
    return resp["result"]


def test_mcp_dialogue_check_is_listed_and_local():
    names = [t["name"] for t in local_mcp.TOOLS]
    assert "dialogue_check" in names and "dialogue_check" in local_mcp.LOCAL_ONLY


def test_mcp_dialogue_check_returns_the_report():
    result = _call({"text": SCRIPT, "voices": [SHEET]})
    assert not result.get("isError"), result
    report = json.loads(result["content"][0]["text"])
    assert report["checks"]["knowledge-leak"] == 1
    assert report["worst"][0]["speaker"] == "WENNA"
    assert all(d["findings"] for d in report["detail"])
    assert "chance for attribution" in report["summary"]


def test_mcp_dialogue_check_rejects_bad_arguments():
    assert _call({"text": 3})["isError"]
    assert _call({"text": SCRIPT, "voices": {"name": "X"}})["isError"]
