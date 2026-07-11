"""Falsifier for the companion seat (harness/companion.py).

The seat is a routing decision, and the load-bearing properties are:

  1. cache HIT answers at ~0 cost -- the selector never runs.
  2. an external ORACLE accept -> LOCAL_VERIFIED, and the accepted text round-trips
     through the cache so the next identical ask is a hit.
  3. behavioral CONSENSUS (no oracle) -> LOCAL_CONSENSUS, carrying the best-effort
     text but flagged as agreement, not verification.
  4. budget exhausted below confidence -> ESCALATE, and an ESCALATE carries NO
     accepted text (text is None), the frontier endpoint to route to, and the
     unverified attempt preserved for the ledger.
  5. C2: the oracle decides accepts. Wrong candidates + a rejecting oracle must
     ESCALATE -- the seat never manufactures a local accept.
  6. every decision is appended to the ledger.
"""
import sys
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.companion import (
    CompanionSeat, CompanionResult, _task_key,
    CACHE, LOCAL_VERIFIED, LOCAL_CONSENSUS, ESCALATE,
)
from harness.proposer import ProposerOutput


# --- fakes (mirror test_adaptive_select fixtures) ------------------------------

class OneCandidateProposer:
    model_ref = "stub"

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(self.text, self.model_ref, seed, "h", "stub")


DIVERSE_CORRECT = [
    "def f(a):\n    return a + 1\n",
    "def f(a):\n    total = a\n    total = total + 1\n    return total\n",
    "def f(a):\n    return sum((a, 1))\n",
    "def f(a):\n    x = 1\n    return a + x\n",
]


class DiverseCorrectProposer:
    """Textually diverse, behaviorally identical -> genuine independent agreement."""
    model_ref = "stub"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        t = DIVERSE_CORRECT[self.calls % len(DIVERSE_CORRECT)]
        self.calls += 1
        return ProposerOutput(t, self.model_ref, seed, "h", "stub")


class CyclingProposer:
    model_ref = "stub"

    def __init__(self, texts):
        self.texts = texts
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        t = self.texts[self.calls % len(self.texts)]
        self.calls += 1
        return ProposerOutput(t, self.model_ref, seed, "h", "stub")


class FakeOracle:
    """Accepts iff a marker substring is present -- an external check the seat
    cannot author or fake."""
    def __init__(self, marker):
        self.marker = marker

    def verify(self, candidate, task):
        return SimpleNamespace(passed=self.marker in candidate)


class DictCache:
    """Duck-typed proof cache: .get(key) / .put(key, value)."""
    def __init__(self):
        self.store = {}
        self.gets = 0
        self.puts = 0

    def get(self, key):
        self.gets += 1
        return self.store.get(key)

    def put(self, key, value):
        self.puts += 1
        self.store[key] = value


TASK = SimpleNamespace(task_id="t1", prompt="solve", max_new_tokens=64, system="")
SIG = "def f(a):\n    return a + 1\n"
GOOD = "def f(a):\n    return a + 1\n"


# --- 1. cache hit --------------------------------------------------------------

def test_cache_hit_answers_without_running_selector():
    cache = DictCache()
    cache.store[_task_key(TASK, SIG)] = {"text": "cached answer", "receipt": {"v": 1}}
    prop = OneCandidateProposer(GOOD)          # would generate if reached
    seat = CompanionSeat(prop, oracle=FakeOracle("+ 1"), cache=cache)
    res = seat.answer(TASK, solution_sig=SIG)
    assert res.source == CACHE
    assert res.text == "cached answer"
    assert prop.calls == 0                     # selector never ran -- ~0 cost


# --- 2. local verified (oracle PASS) + cache round-trip ------------------------

def test_oracle_pass_is_local_verified():
    prop = OneCandidateProposer(GOOD)
    seat = CompanionSeat(prop, oracle=FakeOracle("+ 1"), initial_n=4, max_n=32)
    res = seat.answer(TASK, solution_sig=SIG)
    assert res.source == LOCAL_VERIFIED
    assert res.text == GOOD
    assert res.receipt["verdict"] == "PASS"
    assert res.receipt["method"] == "oracle"
    assert res.escalate_to is None


