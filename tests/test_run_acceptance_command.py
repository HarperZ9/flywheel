from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from scripts import run_acceptance_command as recorder


REPO_ROOT = Path(__file__).resolve().parents[1]


def _base_args(tmp_path: Path, name: str) -> tuple[list[str], Path]:
    evidence_root = tmp_path / "public-evidence"
    artifact_root = evidence_root / "run-001"
    args = [
        "--evidence-root",
        str(evidence_root),
        "--artifact-root",
        str(artifact_root),
        "--receipt-name",
        name,
        "--cwd",
        str(REPO_ROOT),
    ]
    return args, artifact_root / name


def _read_tree(receipt_dir: Path) -> tuple[dict, bytes, bytes]:
    receipt = json.loads((receipt_dir / "receipt.json").read_text(encoding="utf-8"))
    stdout = (receipt_dir / receipt["stdout"]["path"]).read_bytes()
    stderr = (receipt_dir / receipt["stderr"]["path"]).read_bytes()
    return receipt, stdout, stderr


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), *args], text=True, encoding="utf-8"
    ).strip()


def test_json_argv_records_success_and_repository_identity(tmp_path):
    args, receipt_dir = _base_args(tmp_path, "json-success")
    argv = [
        sys.executable,
        "-c",
        "import sys; print(sys.argv[1]); print('warn', file=sys.stderr)",
        "literal && never-run",
    ]

    exit_code = recorder.main([*args, "--argv-json", json.dumps(argv)])
    receipt, stdout, stderr = _read_tree(receipt_dir)

    assert exit_code == 0
    assert receipt["schema"] == "flywheel.acceptance-command/v1"
    assert receipt["command"] == {"argv": argv, "shell": False}
    assert receipt["cwd"] == "."
    assert receipt["source_repository"] == REPO_ROOT.name
    assert receipt["source_head"] == _git("rev-parse", "HEAD")
    assert receipt["exit_code"] == 0
    assert stdout.decode().splitlines() == ["literal && never-run"]
    assert stderr.decode().splitlines() == ["warn"]
    assert receipt["stdout"]["sha256"] == hashlib.sha256(stdout).hexdigest()
    assert receipt["stderr"]["sha256"] == hashlib.sha256(stderr).hexdigest()
    assert receipt["stdout"]["bytes"] == len(stdout)
    assert receipt["stderr"]["bytes"] == len(stderr)
    assert receipt["started_utc"].endswith("Z")
    assert receipt["ended_utc"].endswith("Z")
    assert datetime.fromisoformat(receipt["ended_utc"].replace("Z", "+00:00")) >= datetime.fromisoformat(
        receipt["started_utc"].replace("Z", "+00:00")
    )
    assert receipt["duration_ms"] >= 0
    assert receipt["does_not_prove"]


def test_repeated_args_record_nonzero_child_and_preserve_receipt(tmp_path):
    args, receipt_dir = _base_args(tmp_path, "repeated-failure")

    exit_code = recorder.main(
        [
            *args,
            f"--arg={sys.executable}",
            "--arg=-c",
            "--arg=import sys; print('failed'); sys.exit(7)",
        ]
    )
    receipt, stdout, _stderr = _read_tree(receipt_dir)

    assert exit_code == 7
    assert receipt["exit_code"] == 7
    assert receipt["command"]["argv"][1:] == [
        "-c",
        "import sys; print('failed'); sys.exit(7)",
    ]
    assert stdout.decode().splitlines() == ["failed"]


def test_environment_receipt_has_names_only_and_redacts_secret_values(tmp_path, monkeypatch):
    secret = "recorder-canary-value-5e6b7e7c"
    monkeypatch.setenv("RECORDER_TEST_TOKEN", secret)
    args, receipt_dir = _base_args(tmp_path, "redacted")
    argv = [
        sys.executable,
        "-c",
        "import os,sys; print(os.environ['RECORDER_TEST_TOKEN']); print(sys.argv[1], file=sys.stderr)",
        secret,
    ]

    assert recorder.main(
        [*args, "--secret-env", "RECORDER_TEST_TOKEN", "--argv-json", json.dumps(argv)]
    ) == 0
    receipt, stdout, stderr = _read_tree(receipt_dir)
    serialized = json.dumps(receipt, sort_keys=True).encode() + stdout + stderr

    assert secret.encode() not in serialized
    assert stdout.decode().splitlines() == ["<redacted>"]
    assert stderr.decode().splitlines() == ["<redacted>"]
    assert receipt["command"]["argv"][-1] == "<redacted>"
    assert "RECORDER_TEST_TOKEN" in receipt["environment_variable_names"]
    assert "environment" not in receipt
    assert receipt["redaction"]["secret_environment_names"] == ["RECORDER_TEST_TOKEN"]
    assert receipt["redaction"]["values_serialized"] is False


def test_secret_child_flag_value_is_redacted_from_argv_and_output(tmp_path):
    secret = "argument-only-secret-6f98a"
    args, receipt_dir = _base_args(tmp_path, "argument-secret")
    argv = [sys.executable, "-c", "import sys; print(sys.argv[2])", "--token", secret]

    assert recorder.main([*args, "--argv-json", json.dumps(argv)]) == 0
    receipt, stdout, stderr = _read_tree(receipt_dir)
    serialized = json.dumps(receipt, sort_keys=True).encode() + stdout + stderr

    assert secret.encode() not in serialized
    assert receipt["command"]["argv"][-2:] == ["--token", "<redacted>"]
    assert stdout.decode().splitlines() == ["<redacted>"]


