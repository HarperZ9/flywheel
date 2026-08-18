import hashlib
import json
from datetime import datetime

import pytest

from harness.local_agent import OllamaBackend, ServeBackend
from scripts.run_model_endpoint_gate import _backend_for_profile, _ollama_identity, build_report, main


def profile(backend="serve", model="14B"):
    selector = "qwen:14b"
    row = {
        "profile_id": f"{backend}-{model.lower()}", "model": model, "model_key": model.lower(),
        "model_ref": "serve:expected" if backend == "serve" else f"ollama:{selector}",
        "backend": backend, "provider_role": "flywheel", "endpoint_url": "http://127.0.0.1:8765",
    }
    if backend == "ollama":
        row["selectors"] = [selector]
    return row


def write_profiles(tmp_path, rows):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"schema": "harness.model-endpoint-profiles/v1", "profiles": rows}), encoding="utf-8")
    return path


def transport(method, url, body, timeout):
    if url.endswith("/health"):
        return 200, {"ok": True, "model_ref": "serve:expected"}
    if url.endswith("/generate"):
        return 200, {"text": "active", "model_ref": "serve:expected", "seed": 0}
    if url.endswith("/api/tags"):
        return 200, {"models": [{"name": "qwen:14b", "digest": "sha256:abc"}]}
    if url.endswith("/api/chat"):
        return 200, {"message": {"content": "active"}, "model": "qwen:14b"}
    return 404, {}


def canonical_hash(row):
    encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@pytest.mark.parametrize("digest", [True, False, 0, 1, [], {}, "   "])
def test_ollama_identity_rejects_non_string_or_blank_digest(digest):
    observed, evidence = _ollama_identity(
        profile("ollama"), {"models": [{"name": "qwen:14b", "digest": digest}]})
    assert observed == "ollama:qwen:14b"
    assert evidence == ""


def test_ollama_identity_strips_string_digest():
    _, evidence = _ollama_identity(
        profile("ollama"), {"models": [{"name": "qwen:14b", "digest": " sha256:abc "}]})
    assert evidence == "sha256:abc"


def tag_transport(digest):
    def tagged(method, url, body, timeout):
        if url.endswith("/api/tags"):
            model = {"name": "qwen:14b"}
            if digest != "missing":
                model["digest"] = digest
            return 200, {"models": [model]}
        return transport(method, url, body, timeout)
    return tagged


@pytest.mark.parametrize("digest", [True, "   ", "missing"])
def test_ollama_report_fails_without_valid_digest(tmp_path, digest):
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [profile("ollama")])), models=[], backends=[],
        transport=tag_transport(digest), run_id="digest-run")
    row = report["rows"][0]
    assert row["health_ok"] is False and row["generation_attempted"] is False
    assert row["failure_class"] == "ollama_digest_missing"
    assert report["summary"]["failed_rows"] > 0
    assert report["verdict"] != "MODEL_ENDPOINT_GATE_PASS"


@pytest.mark.parametrize(("digest", "expected"), [
    (True, 1), ("   ", 1), ("missing", 1), ("sha256:abc", 0),
])
def test_strict_exit_tracks_ollama_digest_gate(tmp_path, monkeypatch, digest, expected):
    profiles = write_profiles(tmp_path, [profile("ollama")])
    monkeypatch.setattr(
        "scripts.run_model_endpoint_gate._backend_for_profile",
        lambda selected, *, timeout_seconds, transport=None: _backend_for_profile(
            selected, timeout_seconds=timeout_seconds, transport=tag_transport(digest)))
    assert main(["--profile-artifact", str(profiles), "--strict-exit"]) == expected


def test_backend_for_profile_preserves_defaults():
    serve = _backend_for_profile(profile(), timeout_seconds=12.0)
    ollama = _backend_for_profile(profile("ollama"), timeout_seconds=12.0)
    assert isinstance(serve, ServeBackend) and serve.timeout == 12.0
    assert isinstance(ollama, OllamaBackend) and ollama.model == "qwen:14b"


