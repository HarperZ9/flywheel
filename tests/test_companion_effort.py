"""Falsifiers for the effort dial on the companion seat.

The dial shipped with four named levels and a receipt stamp, and for a release
nothing but the agent surface could set it. Wiring it here is only honest if
the level it names is the level the run actually spends, so these hold the
properties that make the receipt true:

  1. the middle position and no dial at all agree, so adding the control does
     not silently change what an existing caller gets;
  2. a lower position really generates fewer candidates;
  3. one request's dial never reaches the next, because the gateway holds ONE
     seat for its lifetime;
  4. a cache hit reports nothing spent rather than a budget that never ran;
  5. the stamp names candidates, never steps, since this route has no steps.
"""
import sys
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from harness.adaptive_select import SCHEDULE_CAPACITY
from harness.companion import CACHE, CompanionSeat
from harness.effort import CANDIDATE_BUDGET, resolve_effort, stamp_candidates
from harness.proposer import ProposerOutput

# The gateway builds its seat with exactly these, so the tests measure the
# object the operator actually reaches.
GATEWAY_INITIAL_N = 4
GATEWAY_MAX_N = 16


class CountingProposer:
    """Never agrees with itself, so the loop always runs to its ceiling and the
    candidate count is exactly the budget rather than wherever consensus
    happened to land."""
    model_ref = "stub"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(f"distinct answer number {self.calls}",
                              self.model_ref, seed, "h", "stub")


class MarkerOracle:
    def __init__(self, marker):
        self.marker = marker

    def verify(self, candidate, task):
        return SimpleNamespace(passed=self.marker in candidate)


class MemoryCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def put(self, key, value):
        self.store[key] = value


def _seat(proposer=None, **kw):
    return CompanionSeat(proposer or CountingProposer(),
                         initial_n=GATEWAY_INITIAL_N, max_n=GATEWAY_MAX_N, **kw)


def _task(prompt="solve this"):
    return SimpleNamespace(task_id="t1", prompt=prompt, max_new_tokens=64,
                           system="")


def _spend(effort):
    prop = CountingProposer()
    _seat(prop).answer(_task(), effort=effort)
    return prop.calls


def test_the_middle_position_and_no_dial_agree():
    """standard is written to match the seat's constructed default. If it did
    not, every existing caller would change behavior the day a client learned
    to send the dial, and the change would be invisible."""
    assert CANDIDATE_BUDGET["standard"] == {"initial_n": GATEWAY_INITIAL_N,
                                            "max_n": GATEWAY_MAX_N}
    assert _spend("standard") == _spend(None)


def test_a_lower_dial_really_spends_less():
    """A knob that changes a receipt field and nothing else is decoration."""
    low, standard, high = _spend("low"), _spend("standard"), _spend("high")
    assert low < standard < high
    assert low == CANDIDATE_BUDGET["low"]["max_n"]


def test_the_dial_does_not_leak_into_the_next_request():
    """The gateway holds one seat for its whole lifetime. A dial stored on the
    seat would make one operator's ultra request quietly bill the next one."""
    prop = CountingProposer()
    seat = _seat(prop)
    seat.answer(_task("first"), effort="high")
    after_first = prop.calls
    seat.answer(_task("second"))
    assert prop.calls - after_first == GATEWAY_MAX_N, "the default came back"


def test_a_per_call_budget_leaves_the_selector_alone():
    """The mechanism behind the property above, stated directly."""
    seat = _seat()
    seat.answer(_task(), effort="ultra")
    assert seat.selector.initial_n == GATEWAY_INITIAL_N
    assert seat.selector.max_n == GATEWAY_MAX_N


def test_the_stamp_names_candidates_and_never_steps():
    """stamp_applied exists because asserting a nominal dial value as applied
    is a false receipt. This route has no step loop, so the candidate stamp
    must not carry a step field that would read as enforced."""
    seat = _seat()
    result = seat.answer(_task(), effort="high")
    stamp = result.receipt["effort"]
    assert stamp["applied"] == "candidates"
    assert stamp["n_candidates_applied"] is True
    assert "max_steps_applied" not in stamp
    assert stamp["candidates_generated"] == CANDIDATE_BUDGET["high"]["max_n"]
    assert stamp["max_n_applied"] == CANDIDATE_BUDGET["high"]["max_n"]
    assert stamp["max_n_overridden"] is False


def test_a_cache_hit_reports_nothing_spent():
    """The cache answers before the loop runs. Reporting the dial's budget
    there would describe generations that never happened."""

    class FixedProposer:
        model_ref = "stub"

        def generate(self, prompt, *, seed, temperature, max_new_tokens,
                     system=""):
            return ProposerOutput("the marker answer", self.model_ref, seed,
                                  "h", "stub")

    seat = _seat(FixedProposer(), oracle=MarkerOracle("marker"),
                 cache=MemoryCache())
    first = seat.answer(_task(), effort="ultra")
    assert first.source != CACHE, "nothing was cached yet"
    second = seat.answer(_task(), effort="ultra")
    assert second.source == CACHE
    stamp = second.receipt["effort"]
    assert stamp["applied"] == "none"
    assert stamp["candidates_generated"] == 0
    assert stamp["n_candidates_applied"] is False
    assert stamp["name"] == "ultra", "the level stays visible with its reason"


def test_an_unknown_level_falls_back_and_names_the_fallback():
    """A newer client sending a level this build does not know degrades
    visibly. The engine already names its own fallback; the budget must follow
    the resolved name rather than inventing a second, differently-shaped one."""
    seat = _seat()
    stamp = seat.answer(_task(), effort="ubermax").receipt["effort"]
    assert stamp["name"] == "standard"
    assert "ubermax" in stamp["note"]
    assert stamp["max_n_applied"] == CANDIDATE_BUDGET["standard"]["max_n"]


def test_a_budget_past_capacity_is_refused_not_clamped():
    """Past the schedule's capacity the (temperature, seed) grid repeats, so
    more candidates buy no diversity. A silent clamp would produce a receipt
    naming a spend the run never had permission to make."""
    seat = _seat()
    with pytest.raises(ValueError):
        seat.selector.select(_task(), max_n=SCHEDULE_CAPACITY + 1)
    with pytest.raises(ValueError):
        seat.selector.select(_task(), initial_n=8, max_n=4)
    with pytest.raises(ValueError):
        seat.selector.select(_task(), initial_n=0)


def test_every_dial_position_fits_the_schedule():
    """The table is a policy, and a policy that cannot run is a defect. Every
    position must be expressible by the selector that has to honor it."""
    for name, budget in CANDIDATE_BUDGET.items():
        assert 1 <= budget["initial_n"] <= budget["max_n"] <= SCHEDULE_CAPACITY, name
        assert resolve_effort(name)["name"] == name


def test_the_stamp_records_an_override_when_the_ceiling_moves():
    """max_n_overridden is the flag a reader uses to tell a nominal budget from
    an enforced one, so it has to move when the two differ."""
    dial = resolve_effort("low")
    stamp = stamp_candidates(dial, initial_n_applied=1, max_n_applied=9,
                             candidates_generated=9)
    assert stamp["max_n"] == CANDIDATE_BUDGET["low"]["max_n"]
    assert stamp["max_n_applied"] == 9
    assert stamp["max_n_overridden"] is True
