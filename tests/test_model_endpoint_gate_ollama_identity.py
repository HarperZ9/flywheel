"""What the gate decides about an Ollama model's name and digest.

Split out of test_model_endpoint_gate.py on 2026-09-04: two branches each added
cases here and the merged file crossed the 300-line gate, which no new file may
join. The other half checks what the report says.
"""
import pytest

from harness.local_agent import OllamaBackend
from scripts.run_model_endpoint_gate import _backend_for_profile, _ollama_identity, build_report, main
from tests.model_endpoint_gate_fixtures import profile, transport, write_profiles


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


DIGEST_HEX = "7ff88ed3fd95eac7e79cb38a0a5ee3db39b7103a09d5a51d75fcda908522f6d8"


def released_profile(selector, expected_digest):
    row = profile("ollama")
    row.update(selectors=[selector], model_ref=f"ollama:{selector}", expected_ollama_digest=expected_digest)
    return row


def released_transport(name, digest):
    """An Ollama daemon that answers /api/tags the way the real one does."""
    def answer(method, url, body, timeout):
        if url.endswith("/api/tags"):
            return 200, {"models": [{"name": name, "model": name, "digest": digest}]}
        if url.endswith("/api/chat"):
            return 200, {"message": {"content": "active"}, "model": name.split(":")[0]}
        return transport(method, url, body, timeout)
    return answer


def test_untagged_selector_matches_the_latest_tag_ollama_reports(tmp_path):
    """A pulled model read as absent, reproduced.

    `ollama create name` registers `name:latest`, and /api/tags never omits the
    tag. A profile selector written without one therefore matched nothing, and
    both local arms recorded an unavailable endpoint while the model was loaded
    and answering.
    """
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [released_profile("flywheel-local-coder-14b", DIGEST_HEX)])),
        models=[], backends=[],
        transport=released_transport("flywheel-local-coder-14b:latest", DIGEST_HEX), run_id="tag-run")
    row = report["rows"][0]
    assert row["failure_class"] == "", row["failure_class"]
    assert row["health_ok"] is True and row["generation_ok"] is True
    assert row["ollama_digest"] == DIGEST_HEX


@pytest.mark.parametrize("recorded,reported", [
    (f"sha256:{DIGEST_HEX}", DIGEST_HEX),
    (DIGEST_HEX, f"sha256:{DIGEST_HEX}"),
    (f"sha256:{DIGEST_HEX}", f"SHA256:{DIGEST_HEX.upper()}"),
])
def test_digest_check_compares_the_value_not_the_spelling(tmp_path, recorded, reported):
    """The sealed provenance record and the daemon spell one digest two ways."""
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [released_profile("flywheel-local-coder-14b", recorded)])),
        models=[], backends=[],
        transport=released_transport("flywheel-local-coder-14b:latest", reported), run_id="digest-spelling")
    assert report["rows"][0]["failure_class"] == ""


def test_digest_check_still_rejects_a_different_manifest(tmp_path):
    """Normalizing the prefix must not make two different digests compare equal."""
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [released_profile("flywheel-local-coder-14b", f"sha256:{DIGEST_HEX}")])),
        models=[], backends=[],
        transport=released_transport("flywheel-local-coder-14b:latest", "b" * 64), run_id="digest-other")
    assert report["rows"][0]["failure_class"] == "ollama_digest_mismatch"


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


def live_daemon_transport(method, url, body, timeout):
    """What a real ollama daemon answered on 2026-09-03, which is not what the
    fixtures above assume. /api/tags spells the implicit `latest` tag out even
    when the profile pins the model without one, and returns the digest as bare
    hex with no `sha256:` prefix. The fixtures use an exact name and a prefixed
    digest, so neither detail was exercised, and both refused a correctly
    installed model in the head-to-head.

    The two endpoints do not agree with each other: /api/chat echoes the model
    string back exactly as it was sent, tag and all, so the strict comparison in
    OllamaBackend is right and only the /api/tags side needed resolving. Both
    behaviours were checked against a running daemon."""
    if url.endswith("/api/tags"):
        return 200, {"models": [{"name": "flywheel-local-coder-14b:latest", "digest": "abc"}]}
    if url.endswith("/api/chat"):
        return 200, {"message": {"content": "active"}, "model": "flywheel-local-coder-14b"}
    return transport(method, url, body, timeout)


def untagged_profile():
    """A profile pinning a model without a tag, which is how the shipped local
    profiles reference the release weights."""
    row = profile("ollama")
    row["selectors"] = ["flywheel-local-coder-14b"]
    row["model_ref"] = "ollama:flywheel-local-coder-14b"
    return row


def test_a_live_daemons_tag_and_bare_digest_admit_the_model(tmp_path):
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [untagged_profile()])), models=[], backends=[],
        transport=live_daemon_transport, run_id="digest-run")
    row = report["rows"][0]
    assert row["health_ok"] is True, row.get("failure_class")
    assert row["failure_class"] == ""
    # The receipt keeps the digest the daemon actually stated, unrewritten. The
    # comparison normalizes; the record of what was observed does not.
    assert row["ollama_digest"] == "abc"
    assert row["health_model_ref"] == "ollama:flywheel-local-coder-14b:latest"


def test_a_tagged_reference_still_has_to_match_that_tag(tmp_path):
    """Resolving the implicit tag is not permission to accept another one. A
    profile that names `qwen:14b` must not admit a daemon serving `:latest`."""
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [profile("ollama")])), models=[], backends=[],
        transport=live_daemon_transport, run_id="digest-run")
    assert report["rows"][0]["failure_class"] == "ollama_digest_missing"


def test_ollama_report_fails_when_observed_digest_differs_from_profile(tmp_path):
    report = build_report(
        profile_artifact=str(write_profiles(tmp_path, [profile("ollama")])), models=[], backends=[],
        transport=tag_transport("sha256:other"), run_id="digest-run")
    row = report["rows"][0]
    assert row["expected_ollama_digest"] == "sha256:abc"
    assert row["ollama_digest"] == "sha256:other"
    assert row["failure_class"] == "ollama_digest_mismatch"
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
