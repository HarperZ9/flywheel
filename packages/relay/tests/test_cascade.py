"""Local-first cascade: decisions, escalation, ledger records and the bench.

Each behaviour is asserted with a paired mutation that must flip it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from relay.cascade import Cascade, FlakyClassifier
from relay.cascade_bench import calibrate, decide, run, split
from relay.local_session import SessionLedger

FIXTURE = Path(__file__).parent / "fixtures" / "flaky_failure_labels.json"
FLAKY = "requests.exceptions.ConnectionError: Connection reset by peer\nE   429 Too Many Requests"
REAL = "E   ModuleNotFoundError: No module named 'app.config'"


def test_transport_failure_reads_flaky_and_import_error_reads_real():
    clf = FlakyClassifier()
    assert clf.probability(FLAKY) > 0.9
    assert clf.probability(REAL) < 0.1


def test_code_defect_outweighs_a_refused_connection():
    clf = FlakyClassifier()
    alone = "ConnectionRefusedError: [Errno 111] Connection refused"
    crashed = alone + "\nserver exited: ImportError: cannot import name 'settings'"
    assert clf.probability(alone) > 0.5 > clf.probability(crashed)


def test_confident_question_stays_local_and_unsure_one_escalates():
    calls = []
    endpoint = lambda q, s: calls.append(s) or True  # noqa: E731
    cascade = Cascade(FlakyClassifier(), endpoint, threshold=0.9)
    assert cascade.ask("flaky?", REAL).decided_by == "local"
    assert calls == []
    unsure = cascade.ask("flaky?", "test_x FAILED")
    assert unsure.decided_by == "endpoint" and unsure.value is True and len(calls) == 1


def test_default_threshold_escalates_ordinary_questions():
    calls = []
    cascade = Cascade(FlakyClassifier(), lambda q, s: calls.append(s) or False)
    assert cascade.ask("flaky?", "AssertionError: expected 3, got 4").decided_by == "endpoint"
    assert calls


def test_every_answer_is_written_to_the_ledger():
    ledger = SessionLedger()
    cascade = Cascade(FlakyClassifier(), lambda q, s: False, threshold=0.9, ledger=ledger)
    cascade.ask("flaky?", REAL)
    cascade.ask("flaky?", "test_x FAILED")
    metas = [e.meta for e in ledger.entries if e.kind == "cascade"]
    assert [m["decided_by"] for m in metas] == ["local", "endpoint"]
    assert ledger.verify()


def test_threshold_outside_range_is_refused():
    with pytest.raises(ValueError):
        Cascade(FlakyClassifier(), lambda q, s: True, threshold=0.3)


def test_decide_and_calibrate_on_a_toy_set():
    probs, labels = [0.99, 0.02, 0.6, 0.4], [True, False, False, True]
    r = decide(probs, labels, 0.9)
    assert r["decided"] == 2 and r["decided_accuracy"] == 1.0
    assert decide(probs, labels, 0.5)["decided_accuracy"] == 0.5
    assert calibrate(probs, labels) <= 0.9


def test_split_is_deterministic_and_complete():
    items = [{"id": f"f{i:03d}"} for i in range(40)]
    dev, test = split(items)
    assert (dev, test) == split(items) and len(dev) + len(test) == 40


def test_bench_reproduces_the_reported_null():
    items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
    out = run(items)
    assert out["bar"] == {"C1_decides_half": False, "C2_accuracy_095": False,
                          "control_fails_C2": True}
    assert (out["shuffled_label_control"]["decided_accuracy"]
            < out["test_result"]["decided_accuracy"])
    assert out == run(items)
