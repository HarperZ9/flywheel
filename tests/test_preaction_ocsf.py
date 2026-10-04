"""OASP R2: OpenShell OCSF activity logs become sealed, chained Flywheel records.

Asserts outcomes on fixture logs shaped like OpenShell's documented JSONL:
every event becomes one sealed record with the mapped evidence; the store
re-walks MATCH; an edit to an imported record is DRIFT; re-import adds
nothing; and completeness stays UNVERIFIABLE unless the gateway loss counters
read zero, the events are gateway-origin and no line was malformed.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from harness.preaction import cli
from harness.preaction.ocsf_import import (EVENT_SCHEMA, IMPORT_SCHEMA, import_file,
                                           parse_metrics)
from harness.preaction.records import HoldStore
from harness.preaction.verify import verify_store

FIX = Path(__file__).parent / "fixtures" / "openshell_ocsf"


def _metrics(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_supervisor_events_map_to_evidence_and_seal(tmp_path):
    summary = import_file(FIX / "supervisor.jsonl", tmp_path)
    recs = HoldStore(tmp_path).read_all()
    events = [r for r in recs if r["schema"] == EVENT_SCHEMA]
    assert len(events) == 5 and summary["imported"] == 5
    by_uid = {r["metadata_uid"]: r for r in events}
    assert by_uid["evt-001"]["evidence"] == "MATCH"
    assert by_uid["evt-001"]["dst"] == {"domain": "docs.python.org", "ip": "", "port": 443}
    assert by_uid["evt-002"]["evidence"] == "BLOCK"
    assert by_uid["evt-002"]["actor_process"] == "/usr/bin/python3"
    assert by_uid["evt-004"]["evidence"] == "NOTICE"
    assert summary["evidence_counts"] == {"MATCH": 3, "BLOCK": 1, "NOTICE": 1, "RECORDED": 0}
    assert recs[-1]["schema"] == IMPORT_SCHEMA
    assert verify_store(tmp_path)["internal_verdict"] == "MATCH"


def test_supervisor_file_completeness_is_unverifiable_even_with_zero_counters(tmp_path):
    # Sandbox-local records have no loss counters of their own.
    summary = import_file(FIX / "supervisor.jsonl", tmp_path,
                          metrics_text=_metrics("metrics_zero.prom"))
    assert summary["completeness"] == "UNVERIFIABLE"
    assert any("non-gateway" in r for r in summary["completeness_reasons"])


def test_gateway_file_with_zero_loss_counters_is_match(tmp_path):
    summary = import_file(FIX / "gateway.jsonl", tmp_path,
                          metrics_text=_metrics("metrics_zero.prom"))
    assert summary["completeness"] == "MATCH" and summary["completeness_reasons"] == []


def test_gateway_file_without_metrics_is_unverifiable(tmp_path):
    summary = import_file(FIX / "gateway.jsonl", tmp_path)
    assert summary["completeness"] == "UNVERIFIABLE"
    assert summary["completeness_reasons"] == ["no gateway metrics snapshot supplied"]


def test_dropped_records_keep_completeness_unverifiable(tmp_path):
    summary = import_file(FIX / "gateway.jsonl", tmp_path,
                          metrics_text=_metrics("metrics_loss.prom"))
    assert summary["completeness"] == "UNVERIFIABLE"
    reasons = " ".join(summary["completeness_reasons"])
    assert "openshell_ocsf_log_dropped_total = 3" in reasons and "unequal" in reasons


def test_lifecycle_event_means_counters_may_have_reset(tmp_path):
    summary = import_file(FIX / "gateway_lifecycle.jsonl", tmp_path,
                          metrics_text=_metrics("metrics_zero.prom"))
    assert summary["completeness"] == "UNVERIFIABLE"
    assert any("lifecycle" in r for r in summary["completeness_reasons"])


def test_malformed_line_is_counted_and_blocks_completeness(tmp_path):
    summary = import_file(FIX / "malformed.jsonl", tmp_path,
                          metrics_text=_metrics("metrics_zero.prom"))
    assert summary["imported"] == 2 and summary["malformed_lines"] == 1
    assert summary["completeness"] == "UNVERIFIABLE"


def test_missing_loss_counter_is_not_read_as_zero(tmp_path):
    partial = "openshell_ocsf_log_queued_total 2\nopenshell_ocsf_log_written_total 2\n"
    summary = import_file(FIX / "gateway.jsonl", tmp_path, metrics_text=partial)
    assert summary["completeness"] == "UNVERIFIABLE"
    assert any("absent" in r for r in summary["completeness_reasons"])


def test_reimport_skips_events_already_on_record(tmp_path):
    import_file(FIX / "supervisor.jsonl", tmp_path)
    again = import_file(FIX / "supervisor.jsonl", tmp_path)
    assert again["imported"] == 0 and again["skipped_duplicates"] == 5
    assert verify_store(tmp_path)["internal_verdict"] == "MATCH"


def test_edited_imported_record_is_drift(tmp_path):
    import_file(FIX / "supervisor.jsonl", tmp_path)
    path = tmp_path / "records.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    rec["evidence"] = "MATCH"                      # turn the denied connection into an allow
    lines[1] = json.dumps(rec, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = verify_store(tmp_path)
    assert report["verdict"] == "DRIFT"
    assert any(f["cause"] == "SEAL_MISMATCH" for f in report["findings"])


def test_metrics_parser_sums_labels():
    m = parse_metrics(_metrics("metrics_loss.prom"))
    assert m["openshell_ocsf_log_dropped_total"] == 3.0
    assert m["openshell_ocsf_log_queued_total"] == 5.0


def test_cli_import_exit_codes(tmp_path):
    out = io.StringIO()
    code = cli.main(["import-ocsf", str(FIX / "gateway.jsonl"), "--home", str(tmp_path / "a"),
                     "--metrics", str(FIX / "metrics_zero.prom")], stdout=out, stderr=io.StringIO())
    assert code == 0 and json.loads(out.getvalue())["completeness"] == "MATCH"
    code = cli.main(["import-ocsf", str(FIX / "supervisor.jsonl"), "--home", str(tmp_path / "b")],
                    stdout=io.StringIO(), stderr=io.StringIO())
    assert code == 3
