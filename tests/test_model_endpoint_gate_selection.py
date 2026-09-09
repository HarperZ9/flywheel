"""An endpoint gate must admit its entire generation plan before any I/O."""
import json
from pathlib import Path

import pytest

from harness.model_endpoint_gate_cli import build_report, main
from scripts.run_harness_cli import build_command, build_parser
from tests.model_endpoint_gate_fixtures import profile, transport, write_profiles


from scripts import run_model_endpoint_gate as script_wrapper


def test_source_wrapper_reexports_packaged_gate():
    assert script_wrapper.build_report is build_report
    assert script_wrapper.main is main


def run(tmp_path, rows, **kwargs):
    calls = []

    def tracked(*args):
        calls.append(args[0])
        return transport(*args)

    report = build_report(profile_artifact=str(write_profiles(tmp_path, rows)),
                          models=[], backends=[], transport=tracked, **kwargs)
    return report, calls


def test_exact_profile_disambiguates_same_model_and_backend(tmp_path):
    first = profile("ollama")
    second = {**first, "profile_id": "ollama-14b-other"}
    report, calls = run(tmp_path, [first, second], profile_id=second["profile_id"],
                        max_generation_calls=1)
    assert [row["profile_id"] for row in report["rows"]] == [second["profile_id"]]
    assert calls == ["GET", "POST"]
    assert report["generation_plan"] == {
        "profile_ids": [second["profile_id"]], "planned_max_generation_calls": 1,
        "max_generation_calls": 1, "admitted": True,
    }


@pytest.mark.parametrize("cap", [0, 1])
def test_budget_rejects_entire_plan_without_health_or_generation(tmp_path, cap):
    rows = [profile(), {**profile(), "profile_id": "other"}]
    report, calls = run(tmp_path, rows, max_generation_calls=cap)
    assert calls == [] and report["rows"] == []
    assert report["failure_class"] == "generation_call_budget_exceeded"
    assert report["verdict"] == "MODEL_ENDPOINT_GATE_FAIL"
    assert report["generation_plan"]["planned_max_generation_calls"] == 2
    assert report["generation_plan"]["admitted"] is False


@pytest.mark.parametrize(("rows", "wanted", "failure"), [
    ([profile()], "absent", "profile_id_not_found"),
    ([profile(), profile()], "serve-14b", "profile_id_ambiguous"),
    ([profile()], "SERVE-14B", "profile_id_not_found"),
    ([profile()], "", "invalid_profile_id"),
    ([profile()], True, "invalid_profile_id"),
])
def test_explicit_identity_fails_before_transport(tmp_path, rows, wanted, failure):
    report, calls = run(tmp_path, rows, profile_id=wanted)
    assert calls == [] and report["failure_class"] == failure


@pytest.mark.parametrize("cap", [-1, True, 1.5, "1"])
def test_invalid_budget_fails_before_transport(tmp_path, cap):
    report, calls = run(tmp_path, [profile()], max_generation_calls=cap)
    assert calls == [] and report["failure_class"] == "invalid_generation_call_budget"


def test_legacy_unbounded_multi_profile_selection_preserved(tmp_path):
    rows = [profile(), {**profile(), "profile_id": "other"}]
    report, calls = run(tmp_path, rows)
    assert len(report["rows"]) == 2 and calls == ["GET", "POST", "GET", "POST"]
    assert report["generation_plan"]["max_generation_calls"] is None


def test_cli_budget_failure_is_strict_and_receipted(tmp_path, capsys):
    path = write_profiles(tmp_path, [profile()])
    assert main(["--profile-artifact", str(path), "--profile-id", "serve-14b",
                 "--max-generation-calls", "0", "--strict-exit"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["rows"] == [] and report["generation_plan"]["admitted"] is False


def test_explicit_id_does_not_override_model_filter(tmp_path):
    calls = []
    report = build_report(profile_artifact=str(write_profiles(tmp_path, [profile()])),
                          models=["32B"], backends=[], profile_id="serve-14b",
                          transport=lambda *args: calls.append(args))
    assert calls == [] and report["failure_class"] == "no_profiles_selected"


def test_ambiguity_is_detected_before_backend_filter(tmp_path):
    rows = [profile(), {**profile("ollama"), "profile_id": "serve-14b"}]
    report = build_report(profile_artifact=str(write_profiles(tmp_path, rows)),
                          models=[], backends=["serve"], profile_id="serve-14b",
                          transport=lambda *args: pytest.fail("unexpected endpoint I/O"))
    assert report["failure_class"] == "profile_id_ambiguous"


@pytest.mark.parametrize("cap", [0, 1])
def test_front_controller_forwards_exact_identity_and_zero_budget(cap):
    args = build_parser().parse_args(["endpoint-gate", "--profile-id", "ollama-release-14b",
                                      "--max-generation-calls", str(cap)])
    command = build_command(args, repo_root=Path(__file__).resolve().parents[1])
    assert command[command.index("--profile-id") + 1] == "ollama-release-14b"
    assert command[command.index("--max-generation-calls") + 1] == str(cap)
