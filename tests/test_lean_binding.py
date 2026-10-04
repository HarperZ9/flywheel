"""The task binding of the Lean oracle, without a toolchain.

The runner is injected (or the live steps' spawn is replaced), so these run in
CI, which installs no Lean. They pin the step order, the receipt fields, and
each fail-closed exit. tests/test_lean_binding_live.py runs the same cases
against a real kernel where one is installed.
"""
import hashlib
import json
import os

import pytest

from _lean_external_fixture import answer
from harness import lean_binding, lean_replay
from harness.lean_binding import (CHALLENGE_MODULE, SCHEMA, bound_check,
                                  challenge_source, parse_challenge)
from harness.lean_binding_judge import judge

CH = {"theorem": "two", "statement": "1 + 1 = 2"}
CANON = "two.[] : Eq.{1} Nat (HAdd.hAdd 1 1) 2"
GOOD = "theorem two : 1 + 1 = 2 := rfl\n"


def _doc(**kw):
    doc = {"status": "bound", "theorem": "two", "statement_canonical": CANON,
           "axioms": [], "refusals": [], "lean_version": "4.34.1",
           "lean_githash": "abc"}
    doc.update(kw)
    return json.dumps(doc)


def _runner(*, bind=None, compile_rc=0, challenge_rc=0, checker=(0, ""),
            calls=None, **external):
    def run(argv, code):
        if calls is not None:
            calls.append(" ".join(argv))
        if "--run" in argv:
            return 0, bind if bind is not None else _doc()
        ext = answer(argv, githash="abc", **external)
        if ext is not None:
            return ext
        if argv[0] == "leanchecker":
            return checker
        if f"{CHALLENGE_MODULE}.olean" in argv:
            return challenge_rc, "challenge error" if challenge_rc else ""
        return compile_rc, "error: type mismatch" if compile_rc else ""
    return run


@pytest.mark.parametrize("raw", [None, {}, [], {"theorem": "two"},
                                 {"theorem": "1bad", "statement": "True"},
                                 {"theorem": "two", "statement": "  "},
                                 {"theorem": "two", "statement": "True",
                                  "header": 3}])
def test_an_unusable_challenge_is_unpinned_and_runs_nothing(raw):
    calls = []
    doc = bound_check(GOOD, raw, runner=_runner(calls=calls))
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "challenge-unpinned"
    assert doc["statement_binding"] == "unpinned"
    assert calls == []


def test_challenge_source_is_header_then_the_pinned_theorem():
    ch, _ = parse_challenge({"theorem": "d", "statement": "double 1 = 2",
                             "header": "def double (n : Nat) := n + n\n"})
    assert challenge_source(ch) == ("def double (n : Nat) := n + n\n\n"
                                    "theorem d : double 1 = 2 := sorry\n")


def test_a_bound_pass_carries_every_receipt_field():
    doc = bound_check(GOOD, CH, runner=_runner(bind=_doc(
        axioms=["propext", "Quot.sound"])))
    assert doc["passed"] is True
    assert doc["schema"] == SCHEMA
    assert doc["validation_level"] == "leanchecker_replay"
    assert doc["statement_binding"] == "pinned"
    assert doc["statement_sha256"] == hashlib.sha256(
        CANON.encode()).hexdigest()
    assert doc["challenge"]["theorem"] == "two"
    assert len(doc["challenge"]["challenge_sha256"]) == 64
    tb = doc["trusted_base"]
    assert tb["lean_version"] == "4.34.1" and tb["lean_githash"] == "abc"
    assert tb["axioms_used"] == ["propext", "Quot.sound"]
    assert "not #print axioms" in tb["axioms_source"]
    assert doc["spec_fidelity"]["status"] == "UNVERIFIED"
    assert doc["axiom_footprint"] == {"two": ["propext", "Quot.sound"]}


def test_a_compile_error_fails_before_the_bind_runs():
    calls = []
    doc = bound_check(GOOD, CH, runner=_runner(compile_rc=1, calls=calls))
    assert doc["passed"] is False
    assert not any("--run" in c for c in calls)


def test_a_sorry_warning_from_the_compile_is_refusal():
    def run(argv, code):
        return 0, "warning: declaration uses 'sorry'"
    assert bound_check(GOOD, CH, runner=run)["passed"] is False


