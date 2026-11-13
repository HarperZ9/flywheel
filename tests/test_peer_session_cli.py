"""CLI: exit codes carry findings, output is JSON, transcript text never appears."""
from __future__ import annotations

import io
import json

from harness.journey_projection import reduce_events
from harness.peer_mailbox import MAX_MESSAGE_BYTES
from harness.peer_session_cli import main
from tests.peer_session_fixtures import (CANARY, CODEX_THREAD, assert_no_canary, codex_records,
                                         write_claude, write_codex)

CLOCK = "2026-09-10T12:00:00Z"


def run(argv):
    out = io.StringIO()
    code = main(argv, out=out, clock=lambda: CLOCK)
    text = out.getvalue()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    return code, payload, text


def test_list_discovers_synthetic_home(tmp_path):
    a = write_claude(tmp_path)
    c = write_codex(tmp_path)
    code, payload, text = run(["list", "--home", str(tmp_path)])
    assert code == 0
    assert payload["discovered"] == 2 and payload["shown"] == 2
    assert payload["observed_at"] == CLOCK
    assert {e["path"] for e in payload["entries"]} == {str(a), str(c)}
    assert CANARY not in text
    code, payload, _ = run(["list", "--home", str(tmp_path), "--limit", "1"])
    assert code == 0 and payload["shown"] == 1 and payload["discovered"] == 2


def test_observe_infers_harness_from_file_name(tmp_path):
    a = write_claude(tmp_path)
    c = write_codex(tmp_path)
    code, payload, text = run(["observe", str(c)])
    assert code == 0 and payload["harness"] == "codex" and payload["thread_id"] == CODEX_THREAD
    assert payload["observed_at"] == CLOCK
    code, payload, _ = run(["observe", str(a)])
    assert code == 0 and payload["harness"] == "claude_code"
    assert_no_canary(payload)


def test_observe_refuses_to_guess_an_unknown_name(tmp_path):
    odd = tmp_path / "transcript.jsonl"
    odd.write_bytes(b"{}\n")
    code, payload, _ = run(["observe", str(odd)])
    assert code == 2 and payload == {"error": "harness_not_inferable", "path": str(odd)}
    code, payload, _ = run(["observe", str(odd), "--harness", "codex"])
    assert code == 1 and "session_meta_absent_in_head" in payload["issues"]


def test_observe_exit_codes_follow_findings_and_rejections(tmp_path):
    broken = write_codex(tmp_path, records=codex_records()[1:])
    code, payload, _ = run(["observe", str(broken)])
    assert code == 1 and payload["thread_id"] is None
    code, payload, _ = run(["observe", str(tmp_path), "--harness", "codex"])
    assert code == 2 and payload["observed"] is False and payload["error"] == "SourceRejected"
    code, payload, _ = run(["observe", str(tmp_path / "absent-rollout.jsonl"), "--harness",
                            "codex"])
    assert code == 2 and payload["observed"] is False
    code, payload, _ = run(["observe", str(broken), "--head-bytes", "0"])
    assert code == 2 and payload["observed"] is False and payload["error"] == "SourceRejected"


def test_registry_writes_out_file_and_flags_issues(tmp_path):
    write_claude(tmp_path)
    write_codex(tmp_path)
    out = tmp_path / "registry.json"
    code, payload, _ = run(["registry", "--home", str(tmp_path), "--out", str(out)])
    assert code == 0
    assert payload["written"] == str(out) and payload["bytes"] == out.stat().st_size
    registry = json.loads(out.read_text(encoding="utf-8"))
    assert registry["discovered"] == 2 and registry["observed_count"] == 2
    assert_no_canary(registry)
    write_codex(tmp_path, thread_id="01a0ffff-0000-7000-8000-000000000002",
                records=codex_records()[1:])
    code, payload, _ = run(["registry", "--home", str(tmp_path)])
    assert code == 1 and payload["discovered"] == 3


def test_journey_output_reduces_cleanly(tmp_path):
    write_claude(tmp_path)
    write_codex(tmp_path)
    out = tmp_path / "journey.json"
    code, _, _ = run(["journey", "--home", str(tmp_path), "--out", str(out)])
    assert code == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["event_count"] == 3 and len(result["events"]) == 3
    assert result["journey_ref"].startswith("jrn_")
    reduce_events(result["events"])
    assert_no_canary(result)
    assert all(e["occurred_at"] == CLOCK for e in result["events"])


def test_mailbox_send_list_verify_and_drift(tmp_path):
    box = tmp_path / "mailbox"
    box.mkdir()
    body = tmp_path / "body.md"
    body.write_text("hello from the cli\n", encoding="utf-8")
    code, payload, text = run(["mailbox", "send", str(box), "--from", "claude.fable", "--to",
                               "codex.root", "--body-file", str(body)])
    assert code == 0 and payload["receipt_state"] == "MATCH"
    assert payload["file_name"] == "claude.fable-to-codex.root-20260910T120000Z.md"
    assert "body" not in payload and "hello" not in text
    code, payload, _ = run(["mailbox", "list", str(box)])
    assert code == 0 and payload["count"] == 1
    assert payload["messages"][0]["receipt_state"] == "MATCH"
    code, payload, _ = run(["mailbox", "send", str(box), "--from", "claude.fable", "--to",
                            "codex.root", "--body-file", str(body)])
    assert code == 2 and payload["error"] == "FileExistsError"
    target = box / "claude.fable-to-codex.root-20260910T120000Z.md"
    target.write_bytes(target.read_bytes().replace(b"hello", b"jello"))
    code, payload, _ = run(["mailbox", "verify", str(target)])
    assert code == 1 and payload["receipt_state"] == "DRIFT" and "body" not in payload
    code, payload, _ = run(["mailbox", "list", str(box)])
    assert code == 1


