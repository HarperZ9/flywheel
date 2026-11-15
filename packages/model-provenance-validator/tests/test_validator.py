from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

from model_provenance_validator.packet import validate_proof_surface_packet
from model_provenance_validator.validator import load_envelope, load_schema, validate_envelope


FIXTURES = Path(__file__).parent / "fixtures"


def _subprocess_env() -> dict[str, str]:
    """Env for spawned CLI runs: this repo's src plus any inherited PYTHONPATH.

    The CLI now imports the shared ``proof_surface`` package, so the child
    interpreter must be able to resolve it the same way the parent run can
    (via an installed ``proof-surface>=0.1`` dependency or an inherited
    PYTHONPATH). We prepend this repo's ``src`` and preserve the rest.
    """
    env = os.environ.copy()
    src = str(Path(__file__).parents[1] / "src")
    inherited = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(part for part in (src, inherited) if part)
    return env


def test_valid_envelope_passes() -> None:
    errors = validate_envelope(load_envelope(FIXTURES / "valid.json"), load_schema())

    assert errors == []


def test_invalid_envelope_reports_specific_errors() -> None:
    errors = validate_envelope(load_envelope(FIXTURES / "invalid.json"), load_schema())
    messages = {(error.path, error.message) for error in errors}

    assert ("$.subject", "expected non-empty string") in messages
    assert any(error.path == "$.references" for error in errors)
    assert any(error.path == "$.source.kind" for error in errors)
    assert ("$.validation.extra", "unexpected field") in messages


def test_retrieved_at_requires_iso_date_shape() -> None:
    envelope = load_envelope(FIXTURES / "valid.json")
    envelope["references"][0]["retrieved_at"] = "June 13, 2026"

    errors = validate_envelope(envelope, load_schema())
    messages = {(error.path, error.message) for error in errors}

    assert (
        "$.references[0].retrieved_at",
        "expected string matching pattern '\\\\d{4}-\\\\d{2}-\\\\d{2}'",
    ) in messages


def test_retrieved_at_requires_calendar_date() -> None:
    envelope = load_envelope(FIXTURES / "valid.json")
    envelope["references"][0]["retrieved_at"] = "2026-99-99"

    errors = validate_envelope(envelope, load_schema())
    messages = {(error.path, error.message) for error in errors}

    assert (
        "$.references[0].retrieved_at",
        "expected valid calendar date",
    ) in messages


def test_invalid_values_are_redacted_in_errors() -> None:
    envelope = load_envelope(FIXTURES / "valid.json")
    synthetic = "ghp_" + ("A" * 36)
    envelope["source"]["kind"] = f"token={synthetic}"

    errors = validate_envelope(envelope, load_schema())
    rendered = "\n".join(error.message for error in errors)

    assert "ghp_" not in rendered
    assert "<redacted>" in rendered


def test_module_cli_returns_nonzero_for_invalid_envelope() -> None:
    env = _subprocess_env()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "model_provenance_validator",
            str(FIXTURES / "invalid.json"),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "invalid" in result.stdout
    assert str(FIXTURES) not in result.stdout


def test_valid_proof_surface_packet_passes_validation() -> None:
    packet = {
        "proof_surface_version": "0.1",
        "packet_id": "model-provenance-validator-batch",
        "surface": "model provenance validation",
        "status": "ready",
        "claims": [
            {
                "claim": "Model/reference claims carry provenance envelopes.",
                "evidence": "total envelopes=1",
            }
        ],
        "checks": [
            {
                "tool": "model-provenance-validator",
                "status": "pass",
                "summary": "valid=1, invalid=0, errors=0",
            }
        ],
        "action_items": [],
    }

    assert validate_proof_surface_packet(packet) == []


def test_empty_claims_and_checks_are_invalid() -> None:
    packet = {
        "proof_surface_version": "0.1",
        "packet_id": "empty",
        "surface": "model provenance validation",
        "status": "unknown",
        "claims": [],
        "checks": [],
        "action_items": [],
    }

    issues = set(validate_proof_surface_packet(packet))

    assert "$.claims: expected at least 1 item(s)" in issues
    assert "$.checks: expected at least 1 item(s)" in issues


def test_module_cli_emits_proof_packet_for_valid_envelope() -> None:
    env = _subprocess_env()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "model_provenance_validator",
            str(FIXTURES / "valid.json"),
            "--proof-packet",
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "proof_surface_version" in result.stdout
