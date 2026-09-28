"""I17: destructive and egress custody operations need owner presence bound to
their plan digest, one use and five minutes, or say that they do not have it.
Verifiers are injected; the Windows Hello prompt itself is a manual check."""
import pytest

from harness import trace_presence as presence
from harness.trace_custody_ledger import CustodyLedger
from harness.trace_presence import PresenceError

OWNER = "owner_" + "a" * 32
DIGEST = "d" * 64


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class Verifier:
    def __init__(self, name, answer=True):
        self.name, self.answer, self.asked = name, answer, []

    def ask(self, summary):
        self.asked.append(summary)
        return self.answer


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "home" / "state"
    path.mkdir(parents=True)
    return path


def _code(call):
    with pytest.raises(PresenceError) as failure:
        call()
    return failure.value.code


def _confirmed(state, clock=None, verifier=None, digest=DIGEST):
    return presence.confirm(state, OWNER, "delete_apply", digest, "delete 3 items",
                            verifier=verifier or Verifier("none"), clock=clock)


def test_apply_without_a_presence_ref_is_refused(state):
    assert _code(lambda: presence.require(state, OWNER, "delete_apply", DIGEST, None)) == (
        "PRESENCE_REQUIRED")


def test_a_ref_for_another_digest_or_kind_is_refused(state):
    ref = _confirmed(state)
    assert _code(lambda: presence.require(state, OWNER, "delete_apply", "e" * 64, ref)) == (
        "PRESENCE_MISMATCH")
    assert _code(lambda: presence.require(state, OWNER, "export", DIGEST, ref)) == (
        "PRESENCE_MISMATCH")


def test_a_used_ref_is_refused(state):
    ref = _confirmed(state)
    assert presence.require(state, OWNER, "delete_apply", DIGEST, ref) == "none"
    assert _code(lambda: presence.require(state, OWNER, "delete_apply", DIGEST, ref)) == (
        "PRESENCE_USED")


def test_an_expired_ref_is_refused(state):
    clock = Clock()
    ref = _confirmed(state, clock=clock)
    clock.now += presence.TTL_S + 1
    assert _code(lambda: presence.require(state, OWNER, "delete_apply", DIGEST, ref,
                                          clock=clock)) == "PRESENCE_EXPIRED"


def test_a_denied_verification_leaves_no_usable_ref(state, monkeypatch):
    monkeypatch.setattr(presence, "adopted_method", lambda *a: "windows-hello")
    assert _code(lambda: _confirmed(state, verifier=Verifier("windows-hello", False))) == (
        "PRESENCE_DENIED")
    assert presence.PresenceStore(state, OWNER).pending() == []


def test_a_verifier_for_another_method_is_refused(state):
    assert _code(lambda: _confirmed(state, verifier=Verifier("windows-hello"))) == (
        "PRESENCE_METHOD")


def test_the_verifier_sees_the_summary_and_its_method_is_recorded(state, monkeypatch):
    monkeypatch.setattr(presence, "adopted_method", lambda *a: "windows-hello")
    hello = Verifier("windows-hello")
    ref = _confirmed(state, verifier=hello)
    assert hello.asked == ["delete 3 items"]
    assert presence.require(state, OWNER, "delete_apply", DIGEST, ref) == "windows-hello"


def test_none_is_recorded_in_the_response_the_ledger_and_the_report(state):
    from harness.trace_witness import MemorySink, record_custody_event
    ref = _confirmed(state)
    method = presence.require(state, OWNER, "delete_apply", DIGEST, ref)
    report = record_custody_event(state.parent, OWNER, "deletion",
                                  {"plan_digest": DIGEST, "items": 3}, method,
                                  sink=MemorySink())
    assert report["presence"] == "none"
    assert "agents included" in report["presence_statement"]
    entry = CustodyLedger(state.parent, OWNER).entries()[-1]
    assert entry["kind"] == "deletion" and entry["fields"]["presence"] == "none"


