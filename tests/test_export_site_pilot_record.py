"""Falsifiers for the record the public site renders a figure from.

The site hashes this document and republishes it, so two things have to hold.
It must carry nothing from the machine that produced it, and every count in it
must come from the run rather than from a person retyping numbers. The figure
already drifted once the other way: it said four attempts for a week after the
repository's own record said thirty-five.
"""
import json

import pytest

from scripts.export_site_pilot_record import (build, parity_artifacts, receipt_records,
                                              render, role_entry)


def role(name, **over):
    base = {"provider_role": name, "attempts": 7, "launched": 7, "scored": 4, "oracle_pass": 2,
            "pass_rate": 0.5, "latency_ms_median": 4200.0, "latency_ms_p90": 9000.0,
            "cost_usd_total": None, "cost_reported_attempts": 0, "cost_coverage": 0.0,
            "output_tokens_total": None, "models_observed": [name + "-model"],
            "unreadable_reasons": {"refused at the envelope": 1},
            "envelope_recovery": {"refused": 1, "held_an_envelope": 1, "unread": 0},
            "null_reasons": {"cost_usd_total": "provider_cost_unavailable"}}
    base.update(over)
    return base


def row(name, task="agt-001", prompt="a" * 64, context="b" * 64, receipt=""):
    return {"provider_role": name, "task_id": task, "raw_prompt_sha256": prompt,
            "runtime_context_sha256": context, "receipt_path": receipt,
            "receipt_state": "verified"}


def report(roles=None, **over):
    doc = {"schema": "flywheel.graded_metric_report/v1", "run_ids": ["run-1"],
           "source_commits": ["0" * 40], "task_set_ids": ["flywheel_agentic_gauntlet_v1"],
           "counts": {"attempts": 14, "launched": 14, "scored": 8, "roles": 2,
                      "graded_checkers": 1},
           "roles": roles if roles is not None else [role("flywheel_harness"), role("codex_harness")],
           "checkers": [], "does_not_prove": ["Latency is wall clock on one machine."]}
    doc.update(over)
    return doc


def scorecard(rows):
    return {"schema": "harness.cross-harness-task-scorecard/v1", "rows": rows,
            "source_tree_state": "unsealed"}


def test_no_path_from_the_building_machine_can_reach_the_published_record(tmp_path):
    """The failure this guard exists for shipped once already, in another record."""
    for leak in ("C:/dev/run", "C:\\dev\\run", "/home/someone/run",
                 "/Users/someone/run", "AppData"):
        with pytest.raises(ValueError, match="refusing to publish"):
            render({"note": leak})


def test_a_url_is_not_mistaken_for_a_path():
    """The commit link is the one thing a reader can actually follow."""
    text = render({"sourceCommitUrl": "https://github.com/HarperZ9/flywheel/commit/abc",
                   "other": "file://host/share"})
    assert "https://github.com/HarperZ9/flywheel/commit/abc" in text


def test_a_task_whose_roles_got_different_bytes_is_never_called_byte_identical():
    """Parity is the claim the whole comparison rests on, so it is measured."""
    rows = [row("a", prompt="1" * 64), row("b", prompt="2" * 64)]
    record = build(report(), scorecard(rows), "missing")
    assert record["parity"] == {"prompt": "mixed", "runtimeContext": "mixed"}
    assert record["parityArtifacts"][0]["identicalAcrossRoles"] is False
    assert len(record["parityArtifacts"][0]["prompt"]["sha256"]) == 2


def test_matching_bytes_across_every_task_are_reported_as_byte_identical():
    rows = [row("a"), row("b"), row("a", task="agt-002", prompt="c" * 64),
            row("b", task="agt-002", prompt="c" * 64)]
    record = build(report(), scorecard(rows), "missing")
    assert record["parity"]["prompt"] == "byte-identical"
    assert record["counts"]["tasks"] == 2


def test_a_run_with_no_parity_evidence_makes_no_parity_claim():
    """An empty list would otherwise satisfy `all` and publish the strong word."""
    assert build(report(), scorecard([]), "missing")["parity"]["prompt"] == "mixed"


def test_a_receipt_that_cannot_be_read_is_recorded_without_a_hash(tmp_path):
    """A record can outlive its artifacts. Dropping the row would hide an attempt."""
    records = receipt_records([row("a", receipt=str(tmp_path / "gone.json"))])
    assert records[0]["receiptSha256"] is None
    assert records[0]["receiptSubjectSha256"] is None
    assert records[0]["state"] == "verified"


def test_a_receipt_contributes_its_own_two_identities(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({"receipt_subject_sha256": "d" * 64}), encoding="utf-8")
    record = receipt_records([row("a", receipt=str(path))])[0]
    assert record["receiptSubjectSha256"] == "d" * 64
    assert len(record["receiptSha256"]) == 64
    assert record["receiptSha256"] != record["receiptSubjectSha256"]


def test_the_verified_count_counts_states_rather_than_trusting_a_total():
    rows = [row("a", receipt=""), dict(row("b", receipt=""), receipt_state="drift")]
    receipts = build(report(), scorecard(rows), "missing")["receipts"]
    assert receipts == {"attempts": 2, "verified": 1, "records": receipts["records"]}


def test_the_passes_are_summed_from_the_roles_and_not_retyped():
    record = build(report(roles=[role("a", oracle_pass=3), role("b", oracle_pass=1)]),
                   scorecard([row("a")]), "missing")
    assert record["counts"]["passed"] == 4
    assert record["counts"]["attempts"] == 14  # the report's own denominator, untouched


def test_every_reason_an_attempt_went_ungraded_survives_into_the_record():
    """Without these the readable rate reads as a verdict on the harness."""
    entry = role_entry(role("local_32b", unreadable_reasons={
        "the model endpoint did not answer": 4, "refused at the envelope": 1}))
    assert entry["ungraded"]["the model endpoint did not answer"] == 4
    assert entry["envelopeRecovery"]["held_an_envelope"] == 1
    assert entry["nullReasons"]["cost_usd_total"] == "provider_cost_unavailable"


def test_a_cost_the_provider_never_stated_stays_null_with_its_coverage():
    """Zero coverage and a zero cost are different facts and must not merge."""
    entry = role_entry(role("codex_harness"))
    assert entry["cost"] == {"usdTotal": None, "reportedAttempts": 0, "coverage": 0.0}


def test_a_partial_cost_keeps_the_coverage_that_makes_it_readable():
    entry = role_entry(role("claude_code", cost_usd_total=0.4997,
                            cost_reported_attempts=6, cost_coverage=0.8571))
    assert entry["cost"]["usdTotal"] == 0.4997 and entry["cost"]["coverage"] == 0.8571


def test_the_tree_state_the_run_recorded_is_carried_rather_than_assumed_clean():
    """`unsealed` means nobody checked, which is not the same as checked and clean."""
    assert build(report(), scorecard([row("a")]), "missing")["sourceTreeState"] == "unsealed"


def test_an_artifact_that_is_not_on_disk_is_absent_rather_than_hashed_as_empty(tmp_path):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    hashes = build(report(), scorecard([row("a")]), tmp_path)["artifactHashes"]
    assert list(hashes) == ["manifest.json"]
    assert len(hashes["manifest.json"]) == 64


def test_the_limitations_come_from_the_run_and_are_not_written_here():
    """A hand-written limitation list stops matching the run it describes."""
    record = build(report(does_not_prove=["Only one repetition per task."]),
                   scorecard([row("a")]), "missing")
    assert record["limitations"] == ["Only one repetition per task."]
