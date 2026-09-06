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
from harness.action_witness import LOG_NAME, verify_log
from harness.receipting_cost_bench import (RECORDS_PER_ACTION, _actions,
                                           _buffered, _chain_only, _durable,
                                           _known_bytes, _on_disk, _spread,
                                           does_not_prove,
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


def test_a_recorded_action_costs_more_to_keep_than_to_hash():
    """The ordering the three arms have to come out in.

    Each arm does everything the one before it does and then more, so a run
    where they came out in another order is a run whose arms are not what they
    are named, whatever the figures say.
    """
    report = run_receipting_cost_benchmark(**SMALL)
    arms = report["arms"]
    assert arms["chain_only"]["median_us"] <= arms["buffered"]["median_us"]
    assert arms["buffered"]["median_us"] <= arms["durable"]["median_us"]


def test_the_attribution_adds_up_to_the_total_it_split():
    report = run_receipting_cost_benchmark(**SMALL)
    split = report["attribution"]
    parts = (split["hash_and_link_us"] + split["write_us"]
             + split["wait_for_durability_us"])
    assert abs(parts - split["total_us"]) < 0.5
    assert 0.0 <= split["durability_share"] <= 1.0


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
