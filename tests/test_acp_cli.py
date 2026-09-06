"""The command line: one delegated turn, and the receipt it leaves behind."""
import json
from pathlib import Path
import sys

import pytest

from harness.acp_cli import main

ROOT = Path(__file__).resolve().parents[1]

AGENT = '''
import sys
sys.path.insert(0, {root!r})
from tests.acp_fake_agent import FakeAgent, default_prompt

mode = sys.argv[1] if len(sys.argv) > 1 else "answer"
target = sys.argv[2] if len(sys.argv) > 2 else ""


def on_prompt(agent, session_id, prompt):
    if mode == "refuse":
        return "refusal"
    if mode == "read":
        agent.call("fs/read_text_file", {{"sessionId": session_id,
                                         "path": target}})
    return default_prompt(agent, session_id, prompt)


FakeAgent(on_prompt=on_prompt).serve(sys.stdin.buffer, sys.stdout.buffer)
'''


@pytest.fixture
def agent_script(tmp_path):
    script = tmp_path / "agent.py"
    script.write_text(AGENT.format(root=str(ROOT)), encoding="utf-8")
    return script


def argv(script, *extra, mode="answer", target=""):
    return ["run", "--prompt", "hello", *extra, "--",
            sys.executable, str(script), mode, target]


def read_log_records(directory):
    text = (Path(directory) / "action-witness.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_a_turn_that_ends_cleanly_exits_zero_and_prints_the_answer(
        agent_script, tmp_path, capsys):
    code = main(argv(agent_script, "--log-dir", str(tmp_path / "run")))
    assert code == 0
    printed = capsys.readouterr().out
    assert "done: hello" in printed
    assert "end_turn" in printed


def test_a_run_with_no_log_directory_says_it_left_no_record(
        agent_script, capsys):
    assert main(argv(agent_script)) == 0
    assert "this run left no record" in capsys.readouterr().out


def test_a_refusal_is_exit_one_and_not_an_error(agent_script, tmp_path, capsys):
    code = main(argv(agent_script, "--log-dir", str(tmp_path / "run"),
                     mode="refuse"))
    assert code == 1
    assert "refusal" in capsys.readouterr().out


def test_the_log_holds_a_link_for_every_frame_that_crossed(
        agent_script, tmp_path):
    directory = tmp_path / "run"
    main(argv(agent_script, "--log-dir", str(directory)))
    records = read_log_records(directory)
    methods = [r["context"].get("method") for r in records]
    assert "initialize" in methods
    assert "session/prompt" in methods
    assert records[0]["prev"] == ""
    assert all(len(r["sha256"]) == 64 for r in records)


def test_a_log_without_its_transcript_verifies_as_unverifiable(
        agent_script, tmp_path, capsys):
    directory = tmp_path / "run"
    main(argv(agent_script, "--log-dir", str(directory)))
    code = main(["verify", "--log", str(directory / "action-witness.jsonl")])
    assert code == 3
    assert "UNVERIFIABLE" in capsys.readouterr().out


def test_a_log_and_its_transcript_verify_as_a_match(
        agent_script, tmp_path, capsys):
    directory = tmp_path / "run"
    main(argv(agent_script, "--log-dir", str(directory), "--keep-bytes"))
    capsys.readouterr()
    code = main(["verify", "--log", str(directory / "action-witness.jsonl"),
                 "--transcript", str(directory / "frames.jsonl")])
    assert code == 0
    assert "MATCH" in capsys.readouterr().out


def test_an_edited_log_verifies_as_tampered_and_names_the_record(
        agent_script, tmp_path, capsys):
    directory = tmp_path / "run"
    main(argv(agent_script, "--log-dir", str(directory), "--keep-bytes"))
    capsys.readouterr()
    log = directory / "action-witness.jsonl"
    records = read_log_records(directory)
    records[2]["sha256"] = "0" * 64
    log.write_text("".join(json.dumps(r) + chr(10) for r in records),
                   encoding="utf-8")
    code = main(["verify", "--log", str(log),
                 "--transcript", str(directory / "frames.jsonl")])
    assert code == 1
    printed = capsys.readouterr().out
    assert "TAMPERED" in printed
    # Record 2 answers to nothing before it; record 3 is where the edit shows.
    assert "record 3" in printed


