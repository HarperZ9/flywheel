"""SP-oracle: a plan digest mixes in a random nonce kept only with the saved
selection, so the digest in a tombstone, the ledger or the event log cannot
be recomputed from guessed content after the deletion."""
import pytest

from delete_fixtures import OWNER, plant_turn
from harness.evidence_json import canonical_sha256
from harness.trace_delete_apply import apply_plan
from harness.trace_delete_plan import make_plan
from harness.trace_presence import confirm
from harness.trace_witness import MemorySink
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def home(tmp_path):
    with using(StreamTestProvider()):
        yield tmp_path


def _unsalted(plan) -> str:
    return canonical_sha256({"schema": "flywheel.trace-delete-plan/v1", "owner_ref": OWNER,
                             "entries": [[e["store"], e["item"]] for e in plan["entries"]],
                             "receipts": plan["receipts"]})


def test_two_plans_of_one_selection_have_different_digests(home):
    turn = plant_turn(home)
    first = make_plan(home, OWNER, {"turn_refs": [turn["turn_ref"]]})
    second = make_plan(home, OWNER, {"turn_refs": [turn["turn_ref"]]})
    assert first["plan_digest"] != second["plan_digest"]
    assert first["entries"] == second["entries"]


def test_the_digest_is_not_the_hash_of_the_refs(home):
    turn = plant_turn(home)
    plan = make_plan(home, OWNER, {"turn_refs": [turn["turn_ref"]]})
    assert plan["plan_digest"] != _unsalted(plan)


def test_a_saved_plan_still_applies_and_its_nonce_is_gone_after(home):
    turn = plant_turn(home)
    plan = make_plan(home, OWNER, {"turn_refs": [turn["turn_ref"]]})
    ref = confirm(home / "state", OWNER, "delete_apply", plan["plan_digest"], "delete")
    report = apply_plan(home, OWNER, plan["plan_digest"], ref, sink=MemorySink())
    assert report["state"] == "DELETED"
    stored = b"".join(p.read_bytes() for p in (home / "state").rglob("*") if p.is_file())
    assert b"nonce" not in stored
