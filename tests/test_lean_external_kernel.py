"""The second kernel on the bound path, without a toolchain.

The runner is injected, with tests/_lean_external_fixture.py standing in for
lean4export and nanoda, so these run in CI. They pin the rule the external
kernel adds: a PASS needs both kernels (`kernels_agreeing` 2); a kernel
disagreement fails closed; an external kernel that judged nothing is
UNVERIFIABLE, never a pass on one kernel. tests/test_lean_binding_live.py runs
the same cases against the real tools where they are installed.
"""
import json

import pytest
from _lean_external_fixture import answer, export

from harness.lean_binding import bound_check
from harness.lean_external_kernel import (ACCEPTED, ERROR, REJECTED,
                                          classify, nanoda_config)
from harness.lean_oracle import LeanOracle

CH = {"theorem": "two", "statement": "1 + 1 = 2"}
GOOD = "theorem two : 1 + 1 = 2 := rfl\n"
BIND = json.dumps({"status": "bound", "theorem": "two",
                   "statement_canonical": "two.[] : Eq.{1} Nat 2 2",
                   "axioms": [], "refusals": [], "lean_version": "4.34.1",
                   "lean_githash": "abc"})
PANIC = (101, "thread 'main' panicked at src\\tc.rs:955:71:\n"
              "assertion failed: self.def_eq(u, v)")


def _runner(calls=None, checker=(0, ""), **external):
    def run(argv, code):
        if calls is not None:
            calls.append(argv[0])
        if "--run" in argv:
            return 0, BIND
        ext = answer(argv, githash="abc", **external)
        if ext is not None:
            return ext
        return checker if argv[0] == "leanchecker" else (0, "")
    return run


def _check(**kw):
    return bound_check(GOOD, CH, runner=_runner(**kw))


def test_two_agreeing_kernels_pass_with_the_external_block():
    doc = _check()
    assert doc["passed"] is True
    assert doc["kernels_agreeing"] == 2
    ext = doc["external_kernel"]
    assert ext["verdict"] == ACCEPTED
    assert ext["tool"] == "nanoda_bin" and ext["version"] == "0.4.19"
    assert len(ext["source_commit"]) == 40 and ext["binary_sha256"]
    assert ext["exporter"]["tool"] == "lean4export"
    assert ext["exporter"]["version"] == "v4.34.0"
    assert len(ext["statement_sha256"]) == 64
    assert ext["declarations_checked"] == 2
    # the existing #365 receipt fields are all still there
    for key in ("statement_sha256", "challenge", "binding", "trusted_base",
                "spec_fidelity", "artifact_sha256", "leanchecker"):
        assert key in doc
    assert "nanoda" in doc["trusted_base"]["kernel"]


@pytest.mark.parametrize("reply", [
    PANIC, (1, 'Error: export file declares unpermitted axiom "sorryAx"')])
def test_a_planted_kernel_disagreement_fails_closed(reply):
    # Lean's kernel and leanchecker accepted; the external kernel refuses.
    doc = _check(nanoda=reply)
    assert doc["passed"] is False
    assert doc["kernels_agreeing"] == 1
    assert doc["external_kernel"]["verdict"] == REJECTED
    assert "kernels disagree" in doc["kernel_output"]
    r = LeanOracle(runner=_runner(nanoda=reply), challenge=CH).verify(
        GOOD, None)
    assert r.verdict() == "FAIL"


def test_a_missing_external_kernel_is_unverifiable_never_one_kernel_pass():
    doc = _check(missing=True)
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "external-kernel-unavailable"
    assert doc["kernels_agreeing"] == 1
    r = LeanOracle(runner=_runner(missing=True), challenge=CH).verify(
        GOOD, None)
    assert r.verdict() == "UNVERIFIABLE"
    assert r.unverifiable_reason == "TOOLCHAIN_MISSING"
    assert r.attribution.value == "ENVIRONMENT"


@pytest.mark.parametrize("reply", [
    (124, "nanoda timed out after 300s"),
    (1, "Error: Failed to open export file: Os { code: 2 }"),
    (0, "no success line"),
    (3221225725, "")])
def test_an_external_kernel_that_judged_nothing_is_unverifiable(reply):
    doc = _check(nanoda=reply)
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "external-kernel-error"
    assert doc["external_kernel"]["verdict"] == ERROR


@pytest.mark.parametrize("candidate", [
    (1, "lean4export: unknown module"),
    (0, "not json"),
    (0, export("two", "abc").replace('"3.1.0"}, "lean"', '"2.0.0"}, "lean"')),
    (0, export("two", "other-lean"))])
def test_an_export_that_cannot_be_used_is_unverifiable(candidate):
    doc = _check(candidate=candidate)
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "external-kernel-error"


@pytest.mark.parametrize("candidate", [
    (0, export("two", "abc", prop="False")),
    (0, export("two", "abc", kind="def")),
    (0, export("two", "abc").replace('"isRec": false', '"isRec": true'))])
def test_an_exported_statement_that_differs_is_refused(candidate):
    # The Python reader of the export sees a different proposition, a
    # non-theorem, or a constant the statement uses declared differently.
    calls = []
    doc = _check(candidate=candidate, calls=calls)
    assert doc["passed"] is False
    assert doc["external_kernel"]["verdict"] == REJECTED
    assert calls.count("nanoda_bin") == 1          # the --help probe only


def test_the_external_kernel_never_runs_when_the_lean_side_refuses():
    calls = []
    doc = _check(calls=calls, checker=(1, "leanchecker found a problem in "
                                          "Candidate\nwhile replaying"))
    assert doc["passed"] is False
    assert doc["kernels_agreeing"] == 0
    assert doc["external_kernel"]["verdict"] == "NOT_RUN"
    assert "lean4export" not in calls and "nanoda_bin" not in calls


def test_steps_without_an_external_kernel_cannot_pass():
    from harness.lean_binding import parse_challenge
    from harness.lean_binding_judge import judge

    class OneKernel:
        sandbox = None
        olean_sha = staticmethod(lambda: "a")
        compile_candidate = staticmethod(lambda code: (0, ""))
        compile_challenge = staticmethod(lambda src: (0, ""))
        bind = staticmethod(lambda code, thm: (0, BIND))
        replay = staticmethod(lambda code: {"ok": True, "exit": 0,
                                            "detail": ""})
    ch, _ = parse_challenge(CH)
    doc = judge(GOOD, ch, OneKernel(), "sha", "t")
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "external-kernel-unavailable"


def test_classify_reads_nanoda_s_three_outcomes():
    assert classify(0, "x\nChecked 12 declarations with no errors") == \
        (ACCEPTED, 12)
    assert classify(*PANIC) == (REJECTED, None)
    assert classify(1, "Error: declaration type mismatch") == \
        (REJECTED, None)
    assert classify(1, "Error: expected value at line 1") == (ERROR, None)
    assert classify(0, "") == (ERROR, None)
    assert classify(2, "Checked 1 declarations with no errors") == \
        (ERROR, None)


def test_nanoda_config_permits_only_the_classical_trio():
    cfg = nanoda_config("/x/export.ndjson", "two")
    assert cfg["permitted_axioms"] == ["Classical.choice", "Quot.sound",
                                       "propext"]
    assert cfg["unpermitted_axiom_hard_error"] is True
    assert cfg["pp_declars"] == ["two"]
    assert "unsafe_permit_all_axioms" not in cfg
