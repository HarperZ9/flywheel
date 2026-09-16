from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

from harness import standards_cli

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "standards" / "synthetic-administrative-profile.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "harness.standards_cli", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_validate_command_emits_stdout_json_success() -> None:
    proc = run_cli("validate", str(FIXTURE))

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["verdict"] == "VALID"
    assert payload["schema"] == "flywheel.standards-profile-validation/v1"
    assert proc.stderr == ""


def test_assess_command_requires_context_and_as_of() -> None:
    missing_context = run_cli("assess", str(FIXTURE), "--as-of", "2026-09-16")
    assert missing_context.returncode == 2
    assert "usage:" in missing_context.stderr


def test_json_loader_rejects_duplicate_keys_and_non_finite_numbers(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
    proc = run_cli("validate", str(duplicate))
    assert proc.returncode == 2
    assert "duplicate key" in proc.stderr

    non_finite = tmp_path / "nan.json"
    non_finite.write_text('{"schema": NaN}', encoding="utf-8")
    proc = run_cli("validate", str(non_finite))
    assert proc.returncode == 2
    assert "non-finite" in proc.stderr


def test_assess_source_stale_result_uses_unverifiable_exit(tmp_path: Path) -> None:
    profile = json.loads(FIXTURE.read_text(encoding="utf-8"))
    profile["effective"]["effective_from"] = "2026-09-01"
    profile["effective"]["effective_to"] = "2026-09-15"
    profile_path = tmp_path / "stale.json"
    context_path = tmp_path / "context.json"
    write_json(profile_path, profile)
    write_json(context_path, {
        "subject_id": "synthetic-office-workflow",
        "jurisdiction": "SYNTHETIC",
        "operator_role": "operator",
        "covered_use": "administrative_review",
    })

    proc = run_cli(
        "assess", str(profile_path), str(context_path), "--as-of", "2026-09-16")

    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["source"]["status"] == "expired"
    assert payload["requirements"][0]["applicability"] == "needs_review"


def test_unknown_command_uses_usage_exit() -> None:
    proc = run_cli("approve", str(FIXTURE))

    assert proc.returncode == 2
    assert "unknown command" in proc.stderr


def test_cli_main_does_not_open_network_for_source_urls(
    tmp_path: Path, monkeypatch
) -> None:
    profile = json.loads(FIXTURE.read_text(encoding="utf-8"))
    profile["provenance"]["source_url"] = "https://example.invalid/source"
    profile_path = tmp_path / "profile.json"
    write_json(profile_path, profile)

    def blocked_socket(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("network was opened")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert standards_cli.main(["validate", str(profile_path)]) == 0
