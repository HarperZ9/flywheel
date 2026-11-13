"""Discovery and registry: newest first, content-free, name never wins over content."""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from harness import peer_session_registry as reg
from tests.peer_session_fixtures import (CLAUDE_SESSION, CODEX_THREAD, assert_no_canary,
                                         claude_records, codex_records, jsonl, write_claude,
                                         write_codex)

NOW = "2026-09-10T12:00:00Z"


def _home(tmp_path):
    a = write_claude(tmp_path)
    b = write_claude(tmp_path, session_id="6f0c1e2a-1111-4222-8333-444455556677", subagent=True)
    c = write_codex(tmp_path)
    for i, p in enumerate((a, b, c)):
        os.utime(p, (1_800_000_000 + i, 1_800_000_000 + i))
    return a, b, c


def test_default_roots_point_under_home(tmp_path):
    roots = reg.default_roots(tmp_path)
    assert roots == {"claude_code": tmp_path / ".claude" / "projects",
                     "codex": tmp_path / ".codex" / "sessions"}
    assert reg.discover(roots) == []


def test_discover_lists_newest_first_with_flags_and_no_content(tmp_path):
    a, b, c = _home(tmp_path)
    (tmp_path / ".claude" / "projects" / "C--work-repo" / "notes.jsonl").write_text("{}")
    (tmp_path / ".codex" / "sessions" / "2026" / "09" / "10" / "index.json").write_text("{}")
    entries = reg.discover(reg.default_roots(tmp_path))
    assert [e["path"] for e in entries] == [str(c), str(b), str(a)]
    assert entries[0]["harness"] == "codex" and "project_slug" not in entries[0]
    assert entries[1] == {"path": str(b), "harness": "claude_code",
                          "size_bytes": b.stat().st_size, "mtime_utc": entries[1]["mtime_utc"],
                          "subagent_path": True, "project_slug": "C--work-repo"}
    assert entries[2]["subagent_path"] is False
    assert entries[1]["mtime_utc"].endswith("Z")