def test_local_verified_round_trips_through_cache():
    cache = DictCache()
    prop = OneCandidateProposer(GOOD)
    seat = CompanionSeat(prop, oracle=FakeOracle("+ 1"), cache=cache)
    first = seat.answer(TASK, solution_sig=SIG)
    assert first.source == LOCAL_VERIFIED
    assert cache.puts == 1                     # verified accept was cached
    calls_after_first = prop.calls
    second = seat.answer(TASK, solution_sig=SIG)
    assert second.source == CACHE              # now a hit
    assert second.text == GOOD
    assert prop.calls == calls_after_first     # selector did NOT run again


# --- 3. consensus (no oracle) --------------------------------------------------

def test_consensus_is_local_consensus_not_verified():
    prop = DiverseCorrectProposer()
    seat = CompanionSeat(prop, oracle=None, initial_n=4, max_n=32)
    res = seat.answer(TASK, solution_sig=SIG)
    assert res.source == LOCAL_CONSENSUS
    assert res.text in DIVERSE_CORRECT
    assert res.receipt["verdict"] == "CONSENSUS_PASS"   # agreement, not verified
    assert res.best_effort_text is not None
    assert res.escalate_to is None


def test_consensus_not_written_to_cache():
    # Only a VERIFIED accept is a re-checkable fact; agreement must not be cached
    # as if it were verified.
    cache = DictCache()
    prop = DiverseCorrectProposer()
    seat = CompanionSeat(prop, oracle=None, cache=cache)
    res = seat.answer(TASK, solution_sig=SIG)
    assert res.source == LOCAL_CONSENSUS
    assert cache.puts == 0


# --- 4. escalate ---------------------------------------------------------------

def test_low_confidence_escalates_with_best_effort():
    distinct = [f"def f(a):\n    return a + {i}\n" for i in range(64)]
    prop = CyclingProposer(distinct)
    seat = CompanionSeat(prop, oracle=None, initial_n=4, max_n=16,
                         escalation_endpoint="anthropic")
    res = seat.answer(TASK, solution_sig=SIG)
    assert res.source == ESCALATE
    assert res.text is None                    # NO accepted answer on escalate
    assert res.escalate_to == "anthropic"
    assert res.best_effort_text is not None    # attempt preserved for the ledger


# --- 5. C2: the oracle decides accepts -----------------------------------------

def test_rejecting_oracle_forces_escalate_no_false_accept():
    # Distinct WRONG candidates + an oracle that never matches. The seat must not
    # manufacture a local accept -- with the oracle as authority it escalates.
    distinct = [f"def f(a):\n    return a - {i}\n" for i in range(64)]
    prop = CyclingProposer(distinct)
    seat = CompanionSeat(prop, oracle=FakeOracle("NEVER_PRESENT"),
                         initial_n=4, max_n=16)
    res = seat.answer(TASK, solution_sig=SIG)
    assert res.source == ESCALATE
    assert res.text is None


# --- 6. ledger -----------------------------------------------------------------

def test_ledger_records_every_decision():
    seat = CompanionSeat(OneCandidateProposer(GOOD), oracle=FakeOracle("+ 1"))
    seat.answer(TASK, solution_sig=SIG)
    seat.answer(SimpleNamespace(task_id="t2", prompt="p2", max_new_tokens=64, system=""),
                solution_sig=SIG)
    assert len(seat.ledger) == 2
    assert [row["n"] for row in seat.ledger] == [1, 2]
    assert all("source" in row and "receipt" in row for row in seat.ledger)


def test_result_to_dict_is_schema_tagged():
    res = CompanionResult(ESCALATE, None, {"verdict": "ESCALATE"},
                          escalate_to="anthropic", best_effort_text="x")
    d = res.to_dict()
    assert d["schema"] == "flywheel.companion-result/v1"
    assert d["source"] == ESCALATE
    assert d["escalate_to"] == "anthropic"
