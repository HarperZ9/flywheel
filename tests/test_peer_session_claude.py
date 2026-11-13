"""Claude Code transcript observer: content stays out, identity stays honest."""
from __future__ import annotations

import hashlib
import json

from harness.peer_session_claude import observe_claude_transcript
from harness.peer_session_types import DOES_NOT_PROVE, SESSION_SCHEMA
from tests.peer_session_fixtures import (CANARY, CLAUDE_SESSION, CLAUDE_TITLE, assert_no_canary,
                                         claude_records, jsonl, write_claude)

NOW = "2026-09-10T10:10:00Z"


def test_observer_reports_identity_counts_and_hashes_but_no_text(tmp_path):
    path = write_claude(tmp_path)
    rec = observe_claude_transcript(path, observed_at=NOW)
    assert_no_canary(rec)
    assert rec["schema"] == SESSION_SCHEMA and rec["harness"] == "claude_code"
    assert rec["does_not_prove"] == DOES_NOT_PROVE
    assert rec["publication_state"] == "not_approved_for_publication"
    assert rec["source_authenticity"] == "unavailable"
    assert rec["external_calls"] == 0
    assert rec["session_id"] == {"value": CLAUDE_SESSION, "basis": "consistent", "samples": 4}
    assert rec["identity"]["gitBranch"]["value"] == "main"
    assert rec["models_reported"] == ["claude-test-model"]
    assert rec["custom_title_ref"] == {
        "chars": len(CLAUDE_TITLE),
        "sha256": hashlib.sha256(CLAUDE_TITLE.encode()).hexdigest()}
    assert rec["tail"]["record_type_counts"] == {"assistant": 2, "bridge-session": 1,
                                                 "custom-title": 1, "last-prompt": 1, "user": 2}
    assert rec["tail"]["content_block_counts"] == {"assistant:text": 2, "assistant:tool_use": 2,
                                                   "user:text_string": 2}
    assert rec["tail"]["tool_use_counts"] == {"Bash": 2}
    assert rec["tail"]["sidechain_records"] == 0
    assert rec["issues"] == []
    assert rec["first_timestamp_in_head"] == "2026-09-10T10:00:00.000Z"
    assert rec["last_timestamp_in_tail"] == "2026-09-10T10:01:30.000Z"
    assert rec["windows"]["head"]["parse"]["objects"] == 7
    assert rec["windows"]["head"]["parse"]["unparsed_lines"] == 0


def test_last_prompt_is_a_digest_that_matches_the_hidden_text(tmp_path):
    path = write_claude(tmp_path)
    rec = observe_claude_transcript(path, observed_at=NOW)
    prompt = rec["last_user_prompt"]
    expected = f"{CANARY} prompt 1"
    assert prompt["uuid"] == "u-1" and prompt["timestamp"] == "2026-09-10T10:01:00.000Z"
    assert prompt["text_ref"] == {"chars": len(expected),
                                  "sha256": hashlib.sha256(expected.encode()).hexdigest()}
    last = f"{CANARY} last"
    assert rec["tail"]["last_prompt_ref"]["sha256"] == hashlib.sha256(last.encode()).hexdigest()
    assert rec["last_assistant"] == {"timestamp": "2026-09-10T10:01:30.000Z",
                                     "model": "claude-test-model", "stop_reason": "tool_use",
                                     "block_types": ["text", "tool_use"]}


def test_account_and_organization_ids_never_appear(tmp_path):
    path = write_claude(tmp_path)
    rec = observe_claude_transcript(path, observed_at=NOW)
    dumped = json.dumps(rec)
    assert "ownerAccountUuid" not in dumped and "bridgeSessionId" not in dumped
    assert_no_canary(rec)


def test_conflicting_session_ids_in_head_are_reported_not_resolved(tmp_path):
    records = claude_records()
    records[3]["sessionId"] = "other-session"
    path = write_claude(tmp_path, records=records)
    rec = observe_claude_transcript(path, observed_at=NOW)
    assert rec["session_id"] == {"value": None, "basis": "conflict", "samples": 4, "distinct": 2}
    assert "session_id_not_consistent_in_head" in rec["issues"]


def test_head_and_tail_session_id_drift_is_an_issue(tmp_path):
    head = claude_records(turns=1)
    tail = claude_records("ffffffff-0000-4000-8000-000000000000", turns=30)
    path = tmp_path / "drift.jsonl"
    path.write_bytes(jsonl(head + tail))
    rec = observe_claude_transcript(path, observed_at=NOW, head_bytes=600, tail_bytes=2000)
    assert rec["source"]["windows_overlap"] is False
    assert rec["session_id"]["value"] == CLAUDE_SESSION
    assert "session_id_differs_between_head_and_tail" in rec["issues"]


def test_absent_fields_stay_null(tmp_path):
    records = [{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result"}]}},
               {"type": "assistant", "message": {"role": "assistant", "content": "plain"}},
               {"type": "attachment"}, {"type": 7}, "not an object"]
    path = tmp_path / "sparse.jsonl"
    path.write_bytes(jsonl([r for r in records if type(r) is dict]) + b"not json\n")
    rec = observe_claude_transcript(path, observed_at=NOW)
    assert rec["session_id"] == {"value": None, "basis": "not_emitted", "samples": 0}
    assert rec["last_user_prompt"] is None
    assert rec["last_assistant"]["model"] is None
    assert rec["last_assistant"]["block_types"] == ["text_string"]
    assert rec["models_reported"] == []
    assert rec["custom_title_ref"] is None
    assert rec["tail"]["record_type_counts"] == {"assistant": 1, "attachment": 1, "unknown": 1,
                                                 "user": 1}
    assert rec["windows"]["head"]["parse"]["unparsed_lines"] == 1
    assert "session_id_not_consistent_in_head" in rec["issues"]


def test_sidechain_records_are_counted_and_skipped_for_last_prompt(tmp_path):
    records = claude_records(turns=1)
    records.append({**records[1], "uuid": "side", "isSidechain": True,
                    "timestamp": "2026-09-10T11:00:00.000Z",
                    "message": {"role": "user", "content": f"{CANARY} side"}})
    path = write_claude(tmp_path, records=records)
    rec = observe_claude_transcript(path, observed_at=NOW)
    assert rec["tail"]["sidechain_records"] == 1
    assert rec["last_user_prompt"]["uuid"] == "u-0"


def test_activity_follows_file_age_not_content(tmp_path):
    path = write_claude(tmp_path)
    rec = observe_claude_transcript(path, observed_at="2030-01-01T00:00:00Z")
    assert rec["activity"] == "stale" and rec["file_age_seconds"] > 21_600
    rec2 = observe_claude_transcript(path, observed_at=rec["source"]["mtime_utc"])
    assert rec2["activity"] == "recent"
    rec3 = observe_claude_transcript(path, observed_at="garbage")
    assert rec3["activity"] == "unknown" and rec3["file_age_seconds"] is None
