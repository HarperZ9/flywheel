"""The runner pool: who may join, who gets the work, who still holds it.

The claim this module makes is that membership is under the operator's
control and that work cannot be silently held forever. Both halves need a
test that fails when they stop being true, so the cases here are written as
the specific ways a pool goes wrong: a machine that enrolls itself, a ticket
spent twice, a runner advertising a capability nobody granted it, two
machines running the same job, and a job stuck on a laptop that closed.

The last group covers the chain. A pool whose history can be edited is a
dashboard, and a dashboard is the thing this replaces.
"""
import json

import pytest

from harness.runner_pool import (MAX_LEASE_SECONDS, MIN_LEASE_SECONDS,
                                 chain_intact, chain_path, claim, complete,
                                 dispatch, enroll, load_events, mint_ticket,
                                 pool_state, retire, roster)

NOW = "2026-09-06T18:00:00Z"
SOON = "2026-09-06T18:02:00Z"
LATER = "2026-09-06T19:30:00Z"


def _pool(tmp_path, labels=("linux", "gpu")):
    mint_ticket(tmp_path, ticket_id="t1", labels=list(labels), at=NOW)
    enroll(tmp_path, runner_id="tower", ticket_id="t1", labels=list(labels),
           at=NOW)
    return tmp_path


def test_a_machine_cannot_join_a_pool_without_a_ticket_somebody_minted(
        tmp_path):
    """The one property the row claims: membership is the operator's call.

    A runner reaching the engine can do plenty. Adding itself is the thing
    it must not be able to do, so the refusal is checked before anything
    else in this file.
    """
    with pytest.raises(ValueError, match="no ticket"):
        enroll(tmp_path, runner_id="stranger", ticket_id="t1",
               labels=["linux"], at=NOW)
    assert load_events(tmp_path) == []


def test_a_ticket_is_spent_once_and_names_who_spent_it(tmp_path):
    _pool(tmp_path)
    with pytest.raises(ValueError, match="spent by tower"):
        enroll(tmp_path, runner_id="second", ticket_id="t1",
               labels=["linux"], at=NOW)
    state = pool_state(load_events(tmp_path), now=NOW)
    assert state["tickets"]["t1"]["used_by"] == "tower"
    assert list(state["runners"]) == ["tower"]


def test_a_runner_may_claim_only_the_labels_its_ticket_granted(tmp_path):
    """Otherwise enrollment is a form a machine fills in about itself.

    Labels decide what work lands where, so a runner that can write its own
    is a runner that can take work the operator never meant it to see.
    """
    mint_ticket(tmp_path, ticket_id="t1", labels=["linux"], at=NOW)
    with pytest.raises(ValueError, match="does not grant secrets"):
        enroll(tmp_path, runner_id="tower", ticket_id="t1",
               labels=["linux", "secrets"], at=NOW)
    enroll(tmp_path, runner_id="tower", ticket_id="t1", labels=["linux"],
           at=NOW)
    assert pool_state(load_events(tmp_path),
                      now=NOW)["runners"]["tower"]["labels"] == ["linux"]


def test_work_reaches_only_a_machine_carrying_every_label_it_asked_for(
        tmp_path):
    mint_ticket(tmp_path, ticket_id="t1", labels=["linux"], at=NOW)
    enroll(tmp_path, runner_id="plain", ticket_id="t1", labels=["linux"],
           at=NOW)
    dispatch(tmp_path, job_id="train", requires=["linux", "gpu"], at=NOW)
    with pytest.raises(ValueError, match="does not carry gpu"):
        claim(tmp_path, job_id="train", runner_id="plain", lease_seconds=300,
              at=NOW)
    assert pool_state(load_events(tmp_path),
                      now=NOW)["jobs"]["train"]["state"] == "queued"


def test_a_job_already_held_is_refused_to_a_second_machine(tmp_path):
    """Two runners on one job is the failure that wastes money quietly.

    Both finish, both report, and the second result overwrites the first
    without anything in the history showing that two ran.
    """
    _pool(tmp_path)
    mint_ticket(tmp_path, ticket_id="t2", labels=["linux", "gpu"], at=NOW)
    enroll(tmp_path, runner_id="laptop", ticket_id="t2",
           labels=["linux", "gpu"], at=NOW)
    dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)
    claim(tmp_path, job_id="train", runner_id="tower", lease_seconds=600,
          at=NOW)
    with pytest.raises(ValueError, match="held by tower"):
        claim(tmp_path, job_id="train", runner_id="laptop", lease_seconds=600,
              at=SOON)


def test_a_lease_that_lapsed_puts_the_work_back_in_the_queue(tmp_path):
    """The machine that died is not coming back to release it.

    Expiry is arithmetic against the clock rather than a sweep somebody has
    to remember to run, so the same chain reads differently at two instants
    and that is the whole point.
    """
    _pool(tmp_path)
    dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)
    claim(tmp_path, job_id="train", runner_id="tower", lease_seconds=60,
          at=NOW)
    records = load_events(tmp_path)
    assert pool_state(records, now=SOON)["jobs"]["train"]["state"] == "queued"
    assert pool_state(records, now=SOON)["leases_lapsed"] == 1
    assert pool_state(records, now=NOW)["jobs"]["train"]["state"] == "leased"
    claim(tmp_path, job_id="train", runner_id="tower", lease_seconds=600,
          at=SOON)
    assert pool_state(load_events(tmp_path),
                      now=SOON)["jobs"]["train"]["runner_id"] == "tower"


