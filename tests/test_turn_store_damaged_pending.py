"""One damaged pending record (an unclean shutdown can zero-fill a file) must
not stop capture in every other session. It is moved aside with a loss
record, capture goes on, and a deletion of its session still reaches it."""
import pytest

from delete_fixtures import CANARY, OWNER
from harness.trace_capture_settings import DEFAULTS
from harness.trace_custody_ledger import CustodyLedger
from harness.trace_delete_plan import make_plan
from harness.trace_turn_store import TurnStore
from trace_enc_fakes import StreamTestProvider, using

A = "0f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a3b"
B = "1f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a3b"


@pytest.fixture
def store(tmp_path):
    with using(StreamTestProvider()):
        (tmp_path / "state").mkdir()
        yield TurnStore(tmp_path, OWNER, settings={**DEFAULTS, "content": "on"})


def _damage_pending(store):
    pending = next((store.base / "pending").glob("*.enc"))
    pending.write_bytes(b"\0" * pending.stat().st_size)
    return pending


def test_other_sessions_keep_capturing(store):
    store.prompt("claude-code", A, "pid-a", text=CANARY)
    damaged = _damage_pending(store)
    store.prompt("claude-code", B, "pid-b", text="another prompt")
    turn = store.stop("claude-code", B, "pid-b", text="an answer")
    assert turn["pairing"] != "unpaired"
    assert store.expire() == 0
    assert not damaged.exists()
    assert (store.base / "pending-quarantine" / damaged.name).exists()


def test_the_loss_is_recorded(store):
    store.prompt("claude-code", A, "pid-a", text=CANARY)
    _damage_pending(store)
    store.expire()
    losses = [e for e in CustodyLedger(store.home, OWNER).entries() if e["kind"] == "loss"]
    assert [e["fields"]["store"] for e in losses] == ["CT"]


def test_deleting_the_session_reaches_the_quarantined_record(store):
    store.prompt("claude-code", A, "pid-a", text=CANARY)
    damaged = _damage_pending(store)
    store.expire()
    plan = make_plan(store.home, OWNER, {"session": {"client": "claude-code", "session_id": A}})
    rels = {e["rel"] for e in plan["entries"]}
    assert any(rel.endswith("pending-quarantine/" + damaged.name) for rel in rels)
