"""The receipts ledger (GET /api/receipts) must be re-checkable and honest:
envelope hashes move when content moves, unreadable envelopes are reported
not dropped, and an empty run root yields an empty ledger, not an error."""

import json

from harness import gateway


def _write_envelope(env_dir, name, verdict="PASS", task_id="t1"):
    env_dir.mkdir(parents=True, exist_ok=True)
    p = env_dir / name
    p.write_text(json.dumps({"verdict": verdict, "task_id": task_id}),
                 encoding="utf-8")
    return p


def test_ledger_lists_envelopes_with_verdicts(tmp_path):
    env = tmp_path / "run" / "envelopes"
    _write_envelope(env, "a.json", verdict="PASS", task_id="alpha")
    _write_envelope(env, "b.json", verdict="FAIL", task_id="beta")
    doc = gateway.receipts_ledger(tmp_path, tmp_path / "run")
    assert doc["schema"] == "flywheel.receipts/v1"
    assert doc["envelope_count"] == 2
    assert doc["pass_count"] == 1
    by_name = {e["name"]: e for e in doc["envelopes"]}
    assert by_name["a.json"]["verdict"] == "PASS"
    assert by_name["a.json"]["task_id"] == "alpha"
    assert by_name["b.json"]["verdict"] == "FAIL"


def test_ledger_hash_moves_when_envelope_changes(tmp_path):
    env = tmp_path / "run" / "envelopes"
    p = _write_envelope(env, "a.json")
    before = gateway.receipts_ledger(tmp_path, tmp_path / "run")
    p.write_text(json.dumps({"verdict": "PASS", "task_id": "tampered"}),
                 encoding="utf-8")
    after = gateway.receipts_ledger(tmp_path, tmp_path / "run")
    assert before["envelopes"][0]["sha256"] != after["envelopes"][0]["sha256"]


def test_ledger_reports_unreadable_envelope_honestly(tmp_path):
    env = tmp_path / "run" / "envelopes"
    env.mkdir(parents=True)
    (env / "broken.json").write_text("{not json", encoding="utf-8")
    doc = gateway.receipts_ledger(tmp_path, tmp_path / "run")
    assert doc["envelope_count"] == 1
    assert doc["envelopes"][0]["verdict"] == "UNREADABLE"
    assert doc["pass_count"] == 0


def test_ledger_empty_run_root_is_empty_not_error(tmp_path):
    doc = gateway.receipts_ledger(tmp_path, tmp_path / "nonexistent")
    assert doc["envelope_count"] == 0
    assert doc["envelopes"] == []
    # The in-repo catalog is still reported (absent files marked honestly).
    assert len(doc["catalog"]) == len(gateway.RECEIPT_CATALOG)
    assert doc["catalog_present"] == 0
    assert doc["merkle_root"] == "", "an empty log has no root"


def test_every_envelope_proves_inclusion_against_the_root(tmp_path):
    from harness.transparency_log import verify_inclusion, inclusion_proof
    env = tmp_path / "run" / "envelopes"
    for i in range(5):
        _write_envelope(env, f"e{i}.json", task_id=f"t{i}")
    doc = gateway.receipts_ledger(tmp_path, tmp_path / "run")
    root = doc["merkle_root"]
    assert len(root) == 64
    leaves = [e["sha256"] for e in doc["envelopes"]]
    for i, leaf in enumerate(leaves):
        assert verify_inclusion(leaf, inclusion_proof(leaves, i), root)
    # a hash not in the log cannot forge a proof
    import hashlib
    forged = hashlib.sha256(b"not-a-receipt").hexdigest()
    assert not verify_inclusion(forged, inclusion_proof(leaves, 0), root)
