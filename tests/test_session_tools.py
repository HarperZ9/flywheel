"""test_session_tools.py: QoL over the receipt store: browse, resume, export.

Success criteria (each assertion is meaningful, not "it ran"):
  - list_sessions returns one row per envelope file with the documented fields,
    the right values, a stable order, and [] for a missing or empty dir.
  - get_session finds a written task and returns None for an unknown one.
  - resume_context returns the exact VerifiedPool handle loop.py banks.
  - export_transcript is deterministic (same store -> same digest) and, when
    redacted, drops a planted secret, scrubs a planted absolute path, and carries
    the candidate only as a hash; unredacted keeps the raw candidate.
  - engine_status reports code+math domains, a provider count > 20, and the live
    session count, with no secret or path in the summary.
"""
import json
from pathlib import Path

from harness.envelope import ProofEnvelope
from harness import session_tools as st


def _env(task_id="t1", verdict="PASS", candidate="def f():\n    return 1\n",
         model_ref="stub:pass", extra=None):
    e = ProofEnvelope(
        task_id=task_id, candidate=candidate, oracle="pytest",
        oracle_cmd="pytest -q", oracle_output_hash="deadbeef",
        verdict=verdict, model_ref=model_ref, seed=1, prompt_hash="ph",
        budget_spent={"candidates": 1, "oracle_calls": 1})
    for k, v in (extra or {}).items():
        setattr(e, k, v)
    return e


def _write(d, e):
    return e.write(Path(d) / f"{e.task_id}-{e.content_hash()}.json")


def test_list_sessions_lists_written_envelopes(tmp_path):
    _write(tmp_path, _env("t1"))
    _write(tmp_path, _env("t2", model_ref="stub:x", verdict="PASS"))
    rows = st.list_sessions(str(tmp_path))
    assert len(rows) == 2
    assert set(rows[0]) == {"task_id", "verdict", "model_ref",
                            "content_hash", "accepted", "path"}
    by_id = {r["task_id"]: r for r in rows}
    assert by_id["t1"]["verdict"] == "PASS"
    assert by_id["t1"]["accepted"] is True
    assert by_id["t1"]["model_ref"] == "stub:pass"
    assert len(by_id["t1"]["content_hash"]) == 16


def test_list_sessions_missing_and_empty_dir(tmp_path):
    assert st.list_sessions(str(tmp_path / "does-not-exist")) == []
    empty = tmp_path / "empty"
    empty.mkdir()
    assert st.list_sessions(str(empty)) == []
    assert st.list_sessions(None) == []


def test_list_sessions_is_stable(tmp_path):
    _write(tmp_path, _env("b"))
    _write(tmp_path, _env("a"))
    first = [r["task_id"] for r in st.list_sessions(str(tmp_path))]
    second = [r["task_id"] for r in st.list_sessions(str(tmp_path))]
    assert first == second == ["a", "b"]


def test_get_session_found_and_unknown(tmp_path):
    e = _write(tmp_path, _env("t1"))
    got = st.get_session(str(tmp_path), "t1")
    assert got is not None
    assert got["task_id"] == "t1"
    assert got["candidate"] == "def f():\n    return 1\n"
    assert st.get_session(str(tmp_path), "nope") is None


def test_resume_context_returns_pool_handle(tmp_path):
    e = _env("t1")
    _write(tmp_path, e)
    ctx = st.resume_context(str(tmp_path), "t1")
    # exactly the handle loop.py banks: pool.add_verified(task_id, "envelope:<h>")
    assert ctx == {"t1": f"envelope:{e.content_hash()}"}
    assert st.resume_context(str(tmp_path), "nope") is None


def test_resume_context_ignores_non_pass(tmp_path):
    _write(tmp_path, _env("t9", verdict="FAIL"))
    assert st.resume_context(str(tmp_path), "t9") is None


def test_export_transcript_is_deterministic(tmp_path):
    _write(tmp_path, _env("t1"))
    a = st.export_transcript(str(tmp_path), "t1")
    b = st.export_transcript(str(tmp_path), "t1")
    assert a["schema"] == "flywheel.transcript-export/v1"
    assert a["task_id"] == "t1"
    assert a["bundle_digest"].startswith("sha256:")
    assert a["bundle_digest"] == b["bundle_digest"]
    assert len(a["entries"]) == 1


def test_export_transcript_redacts_secret_path_and_candidate(tmp_path):
    e = _env(
        "t1",
        candidate="TOPSECRET_CANDIDATE_SOURCE_should_not_ship",
        extra={
            "admission": {
                "authorization": "Bearer sk-live-supersecret-value",
                "api_key": "another-secret",
                "workdir": "C:\\Users\\Zain\\secrets\\creds.txt",
            },
            "retrieved": [{"source": "/home/zain/proj/module.py",
                           "receipt": "envelope:abc"}],
        })
    _write(tmp_path, e)
    bundle = st.export_transcript(str(tmp_path), "t1", redacted=True)
    blob = json.dumps(bundle)

    # planted secret values are gone
    assert "supersecret-value" not in blob
    assert "another-secret" not in blob
    # planted candidate source is gone, carried only as a hash
    assert "TOPSECRET_CANDIDATE_SOURCE_should_not_ship" not in blob
    # absolute paths scrubbed (Windows and POSIX)
    assert "Zain" not in blob
    assert "creds.txt" not in blob
    assert "/home/zain/proj/module.py" not in blob

    entry = bundle["entries"][0]
    assert "candidate" not in entry
    assert entry["candidate_sha256"].startswith("sha256:")
    assert entry["admission"]["authorization"] == "[redacted]"
    assert entry["admission"]["api_key"] == "[redacted]"
    assert entry["admission"]["workdir"] == "[redacted-path]"


def test_export_unredacted_keeps_raw_candidate(tmp_path):
    _write(tmp_path, _env("t1", candidate="RAW_CANDIDATE_TEXT"))
    bundle = st.export_transcript(str(tmp_path), "t1", redacted=False)
    assert bundle["entries"][0]["candidate"] == "RAW_CANDIDATE_TEXT"


def test_engine_status_reports_domains_providers_sessions(tmp_path):
    _write(tmp_path, _env("t1"))
    status = st.engine_status(envelopes_dir=str(tmp_path))
    assert "code" in status["domains"]
    assert "math" in status["domains"]
    assert status["provider_count"] > 20
    assert status["session_count"] == 1
    # presence-only: no secret or absolute path leaks into the summary
    assert "secret" not in json.dumps(status).lower()


def test_engine_status_works_without_dir():
    status = st.engine_status()
    assert "code" in status["domains"] and "math" in status["domains"]
    assert status["provider_count"] > 20
    assert status["session_count"] == 0
