"""Falsifier for the corpus->model export (harness/corpus_export.py).

Gap E: the path from verified experience to a training shard must be wired and
re-checkable. The export reads accepted PASS envelopes, writes a JSONL shard,
and stamps a shard-root hash. verify_corpus_export recomputes it. The training
START remains operator-gated (not tested here -- that is the deliberate open
trigger, not a code gap).
"""
import json

from harness.corpus_export import export_corpus, verify_corpus_export


def _write_envelope(d, name, verdict, task_id="tA", candidate_hash="ch1"):
    (d / name).write_text(json.dumps({
        "verdict": verdict, "task_id": task_id,
        "candidate_sha256": candidate_hash, "oracle_cmd": "pytest",
        "content_hash": "env_" + name,
    }), encoding="utf-8")


def test_export_writes_pass_shard_and_receipt(tmp_path):
    env = tmp_path / "envelopes"
    env.mkdir()
    _write_envelope(env, "tA-pass1.json", "PASS")
    _write_envelope(env, "tA-fail.json", "FAIL")
    out = tmp_path / "shard.jsonl"
    r = export_corpus(env, out)
    assert r["schema"] == "flywheel.corpus-export/v1"
    assert r["exported"] == 1            # only the PASS exported by default
    assert r["skipped"] == 1
    assert r["shard_root_sha256"]
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["verdict"] == "PASS" and row["task_id"] == "tA"


def test_receipt_verifies_against_its_own_shard(tmp_path):
    env = tmp_path / "envelopes"
    env.mkdir()
    _write_envelope(env, "a.json", "PASS", "tA")
    _write_envelope(env, "b.json", "PASS", "tB")
    out = tmp_path / "shard.jsonl"
    r = export_corpus(env, out)
    assert verify_corpus_export(r) == "MATCH"


def test_tampered_shard_is_drift(tmp_path):
    env = tmp_path / "envelopes"
    env.mkdir()
    _write_envelope(env, "a.json", "PASS", "tA")
    out = tmp_path / "shard.jsonl"
    r = export_corpus(env, out)
    # tamper: append an extra line
    out.write_text(out.read_text(encoding="utf-8") +
                   json.dumps({"task_id": "EVIL", "verdict": "PASS"}) + "\n",
                   encoding="utf-8")
    assert verify_corpus_export(r) == "DRIFT"


def test_empty_envelopes_dir_exports_zero(tmp_path):
    env = tmp_path / "envelopes"
    env.mkdir()
    out = tmp_path / "shard.jsonl"
    r = export_corpus(env, out)
    assert r["exported"] == 0
    assert r["shard_root_sha256"] == ""


def test_failure_corpus_mode_exports_non_pass(tmp_path):
    # verdict_filter="" exports everything (useful for a failure-corpus lane).
    env = tmp_path / "envelopes"
    env.mkdir()
    _write_envelope(env, "a.json", "PASS", "tA")
    _write_envelope(env, "b.json", "FAIL", "tB")
    out = tmp_path / "failures.jsonl"
    r = export_corpus(env, out, verdict_filter="FAIL")
    assert r["exported"] == 1
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["verdict"] == "FAIL"