def test_discover_refuses_symlinked_directories(tmp_path):
    _home(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    write_codex(other, thread_id="01a0ffff-0000-7000-8000-000000000009")
    link = tmp_path / ".codex" / "sessions" / "2026" / "09" / "11"
    try:
        os.symlink(other / ".codex" / "sessions" / "2026" / "09" / "10", link,
                   target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted here")
    paths = [e["path"] for e in reg.discover(reg.default_roots(tmp_path))]
    assert not any("elsewhere" in p or "\\11\\" in p or "/11/" in p for p in paths)
    assert len(paths) == 3


def test_registry_observes_only_the_newest_limit_and_hashes_its_body(tmp_path):
    a, b, c = _home(tmp_path)
    registry = reg.build_registry(reg.discover(reg.default_roots(tmp_path)), observed_at=NOW,
                                  limit=2)
    assert_no_canary(registry)
    assert registry["discovered"] == 3
    assert registry["discovered_by_harness"] == {"claude_code": 2, "codex": 1}
    assert registry["observed_count"] == 2 and registry["observe_failures"] == 0
    assert [s["source"]["path"] for s in registry["sessions"]] == [str(c), str(b)]
    assert registry["unobserved"] == [{"path": str(a), "harness": "claude_code",
                                       "size_bytes": a.stat().st_size,
                                       "mtime_utc": registry["unobserved"][0]["mtime_utc"]}]
    assert registry["sessions"][1]["subagent_path"] is True
    assert registry["sessions"][1]["project_slug"] == "C--work-repo"
    assert all(s["name_ref_consistent"] is True for s in registry["sessions"])
    body = {k: v for k, v in registry.items() if k != "registry_sha256"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert registry["registry_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    assert "does not prove any session is running" in registry["does_not_prove"]


def test_registry_hash_and_window_hashes_change_on_append_and_truncate(tmp_path):
    path = write_codex(tmp_path)
    entries = reg.discover(reg.default_roots(tmp_path))
    before = reg.build_registry(entries, observed_at=NOW)
    with path.open("ab") as fh:
        fh.write(jsonl(codex_records(turns=1)[1:2]))
    after = reg.build_registry(reg.discover(reg.default_roots(tmp_path)), observed_at=NOW)
    assert after["registry_sha256"] != before["registry_sha256"]
    assert (after["sessions"][0]["windows"]["tail"]["sha256"]
            != before["sessions"][0]["windows"]["tail"]["sha256"])
    with path.open("r+b") as fh:
        fh.truncate(200)
    cut = reg.build_registry(reg.discover(reg.default_roots(tmp_path)), observed_at=NOW)
    assert cut["registry_sha256"] not in (before["registry_sha256"], after["registry_sha256"])
    assert cut["sessions"][0]["windows"]["head"]["parse"]["trailing_partial_line"] is True
    raw = path.read_bytes()
    head = cut["sessions"][0]["windows"]["head"]
    assert len(raw) == 200 and cut["sessions"][0]["source"]["size_bytes"] == 200
    assert head["offset"] == 0 and head["length"] == 200
    assert head["sha256"] == hashlib.sha256(raw).hexdigest()
    assert head["sha256"] != before["sessions"][0]["windows"]["head"]["sha256"]


def test_file_name_does_not_win_when_content_disagrees_or_is_absent(tmp_path):
    """A file name is chosen by whoever wrote the file, so an id read from a name
    is never reported as the session's id. Both files here are named for one id
    and hold another, and neither name reaches the record outside its path."""
    other = "ffffffff-0000-4000-8000-000000000001"
    named_for = "01a0aaaa-bbbb-7ccc-8ddd-eeeeffff0099"
    mismatched = write_claude(tmp_path, session_id=other, records=claude_records(CLAUDE_SESSION))
    unparseable = tmp_path / ".codex" / "sessions" / "2026" / "09" / "10"
    unparseable.mkdir(parents=True)
    broken = unparseable / f"rollout-2026-09-10T09-00-00-{named_for}.jsonl"
    broken.write_bytes(b"\xef\xbb\xbf{not json at all\n" + jsonl(codex_records()[1:]))
    registry = reg.build_registry(reg.discover(reg.default_roots(tmp_path)), observed_at=NOW)
    by_path = {s["source"]["path"]: s for s in registry["sessions"]}
    claude = by_path[str(mismatched)]
    assert claude["session_id"]["value"] == CLAUDE_SESSION
    assert claude["name_ref_consistent"] is False
    assert other not in json.dumps({k: v for k, v in claude.items() if k != "source"})
    codex = by_path[str(broken)]
    assert codex["thread_id"] is None
    assert codex["name_ref_consistent"] is None
    assert "session_meta_absent_in_head" in codex["issues"]
    assert codex["windows"]["head"]["parse"]["unparsed_lines"] == 1
    body = json.dumps({k: v for k, v in codex.items() if k != "source"})
    assert named_for not in body


def test_an_id_read_only_from_the_tail_is_reported_as_a_tail_reading(tmp_path):
    """A rollout whose session_meta is gone still carries its id in the turn
    records. That reading is reported under its own key, with the sample count
    that produced it, and it never becomes the declared thread_id."""
    unparseable = tmp_path / ".codex" / "sessions" / "2026" / "09" / "10"
    unparseable.mkdir(parents=True)
    broken = unparseable / "rollout-2026-09-10T09-00-00-not-an-id.jsonl"
    broken.write_bytes(jsonl(codex_records()[1:]))
    registry = reg.build_registry(reg.discover(reg.default_roots(tmp_path)), observed_at=NOW)
    codex = registry["sessions"][0]
    assert codex["thread_id"] is None and codex["thread_id_basis"]["value"] is None
    assert codex["thread_id_in_tail"] == {"value": CODEX_THREAD, "basis": "consistent",
                                          "samples": 6}
    body = json.dumps({k: v for k, v in codex.items() if k != "source"})
    assert body.count(CODEX_THREAD) == 1


def test_observe_failure_is_recorded_not_raised(tmp_path):
    a, _, _ = _home(tmp_path)
    ghost = {"path": str(tmp_path / "missing.jsonl"), "harness": "codex", "size_bytes": 0,
             "mtime_utc": "2030-01-01T00:00:00Z", "subagent_path": False}
    folder = {"path": str(tmp_path), "harness": "claude_code", "size_bytes": 0,
              "mtime_utc": "2030-01-01T00:00:01Z", "subagent_path": False}
    entries = reg.discover(reg.default_roots(tmp_path)) + [ghost, folder]
    registry = reg.build_registry(entries, observed_at=NOW, limit=2)
    assert registry["observe_failures"] == 2 and registry["observed_count"] == 0
    assert registry["sessions"][0] == {"path": str(tmp_path), "harness": "claude_code",
                                       "observed": False, "error": "SourceRejected",
                                       "subagent_path": False}
    assert registry["sessions"][1]["observed"] is False
    assert registry["unobserved"][0]["path"] == str(reg.discover(reg.default_roots(tmp_path))[0]["path"])


def test_registry_rejects_bad_limit(tmp_path):
    with pytest.raises(ValueError):
        reg.build_registry([], observed_at=NOW, limit=-1)
    with pytest.raises(ValueError):
        reg.build_registry([], observed_at=NOW, limit=True)


def test_limit_zero_observes_nothing(tmp_path):
    _home(tmp_path)
    registry = reg.build_registry(reg.discover(reg.default_roots(tmp_path)), observed_at=NOW,
                                  limit=0)
    assert registry["sessions"] == [] and len(registry["unobserved"]) == 3


def test_unobserved_list_is_bounded_but_counted_in_full():
    entries = [{"path": f"C:/x/rollout-{i:04d}.jsonl", "harness": "codex", "size_bytes": i,
                "mtime_utc": f"2026-09-10T00:{i // 60:02d}:{i % 60:02d}Z", "subagent_path": False}
               for i in range(reg.MAX_UNOBSERVED_LISTED + 6)]
    registry = reg.build_registry(entries, observed_at=NOW, limit=0)
    assert registry["discovered"] == reg.MAX_UNOBSERVED_LISTED + 6
    assert registry["unobserved_count"] == reg.MAX_UNOBSERVED_LISTED + 6
    assert registry["unobserved_listed"] == len(registry["unobserved"]) == reg.MAX_UNOBSERVED_LISTED
    assert registry["unobserved"][0]["path"].endswith("0069.jsonl")
    assert "0000.jsonl" not in json.dumps(registry)
