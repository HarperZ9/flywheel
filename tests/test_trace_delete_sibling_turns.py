"""A Stop segment copies its prompt from the pending record, so deleting one
segment of a turn deletes every segment that shares that prompt: no sibling
turn may still decrypt to the deleted prompt."""
import pytest

from delete_fixtures import CANARY, OWNER, SESSION
from harness.trace_capture_settings import DEFAULTS
from harness.trace_delete_apply import apply_plan
from harness.trace_delete_plan import make_plan
from harness.trace_presence import confirm
from harness.trace_turn_store import TurnStore
from harness.trace_witness import MemorySink
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def home(tmp_path):
    with using(StreamTestProvider()):
        (tmp_path / "state").mkdir()
        yield tmp_path


def _segments(home):
    store = TurnStore(home, OWNER, settings={**DEFAULTS, "content": "on"})
    store.prompt("claude-code", SESSION, "pid-1", text=CANARY)
    first = store.stop("claude-code", SESSION, "pid-1", text="answer one")
    second = store.stop("claude-code", SESSION, "pid-1", text="answer two",
                        stop_hook_active=True)
    return store, first, second


def test_the_plan_for_one_segment_lists_every_segment_of_the_prompt(home):
    _, first, second = _segments(home)
    plan = make_plan(home, OWNER, {"turn_refs": [first["turn_ref"]]})
    items = {e["item"] for e in plan["entries"] if e["store"] == "CT"}
    assert {first["turn_ref"], second["turn_ref"]} <= items
    assert sorted(plan["receipts"]) == sorted(r["eid"] for r in (first, second) if r.get("eid"))


def test_deleting_one_segment_leaves_no_sibling_holding_the_prompt(home):
    store, first, second = _segments(home)
    plan = make_plan(home, OWNER, {"turn_refs": [first["turn_ref"]]})
    ref = confirm(home / "state", OWNER, "delete_apply", plan["plan_digest"], "delete")
    report = apply_plan(home, OWNER, plan["plan_digest"], ref, sink=MemorySink())
    assert report["state"] == "DELETED"
    remaining = [t["turn_ref"] for t in store.turns()]
    assert first["turn_ref"] not in remaining and second["turn_ref"] not in remaining