def test_streams_are_bounded_and_report_observed_size(tmp_path):
    args, receipt_dir = _base_args(tmp_path, "bounded")
    argv = [sys.executable, "-c", "import sys; print('x'*800); print('y'*700, file=sys.stderr)"]

    assert recorder.main(
        [*args, "--max-output-bytes", "128", "--argv-json", json.dumps(argv)]
    ) == 0
    receipt, stdout, stderr = _read_tree(receipt_dir)

    assert len(stdout) <= 128
    assert len(stderr) <= 128
    assert receipt["stdout"]["truncated"] is True
    assert receipt["stderr"]["truncated"] is True
    assert receipt["stdout"]["observed_bytes"] > receipt["stdout"]["bytes"]
    assert receipt["stderr"]["observed_bytes"] > receipt["stderr"]["bytes"]
    assert receipt["output_limit_bytes"] == 128


def test_artifact_root_outside_evidence_root_is_refused_before_child_runs(tmp_path):
    evidence_root = tmp_path / "public-evidence"
    artifact_root = tmp_path / "outside"
    marker = tmp_path / "child-ran"
    argv = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"]

    exit_code = recorder.main(
        [
            "--evidence-root",
            str(evidence_root),
            "--artifact-root",
            str(artifact_root),
            "--receipt-name",
            "escape",
            "--cwd",
            str(REPO_ROOT),
            "--argv-json",
            json.dumps(argv),
        ]
    )

    assert exit_code == 2
    assert not marker.exists()
    assert not artifact_root.exists()


def test_receipt_name_cannot_escape_artifact_root(tmp_path):
    args, _receipt_dir = _base_args(tmp_path, "unused")
    name_index = args.index("--receipt-name") + 1
    args[name_index] = "../escape"

    assert recorder.main([*args, "--argv-json", json.dumps([sys.executable, "-c", "pass"])]) == 2
    assert not (tmp_path / "public-evidence" / "escape").exists()


def test_existing_receipt_tree_is_never_overwritten(tmp_path):
    args, receipt_dir = _base_args(tmp_path, "immutable")
    argv = [sys.executable, "-c", "print('first')"]
    assert recorder.main([*args, "--argv-json", json.dumps(argv)]) == 0

    assert recorder.main([*args, "--argv-json", json.dumps([sys.executable, "-c", "print('second')"])]) == 2
    _receipt, stdout, _stderr = _read_tree(receipt_dir)
    assert stdout.decode().splitlines() == ["first"]


def test_git_commits_fixture_streams_as_receipt_hashed_bytes(tmp_path):
    clone = tmp_path / "fixture-commit"
    clone.mkdir()
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "core.autocrlf", "true"], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "user.email", "fixture@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "user.name", "Fixture Test"], check=True)
    (clone / ".gitattributes").write_bytes((REPO_ROOT / ".gitattributes").read_bytes())
    relative_root = Path("artifacts/closeout/FW-2026-08-02-CLOSEOUT/task-0-bootstrap")
    fixture_paths: list[Path] = []
    for name in ("passing-fixture", "failing-fixture"):
        source = REPO_ROOT / relative_root / name
        target = clone / relative_root / name
        target.mkdir(parents=True)
        for filename in ("receipt.json", "stdout.txt", "stderr.txt"):
            (target / filename).write_bytes((source / filename).read_bytes())
        fixture_paths.append(relative_root / name)
    subprocess.run(["git", "-C", str(clone), "add", "."], check=True)
    subprocess.run(["git", "-C", str(clone), "commit", "-q", "-m", "fixture"], check=True)

    for fixture_path in fixture_paths:
        receipt = json.loads((clone / fixture_path / "receipt.json").read_text(encoding="utf-8"))
        for stream in ("stdout", "stderr"):
            relative_stream = (fixture_path / receipt[stream]["path"]).as_posix()
            committed = subprocess.check_output(["git", "-C", str(clone), "show", f"HEAD:{relative_stream}"])
            expected = (REPO_ROOT / relative_stream).read_bytes()
            assert committed == expected
            assert len(committed) == receipt[stream]["bytes"]
            assert hashlib.sha256(committed).hexdigest() == receipt[stream]["sha256"]


def test_git_diff_check_accepts_exact_receipt_stream_bytes(tmp_path):
    clone = tmp_path / "fixture-diff"
    stream = clone / "artifacts/closeout/run/receipt/stdout.txt"
    stream.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "core.autocrlf", "true"], check=True)
    (clone / ".gitattributes").write_bytes((REPO_ROOT / ".gitattributes").read_bytes())
    stream.write_bytes(b"captured output\r\n")
    subprocess.run(["git", "-C", str(clone), "add", "."], check=True)

    result = subprocess.run(
        ["git", "-C", str(clone), "diff", "--cached", "--check"],
        text=True,
        encoding="utf-8",
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