def test_a_challenge_that_does_not_compile_is_the_task_s_gap():
    doc = bound_check(GOOD, CH, runner=_runner(challenge_rc=1))
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "challenge-compile-failed"


def test_a_binding_refusal_is_a_fail_naming_each_reason():
    bind = _doc(status="refused", refusals=["two states a different "
                                            "proposition than the challenge"])
    doc = bound_check(GOOD, CH, runner=_runner(bind=bind))
    assert doc["passed"] is False
    assert "different proposition" in doc["kernel_output"]
    assert doc["leanchecker"] is None          # the replay never ran


def test_bound_with_refusals_is_still_refused():
    doc = bound_check(GOOD, CH, runner=_runner(bind=_doc(refusals=["x"])))
    assert doc["passed"] is False


@pytest.mark.parametrize("axiom", ["sorryAx", "cheat", "evil",
                                   "Lean.ofReduceBool"])
def test_an_axiom_outside_the_trio_fails(axiom):
    doc = bound_check(GOOD, CH, runner=_runner(bind=_doc(
        axioms=["propext", axiom])))
    assert doc["passed"] is False
    assert axiom in doc["kernel_output"]


@pytest.mark.parametrize("out", ["", "not json", '{"status": "error", '
                                 '"detail": "boom"}', _doc(theorem="other")])
def test_a_bind_that_judged_nothing_is_never_a_pass(out):
    doc = bound_check(GOOD, CH, runner=_runner(bind=out))
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "binding-check-error"


def test_a_module_system_candidate_is_unsupported_not_passed():
    doc = bound_check(GOOD, CH, runner=_runner(bind=_doc(
        status="unsupported", detail="module")))
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "binding-unsupported"


def test_a_pinned_statement_hash_must_match_the_elaboration():
    good = dict(CH, statement_sha256=hashlib.sha256(CANON.encode()).hexdigest())
    assert bound_check(GOOD, good, runner=_runner())["passed"] is True
    bad = dict(CH, statement_sha256="0" * 64)
    doc = bound_check(GOOD, bad, runner=_runner())
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "statement-hash-mismatch"


def test_a_replay_refusal_after_binding_fails():
    doc = bound_check(GOOD, CH, runner=_runner(checker=(
        1, "leanchecker found a problem in Candidate\nwhile replaying")))
    assert doc["passed"] is False
    assert doc["validation_level"] == "print_axioms"


class _Changing:
    """Steps whose compiled module changes after the bind step."""
    def __init__(self):
        self.n = 0

    def olean_sha(self):
        self.n += 1
        return "a" if self.n < 3 else "b"

    compile_candidate = staticmethod(lambda code: (0, ""))
    compile_challenge = staticmethod(lambda src: (0, ""))
    bind = staticmethod(lambda code, thm: (0, _doc()))
    replay = staticmethod(lambda code: {"ok": True, "exit": 0, "detail": ""})


def test_an_artifact_that_changes_between_steps_fails_closed():
    ch, _ = parse_challenge(CH)
    doc = judge(GOOD, ch, _Changing(), "sha", "t")
    assert doc["passed"] is False
    assert "changed between checks" in doc["kernel_output"]


def _live(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    return lean_binding._Live(root, "lean", "leanchecker", str(tmp_path))


def test_live_bind_refuses_a_challenge_name_on_the_inherited_path(
        monkeypatch, tmp_path):
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / f"{CHALLENGE_MODULE}.olean").write_bytes(b"x")
    monkeypatch.setenv("LEAN_PATH", str(planted))
    rc, out = _live(tmp_path).bind(GOOD, "two")
    assert rc is None and CHALLENGE_MODULE in out


def test_live_bind_never_puts_the_candidate_build_on_its_path(
        monkeypatch, tmp_path):
    seen = {}

    def spawn(argv, *, timeout=0, env=None, label="", stderr=None):
        seen["argv"], seen["env"] = argv, env
        return 0, _doc()
    monkeypatch.setattr(lean_replay, "run_killable", spawn)
    monkeypatch.delenv("LEAN_PATH", raising=False)
    steps = _live(tmp_path)
    steps.bind(GOOD, "two")
    path = seen["env"]["LEAN_PATH"]
    assert str(steps.root / "chb") in path
    assert str(steps.root / "cb") not in path.split(os.pathsep)
    assert seen["argv"][-3:] == [str(steps.olean), CHALLENGE_MODULE, "two"]
