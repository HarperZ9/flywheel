"""The debug command line, and the four ways it must refuse to say "fine".

Exit codes are the point of a command a harness calls, so they are what is
asserted here. A program that never stopped, an adapter that never started, an
adapter that refused the launch, and a chain whose bytes nobody kept all produce
nothing a caller can act on, and none of them may leave through the door marked
success.

The control on the whole design is `test_a_debuggee_value_stays_off_stdout`. A
variable's value is the debuggee's memory, and the command that printed it by
default would be a leak nobody asked for and nobody would notice.
"""
import json
import sys
from pathlib import Path

import pytest

from harness.dap_args import breakpoints_from
from harness.dap_cli import FAILED, OK, UNCHECKED, main

FAKE = [sys.executable, str(Path(__file__).parent / "fake_dap_adapter.py")]


@pytest.fixture
def cli(capsys):
    """Run the command in this process and hand back its code and output."""
    def go(*argv):
        code = main(list(argv))
        return code, capsys.readouterr().out
    return go


@pytest.fixture
def run(cli):
    """One debug run against the fake adapter: two breakpoints, one bound."""
    def go(*flags, adapter=(), program="program.py"):
        return cli("run", "--program", program, "--break", "program.py:10",
                   "--break", "program.py:999", "--wait", "10", *flags,
                   "--", *FAKE, *adapter)
    return go


def records(path):
    return [json.loads(line) for line in
            Path(path).read_text(encoding="utf-8").splitlines()]


def test_a_run_reports_where_it_stopped_and_how_much_of_it_bound(run):
    code, out = run()
    assert code == OK
    # Bound out of asked for, because an unverified breakpoint is the ordinary
    # case for a file the debuggee has not loaded and a reader who sees only the
    # request will read a stack that never happened as a stack that did.
    assert "1 bound of 2 asked for" in out
    assert "not bound      program.py:999  no code on that line" in out
    assert "stopped          breakpoint on thread 1" in out
    assert "frame0" in out


def test_a_debuggee_value_stays_off_stdout_until_it_is_asked_for(run):
    # The control. The fake reports a local `total` whose value is "42", and a
    # command that printed the debuggee's memory by default would be a leak
    # nobody asked for. The name is useful; the value is the secret.
    code, out = run()
    assert code == OK
    assert "total" in out
    assert "42" not in out
    # An expensive scope is one the adapter asked not to be read without cause,
    # and the fake answers it with a marker so a client that read it anyway says
    # so here.
    assert "expensive_was_read" not in out
    code, shown = run("--values")
    assert code == OK
    assert "total = 42" in shown


def test_a_program_that_never_stopped_is_unchecked_rather_than_clean(run):
    # Silence is not a pass. Zero would tell a script the debugger reached the
    # line, and nothing here reached anything.
    code, out = run("--wait", "1", adapter=("--no-config-done",))
    assert code == UNCHECKED
    assert "nothing stopped in the time allowed" in out
    assert "not the same as a clean run" in out


def test_a_refused_launch_is_the_adapters_failure_and_says_so(run):
    code, out = run(adapter=("--launch-fails",))
    assert code == FAILED
    # The adapter's own prose. A command that substituted its own guess would
    # hide the one sentence naming what went wrong.
    assert "the program could not be started" in out


def test_an_adapter_that_never_starts_is_unchecked_and_shows_its_complaint(
        cli):
    code, out = cli("run", "--program", "program.py", "--wait", "2", "--",
                    *FAKE, "--die")
    assert code == UNCHECKED
    assert "no runtime found" in out


def test_a_session_that_is_neither_launched_nor_attached_is_a_usage_failure(
        cli):
    code, out = cli("run", "--wait", "2", "--", *FAKE)
    assert code == UNCHECKED
    assert "--program or attached with --attach-pid" in out


def test_a_terminal_the_adapter_asked_for_is_refused_and_recorded(run,
                                                                  tmp_path):
    # A run where the adapter asked to start a process and was told no looks,
    # from its exit code alone, exactly like a run where it never asked. So the
    # ask and the answer are both printed and both on the record.
    code, out = run("--log-dir", str(tmp_path), adapter=("--ask-terminal",))
    assert code == OK
    assert "refused  runInTerminal" in out
    assert "python program.py" in out
    written = records(tmp_path / "action-witness.jsonl")
    decisions = [r for r in written
                 if r["context"]["action"] == "dap/decision"]
    assert [d["context"]["allowed"] for d in decisions] == [False]


