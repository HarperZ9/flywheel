"""Falsifier for the findings composer (harness/findings.py).

The composer must: bind every value to a source artifact + hash, emit honest
"pending" (never a fabricated number) for a missing artifact, produce a root hash
that changes iff a source changes, and self-verify (a stale doc fails).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.findings import project_findings, verify_findings


def _write_min_artifacts(root: Path, consensus_passed=4):
    (root / "difficulty_screen_hard_v2_110.json").write_text(json.dumps({
        "n_tasks": 110, "headroom_at_temp0": ["t"] * 61,
    }), encoding="utf-8")
    (root / "selector_consensus_headroom.json").write_text(json.dumps({
        "n_tasks": 61,
        "single_shot": {"passed": 3}, "verified_external": {"passed": 14},
        "verified_self": {"passed": 3}, "verified_consensus": {"passed": consensus_passed},
    }), encoding="utf-8")
    (root / "he_base_comparison.json").write_text(json.dumps({"delta": -3.0}), encoding="utf-8")


def test_all_pending_when_no_artifacts(tmp_path):
    doc = project_findings(tmp_path)
    assert doc["schema"] == "flywheel.findings/v1"
    assert doc["measured"] == 0
    assert all(f["status"] == "pending" and f["value"] is None for f in doc["findings"])


def test_measured_bind_source_and_hash(tmp_path):
    _write_min_artifacts(tmp_path)
    doc = project_findings(tmp_path)
    measured = [f for f in doc["findings"] if f["status"] == "measured"]
    assert len(measured) == 3
    for f in measured:
        assert f["value"] is not None
        assert f["source_sha256"] is not None and len(f["source_sha256"]) == 64


def test_root_hash_changes_when_artifact_changes(tmp_path):
    _write_min_artifacts(tmp_path, consensus_passed=4)
    h1 = project_findings(tmp_path)["root_hash"]
    _write_min_artifacts(tmp_path, consensus_passed=9)   # a source changed
    h2 = project_findings(tmp_path)["root_hash"]
    assert h1 != h2


def test_root_hash_stable_when_unchanged(tmp_path):
    _write_min_artifacts(tmp_path)
    assert project_findings(tmp_path)["root_hash"] == project_findings(tmp_path)["root_hash"]


def test_verify_detects_stale(tmp_path):
    _write_min_artifacts(tmp_path)
    doc = project_findings(tmp_path)
    assert verify_findings(doc, tmp_path) is True
    _write_min_artifacts(tmp_path, consensus_passed=99)   # source moved under it
    assert verify_findings(doc, tmp_path) is False


def test_present_but_malformed_is_pending(tmp_path):
    # artifact exists but is missing the required keys -> honest pending, NOT a
    # fabricated "single None/None" value
    (tmp_path / "selector_consensus_headroom.json").write_text(
        json.dumps({"n_tasks": 61, "single_shot": {}}), encoding="utf-8")
    doc = project_findings(tmp_path)
    sel = next(f for f in doc["findings"] if f["key"] == "selector_comparison")
    assert sel["status"] == "pending"
    assert sel["value"] is None
    assert sel["source_sha256"] is not None      # still commits to the (bad) file


def test_unparseable_artifact_is_pending(tmp_path):
    (tmp_path / "he_base_comparison.json").write_text("{not json", encoding="utf-8")
    doc = project_findings(tmp_path)
    he = next(f for f in doc["findings"] if f["key"] == "humaneval_base_vs_cpt")
    assert he["status"] == "pending" and he["value"] is None


def test_pending_never_fabricates(tmp_path):
    # only the difficulty screen present -> the others must be honest pending
    (tmp_path / "difficulty_screen_hard_v2_110.json").write_text(
        json.dumps({"n_tasks": 110, "headroom_at_temp0": []}), encoding="utf-8")
    doc = project_findings(tmp_path)
    passn = next(f for f in doc["findings"] if f["key"] == "passn_curve")
    assert passn["status"] == "pending"
    assert passn["value"] is None


def test_nested_non_dict_inner_is_pending_not_crash(tmp_path):
    # single_shot is a STRING, not a dict -> must degrade to pending, not crash
    (tmp_path / "selector_consensus_headroom.json").write_text(json.dumps({
        "n_tasks": 61, "single_shot": "oops", "verified_external": {"passed": 14},
        "verified_self": {"passed": 3}, "verified_consensus": {"passed": 4},
    }), encoding="utf-8")
    doc = project_findings(tmp_path)      # must not raise
    sel = next(f for f in doc["findings"] if f["key"] == "selector_comparison")
    assert sel["status"] == "pending"


def test_n_tasks_zero_is_preserved_not_replaced(tmp_path):
    # a legitimate n_tasks of 0 must survive, not fall through the truthy 'or'
    (tmp_path / "difficulty_screen_hard_v2_110.json").write_text(
        json.dumps({"n_tasks": 0, "headroom_at_temp0": []}), encoding="utf-8")
    doc = project_findings(tmp_path)
    diff = next(f for f in doc["findings"] if f["key"] == "difficulty_screen")
    assert "of 0 at temp 0" in diff["value"]      # 0 preserved, not recomputed


def test_humaneval_value_has_no_raw_dump(tmp_path):
    # the public value must carry only known fields, never arbitrary artifact keys
    (tmp_path / "he_base_comparison.json").write_text(json.dumps({
        "delta": -3.0, "flywheel_pass": 136, "base_pass": 141,
        "secret_internal_path": "C:/should/not/appear",
    }), encoding="utf-8")
    doc = project_findings(tmp_path)
    he = next(f for f in doc["findings"] if f["key"] == "humaneval_base_vs_cpt")
    assert he["status"] == "measured"
    assert "should/not/appear" not in (he["value"] or "")   # no raw leak
    assert "flywheel 136 vs base 141" in he["value"]


def test_envelope_finding_mints_and_moves_root_hash(tmp_path):
    """Gap C falsifier: a freshly-minted PASS envelope must appear in the
    findings doc and move its root hash; deleting it must move it back. Before
    Phase 3, envelopes/ was invisible to project_findings."""
    _write_min_artifacts(tmp_path)
    base = project_findings(tmp_path)
    env_finding = next((f for f in base["findings"] if f["key"] == "verified_envelopes"), None)
    assert env_finding is not None, "envelope finding must exist (pending when empty)"
    assert env_finding["status"] == "pending"   # no envelopes yet
    h_before = base["root_hash"]

    # mint one PASS envelope
    env_dir = tmp_path / "envelopes"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "taskA-abc123.json").write_text(json.dumps({
        "verdict": "PASS", "task_id": "taskA", "content_hash": "abc123",
    }), encoding="utf-8")
    after = project_findings(tmp_path)
    env_after = next(f for f in after["findings"] if f["key"] == "verified_envelopes")
    assert env_after["status"] == "measured"
    assert "1 PASS of 1" in env_after["value"]
    assert after["root_hash"] != h_before, "new envelope must move the root hash"

    # delete it -> root hash reverts
    (env_dir / "taskA-abc123.json").unlink()
    reverted = project_findings(tmp_path)
    assert reverted["root_hash"] == h_before, "deleting the envelope must revert the root hash"