def test_a_forged_satisfied_challenge_file_confirms_nothing(state):
    """A process running as the owner writes a challenge file that says
    satisfied by windows-hello; only the verifier's own process can satisfy."""
    import json
    ref = "prs_" + "f" * 32
    forged = presence.PresenceStore(state, OWNER).dir / f"{ref}.json"
    forged.parent.mkdir(parents=True)
    forged.write_text(json.dumps({"schema": "flywheel.presence-challenge/v1", "ref": ref,
                                  "kind": "delete_apply", "plan_digest": DIGEST,
                                  "created_at": 0, "expires_at": 4_000_000_000,
                                  "state": "satisfied", "method": "windows-hello",
                                  "synthetic": False}))
    assert _code(lambda: presence.require(state, OWNER, "delete_apply", DIGEST, ref)) == (
        "PRESENCE_REQUIRED")


def test_a_real_challenge_rewritten_on_disk_stays_pending(state):
    import json
    store = presence.PresenceStore(state, OWNER)
    challenge = store.create("delete_apply", DIGEST)
    path = store.dir / f"{challenge['ref']}.json"
    path.write_text(json.dumps({**challenge, "state": "satisfied", "method": "windows-hello"}))
    assert _code(lambda: presence.require(state, OWNER, "delete_apply", DIGEST,
                                          challenge["ref"])) == "PRESENCE_REQUIRED"


def test_desktop_dialog_is_not_a_method_and_has_no_approval_call(state):
    assert "desktop-dialog" not in presence.METHODS
    assert not hasattr(presence, "approve_from_desktop")
    assert _code(lambda: presence.set_method(state, OWNER, "desktop-dialog", None)) == (
        "PRESENCE_INVALID")


def test_doctor_synthetic_is_given_only_to_a_doctor_session(state):
    """No public call satisfies a challenge as doctor-synthetic; confirm_synthetic
    refuses a session that is not the doctor's own."""
    store = presence.PresenceStore(state, OWNER)
    assert not hasattr(store, "satisfy")
    ordinary = store.create("delete_apply", DIGEST)
    assert _code(lambda: store._satisfy(ordinary["ref"], "doctor-synthetic")) == (
        "PRESENCE_METHOD")
    for session in ("0f0e0d0c-0b0a-0908-0706-050403020100", "flywheel-doctor-x", None):
        assert _code(lambda: presence.confirm_synthetic(state.parent, OWNER, session)) == (
            "PRESENCE_METHOD")


def test_status_names_the_method_and_what_none_means(state):
    status = presence.presence_status(state, OWNER)
    assert status["method"] == "none"
    assert "agents included" in status["statement"]


def test_changing_the_method_needs_presence_and_a_missing_file_does_not_downgrade(state):
    with pytest.raises(PresenceError):
        presence.set_method(state, OWNER, "windows-hello", None)
    ref = presence.confirm(state, OWNER, "presence_method",
                           presence.method_digest("windows-hello"), "set method",
                           verifier=Verifier("none"))
    presence.set_method(state, OWNER, "windows-hello", ref)
    assert presence.adopted_method(state, OWNER) == "windows-hello"
    presence.method_path(state, OWNER).unlink()
    assert _code(lambda: presence.adopted_method(state, OWNER)) == "PRESENCE_CONFIG_MISSING"


def test_a_method_file_written_without_an_adoption_is_tampered(state):
    """Writing method.json directly does not change the method: it must
    match the latest adoption in the verified custody ledger."""
    presence._write(presence.method_path(state, OWNER),
                    {"schema": "flywheel.presence-method/v1", "method": "windows-hello"})
    assert _code(lambda: presence.adopted_method(state, OWNER)) == "SETTINGS_TAMPERED"
    assert presence.presence_status(state, OWNER)["method"] == "unknown"
    assert _code(lambda: _confirmed(state)) == "SETTINGS_TAMPERED"


def test_a_method_file_swapped_after_adoption_is_tampered(state):
    ref = presence.confirm(state, OWNER, "presence_method",
                           presence.method_digest("windows-hello"), "set method",
                           verifier=Verifier("none"))
    presence.set_method(state, OWNER, "windows-hello", ref)
    presence._write(presence.method_path(state, OWNER),
                    {"schema": "flywheel.presence-method/v1", "method": "none"})
    assert _code(lambda: presence.adopted_method(state, OWNER)) == "SETTINGS_TAMPERED"
