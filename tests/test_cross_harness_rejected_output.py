"""Falsifiers for the evidence a refused attempt leaves behind.

The 2026-09-03 head-to-head launched twenty attempts and four of them recorded
no raw output at all. `claude_code` on `agt-001` ran five provider turns, billed
$0.1398, produced 10,421 output tokens, and left nothing to read: the receipt
kept the counts and the cost and dropped the text. Every one of the four was
driven by a CLI adapter, which is where the discard lived.

These tests hold the three properties that fix has to keep:

- a refused attempt keeps the provider's own bytes, and a returned one does not
  grow a second copy of an answer `output.txt` already holds;
- the kept bytes are still redacted, still bounded, and say so when cut;
- nothing kept here is ever graded, because only `output.txt` is read by an
  oracle and it is still written only for an attempt that returned.

Every stream below is a fixture. Nothing here calls a provider.
"""
import json

from harness.cross_harness_adapters import DirectCodexAdapter, ProcessOutcome
from harness.cross_harness_artifacts import _STANDARD_NAMES
from harness.cross_harness_executor import SHARED_TOOL_POLICY
from harness.cross_harness_peer_adapters import DirectClaudeCodeAdapter, DirectCursorAdapter
from harness.cross_harness_rejected_output import (MAX_REJECTED_BYTES, REJECTED_OUTPUT_NAME,
                                                   record_rejected_output)
from harness.cross_harness_types import AttemptRequest

IDENTITY = {"raw_prompt_sha256": "a" * 64, "input_sha256s": {}, "oracle_spec_sha256": "d" * 64}


def request(tmp_path, role="codex_harness", adapter="codex_cli_json/v1", model="gpt-5.3-codex-spark"):
    return AttemptRequest("run", "spark", "set", "agt-001-full", "do the task", "a" * 64, role,
                          role.split("_")[0], adapter, model, model, tmp_path, "b" * 64, {},
                          SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 3, tmp_path)


def _codex(stdout, tmp_path):
    adapter = DirectCodexAdapter(runner=lambda argv, **kw: ProcessOutcome(0, stdout, "", 7, False),
                                 executable_resolver=lambda: "C:/bin/codex.cmd",
                                 task_identity_by_id={"agt-001-full": IDENTITY})
    return adapter.execute(request(tmp_path))


def _claude(stdout, tmp_path):
    adapter = DirectClaudeCodeAdapter(runner=lambda argv, **kw: ProcessOutcome(0, stdout, "", 7, False),
                                      executable_resolver=lambda: "C:/bin/claude.cmd",
                                      task_identity_by_id={"agt-001-full": IDENTITY},
                                      version_probe=lambda _: "")
    return adapter.execute(request(tmp_path, role="claude_code", adapter="claude_code_cli_json/v1",
                                   model="claude-sonnet-5"))


def _cursor(stdout, tmp_path):
    adapter = DirectCursorAdapter(runner=lambda argv, **kw: ProcessOutcome(0, stdout, "", 7, False),
                                  executable_resolver=lambda: "C:/bin/cursor-agent.cmd",
                                  task_identity_by_id={"agt-001-full": IDENTITY},
                                  version_probe=lambda _: "")
    return adapter.execute(request(tmp_path, role="cursor", adapter="cursor_agent_cli_json/v1",
                                   model="composer-1"))


def test_a_refused_cli_attempt_hands_its_bytes_over_instead_of_dropping_them(tmp_path):
    """The defect itself: an attempt the parser refuses used to leave nothing.

    One unparseable line is enough to fail the whole stream, and the paid text
    that came with it went nowhere. It now comes back on the result.
    """
    stdout = "not-json\nthe model said something worth reading\n"
    for execute in (_codex, _claude, _cursor):
        result = execute(stdout, tmp_path)
        assert result.execution_state == "malformed", execute
        assert result.output_text == "", execute
        assert "worth reading" in result.rejected_output, execute


def test_a_returned_attempt_keeps_no_second_copy_of_its_answer(tmp_path):
    """`output.txt` is the answer. A returned attempt has nothing refused."""
    stdout = json.dumps({"type": "item.completed",
                         "item": {"type": "agent_message", "text": "answer"}})
    result = _codex(stdout, tmp_path)
    assert result.execution_state == "returned"
    assert result.output_text == "answer" and result.rejected_output == ""


def test_the_kept_bytes_are_redacted_the_way_a_failure_detail_is(tmp_path):
    """Refusing to grade output is not a reason to stop redacting it."""
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"
    key = "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz"
    stdout = f"not-json\nAuthorization: Bearer hide-me\njwt {token}\nkey {key}\n"
    for execute in (_codex, _claude, _cursor):
        kept = execute(stdout, tmp_path).rejected_output
        assert "hide-me" not in kept and token not in kept and key not in kept, execute
        assert "[REDACTED]" in kept, execute


def test_nothing_is_written_when_the_provider_produced_nothing(tmp_path):
    """An empty refusal is not a file. A caller can still update a row."""
    files: dict = {}
    assert record_rejected_output("", tmp_path, files) == {}
    assert files == {} and not (tmp_path / REJECTED_OUTPUT_NAME).exists()


def test_what_is_written_is_hashed_and_named_in_the_row(tmp_path):
    files: dict = {}
    fields = record_rejected_output("refused text", tmp_path, files)
    target = tmp_path / REJECTED_OUTPUT_NAME
    assert files == {REJECTED_OUTPUT_NAME: target}
    assert target.read_bytes() == b"refused text"
    assert fields["rejected_output_path"] == str(target)
    assert fields["rejected_output_bytes"] == fields["rejected_output_arrived_bytes"] == 12
    assert fields["rejected_output_truncated"] is False
    assert len(fields["rejected_output_sha256"]) == 64


def test_a_cut_stream_says_it_was_cut_and_stays_valid_utf8(tmp_path):
    """A short answer and a cut one must not read the same.

    The cut lands on a byte offset, which can fall inside a character, so the
    prefix is re-encoded before it is written and the file is always decodable.
    """
    text = "\u00e9" * MAX_REJECTED_BYTES  # two bytes each, so the cut splits one
    fields = record_rejected_output(text, tmp_path, {})
    assert fields["rejected_output_truncated"] is True
    assert fields["rejected_output_arrived_bytes"] == 2 * MAX_REJECTED_BYTES
    assert fields["rejected_output_bytes"] <= MAX_REJECTED_BYTES
    written = (tmp_path / REJECTED_OUTPUT_NAME).read_bytes()
    assert written.decode("utf-8") == text[:len(written) // 2]


def test_a_task_cannot_declare_an_artifact_that_would_overwrite_the_evidence(tmp_path):
    assert REJECTED_OUTPUT_NAME in _STANDARD_NAMES
