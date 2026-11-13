"""Codex rollout observer: identity from session_meta, counts from the tail, no text."""
from __future__ import annotations

import hashlib
import json

from harness.peer_session_codex import observe_codex_rollout
from harness.peer_session_types import SESSION_SCHEMA
from tests.peer_session_fixtures import (CANARY, CODEX_PARENT, CODEX_REPO_URL, CODEX_THREAD,
                                         assert_no_canary, codex_records, jsonl, write_codex)

NOW = "2026-09-10T09:10:00Z"


def test_observer_reports_meta_counts_usage_but_no_text(tmp_path):
    path = write_codex(tmp_path)
    rec = observe_codex_rollout(path, observed_at=NOW)
    assert_no_canary(rec)
    assert rec["schema"] == SESSION_SCHEMA and rec["harness"] == "codex"
    assert rec["thread_id"] == CODEX_THREAD
    assert rec["is_subagent"] is False and rec["parent_thread_id"] is None
    meta = rec["session_meta"]
    assert meta["present"] is True
    assert meta["cli_version"] == "1.2.3" and meta["originator"] == "codex_desktop"
    assert meta["source"] == "vscode"
    assert meta["git"] == {"branch": "main", "commit_hash": "0" * 40,
                           "repository_url_ref": {
                               "chars": len(CODEX_REPO_URL),
                               "sha256": hashlib.sha256(CODEX_REPO_URL.encode()).hexdigest()}}
    assert meta["session_meta_records_in_head"] == 1
    instructions = f"{CANARY} instructions"
    assert meta["base_instructions_ref"] == {
        "chars": len(instructions), "sha256": hashlib.sha256(instructions.encode()).hexdigest()}
    assert rec["model_reported"] == {"value": "gpt-test-model", "basis": "consistent",
                                     "samples": 2}
    assert rec["cwd_reported"]["value"] == "C:\\work\\repo"
    tail = rec["tail"]
    assert tail["record_type_counts"] == {"event_msg": 6, "response_item": 2, "session_meta": 1,
                                          "turn_context": 2}
    assert tail["event_msg_counts"] == {"agent_message": 2, "token_count": 2, "user_message": 2}
    assert tail["response_item_counts"] == {"function_call": 2}
    assert tail["tool_call_counts"] == {"shell": 2}
    assert tail["turns_seen"] == 2 and tail["ordinal_range"] == [0, 10]
    assert tail["total_token_usage_reported"] == {"input_tokens": 200, "cached_input_tokens": 10,
                                                  "output_tokens": 20,
                                                  "reasoning_output_tokens": 5,
                                                  "total_tokens": 220}
    answer = f"{CANARY} answer 1"
    assert tail["last"]["agent_message"] == {
        "timestamp": "2026-09-10T09:01:00.000Z",
        "text_ref": {"chars": len(answer), "sha256": hashlib.sha256(answer.encode()).hexdigest()}}
    assert tail["last"]["task_started"] is None
    assert rec["issues"] == []


def test_subagent_spawn_metadata_is_lifted_from_source(tmp_path):
    path = write_codex(tmp_path, records=codex_records(subagent=True))
    rec = observe_codex_rollout(path, observed_at=NOW)
    assert rec["is_subagent"] is True and rec["parent_thread_id"] == CODEX_PARENT
    meta = rec["session_meta"]
    assert meta["source"] == "object"
    assert meta["agent_nickname"] == "worker" and meta["agent_role"] == "default"
    assert meta["spawn_depth"] == 1
    assert_no_canary(rec)


def test_missing_session_meta_is_an_issue_and_thread_id_stays_null(tmp_path):
    records = codex_records()[1:]
    path = write_codex(tmp_path, records=records)
    rec = observe_codex_rollout(path, observed_at=NOW)
    assert rec["thread_id"] is None and rec["session_meta"] is None
    assert "session_meta_absent_in_head" in rec["issues"]
    assert rec["cwd_reported"]["basis"] == "consistent"


