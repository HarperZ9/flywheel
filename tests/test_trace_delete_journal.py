"""I14, SP-17: a deletion is journaled before it acts, resumes to the same end
state after a fault at any step, verifies from its encrypted scan set after a
resume, writes a tombstone only once verified, and then destroys the scan-set
key and removes the journal."""
import json

import pytest

from harness.trace_delete_journal import DeletionJournal, apply_journaled, pending
from harness.trace_keystore import Keystore
from harness.trace_tombstones import TombstoneLedger
from trace_enc_fakes import StreamTestProvider, using

OWNER = "owner_" + "a" * 32
PLAN = "c" * 64
STEPS = ("destroy_keys", "remove_blobs", "scrub_sqlite")


class Fault(Exception):
    pass


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "state"
    path.mkdir()
    with using(StreamTestProvider()):
        yield path


def _store(state):
    path = state.parent / "fake-store.json"
    if not path.exists():
        path.write_text(json.dumps({"items": ["keep", "gone"], "log": []}))
    return path


def _steps(state, fail_at=None):
    path = _store(state)

    def step(name):
        def run():
            if name == fail_at:
                raise Fault(name)
            doc = json.loads(path.read_text())
            doc["items"] = [i for i in doc["items"] if i != "gone"]
            if name not in doc["log"]:
                doc["log"].append(name)
            path.write_text(json.dumps(doc))
        return run
    return [(name, step(name)) for name in STEPS]


def _verify(state, fail=False):
    def verify(scan_set):
        if fail:
            raise Fault("verify")
        text = _store(state).read_text()
        return {"ok": all(s not in text for s in scan_set or ()),
                "checks": ["scan_set"] if scan_set is not None else ["structural"]}
    return verify


def _journal(state):
    return DeletionJournal(state, OWNER, PLAN)


def _run(state, fail_at=None, fail_verify=False):
    return apply_journaled(_journal(state), _steps(state, fail_at), _verify(state, fail_verify),
                           scan_set=['"gone"'], tombstone={"stores": ["X1"],
                                                           "reason_code": "owner_request"})


@pytest.mark.parametrize("fail_at", STEPS)
def test_a_fault_at_each_step_resumes_to_the_same_end_state(state, fail_at):
    with pytest.raises(Fault):
        _run(state, fail_at=fail_at)
    assert pending(state, OWNER) == [PLAN]
    assert TombstoneLedger(state, OWNER).entries() == []
    result = _run(state)
    assert result["state"] == "DELETED"
    assert json.loads(_store(state).read_text()) == {"items": ["keep"], "log": list(STEPS)}
    assert len(TombstoneLedger(state, OWNER).entries()) == 1
    assert pending(state, OWNER) == []


def test_a_resume_between_apply_and_verify_verifies_from_the_scan_set(state):
    with pytest.raises(Fault):
        _run(state, fail_verify=True)
    resumed = _journal(state)
    assert resumed.done_steps() == set(STEPS)
    assert resumed.scan_set() == ['"gone"']
    result = apply_journaled(resumed, _steps(state), _verify(state))
    assert result["state"] == "DELETED" and result["checks"] == ["scan_set"]


def test_the_scan_set_key_and_the_journal_are_gone_after_the_tombstone(state):
    _run(state)
    assert not Keystore(state, OWNER).present("deletions", PLAN)
    assert list((state / "trace-deletions").rglob("journal/*")) == []


def test_an_unverified_deletion_writes_no_tombstone_and_stays_pending(state):
    def never(scan_set):
        return {"ok": False, "checks": ["scan_set"], "reason": "RESIDUE_FOUND"}
    result = apply_journaled(_journal(state), _steps(state), never, scan_set=["x"],
                             tombstone={"stores": ["X1"], "reason_code": "owner_request"})
    assert result == {"state": "DELETE_PENDING", "reason": "RESIDUE_FOUND",
                      "checks": ["scan_set"]}
    assert TombstoneLedger(state, OWNER).entries() == []
    assert pending(state, OWNER) == [PLAN]


def test_the_scan_set_is_ciphertext_on_disk(state):
    with pytest.raises(Fault):
        _run(state, fail_verify=True)
    raw = b"".join(p.read_bytes() for p in (state / "trace-deletions").rglob("*") if p.is_file())
    assert b'"gone"' not in raw and b"gone" not in raw