def test_mailbox_rejections_exit_two_with_error_json(tmp_path):
    box = tmp_path / "mailbox"
    box.mkdir()
    body = tmp_path / "body.md"
    body.write_text("x\n", encoding="utf-8")
    code, payload, _ = run(["mailbox", "send", str(box), "--from", "a-to-b", "--to", "c",
                            "--body-file", str(body)])
    assert code == 2 and payload["error"] == "MailboxError"
    code, payload, _ = run(["mailbox", "send", str(tmp_path / "nope"), "--from", "a", "--to",
                            "c", "--body-file", str(body)])
    assert code == 2 and payload["error"] == "MailboxError"
    code, payload, _ = run(["mailbox", "verify", str(tmp_path / "absent.md")])
    assert code == 2 and payload["error"] == "MailboxError"
    assert list(box.iterdir()) == []


def test_usage_errors_exit_two_and_help_exits_zero(capsys):
    assert main([], out=io.StringIO()) == 2
    assert main(["bogus"], out=io.StringIO()) == 2
    assert main(["--help"], out=io.StringIO()) == 0
    capsys.readouterr()


def test_out_refuses_a_path_that_is_not_a_regular_file(tmp_path):
    """A directory or a link at --out would send the write somewhere else. The path
    is checked before the open, so the run ends as a rejected input."""
    write_codex(tmp_path)
    for command in ("registry", "journey"):
        code, payload, _ = run([command, "--home", str(tmp_path), "--out", str(tmp_path)])
        assert code == 2 and payload["error"] == "SourceRejected"
        assert "link" in payload["detail"]


def test_a_negative_limit_is_a_usage_error_and_zero_is_an_empty_page(tmp_path):
    """A negative limit reads as "no limit" in Python slicing, which would quietly
    widen the output. It is refused by the argument type instead."""
    write_codex(tmp_path)
    for command in ("list", "registry", "journey"):
        assert run([command, "--home", str(tmp_path), "--limit", "-1"])[0] == 2
    code, payload, _ = run(["list", "--home", str(tmp_path), "--limit", "0"])
    assert code == 0 and payload["discovered"] == 1 and payload["shown"] == 0


def test_registry_and_journey_reject_an_out_of_range_window(tmp_path):
    """A zero window would fail every observation. That is a rejected argument, not
    a registry in which nothing happened to be readable."""
    write_codex(tmp_path)
    for command in ("registry", "journey"):
        code, payload, _ = run([command, "--home", str(tmp_path), "--head-bytes", "0"])
        assert code == 2
        assert payload == {"error": "SourceRejected", "detail": "--head-bytes out of range"}
        code, payload, _ = run([command, "--home", str(tmp_path), "--tail-bytes", str(2 ** 40)])
        assert code == 2 and payload["detail"] == "--tail-bytes out of range"


def test_journey_exits_one_when_a_session_carries_an_issue(tmp_path):
    """The journey states what the registry states, so a session with an issue has
    to move its exit code too. Otherwise a finding is visible in one view only."""
    write_codex(tmp_path, records=codex_records()[1:])
    assert run(["registry", "--home", str(tmp_path)])[0] == 1
    code, payload, _ = run(["journey", "--home", str(tmp_path)])
    assert code == 1
    fact = payload["events"][1]["payload"]["facts"][0]
    assert "session_meta_absent_in_head" in fact["issues"]


def test_mailbox_flags_a_renamed_file_whose_body_still_hashes(tmp_path):
    """A file renamed to claim a different sender still passes the hash check. The
    name check is what catches it, and it exits the way drift does."""
    box = tmp_path / "mailbox"
    box.mkdir()
    body = tmp_path / "body.md"
    body.write_text("status\n", encoding="utf-8")
    code, payload, _ = run(["mailbox", "send", str(box), "--from", "claude.fable", "--to",
                            "codex.root", "--body-file", str(body)])
    assert code == 0
    renamed = box / "codex.root-to-claude.fable-20260910T120000Z.md"
    (box / payload["file_name"]).rename(renamed)
    code, payload, _ = run(["mailbox", "verify", str(renamed)])
    assert code == 1 and payload["receipt_state"] == "MATCH"
    assert payload["file_name_consistent"] is False
    assert run(["mailbox", "list", str(box)])[0] == 1


def test_a_body_file_that_is_too_large_or_absent_is_refused(tmp_path):
    box = tmp_path / "mailbox"
    box.mkdir()
    body = tmp_path / "body.md"
    body.write_text("x" * (MAX_MESSAGE_BYTES + 1), encoding="utf-8")
    code, payload, _ = run(["mailbox", "send", str(box), "--from", "a", "--to", "b",
                            "--body-file", str(body)])
    assert code == 2 and payload["error"] == "MailboxError"
    code, payload, _ = run(["mailbox", "send", str(box), "--from", "a", "--to", "b",
                            "--body-file", str(tmp_path / "absent.md")])
    assert code == 2 and payload["error"] == "MailboxError"
    assert list(box.iterdir()) == []


def test_an_operating_system_error_reports_its_name_and_errno_only(tmp_path):
    """An OSError's text repeats the path it failed on and a localized system
    string. Only the errno name is printed, so error output stays content-free."""
    box = tmp_path / "mailbox"
    box.mkdir()
    body = tmp_path / "body.md"
    body.write_text("x\n", encoding="utf-8")
    argv = ["mailbox", "send", str(box), "--from", "a", "--to", "b", "--body-file", str(body)]
    assert run(argv)[0] == 0
    code, payload, text = run(argv)
    assert code == 2 and payload == {"error": "FileExistsError", "errno": "EEXIST"}
    assert str(box) not in text