def test_the_record_a_run_leaves_verifies_offline_against_its_bytes(run, cli,
                                                                    tmp_path):
    code, out = run("--log-dir", str(tmp_path), "--keep-bytes", "--run-id",
                    "one")
    assert code == OK
    log = tmp_path / "action-witness.jsonl"
    transcript = tmp_path / "frames.jsonl"
    assert str(log) in out
    code, verified = cli("verify", "--log", str(log), "--transcript",
                         str(transcript))
    assert code == OK
    assert "verdict          MATCH" in verified
    # A verdict that came with nothing it leaves open would be the wrong kind of
    # answer for a command whose whole subject is what a record does not show.
    assert "does not prove:" in verified


def test_a_chain_without_its_bytes_is_unchecked_rather_than_matched(run, cli,
                                                                    tmp_path):
    run("--log-dir", str(tmp_path))
    code, out = cli("verify", "--log", str(tmp_path / "action-witness.jsonl"))
    assert code == UNCHECKED
    assert "UNVERIFIABLE" in out


def test_an_edited_frame_fails_the_check_rather_than_going_unnoticed(run, cli,
                                                                     tmp_path):
    run("--log-dir", str(tmp_path), "--keep-bytes")
    log = tmp_path / "action-witness.jsonl"
    written = records(log)
    written[3]["sha256"] = "0" * 64
    log.write_text("".join(json.dumps(r) + chr(10) for r in written),
                   encoding="utf-8")
    code, out = cli("verify", "--log", str(log), "--transcript",
                    str(tmp_path / "frames.jsonl"))
    assert code == FAILED
    assert "TAMPERED" in out
    assert "record 4" in out


def test_a_missing_transcript_is_unchecked_and_not_a_verdict(cli, tmp_path):
    code, out = cli("verify", "--log", str(tmp_path / "nothing.jsonl"),
                    "--transcript", str(tmp_path / "gone.jsonl"))
    assert code == UNCHECKED
    assert "the transcript could not be read" in out


def test_the_json_shape_carries_the_numbers_a_caller_branches_on(run,
                                                                 tmp_path):
    code, out = run("--json", "--log-dir", str(tmp_path))
    assert code == OK
    report = json.loads(out)
    assert (report["verified"], report["requested"]) == (1, 2)
    assert report["stop"]["reason"] == "breakpoint"
    assert report["does_not_prove"]
    # Values stay out of the machine-readable shape too. A caller that logged
    # this report wholesale would otherwise be keeping the debuggee's memory.
    assert "42" not in json.dumps(report["scopes"])


def test_a_run_without_a_log_directory_says_it_left_no_record(run):
    _, out = run()
    assert "log              none: this run left no record" in out


def test_the_limits_are_printable_without_starting_anything(cli):
    code, out = cli("--limits")
    assert code == OK
    assert "not an independent observation" in out


def test_breakpoints_are_grouped_by_source_and_a_bad_one_is_rejected():
    # One request per source carrying every line at once, because a second
    # request for the same file replaces the first. A caller that sent them one
    # at a time would end up with only the last.
    assert breakpoints_from(["a.py:1", "b.py:2", "a.py:3"]) == {
        "a.py": [1, 3], "b.py": [2]}
    assert breakpoints_from(["C:\\src\\a.py:40"]) == {"C:\\src\\a.py": [40]}
    assert breakpoints_from([]) == {}
    for bad in ("a.py", "a.py:", ":10", "a.py:ten"):
        with pytest.raises(ValueError):
            breakpoints_from([bad])


def test_an_abbreviated_flag_is_a_usage_error_rather_than_a_grant():
    # `--allow-terminal` decides whether this client starts a process. Argparse
    # takes any unambiguous prefix by default, and a near miss of that flag has
    # to fail rather than land somewhere close to it.
    with pytest.raises(SystemExit):
        main(["run", "--allow-term", "--program", "a.py", "--", *FAKE])