def test_only_the_machine_holding_the_lease_reports_the_outcome(tmp_path):
    _pool(tmp_path)
    mint_ticket(tmp_path, ticket_id="t2", labels=["gpu"], at=NOW)
    enroll(tmp_path, runner_id="laptop", ticket_id="t2", labels=["gpu"],
           at=NOW)
    dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)
    claim(tmp_path, job_id="train", runner_id="tower", lease_seconds=600,
          at=NOW)
    with pytest.raises(ValueError, match="held by tower, not laptop"):
        complete(tmp_path, job_id="train", runner_id="laptop", ok=True,
                 at=SOON)
    complete(tmp_path, job_id="train", runner_id="tower", ok=True, at=SOON)
    job = pool_state(load_events(tmp_path), now=SOON)["jobs"]["train"]
    assert job["state"] == "done" and job["ok"] is True


def test_an_outcome_for_work_nobody_holds_is_refused(tmp_path):
    _pool(tmp_path)
    dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)
    with pytest.raises(ValueError, match="nobody holds its lease"):
        complete(tmp_path, job_id="train", runner_id="tower", ok=True, at=NOW)


def test_a_retired_machine_keeps_its_history_and_takes_no_more_work(tmp_path):
    _pool(tmp_path)
    dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)
    retire(tmp_path, runner_id="tower", at=NOW)
    with pytest.raises(ValueError, match="not an enrolled runner"):
        claim(tmp_path, job_id="train", runner_id="tower", lease_seconds=300,
              at=SOON)
    state = pool_state(load_events(tmp_path), now=SOON)
    assert state["runners"]["tower"]["enrolled"] is False
    assert state["runners"]["tower"]["enrolled_at"] == NOW


def test_a_lease_outside_the_bounds_is_refused_at_both_ends(tmp_path):
    _pool(tmp_path)
    dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)
    for seconds in (MIN_LEASE_SECONDS - 1, MAX_LEASE_SECONDS + 1, "soon"):
        with pytest.raises(ValueError, match="lease_seconds"):
            claim(tmp_path, job_id="train", runner_id="tower",
                  lease_seconds=seconds, at=NOW)


def test_an_id_that_would_escape_the_run_root_is_refused(tmp_path):
    with pytest.raises(ValueError, match="ticket_id may hold"):
        mint_ticket(tmp_path, ticket_id="../../etc/passwd", labels=["linux"],
                    at=NOW)
    with pytest.raises(ValueError, match="ticket_id must be"):
        mint_ticket(tmp_path, ticket_id="", labels=["linux"], at=NOW)


def test_a_naive_instant_is_refused_rather_than_guessed_at(tmp_path):
    with pytest.raises(ValueError, match="carries no timezone"):
        mint_ticket(tmp_path, ticket_id="t1", labels=["linux"],
                    at="2026-09-06T18:00:00")


def test_the_same_id_is_never_minted_or_dispatched_twice(tmp_path):
    _pool(tmp_path)
    with pytest.raises(ValueError, match="already minted"):
        mint_ticket(tmp_path, ticket_id="t1", labels=["linux"], at=NOW)
    dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)
    with pytest.raises(ValueError, match="already dispatched"):
        dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)


def test_every_record_cites_the_one_before_it(tmp_path):
    _pool(tmp_path)
    records = load_events(tmp_path)
    assert [r["kind"] for r in records] == ["ticket", "enroll"]
    assert records[0]["prev_sha256"] == ""
    assert records[1]["prev_sha256"] == records[0]["event_sha256"]
    assert chain_intact(records) is True


def test_editing_the_history_refuses_the_next_write(tmp_path):
    """The edit somebody would actually make: quietly widening a runner.

    Nothing here can stop a file being edited. What it can do is refuse to
    write the next record onto the result, so the tampering surfaces at the
    moment the pool is used rather than months later.
    """
    _pool(tmp_path, labels=["linux"])
    path = chain_path(tmp_path)
    records = json.loads(path.read_text(encoding="utf-8"))
    records[1]["labels"] = ["linux", "gpu"]
    path.write_text(json.dumps(records), encoding="utf-8")
    assert chain_intact(load_events(tmp_path)) is False
    with pytest.raises(ValueError, match="chain is broken"):
        dispatch(tmp_path, job_id="train", requires=["linux"], at=NOW)
    assert roster(tmp_path, now=NOW)["chain_intact"] is False


def test_a_deleted_record_breaks_the_citation_at_the_one_after_it(tmp_path):
    _pool(tmp_path)
    dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)
    path = chain_path(tmp_path)
    records = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(records[1:]), encoding="utf-8")
    assert chain_intact(load_events(tmp_path)) is False


def test_the_roster_reads_empty_before_anything_has_happened(tmp_path):
    body = roster(tmp_path, now=NOW)
    assert body["events"] == 0 and body["chain_intact"] is True
    assert body["runners"] == [] and body["jobs"] == []
    assert body["queued"] == 0 and body["tickets_unspent"] == 0


def test_the_roster_counts_what_a_reader_would_otherwise_have_to_add_up(
        tmp_path):
    _pool(tmp_path)
    mint_ticket(tmp_path, ticket_id="spare", labels=["linux"], at=NOW)
    dispatch(tmp_path, job_id="train", requires=["gpu"], at=NOW)
    dispatch(tmp_path, job_id="build", requires=["linux"], at=NOW)
    claim(tmp_path, job_id="train", runner_id="tower", lease_seconds=600,
          at=NOW)
    body = roster(tmp_path, now=SOON)
    assert body["leased"] == 1 and body["queued"] == 1
    assert body["tickets_unspent"] == 1
    assert body["runners"][0]["runner_id"] == "tower"
    assert [j["job_id"] for j in body["jobs"]] == ["build", "train"]
    assert roster(tmp_path, now=LATER)["queued"] == 2