@pytest.mark.parametrize("backend", ["serve", "ollama"])
def test_gate_emits_exact_profile_identity_and_fresh_observation(tmp_path, backend):
    selected = profile(backend)
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [selected])), models=["14B"], backends=[],
        transport=transport, run_id="gate-run",
    )

    row = report["rows"][0]
    assert row["selected_profile_id"] == selected["profile_id"]
    assert row["profile_sha256"] == canonical_hash(selected)
    assert row["expected_model_ref"] == selected["model_ref"]
    assert row["observed_model_ref"] == selected["model_ref"]
    assert row["backend"] == backend
    assert row["health_ok"] is True and row["generation_ok"] is True
    assert row["failure_class"] == ""
    assert row["ollama_digest"] == ("sha256:abc" if backend == "ollama" else "")
    assert row["run_id"] == report["run_id"] == "gate-run"
    assert row["quality_score"] == 1.0 and row["response_sha256"] and row["receipt_hash"]
    assert datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0


def test_gate_preserves_failed_probe_identity(tmp_path):
    selected = profile("unsupported")
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [selected])), models=[], backends=[],
        transport=transport, run_id="failed-run",
    )
    row = report["rows"][0]
    assert row["failure_class"] == "unsupported_backend"
    assert row["profile_sha256"] == canonical_hash(selected)
    assert row["run_id"] == "failed-run"
    assert row["observed_at"].endswith("Z")
    assert row["quality_score"] == 0.0 and row["receipt_hash"]


@pytest.mark.parametrize(("health", "failure", "health_ok"), [
    ((404, {}), "wrong_service_or_path", False),
    ((200, {"ok": True, "model_ref": "serve:other"}), "health_model_ref_mismatch", True),
])
def test_gate_preserves_health_failure_classes(tmp_path, health, failure, health_ok):
    def failing_transport(method, url, body, timeout):
        return health if url.endswith("/health") else transport(method, url, body, timeout)

    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [profile()])), models=[], backends=[],
        transport=failing_transport,
    )
    row = report["rows"][0]
    assert row["health_ok"] is health_ok
    assert row["generation_attempted"] is False
    assert row["failure_class"] == failure


def test_gate_rejects_generation_model_reference_mismatch(tmp_path):
    def wrong_ref_transport(method, url, body, timeout):
        if url.endswith("/generate"):
            return 200, {"text": "active", "model_ref": "serve:other", "seed": 0}
        return transport(method, url, body, timeout)

    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [profile()])), models=[], backends=[],
        transport=wrong_ref_transport,
    )
    row = report["rows"][0]
    assert row["generation_ok"] is False
    assert row["failure_class"] == "model_ref_mismatch"
    assert row["observed_model_ref"] == "serve:other"


def test_gate_main_writes_run_identity(tmp_path):
    profiles = write_profiles(tmp_path, [profile("unsupported")])
    out = tmp_path / "gate.json"
    rc = main(["--profile-artifact", str(profiles), "--out", str(out), "--run-id", "cli-run"])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["run_id"] == "cli-run"
    assert report["rows"][0]["run_id"] == "cli-run"


def test_gate_main_strict_exit_rejects_failure(tmp_path):
    profiles = write_profiles(tmp_path, [profile("unsupported")])
    assert main(["--profile-artifact", str(profiles), "--strict-exit"]) == 1


@pytest.mark.parametrize(("rows", "models"), [([], []), ([profile()], ["32B"])])
def test_zero_selected_profiles_is_an_explicit_failed_report(tmp_path, rows, models):
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, rows)), models=models, backends=[],
        transport=transport, run_id="empty-run",
    )
    assert report["summary"]["profiles_selected"] == 0
    assert report["summary"]["failed_rows"] == 1
    assert report["failure_class"] == "no_profiles_selected"
    assert report["verdict"] == "MODEL_ENDPOINT_GATE_FAIL"


@pytest.mark.parametrize(("rows", "extra"), [
    ([], []),
    ([profile()], ["--models", "32B"]),
])
def test_strict_exit_rejects_zero_selected_profiles(tmp_path, rows, extra):
    profiles = write_profiles(tmp_path, rows)
    assert main(["--profile-artifact", str(profiles), "--strict-exit", *extra]) == 1
