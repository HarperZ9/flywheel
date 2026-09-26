"""I4 end to end: a long canary planted in every store the deletion engine
covers, temporary files redirected into the scanned tree, and a reader held
open on store.db during the first apply. The first apply stops DB_BUSY and
stays pending; after the reader closes, a second apply with fresh presence
finishes. Then no file under the home or the run root holds any window of
the canary in any searched encoding, one tombstone exists, both store.db
verifiers pass, and the report names every store it does not cover."""
import functools
import sqlite3

import pytest

from delete_fixtures import CANARY, OWNER, SESSION
from harness import store_tombstone
from harness.store import verify_chain, verify_records
from harness.trace_delete_apply import apply_plan
from harness.trace_delete_plan import make_plan
from harness.trace_presence import confirm
from harness.trace_residual_scan import Needles, scan_paths
from harness.trace_sqlite_scrub import scrub
from harness.trace_tombstones import TombstoneLedger
from harness.trace_witness import MemorySink
from plain_fixtures import plant_legacy_run, plant_note, plant_profile_trace, plant_v1_receipt
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def world(tmp_path, monkeypatch):
    home, run = tmp_path / "home", tmp_path / "run"
    (home / "state").mkdir(parents=True)
    (home / "tmp").mkdir()
    run.mkdir()
    for name in ("TMP", "TEMP", "SQLITE_TMPDIR"):
        monkeypatch.setenv(name, str(home / "tmp"))
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(run))
    monkeypatch.setattr(store_tombstone, "scrub", functools.partial(scrub, retry_s=0.3))
    with using(StreamTestProvider()):
        yield home, run


def _turn_with_snapshot(home, monkeypatch):
    from harness import web_fetch_pinned
    from harness.trace_capture_settings import DEFAULTS
    from harness.trace_turn_store import TurnStore
    monkeypatch.setattr(web_fetch_pinned, "fetch_pinned", lambda url, **kw: (
        200, {"Content-Type": "text/plain"}, CANARY.encode(), url))
    store = TurnStore(home, OWNER, settings={**DEFAULTS, "content": "on", "freeze_urls": "on"})
    store.prompt("claude-code", SESSION, "pid-1", text=CANARY)
    assert store.freeze("claude-code", SESSION, "pid-1", ["https://docs.example/p"])["frozen"]
    return store.stop("claude-code", SESSION, "pid-1", text="answer " + CANARY[:400])


def _plant_everything(home, run, monkeypatch) -> dict:
    turn = _turn_with_snapshot(home, monkeypatch)
    return {"trace_refs": [plant_profile_trace(home, CANARY)],
            "turn_refs": [turn["turn_ref"]],
            "receipt_eids": [plant_v1_receipt(home, CANARY)],
            "note_refs": [plant_note(run, CANARY)],
            "legacy_runs": [plant_legacy_run(run, CANARY)]}


def _apply(home, digest):
    ref = confirm(home / "state", OWNER, "delete_apply", digest, "delete")
    return apply_plan(home, OWNER, digest, ref, sink=MemorySink())


def test_a_canary_in_every_covered_store_is_gone_after_apply(world, monkeypatch):
    home, run = world
    plan = make_plan(home, OWNER, _plant_everything(home, run, monkeypatch))
    assert {"S1", "S2", "S6", "S7", "S8b", "S9", "S10", "S11", "CT"} <= set(plan["counts"])
    reader = sqlite3.connect(home / "store.db")
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM entities").fetchone()
    first = _apply(home, plan["plan_digest"])
    reader.close()
    assert first["state"] == "DELETE_PENDING" and first["reason"] == "DB_BUSY"
    second = _apply(home, plan["plan_digest"])
    assert second["state"] == "DELETED", second
    files = [p for base in (home, run) for p in base.rglob("*") if p.is_file()]
    assert scan_paths(files, Needles.build([CANARY]))["total"] == 0
    assert len(TombstoneLedger(home / "state", OWNER).entries()) == 1
    assert verify_chain(home=home)["ok"] and verify_records(home=home)["ok"]
    assert {"S3", "S4", "S5", "S8", "S13"} <= set(second["not_covered"])
    assert second["residue"]["freed_clusters"] >= 1
    assert list((home / "tmp").iterdir()) == []