def test_a_transcript_that_cannot_be_read_is_unchecked_not_a_crash(
        tmp_path, capsys):
    code = main(["verify", "--log", str(tmp_path / "absent.jsonl"),
                 "--transcript", str(tmp_path / "also-absent.jsonl")])
    assert code == 3
    assert "could not be read" in capsys.readouterr().out


def test_a_file_read_is_refused_by_default_and_the_refusal_is_recorded(
        agent_script, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("do not read me", encoding="utf-8")
    directory = tmp_path / "run"
    assert main(argv(agent_script, "--log-dir", str(directory),
                     mode="read", target=str(secret))) == 0
    decisions = [r for r in read_log_records(directory)
                 if r["context"]["action"] == "acp/decision"]
    assert [d["context"]["allowed"] for d in decisions] == [False]
    assert decisions[0]["context"]["policy"] == "deny-all"


def test_a_workspace_grant_lets_the_same_read_through(agent_script, tmp_path):
    workspace = tmp_path / "space"
    workspace.mkdir()
    note = workspace / "note.txt"
    note.write_text("readable", encoding="utf-8")
    directory = tmp_path / "run"
    assert main(argv(agent_script, "--log-dir", str(directory),
                     "--workspace", str(workspace),
                     mode="read", target=str(note))) == 0
    decisions = [r for r in read_log_records(directory)
                 if r["context"]["action"] == "acp/decision"]
    assert [d["context"]["allowed"] for d in decisions] == [True]
    assert decisions[0]["context"]["policy"] == "workspace"


def test_the_transcript_is_not_written_unless_it_was_asked_for(
        agent_script, tmp_path):
    directory = tmp_path / "run"
    main(argv(agent_script, "--log-dir", str(directory)))
    assert (directory / "action-witness.jsonl").exists()
    assert not (directory / "frames.jsonl").exists()


def test_json_output_is_the_same_run_in_a_shape_a_harness_can_read(
        agent_script, tmp_path, capsys):
    directory = tmp_path / "run"
    main(argv(agent_script, "--log-dir", str(directory), "--json"))
    report = json.loads(capsys.readouterr().out)
    assert report["stop_reason"] == "end_turn"
    assert report["text"] == "done: hello"
    assert report["protocol_version"] == 2
    assert len(report["receipt"]["link"]) == 64


def test_an_agent_that_will_not_start_is_reported_with_what_it_said(
        tmp_path, capsys):
    broken = tmp_path / "broken.py"
    broken.write_text(chr(10).join([
        "import sys",
        "sys.stderr.write('no such model' + chr(10))",
        "raise SystemExit(2)",
    ]), encoding="utf-8")
    code = main(["run", "--prompt", "hello", "--", sys.executable,
                 str(broken)])
    assert code == 3
    printed = capsys.readouterr().out
    assert "the turn did not run" in printed
    assert "no such model" in printed


def test_allow_all_is_the_flag_that_drops_the_boundary(agent_script, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("anything", encoding="utf-8")
    directory = tmp_path / "run"
    assert main(argv(agent_script, "--log-dir", str(directory), "--allow-all",
                     mode="read", target=str(outside))) == 0
    decisions = [r for r in read_log_records(directory)
                 if r["context"]["action"] == "acp/decision"]
    assert [d["context"]["policy"] for d in decisions] == ["allow-all"]
    assert decisions[0]["context"]["allowed"] is True


def test_the_limits_of_the_record_are_a_command_of_their_own(capsys):
    assert main(["--limits"]) == 0
    printed = capsys.readouterr().out
    assert "does not prove" in printed or "did not carry" in printed


def test_no_subcommand_prints_help_rather_than_doing_something(capsys):
    assert main([]) == 3
    assert "verify" in capsys.readouterr().out


def test_an_abbreviated_grant_flag_is_a_usage_error(agent_script):
    # `--allow-a` was an unambiguous prefix of `--allow-all`, which is the flag
    # that drops the boundary entirely. Argparse takes any unambiguous prefix by
    # default, and a subparser does not inherit the setting that turns it off,
    # so the widest grant here was reachable by a near miss of its name.
    with pytest.raises(SystemExit):
        main(["run", "--prompt", "hello", "--allow-a", "--", agent_script])
