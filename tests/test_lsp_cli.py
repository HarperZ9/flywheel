"""The command line, including the three ways it must refuse to say "fine".

Exit codes are the whole point of a command a harness calls, so they are what is
asserted here. Three of them cover the same failure shape: a server that never
started, a chain whose bytes nobody kept, and a server that published nothing
all produce no evidence, and none of them may leave through the door marked
success.
"""
import json
import sys
from pathlib import Path

import pytest

from harness.lsp_cli import FAILED, OK, UNCHECKED, main

FAKE = [sys.executable, str(Path(__file__).parent / "fake_lsp_server.py")]
BROKEN = "broken thing\nsecond\n"
CLEAN = "fine thing\nsecond\n"


@pytest.fixture
def cli(capsys):
    """Run the command in this process and hand back its code and output."""
    def go(*argv):
        code = main(list(argv))
        return code, capsys.readouterr().out
    return go


@pytest.fixture
def source(tmp_path):
    def write(text=BROKEN, name="a.py"):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return str(path)
    return write


def records(path):
    return [json.loads(line) for line in
            Path(path).read_text(encoding="utf-8").splitlines()]


def test_ask_says_which_version_and_encoding_the_answer_was_taken_under(
        cli, source):
    code, out = cli("ask", "--file", source(), "--operation", "definition",
                    "--", *FAKE)
    assert code == OK
    assert "textDocument/definition" in out
    assert "version          1" in out
    assert "encoding         utf-16" in out
    assert "current          yes" in out


def test_a_server_with_nothing_to_say_is_unchecked_rather_than_answered(
        cli, source):
    # A null result is an ordinary answer and not a failure, and it is also not
    # something a caller can act on. Zero would tell a script it got a location.
    code, out = cli("ask", "--file", source(), "--operation", "rename",
                    "--new-name", "other", "--", *FAKE)
    assert code == UNCHECKED
    assert "nothing to say" in out


def test_a_request_the_server_never_advertised_fails_under_strict(cli, source):
    code, out = cli("ask", "--file", source(), "--operation", "rename",
                    "--strict", "--", *FAKE)
    assert code == FAILED
    assert "textDocument/rename" in out


def test_a_server_that_never_starts_is_unchecked_and_shows_its_own_error(
        cli, source):
    code, out = cli("ask", "--file", source(), "--", sys.executable, "-c",
                    "import sys; sys.stderr.write('no server here\\n')")
    assert code == UNCHECKED
    # The server's own complaint, not this command's guess at one. A server that
    # dies on a bad config writes the reason there and nowhere else.
    assert "no server here" in out


def test_a_run_and_the_bytes_it_kept_verify_back_through_the_command(
        cli, source, tmp_path):
    directory = tmp_path / "run"
    code, out = cli("ask", "--file", source(), "--log-dir", str(directory),
                    "--keep-bytes", "--", *FAKE)
    assert code == OK
    assert "receipt          " in out
    code, out = cli("verify", "--log", str(directory / "action-witness.jsonl"),
                    "--transcript", str(directory / "frames.jsonl"))
    assert code == OK
    assert "MATCH" in out


def test_a_chain_without_its_bytes_is_unverifiable_and_not_a_pass(
        cli, source, tmp_path):
    directory = tmp_path / "run"
    cli("ask", "--file", source(), "--log-dir", str(directory), "--", *FAKE)
    code, out = cli("verify", "--log",
                    str(directory / "action-witness.jsonl"))
    assert code == UNCHECKED
    assert "UNVERIFIABLE" in out


def test_an_edited_log_verifies_as_tampered(cli, source, tmp_path):
    directory = tmp_path / "run"
    cli("ask", "--file", source(), "--log-dir", str(directory), "--keep-bytes",
        "--", *FAKE)
    log = directory / "action-witness.jsonl"
    entries = records(log)
    entries[2]["sha256"] = "0" * 64
    log.write_text("".join(json.dumps(entry) + chr(10) for entry in entries),
                   encoding="utf-8")
    code, out = cli("verify", "--log", str(log), "--transcript",
                    str(directory / "frames.jsonl"))
    assert code == FAILED
    assert "TAMPERED" in out
    assert "broken at        record 3" in out


