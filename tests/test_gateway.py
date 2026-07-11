"""gateway contract — the two SUPERAPP increment-2 falsifiers, unit-level.

Both verifiers must be able to fail:
  - a down local endpoint reads as unhealthy (not silently healthy)
  - touching a cataloged receipt moves the world root hash
Plus: enterprise providers expose credential-presence booleans, never values.
"""
import json

from harness import gateway


def test_world_root_hash_changes_when_a_receipt_changes(tmp_path):
    (tmp_path / "a.json").write_text('{"v": 1}', encoding="utf-8")
    catalog = ("a.json",)
    before = gateway.world_state(tmp_path, catalog)["root_hash"]
    (tmp_path / "a.json").write_text('{"v": 2}', encoding="utf-8")
    after = gateway.world_state(tmp_path, catalog)["root_hash"]
    assert before != after, "root hash did not move on a receipt change — catalog is fake"


def test_world_marks_missing_receipts_honestly(tmp_path):
    w = gateway.world_state(tmp_path, ("does_not_exist.json",))
    assert w["present_count"] == 0
    assert w["receipts"][0]["sha256"] == "MISSING"
    assert w["receipts"][0]["present"] is False


def test_world_root_hash_stable_when_nothing_changes(tmp_path):
    (tmp_path / "a.json").write_text("stable", encoding="utf-8")
    h1 = gateway.world_state(tmp_path, ("a.json",))["root_hash"]
    h2 = gateway.world_state(tmp_path, ("a.json",))["root_hash"]
    assert h1 == h2


def test_down_local_endpoint_reads_unhealthy():
    # ports chosen to be almost certainly closed -> probe must fail closed
    roster = gateway.endpoint_roster("http://127.0.0.1:9", "http://127.0.0.1:9")
    assert roster["local_healthy"] == 0
    assert all(e["healthy"] is False for e in roster["local"])


def test_enterprise_reports_credential_presence_not_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-canary-value")
    roster = gateway.endpoint_roster("http://127.0.0.1:9", "http://127.0.0.1:9")
    blob = json.dumps(roster)
    assert "sk-fake-canary-value" not in blob, "a key VALUE leaked into the roster"
    codex = next((e for e in roster["enterprise"] if e["name"] == "codex"), None)
    if codex is not None:  # roster present only if endpoints.py imported
        assert codex["credential_present"] is True
        assert codex["key_env"] == "OPENAI_API_KEY"


def test_spine_roster_present():
    w = gateway.world_state(gateway.REPO)
    assert "local-model" in w["spine"] and "telos" in w["spine"]


# --- companion route: the two SUPERAPP increment-5 falsifiers ------------------

from types import SimpleNamespace

from harness.companion import CompanionSeat
from harness.proposer import ProposerOutput


class _CyclingProposer:
    model_ref = "stub"

    def __init__(self, texts):
        self.texts = texts
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        t = self.texts[self.calls % len(self.texts)]
        self.calls += 1
        return ProposerOutput(t, self.model_ref, seed, "h", "stub")


class _OneProposer:
    model_ref = "stub"

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(self.text, self.model_ref, seed, "h", "stub")


class _FakeOracle:
    def __init__(self, marker):
        self.marker = marker

    def verify(self, candidate, task):
        return SimpleNamespace(passed=self.marker in candidate)


def test_companion_cache_hit_triggers_no_frontier_call():
    # Falsifier 1: a proof-cached fact must answer at ~0 cost, with NO escalate in
    # the ledger. Seat over an oracle-verified accept so the answer is cached, then
    # ask again -> the second answer is a cache hit, and no ledger row escalates.
    seat = CompanionSeat(_OneProposer("def f(a):\n    return a + 1\n"),
                         oracle=_FakeOracle("+ 1"),
                         cache=gateway._MemoryProofCache())
    sig = "def f(a):\n    return a + 1\n"
    first = gateway.companion_answer(seat, "add one", sig)
    assert first["source"] == "local-verified"
    second = gateway.companion_answer(seat, "add one", sig)
    assert second["source"] == "cache"
    assert second["text"] == "def f(a):\n    return a + 1\n"
    assert all(row["source"] != "escalate" for row in seat.ledger), \
        "a cached fact triggered an escalation -- increment-5 falsifier 1 broken"


def test_companion_escalate_carries_ledgered_failed_local_receipt():
    # Falsifier 2: on a local failure the escalate decision must be PRECEDED by a
    # ledgered failed-local SelectionReceipt -- escalation is a verdict on evidence,
    # never a bare guess. Distinct-disagreeing candidates + no oracle -> escalate.
    distinct = [f"def f(a):\n    return a + {i}\n" for i in range(64)]
    seat = CompanionSeat(_CyclingProposer(distinct), oracle=None,
                         cache=gateway._MemoryProofCache(), max_n=16)
    out = gateway.companion_answer(seat, "hard task", "def f(a):\n    return a + 1\n")
    assert out["source"] == "escalate"
    assert out["text"] is None                    # no accepted answer travels on escalate
    assert out["escalate_to"] == "anthropic"
    assert out["best_effort_text"] is not None    # the failed local attempt is preserved
    row = seat.ledger[-1]
    assert row["source"] == "escalate"
    assert row["receipt"]["verdict"] == "ESCALATE"
    assert row["receipt"]["candidates_used"] > 0, \
        "escalate has no evidence of a real local attempt -- increment-5 falsifier 2 broken"


def test_companion_answer_never_calls_frontier_inline():
    # The frontier tier is only NAMED, never invoked, from the seat/route: the
    # escalate_to endpoint is a string, and routing to it is a caller-gated action.
    seat = CompanionSeat(_CyclingProposer([f"x{i}" for i in range(64)]), oracle=None,
                         cache=gateway._MemoryProofCache(), max_n=8)
    out = gateway.companion_answer(seat, "anything")
    assert isinstance(out["escalate_to"], str) and out["text"] is None


# --- training status route (read-only) -----------------------------------------

def test_training_status_route_reports_stopped_when_no_run(tmp_path, monkeypatch):
    # Route is read-only and honest with no run present. Inject a dead-screen probe
    # so the test never shells wsl.
    import harness.training_lane as T
    monkeypatch.setattr(T, "screen_alive", lambda *a, **k: False)
    s = gateway._training_status(str(tmp_path))
    assert s["schema"] == "flywheel.training-status/v1"
    assert s["state"] == "stopped"
    assert s["screen_alive"] is False


def test_training_status_route_degrades_on_runtime_error(monkeypatch):
    # A runtime failure INSIDE the present module (not an import failure) must return
    # an honest error dict, never crash the handler thread with a traceback.
    import harness.training_lane as T
    def boom(*a, **k):
        raise PermissionError("log locked")
    monkeypatch.setattr(T, "training_status", boom)
    out = gateway._training_status("whatever")
    assert "error" in out and "training_status failed" in out["error"]


class _FakeHeaders:
    def __init__(self, cl):
        self._cl = cl

    def get(self, key, default=None):
        return self._cl if key == "Content-Length" else default


def _content_length(cl):
    h = gateway._Handler.__new__(gateway._Handler)   # no socket, just the method
    h.headers = _FakeHeaders(cl)
    return h._content_length()


def test_content_length_guard_rejects_garbage_and_oversize():
    assert _content_length("42") == 42                 # valid
    assert _content_length("0") == 0
    assert _content_length("x") is None                # non-numeric -> 400, not a crash
    assert _content_length("") is None                 # present-but-empty
    assert _content_length("-5") is None               # negative
    assert _content_length(str(gateway._Handler.MAX_BODY + 1)) is None   # oversized
