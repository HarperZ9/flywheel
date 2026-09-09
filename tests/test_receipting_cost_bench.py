"""The cost measurement, and the two ways it could be measuring a fiction.

A timing suite is easy to write and easy to write wrongly. The failure that
matters here is not an inaccurate number, it is an arm that is not doing what
its name says: a buffered arm that skipped the write rather than the wait
would report a cost that nothing pays, and the attribution built on it would
read as an engineering fact.

So the controls are on the arms, not on the figures. The buffered arm must
still write every byte, and the durability syscall must be back in place the
moment that arm is over.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from harness import action_witness
from harness import receipting_cost_bench as bench
from harness.action_witness import LOG_NAME, verify_log
from harness.receipting_cost_bench import (RECORDS_PER_ACTION, _actions,
                                           _buffered, _chain_only, _durable,
                                           _known_bytes, _on_disk, _reading,
                                           _share, _spread, does_not_prove,
                                           run_receipting_cost_benchmark)

SMALL = {"batches": 2, "per_batch": 3}


def test_the_buffered_arm_removes_the_wait_and_keeps_every_byte():
    """The control on the attribution.

    Dropping fsync must drop the wait and nothing else. An arm that wrote less
    would be timing a smaller job and calling the difference durability.
    """
    with _buffered(0) as log:
        assert action_witness.os.fsync(0) is None
        _actions(log, 4)
        path = Path(log.path)
        assert path.exists()
        written = path.read_text(encoding="utf-8").splitlines()
        assert len(written) == 4 * RECORDS_PER_ACTION
        assert log.dropped == 0
        assert verify_log(path)["checked"] == 4 * RECORDS_PER_ACTION


def test_the_durability_syscall_is_back_the_moment_the_arm_ends():
    """Nothing else in the process may lose its fsync to this benchmark."""
    before = action_witness.os
    with _buffered(0) as log:
        assert action_witness.os is not before
        _actions(log, 1)
    assert action_witness.os is before
    assert action_witness.os.fsync is os.fsync


def test_the_chain_only_arm_writes_nothing_to_disk():
    """Its name is its whole claim: hashing and linking, no file."""
    with _chain_only(0) as log:
        _actions(log, 3)
        assert log.path is None
        assert len(log) == 3 * RECORDS_PER_ACTION


def test_the_durable_arm_runs_the_path_that_ships():
    with _durable(0) as log:
        _actions(log, 2)
        assert Path(log.path).name == LOG_NAME
        assert log.dropped == 0


def test_a_recorded_action_reports_each_timed_arm_with_a_spread():
    """The live timing check is only that every arm publishes its own spread.

    The arms run as separate wall-clock samples, so their medians are evidence
    for this run rather than a reliable ordering oracle on a shared CI host.
    The controls above test the work each arm performs; this check only guards
    the report shape those measured figures travel in.
    """
    report = run_receipting_cost_benchmark(**SMALL)
    arms = report["arms"]
    assert set(arms) == {"chain_only", "buffered", "durable"}
    for spread in arms.values():
        assert 0.0 <= spread["low_us"] <= spread["median_us"] <= spread["high_us"]


def test_the_attribution_adds_up_to_the_total_it_split():
    report = run_receipting_cost_benchmark(**SMALL)
    split = report["attribution"]
    parts = (split["hash_and_link_us"] + split["write_us"]
             + split["wait_for_durability_us"])
    assert abs(parts - split["total_us"]) < 0.5
    # Two of the three parts are differences between separately timed arms, so
    # a small sample on a busy host can invert one. A share is then not a small
    # number, it is a number that does not exist, and the report has to say so
    # in both places rather than publish a negative fraction.
    share = split["durability_share"]
    if share is None:
        assert "did not separate" in report["reading"]
    else:
        assert 0.0 <= share <= 1.0
        assert split["wait_for_durability_us"] > 0


def test_a_run_that_did_not_separate_the_arms_publishes_no_share():
    """A Windows runner measured a durable arm faster than the buffered one.

    The assertion it broke was reading -1.09 as a share. Both halves of the
    answer are checked here because either one alone is misleading: a null
    share with the ordinary reading beside it looks like a missing field, and
    the reading alone leaves a negative fraction in the record.
    """
    assert _share(-1.0897, 10.0) is None
    assert _share(0.0, 10.0) is None, "no measured difference is not a share"
    assert _share(5.0, 10.0) == 0.5
    assert "did not separate" in _reading(-1.0897, 10.0)
    assert "did not separate" not in _reading(5.0, 10.0)


def test_a_report_with_the_ci_timing_inversion_publishes_no_share(monkeypatch):
    """The CI failure shape is an honest no-separation result, not a failure."""
    arm_figures = {
        bench._chain_only: [10000.0, 11000.0],
        bench._buffered: [139877.9, 140000.0],
        bench._durable: [20000.0, 23223.9],
    }

    def fake_microseconds_per_action(arm, batches, per_batch):
        assert (batches, per_batch) == (SMALL["batches"], SMALL["per_batch"])
        return arm_figures[arm]

    monkeypatch.setattr(bench, "_microseconds_per_action",
                        fake_microseconds_per_action)
    monkeypatch.setattr(bench, "_on_disk",
                        lambda: {"actions": 1, "records_checked": 2,
                                 "verdict": "MATCH", "log_bytes": 10,
                                 "bytes_per_action": 10.0,
                                 "verify_us_per_record": 1.0})
    report = bench.run_receipting_cost_benchmark(**SMALL)
    split = report["attribution"]
    parts = (split["hash_and_link_us"] + split["write_us"]
             + split["wait_for_durability_us"])

    assert split["wait_for_durability_us"] < 0
    assert abs(parts - split["total_us"]) < 0.5
    assert split["durability_share"] is None
    assert "did not separate" in report["reading"]


def test_the_denominator_travels_with_the_number():
    """A figure whose batch count and payload size are elsewhere is a slogan."""
    report = run_receipting_cost_benchmark(**SMALL)
    given = report["denominator"]
    assert given["batches"] == 2
    assert given["actions_per_batch"] == 3
    assert given["records_per_action"] == RECORDS_PER_ACTION
    assert given["payload_bytes"] > 0
    assert report["platform"]["system"]


def test_the_log_is_weighed_and_rechecked_against_its_own_bytes():
    """The disk figures, and the verdict that says the recheck was real.

    Handing the verifier no bytes would still produce a number, and it would
    be the cost of checking links rather than the cost of checking content.
    """
    disk = _on_disk(count=5)
    assert disk["records_checked"] == 5 * RECORDS_PER_ACTION
    assert disk["verdict"] == "MATCH"
    assert disk["bytes_per_action"] > 0
    assert disk["log_bytes"] > 0


def test_the_resolver_holds_the_bytes_the_records_were_taken_over():
    """Two payloads per action, so two entries, and both have to be right."""
    known = _known_bytes()
    assert len(known) == RECORDS_PER_ACTION
    with tempfile.TemporaryDirectory() as tmp:
        log = action_witness.open_log("resolver", directory=tmp)
        _actions(log, 2)
        for record in log.records():
            assert record["sha256"] in known


def test_a_single_figure_is_never_reported_without_its_spread():
    figures = [10.0, 12.0, 40.0]
    assert _spread(figures) == {"median_us": 12.0, "low_us": 10.0,
                                "high_us": 40.0}


def test_the_measurement_says_what_it_leaves_open():
    limits = does_not_prove()
    assert limits
    assert any("one filesystem" in limit for limit in limits)
    report = run_receipting_cost_benchmark(**SMALL)
    assert report["does_not_prove"] == limits
    assert report["reading"]
