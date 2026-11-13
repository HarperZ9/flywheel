"""Falsifiers for the first-run surface: help that lists every real command,
an unknown command named as unknown, a `down` that says what it cannot do, a
`why` that reads what `gate` writes, and start documents that match the code."""
import json
import re
from pathlib import Path

import pytest

from harness import cli_entry, cli_help
from harness.capture_hooks import client as capture_client
from harness.gate import run_gate
from harness.why import WhyError, explain, render

ROOT = Path(__file__).resolve().parent.parent


def _no_repo():
    raise FileNotFoundError("no checkout")


def test_every_command_the_dispatcher_accepts_has_a_description():
    real = set(cli_entry._PACKAGED) | set(cli_entry._UMBRELLA_COMMANDS) | {"app"}
    assert set(cli_help.COMMANDS) == real
    assert all(line and len(line) < 75 for line in cli_help.COMMANDS.values())


def test_checkout_only_list_matches_the_script_parser():
    text = (ROOT / "scripts" / "run_harness_cli.py").read_text(encoding="utf-8")
    names = set(re.findall(r'subparsers\.add_parser\(\s*"([a-z0-9-]+)"', text))
    assert names - set(cli_help.COMMANDS) == set(cli_help.CHECKOUT_ONLY)


@pytest.mark.parametrize("checkout", [True, False])
def test_help_lists_every_command_with_a_line_in_and_out_of_a_checkout(
        checkout, monkeypatch, capsys):
    if not checkout:
        monkeypatch.setattr(cli_entry, "find_repo_root", _no_repo)
    assert cli_entry.main(["--help"]) == 0
    out = capsys.readouterr().out
    for name in ("setup", "auth", "mcp", "plugin", "update", "app", "code", "gate"):
        assert re.search(rf"^  {name}\s+\S", out, re.M), name
    assert all(name in out for name in cli_help.COMMANDS)


def test_bare_flywheel_is_an_error_that_still_shows_the_list(capsys):
    assert cli_entry.main([]) == 2
    assert "usage: flywheel <command>" in capsys.readouterr().err


@pytest.mark.parametrize("typed,meant", [("verify", "gate"), ("status", "doctor"),
                                         ("setpu", "setup"), ("lane", "lanes")])
def test_an_unknown_command_is_named_unknown_with_the_nearest_one(
        typed, meant, monkeypatch, capsys):
    monkeypatch.setattr(cli_entry, "find_repo_root", _no_repo)
    assert cli_entry.main([typed]) == 2
    err = capsys.readouterr().err
    assert f"`flywheel {typed}` is not a command" in err
    assert f"Did you mean `flywheel {meant}`?" in err
    assert "source checkout" not in err


def test_a_checkout_command_still_says_it_needs_a_checkout(monkeypatch, capsys):
    monkeypatch.setattr(cli_entry, "find_repo_root", _no_repo)
    assert cli_entry.main(["package-doctor"]) == 2
    assert "requires a source checkout" in capsys.readouterr().err


def test_down_with_nothing_running_says_so(monkeypatch, capsys):
    def absent(home):
        raise capture_client.CaptureFailure("GATEWAY_NOT_RUNNING")
    monkeypatch.setattr(capture_client, "read_endpoint", absent)
    assert cli_entry.main(["down"]) == 0
    assert "nothing to stop" in capsys.readouterr().out


def test_down_names_a_running_gateway_and_what_it_cannot_do(monkeypatch, capsys):
    monkeypatch.setattr(capture_client, "read_endpoint",
                        lambda home: {"host": "127.0.0.1", "port": 8799, "pid": 4242})
    assert cli_entry.main(["down"]) == 1
    err = capsys.readouterr().err
    assert "http://127.0.0.1:8799" in err and "cannot stop it" in err and "Ctrl-C" in err


def test_why_reads_the_record_gate_writes(tmp_path, capsys):
    assert run_gate(tmp_path).rewitness == "MATCH"
    answer = explain(tmp_path / "gate_envelope.json")
    assert answer["kind"] == "gate" and answer["report"] == {
        "present": True, "agrees": True, "rewitness": "MATCH"}
    assert explain(tmp_path)["claim"] == answer["claim"]
    assert cli_entry.main(["why", str(tmp_path / "gate_envelope.json")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("PASS on gate-matmul-2x2x2 (gate record, unsigned)")
    assert "what would change it:" in out and "scope:" in out
    assert out.index("what would change it:") < out.index("what decided it:")


def test_why_reports_drift_when_the_report_names_another_envelope(tmp_path):
    run_gate(tmp_path)
    path = tmp_path / "gate_envelope.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["verdict"] = "FAIL"
    path.write_text(json.dumps(record), encoding="utf-8")
    text = render(explain(path))
    assert text.startswith("FAIL on") and "DRIFT between the two files" in text
    (tmp_path / "gate_report.json").unlink()
    assert "no gate_report.json beside it" in render(explain(path))


def test_why_still_refuses_a_file_that_is_neither_record(tmp_path):
    other = tmp_path / "notes.json"
    other.write_text(json.dumps({"task_id": "x", "verdict": "PASS"}), encoding="utf-8")
    with pytest.raises(WhyError, match="not a receipt envelope"):
        explain(other)


def _doc(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_quickstart_names_the_current_release_and_pins_no_download():
    version = re.search(r'^version\s*=\s*"(.+?)"', _doc("pyproject.toml"), re.M).group(1)
    text = _doc("QUICKSTART.md")
    assert f"current release is `{version}`" in text, "bump QUICKSTART.md with the version"
    assert not re.findall(r"releases/(?:tag|download)/v\d", text)


@pytest.mark.parametrize("name", ["README.md", "QUICKSTART.md", "GETTING-STARTED.md"])
def test_start_documents_say_where_the_gateway_token_is(name):
    text = _doc(name)
    assert "gateway.token" in text and "Authorization: Bearer" in text


def test_quickstart_curl_examples_send_the_token():
    blocks = re.findall(r"```\n(curl .*?)```", _doc("QUICKSTART.md"), re.S)
    assert blocks and all("Authorization: Bearer" in block for block in blocks)


def test_getting_started_matches_the_code_for_claude_sign_in():
    from harness.oauth_profiles import PROFILES
    text = _doc("GETTING-STARTED.md")
    assert PROFILES["anthropic"].kind == "official-cli"
    assert "setup-token" not in text and "claude auth login" in text
    assert "flywheel auth use openai work" in text