def test_meta_cwd_is_labelled_when_no_turn_context_seen(tmp_path):
    path = write_codex(tmp_path, records=codex_records()[:1])
    rec = observe_codex_rollout(path, observed_at=NOW)
    assert rec["cwd_reported"] == {"value": "C:\\work\\repo", "basis": "session_meta_only",
                                   "samples": 1}
    assert rec["model_reported"]["basis"] == "not_emitted"


def test_thread_id_drift_between_meta_and_tail_is_an_issue(tmp_path):
    head = codex_records(turns=1)
    tail = codex_records("01a0ffff-0000-7000-8000-000000000000", turns=40)[1:]
    path = tmp_path / "rollout-drift.jsonl"
    path.write_bytes(jsonl(head + tail))
    rec = observe_codex_rollout(path, observed_at=NOW, head_bytes=1200, tail_bytes=3000)
    assert rec["source"]["windows_overlap"] is False
    assert rec["thread_id"] == CODEX_THREAD
    assert "thread_id_differs_between_meta_and_tail" in rec["issues"]


def test_model_conflict_is_reported_as_conflict(tmp_path):
    records = codex_records()
    records[1]["payload"]["model"] = "other-model"
    path = write_codex(tmp_path, records=records)
    rec = observe_codex_rollout(path, observed_at=NOW)
    assert rec["model_reported"] == {"value": None, "basis": "conflict", "samples": 2,
                                     "distinct": 2}


def test_thread_settings_model_counts_toward_consistency(tmp_path):
    records = codex_records(turns=1)
    records.append({"timestamp": "2026-09-10T09:05:00.000Z", "ordinal": 99, "type": "event_msg",
                    "payload": {"type": "thread_settings_applied", "thread_id": CODEX_THREAD,
                                "thread_settings": {"model": "gpt-test-model"}}})
    path = write_codex(tmp_path, records=records)
    rec = observe_codex_rollout(path, observed_at=NOW)
    assert rec["model_reported"]["samples"] == 2
    assert rec["tail"]["event_msg_counts"]["thread_settings_applied"] == 1


def test_non_object_payloads_do_not_crash(tmp_path):
    records = [{"timestamp": "t", "ordinal": 0, "type": "session_meta", "payload": "string"},
               {"timestamp": "t", "ordinal": 1, "type": "turn_context", "payload": None},
               {"timestamp": "t", "ordinal": "x", "type": None}]
    path = write_codex(tmp_path, records=records)
    rec = observe_codex_rollout(path, observed_at=NOW)
    assert rec["session_meta"] == {"present": True, "payload_shape": "not_an_object",
                                  "session_meta_records_in_head": 1}
    assert rec["thread_id"] is None
    assert rec["tail"]["ordinal_range"] == [0, 1]
    assert rec["tail"]["record_type_counts"]["unknown"] == 1


def test_a_token_in_a_remote_url_never_leaves_the_observer(tmp_path):
    """A remote URL carries the host and sometimes a pasted access token in its
    userinfo, so only its length and hash are reported."""
    path = write_codex(tmp_path)
    rec = observe_codex_rollout(path, observed_at=NOW)
    assert "repository_url" not in rec["session_meta"]["git"]
    assert CODEX_REPO_URL not in json.dumps(rec)
    assert "example.invalid" not in json.dumps(rec)


def test_a_second_session_meta_in_the_head_is_counted_and_flagged(tmp_path):
    """A rollout carries one session_meta. A second one means the file does not
    have the shape this observer assumes, so the count is reported."""
    records = codex_records(turns=1)
    records.insert(1, dict(records[0]))
    path = write_codex(tmp_path, records=records)
    rec = observe_codex_rollout(path, observed_at=NOW)
    assert rec["session_meta"]["session_meta_records_in_head"] == 2
    assert "multiple_session_meta_in_head" in rec["issues"]
    assert rec["thread_id"] == CODEX_THREAD
