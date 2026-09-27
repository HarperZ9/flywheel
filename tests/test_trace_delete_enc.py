"""I4, I14 for encrypted stores: a deletion plans the closure (trace, turn,
pending record, snapshots, receipts and keys), destroys keys before it
removes files, leaves no blob and no key, writes one tombstone, and scans
clean. Its report names what it could not reach."""
import pytest

from delete_fixtures import CANARY, JOURNEY, OPERATION, OWNER, plant_trace, plant_turn
from harness import trace_delete_apply
from harness.gateway_agent_trace import AgentTrace
from harness.trace_delete_apply import apply_plan
from harness.trace_delete_plan import make_plan
from harness.trace_keystore import Keystore
from harness.trace_presence import confirm
from harness.trace_residual_scan import Needles, scan_paths
from harness.trace_tombstones import TombstoneLedger
from harness.trace_witness import MemorySink
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def home(tmp_path):
    with using(StreamTestProvider()):
        yield tmp_path


def _apply(home, plan, sink=None):
    ref = confirm(home / "state", OWNER, "delete_apply", plan["plan_digest"], "delete")
    return apply_plan(home, OWNER, plan["plan_digest"], ref, sink=sink or MemorySink())


def test_the_plan_lists_items_receipts_and_keys(home):
    trace_ref = plant_trace(home)
    turn = plant_turn(home)
    plan = make_plan(home, OWNER, {"trace_refs": [trace_ref], "turn_refs": [turn["turn_ref"]]})
    stores = {(e["store"], e["item"]) for e in plan["entries"]}
    assert ("S1", trace_ref) in stores and ("CT", turn["turn_ref"]) in stores
    assert any(store == "CT" and item != turn["turn_ref"] for store, item in stores), "pending"
    assert plan["receipts"] == [turn["eid"]]
    assert set(plan["keys"]) == {"S1", "CT"}
    assert len(plan["plan_digest"]) == 64
    assert plan["out_of_reach"]["client_transcript"] == 1


def test_apply_destroys_keys_first_then_files_and_leaves_nothing(home, monkeypatch):
    trace_ref = plant_trace(home)
    turn = plant_turn(home)
    order = []
    real_destroy, real_remove = Keystore.destroy, trace_delete_apply.remove
    monkeypatch.setattr(Keystore, "destroy", lambda self, store, items: order.append(
        "keys") or real_destroy(self, store, items))
    monkeypatch.setattr(trace_delete_apply, "remove", lambda *a, **k: order.append(
        "files") or real_remove(*a, **k))
    plan = make_plan(home, OWNER, {"trace_refs": [trace_ref], "turn_refs": [turn["turn_ref"]]})
    report = _apply(home, plan)
    assert report["state"] == "DELETED", report
    assert order.index("keys") < order.index("files")
    assert AgentTrace(home / "state", OWNER, JOURNEY, OPERATION).read() == []
    keystore = Keystore(home / "state", OWNER)
    assert not keystore.present("S1", trace_ref) and not keystore.present("CT", turn["turn_ref"])
    assert not list((home / "state" / "gateway-agent-traces").rglob("*.json"))
    assert not list((home / "state" / "captured-turns").rglob("*.enc"))
    tombstones = TombstoneLedger(home / "state", OWNER).entries()
    assert len(tombstones) == 1 and tombstones[0]["plan_digest"] == plan["plan_digest"]
    everything = [p for p in home.rglob("*") if p.is_file()]
    assert scan_paths(everything, Needles.build([CANARY]))["total"] == 0


def test_the_report_names_out_of_reach_copies_and_presence(home):
    trace_ref = plant_trace(home)
    plan = make_plan(home, OWNER, {"trace_refs": [trace_ref]})
    report = _apply(home, plan)
    assert report["out_of_reach"]["provider"] == 1
    assert report["presence"] == "none" and "agents included" in report["presence_statement"]
    assert "backups" in report["out_of_reach"]


def test_status_counts_tombstones(home, monkeypatch):
    from harness import trace_inventory_scan
    trace_ref = plant_trace(home)
    _apply(home, make_plan(home, OWNER, {"trace_refs": [trace_ref]}))
    (home / "owner.ref").write_text(OWNER)
    doc = trace_inventory_scan.scan(environ={"FLYWHEEL_HOME": str(home),
                                             "FLYWHEEL_RUN_ROOT": str(home / "run")})
    assert doc["deletions"] == {"tombstones": 1, "pending": 0}


def test_an_unknown_ref_is_refused_in_the_plan(home):
    from harness.trace_delete_plan import PlanError
    with pytest.raises(PlanError) as refused:
        make_plan(home, OWNER, {"trace_refs": ["agt_" + "0" * 32]})
    assert refused.value.code == "NOT_FOUND"


def test_a_trace_whose_run_still_writes_is_not_deleted(home):
    trace_ref = plant_trace(home)
    plan = make_plan(home, OWNER, {"trace_refs": [trace_ref]})
    with AgentTrace(home / "state", OWNER, JOURNEY, OPERATION).hold():
        report = _apply(home, plan)
    assert report["state"] == "DELETE_PENDING" and report["reason"] == "ITEM_BUSY"
    assert AgentTrace(home / "state", OWNER, JOURNEY, OPERATION).read()


def test_a_turn_deletion_names_the_provider_copy(home):
    """The model provider saw the prompt too; the plan names that copy for
    a captured turn, not only for a gateway trace."""
    turn = plant_turn(home)
    plan = make_plan(home, OWNER, {"turn_refs": [turn["turn_ref"]]})
    assert plan["out_of_reach"]["provider"] == 1


def test_plaintext_items_are_not_counted_as_ciphertext_residue():
    """With no OS key store the stores are plaintext; the residue forecast
    and the CLI plan must not call them ciphertext or promise key destruction."""
    import tempfile
    from pathlib import Path
    from harness.trace_enc import NoProvider
    with tempfile.TemporaryDirectory() as folder, using(NoProvider()):
        home = Path(folder)
        refs = [plant_trace(home, operation=f"op_{i:032x}") for i in range(2)]
        plan = make_plan(home, OWNER, {"trace_refs": refs})
        assert "ciphertext_freed_clusters" not in plan["residue_forecast"]
        assert plan["residue_forecast"]["freed_clusters"] == len(plan["entries"])


def test_a_custody_lock_timeout_is_not_called_a_busy_item(home, monkeypatch):
    """C12: another custody writer holding the lock past the timeout is
    CUSTODY_BUSY; ITEM_BUSY stays for a trace whose run holds its writer lock."""
    import contextlib
    from harness.journey_lock import JourneyLockBusy

    @contextlib.contextmanager
    def busy(*a, **k):
        raise JourneyLockBusy()
        yield
    trace_ref = plant_trace(home)
    plan = make_plan(home, OWNER, {"trace_refs": [trace_ref]})
    monkeypatch.setattr(trace_delete_apply, "custody_lock", busy)
    report = _apply(home, plan)
    assert report["state"] == "DELETE_PENDING" and report["reason"] == "CUSTODY_BUSY"
