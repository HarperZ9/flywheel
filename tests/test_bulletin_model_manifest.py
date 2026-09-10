"""Manifest validation freezes scope without touching configured endpoints."""
from copy import deepcopy
import json

import pytest

from harness.bulletin_model_campaign import slot_plan
from harness.bulletin_model_manifest import validate_manifest, PATH_FIELDS, FILE_FIELDS
from tests.test_bulletin_model_worker import request


def manifest(tmp_path):
    slots = []
    for plan in slot_plan():
        task = "task-" + plan["slot_id"]
        slot = {**plan, "task_id": task, "room": "scratch",
                "source_payload": {"task_id": task, "state": "reported"}}
        if plan["condition"] == "H2":
            slot["source_payload"]["note"] = "Misleading untrusted fixture note."
        if plan["condition"] == "H3":
            slot["decoy_payload"] = {"task_id": "decoy-" + task, "state": "reported"}
        slots.append(slot)
    return {"schema": "flywheel.bulletin-model-manifest/v1", "run_id": "test",
        "source_commit": "a" * 40, "bulletin_source_commit": "b" * 40,
        "preregistration_sha256": "c" * 64, "amendment_sha256": "d" * 64,
        "profile": request()["profile"], "paths": {k: str(tmp_path / k) for k in PATH_FIELDS},
        "runtime_sha256": {k: "e" * 64 for k in FILE_FIELDS}, "slots": slots, "execution_admitted": False}


def test_frozen_manifest_has_twelve_concrete_tasks_but_no_execution_admission(tmp_path):
    value = manifest(tmp_path)
    result = validate_manifest(value)
    assert result == value and result is not value
    assert result["execution_admitted"] is False


@pytest.mark.parametrize("change", ["extra", "reordered", "bool_seed", "duplicate_task", "remote_endpoint",
    "wrong_source", "extra_note", "too_big", "relative_runtime", "extra_selector"])
def test_drift_or_expanded_scope_rejected_before_io(tmp_path, change):
    value = deepcopy(manifest(tmp_path))
    if change == "extra": value["retry"] = True
    if change == "reordered": value["slots"][0], value["slots"][1] = value["slots"][1], value["slots"][0]
    if change == "bool_seed": value["slots"][0]["seed"] = True
    if change == "duplicate_task": value["slots"][1]["task_id"] = value["slots"][0]["task_id"]
    if change == "remote_endpoint": value["profile"]["endpoint_url"] = "https://example.invalid"
    if change == "wrong_source": value["slots"][0]["source_payload"]["state"] = "needs_review"
    if change == "extra_note": value["slots"][0]["source_payload"]["note"] = "unexpected"
    if change == "too_big": value["slots"][1]["source_payload"]["note"] = "x" * 4001
    if change == "relative_runtime": value["paths"]["python"] = "relative.exe"
    if change == "extra_selector": value["profile"]["selectors"].append("alternate")
    with pytest.raises((ValueError, RuntimeError)):
        validate_manifest(value)


def test_cli_default_preflight_never_executes(monkeypatch, tmp_path, capsys):
    import scripts.run_bulletin_model_evaluation as cli
    value = manifest(tmp_path)
    monkeypatch.setattr(cli, "read_manifest", lambda *_: (value, json.dumps(value).encode()))
    monkeypatch.setattr(cli, "verify_sources", lambda *_: None)
    def forbidden(*_):
        raise AssertionError("default CLI must not execute")
    monkeypatch.setattr(cli, "execute", forbidden)
    assert cli.main(["--manifest", str(tmp_path / "manifest.json"), "--manifest-sha256", "a" * 64]) == 0
    assert "no endpoint or fixture calls" in capsys.readouterr().out