def test_a_transcript_that_is_not_there_is_unchecked_not_a_pass(
        cli, source, tmp_path):
    directory = tmp_path / "run"
    cli("ask", "--file", source(), "--log-dir", str(directory), "--", *FAKE)
    code, out = cli("verify", "--log",
                    str(directory / "action-witness.jsonl"),
                    "--transcript", str(tmp_path / "gone.jsonl"))
    assert code == UNCHECKED
    assert "transcript could not be read" in out


def test_diagnostics_reports_what_the_server_found_and_exits_failed(
        cli, source):
    code, out = cli("diagnostics", "--file", source(), "--", *FAKE)
    assert code == FAILED
    assert "diagnostics      1" in out
    assert "fake: broken symbol" in out
    assert "version          1" in out


def test_a_file_the_server_calls_clean_exits_zero(cli, source):
    code, out = cli("diagnostics", "--file", source(CLEAN), "--", *FAKE)
    assert code == OK
    assert "diagnostics      0" in out


def test_a_server_that_publishes_nothing_is_unknown_and_never_clean(
        cli, source):
    # The false-success control. This run and the one above differ only in
    # whether the server spoke, and a command that treated silence as an empty
    # set would report a file nobody analysed as a clean one.
    code, out = cli("diagnostics", "--file", source(), "--wait", "0.3",
                    "--", *FAKE, "--never-publish")
    assert code == UNCHECKED
    assert "unknown and not clean" in out
    assert "diagnostics      0" not in out


def test_json_output_carries_the_stamp_the_rendering_shows(cli, source):
    code, out = cli("ask", "--file", source(), "--json", "--", *FAKE)
    report = json.loads(out)
    assert code == OK
    assert report["version"] == 1
    assert report["encoding"] == "utf-16"
    assert report["current"] is True
    assert report["result"][0]["range"]["start"]["line"] == 2
    assert report["log"] is None


def test_a_position_is_converted_before_it_is_sent(cli, tmp_path):
    # The character on the wire is not the one on the command line. Past an
    # astral character a Python index and a utf-16 offset are different numbers,
    # and the echo is where that becomes visible.
    path = tmp_path / "a.py"
    path.write_text('q = "\U0001f600b"\n', encoding="utf-8")
    code, out = cli("ask", "--file", str(path), "--operation", "highlight",
                    "--line", "0", "--character", "6", "--json", "--", *FAKE)
    assert code == OK
    assert json.loads(out)["result"][0]["range"]["start"]["character"] == 7


def test_the_limits_are_printed_without_running_anything(cli):
    code, out = cli("--limits")
    assert code == OK
    assert "negotiated encoding" in out


def test_no_subcommand_prints_the_help_and_is_unchecked(cli):
    code, out = cli()
    assert code == UNCHECKED
    assert "diagnostics" in out and "verify" in out


def test_a_pull_server_is_asked_rather_than_waited_on(cli, source):
    # The gap a real ruff server exposed. It advertises a diagnostic provider,
    # pushes nothing, and the waiting path sat out its whole clock on a file
    # with obvious problems before reporting, correctly, that it knew nothing.
    code, out = cli("diagnostics", "--file", source(), "--wait", "0",
                    "--", *FAKE, "--pull")
    assert code == FAILED
    assert "model            diagnostic" in out
    assert "diagnostics      1" in out
    assert "fake: broken symbol" in out


def test_a_pulled_empty_report_is_an_answer_and_exits_zero(cli, source):
    code, out = cli("diagnostics", "--file", source(CLEAN), "--wait", "0",
                    "--", *FAKE, "--pull")
    assert code == OK
    assert "diagnostics      0" in out


def test_an_unchanged_report_is_not_an_empty_set(cli, source):
    # The pull path's false-success control. "Unchanged" means the same as the
    # result id you hold, and a client holding none has been told nothing. A
    # command reading that as zero would call an unexamined file clean.
    code, out = cli("diagnostics", "--file", source(), "--wait", "0.2",
                    "--", *FAKE, "--pull-unchanged")
    assert code == UNCHECKED
    assert "unknown and not clean" in out
    assert "diagnostics      0" not in out


def test_the_record_says_which_model_produced_the_set(cli, source, tmp_path):
    directory = tmp_path / "run"
    cli("diagnostics", "--file", source(), "--log-dir", str(directory),
        "--wait", "0", "--", *FAKE, "--pull")
    folded = [entry for entry in records(directory / "action-witness.jsonl")
              if entry["context"]["action"] == "lsp/published"]
    assert [entry["context"]["model"] for entry in folded] == ["diagnostic"]
