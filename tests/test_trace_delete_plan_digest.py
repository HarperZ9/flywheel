"""7.10: apply runs exactly the plan the owner saw. A digest nobody planned,
or a plan whose items changed since, is refused; presence must match."""
import pytest

from delete_fixtures import OWNER, SESSION, plant_trace, plant_turn
from harness.trace_delete_apply import apply_plan
from harness.trace_delete_plan import PlanError, make_plan
from harness.trace_presence import PresenceError, confirm
from harness.trace_witness import MemorySink
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def home(tmp_path):
    with using(StreamTestProvider()):
        yield tmp_path


def _confirm(home, digest):
    return confirm(home / "state", OWNER, "delete_apply", digest, "delete")


def test_a_stale_digest_is_refused(home):
    plant_trace(home)
    digest = "e" * 64
    with pytest.raises(PlanError) as refused:
        apply_plan(home, OWNER, digest, _confirm(home, digest), sink=MemorySink())
    assert refused.value.code == "PLAN_NOT_FOUND"


def test_a_drifted_plan_is_refused(home):
    from harness.trace_capture_settings import DEFAULTS
    from harness.trace_turn_store import TurnStore
    plant_turn(home)
    plan = make_plan(home, OWNER, {"session": {"client": "claude-code", "session_id": SESSION}})
    store = TurnStore(home, OWNER, settings={**DEFAULTS, "content": "on"})
    store.prompt("claude-code", SESSION, "pid-2", text="later")
    store.stop("claude-code", SESSION, "pid-2", text="a later answer")
    with pytest.raises(PlanError) as refused:
        apply_plan(home, OWNER, plan["plan_digest"], _confirm(home, plan["plan_digest"]),
                   sink=MemorySink())
    assert refused.value.code == "PLAN_DRIFTED"


def test_apply_without_presence_is_refused(home):
    plan = make_plan(home, OWNER, {"trace_refs": [plant_trace(home)]})
    with pytest.raises(PresenceError) as refused:
        apply_plan(home, OWNER, plan["plan_digest"], None, sink=MemorySink())
    assert refused.value.code == "PRESENCE_REQUIRED"


def test_presence_for_another_plan_is_refused(home):
    plan = make_plan(home, OWNER, {"trace_refs": [plant_trace(home)]})
    other = _confirm(home, "f" * 64)
    with pytest.raises(PresenceError) as refused:
        apply_plan(home, OWNER, plan["plan_digest"], other, sink=MemorySink())
    assert refused.value.code == "PRESENCE_MISMATCH"
