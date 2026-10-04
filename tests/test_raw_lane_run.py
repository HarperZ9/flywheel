"""The raw lane adapter and level 2, against the real raw-native 0.5.0 binary.

Claims under test:
- a render at the default tolerance is COMPLETED and PASS, its own files pass
  level 1, and its receipt verifies with MATCH and PASS;
- the same view at tolerance 0.05 is FAIL, with a receipt reading MATCH and FAIL;
- bad params exit 2 and map to HARNESS_ERROR; a budget too short maps to
  TIMEOUT; exit 1 maps to RESOURCE_EXCEEDED and FAIL; any other exit is CRASHED;
- a renderer whose files disagree with its own certificate is UNVERIFIABLE,
  not PASS;
- level 2 replays the Windows and the Linux recorded renders on this host and
  reads MATCH, so cross-platform replay is byte-identical for these renders;
- a record whose digest was edited replays as DRIFT attributed to the candidate
  on the same platform, and as DRIFT with the cross-device note across platforms;
- a 0.2.0 certificate cannot be replayed and says so;
- paired mutation: a replay comparator that ignores the digests is caught.
Tests that need the binary skip with the installer's reason where it cannot be
installed, and fail instead when RAW_LANE_REQUIRE_BINARY=1.
"""
from __future__ import annotations

import pytest

from harness import raw_lane, raw_lane_install as inst, raw_lane_replay as rp
from harness.certificates import raw_ao_receipt as rr
from harness.certificates.replay import CROSS_DEVICE_NOTE
from harness.verdict import Execution, Verdict
from tests.raw_native_fixtures import cert, installed_home, run_record  # noqa: F401

SMALL = {"width": 32, "height": 32}


def test_a_render_passes_with_a_receipt_that_reads_match_and_pass(installed_home):  # noqa: F811
    run = raw_lane.run(SMALL, environ=installed_home)
    assert run.execution is Execution.COMPLETED and run.rc == 0
    assert run.result.verdict_ is Verdict.PASS
    assert rr.check(run.receipt) == []
    fw = run.receipt["flywheel"]
    assert (fw["identity"], fw["tolerance"], fw["level1"], fw["verdict"]) == (
        "MATCH", "PASS", "PASS", "PASS")
    assert run.arena["verdict"] == "verified" and run.channels
    assert run.native_receipt["schema"] == "superstack.receipt/1"
    assert fw["native_receipt"]["agrees"] is True


def test_a_tight_tolerance_fails_and_the_receipt_reads_fail(installed_home):  # noqa: F811
    run = raw_lane.run({**SMALL, "tolerance": 0.05}, environ=installed_home)
    assert run.result.verdict_ is Verdict.FAIL
    assert (run.receipt["flywheel"]["identity"], run.receipt["flywheel"]["tolerance"]) == (
        "MATCH", "FAIL")


def test_bad_params_are_a_harness_error(installed_home):  # noqa: F811
    run = raw_lane.run({"width": 0, "height": 8}, environ=installed_home)
    assert (run.execution, run.rc) == (Execution.HARNESS_ERROR, 2)
    assert run.result.verdict_ is Verdict.UNVERIFIABLE
    assert "must be positive" in run.result.stdout_excerpt


def test_a_budget_too_short_is_a_timeout(installed_home):  # noqa: F811
    run = raw_lane.run({"width": 512, "height": 512}, environ=installed_home, timeout=0.01)
    assert run.execution is Execution.TIMEOUT
    assert run.result.verdict_ is Verdict.UNVERIFIABLE


@pytest.mark.parametrize("rc,execution,verdict", [
    (1, Execution.RESOURCE_EXCEEDED, Verdict.FAIL),
    (2, Execution.HARNESS_ERROR, Verdict.UNVERIFIABLE),
    (7, Execution.CRASHED, Verdict.UNVERIFIABLE)])
def test_exit_codes_map_to_executions(monkeypatch, tmp_path, rc, execution, verdict):
    monkeypatch.setattr(inst, "resolve", lambda *a, **k: tmp_path / "raw_native_cli")
    arena = b'{"oracle":"raw-arena-v1","verdict":"refuted"}'
    monkeypatch.setattr(raw_lane, "_spawn", lambda b, p, t: (rc, {
        "arena_certificate.json": arena}, "said"))
    run = raw_lane.run(SMALL)
    assert (run.execution, run.result.verdict_) == (execution, verdict)


def test_a_renderer_whose_files_disagree_with_its_certificate_is_unverifiable(
        monkeypatch, installed_home):  # noqa: F811
    real = raw_lane._spawn

    def tampered(binary, params, timeout):
        rc, files, said = real(binary, params, timeout)
        files["mask.pgm"] = files["mask.pgm"][:-1] + b"\x00"
        return rc, files, said
    monkeypatch.setattr(raw_lane, "_spawn", tampered)
    run = raw_lane.run(SMALL, environ=installed_home)
    assert run.result.verdict_ is Verdict.UNVERIFIABLE
    assert run.result.unverifiable_reason == "ORACLE_UNAVAILABLE"
    assert run.receipt["flywheel"]["identity"] == "DRIFT"


@pytest.mark.parametrize("recorded", ["windows-x64", "linux-x64"])
def test_replay_of_each_platforms_record_matches_here(installed_home, recorded):  # noqa: F811
    out = rp.replay(cert(recorded), claimed_platform=run_record(recorded)["platform"],
                    environ=installed_home)
    assert out["verdict"] == "MATCH", out["reason"]
    assert rr.check(out["receipt"]) == []
    fw = out["receipt"]["flywheel"]
    assert (fw["identity"], fw["tolerance"]) == ("MATCH", "PASS")
    assert fw["replayed_platform"] == inst.platform_key()


def _edited_record() -> dict:
    c = cert("windows-x64")
    c["outputs"]["frame.ppm"] = "0" * 64
    return c


def _drift_known_answer(environ) -> None:
    here = inst.platform_key()
    same = rp.replay(_edited_record(), claimed_platform=here, environ=environ)
    assert (same["verdict"], same["attribution"]) == ("DRIFT", "CANDIDATE")
    assert CROSS_DEVICE_NOTE not in same["receipt"]["does_not_prove"]
    assert same["receipt"]["flywheel"]["tolerance"] == "PASS"
    other = rp.replay(_edited_record(), claimed_platform="elsewhere-x64", environ=environ)
    assert (other["verdict"], other["attribution"]) == ("DRIFT", "ENVIRONMENT")
    assert CROSS_DEVICE_NOTE in other["receipt"]["does_not_prove"]


def test_an_edited_record_replays_as_drift(installed_home):  # noqa: F811
    _drift_known_answer(installed_home)


def test_paired_mutation_a_comparator_that_ignores_digests_is_caught(
        monkeypatch, installed_home):  # noqa: F811
    monkeypatch.setattr(rp, "_verdict", lambda *a: ("MATCH", None, [], "ignored"))
    with pytest.raises(AssertionError):
        _drift_known_answer(installed_home)


def test_a_0_2_0_certificate_cannot_be_replayed():
    c = cert("windows-x64")
    del c["schema"]
    out = rp.replay(c)
    assert out["verdict"] == "UNVERIFIABLE" and out["receipt"] is None
