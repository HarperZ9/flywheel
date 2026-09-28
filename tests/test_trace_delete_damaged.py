"""A trace that can no longer be read can still be deleted. Planning takes the
trace from its folder and header; the closure read from inside it (profile
folders) is best-effort, and the plan says when it could not be read."""
import pytest

from delete_fixtures import OWNER, plant_trace
from harness.trace_delete_apply import apply_plan
from harness.trace_delete_plan import make_plan
from harness.trace_presence import confirm
from harness.trace_witness import MemorySink
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def home(tmp_path):
    with using(StreamTestProvider()):
        yield tmp_path


def _folder(home):
    return next((home / "state" / "gateway-agent-traces").rglob("op_*"))


def _flip_body(home):
    record = _folder(home) / "00000001.json"
    data = bytearray(record.read_bytes())
    data[-40] ^= 0x01
    record.write_bytes(bytes(data))


def _drop_checkpoint(home):
    (_folder(home) / "head-00000001.json").unlink()


@pytest.mark.parametrize("damage", [_flip_body, _drop_checkpoint], ids=["flipped", "crash"])
def test_a_damaged_trace_is_planned_and_deleted(home, damage):
    ref = plant_trace(home)
    damage(home)
    plan = make_plan(home, OWNER, {"trace_refs": [ref]})
    assert ("S1", ref) in {(e["store"], e["item"]) for e in plan["entries"]}
    assert any("could not be read" in note for note in plan["notes"])
    token = confirm(home / "state", OWNER, "delete_apply", plan["plan_digest"], "delete")
    report = apply_plan(home, OWNER, plan["plan_digest"], token, sink=MemorySink())
    assert report["state"] == "DELETED", report
    assert not (home / "state" / "gateway-agent-traces").rglob("op_*").__next__.__self__ \
        or not list((home / "state" / "gateway-agent-traces").rglob("0000000*.json"))


def test_a_lost_os_key_does_not_block_the_plan(home, monkeypatch):
    from harness import trace_enc_write
    from harness.trace_enc import EncError
    ref = plant_trace(home)

    def lost(*a, **k):
        raise EncError("OS_KEY_UNAVAILABLE")
    monkeypatch.setattr(trace_enc_write.ItemCipher, "open", lost)
    plan = make_plan(home, OWNER, {"trace_refs": [ref]})
    assert ("S1", ref) in {(e["store"], e["item"]) for e in plan["entries"]}
