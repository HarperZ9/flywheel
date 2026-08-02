from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

from scripts import run_acceptance_command as recorder


REPO_ROOT = Path(__file__).resolve().parents[1]


def _invoke(
    tmp_path: Path,
    name: str,
    argv: list[str],
    *extra: str,
) -> tuple[int, Path, Path]:
    evidence_root = tmp_path / "evidence"
    artifact_root = evidence_root / "run"
    args = [
        "--evidence-root",
        str(evidence_root),
        "--artifact-root",
        str(artifact_root),
        "--receipt-name",
        name,
        "--cwd",
        str(REPO_ROOT),
        *extra,
        "--argv-json",
        json.dumps(argv),
    ]
    try:
        result = recorder.main(args)
    except SystemExit as exc:
        result = int(exc.code)
    return result, artifact_root / name, artifact_root


def _receipt(receipt_dir: Path) -> dict:
    return json.loads((receipt_dir / "receipt.json").read_text(encoding="utf-8"))


def test_invalid_utf8_bytes_survive_secret_redaction(tmp_path, monkeypatch):
    monkeypatch.setenv("BINARY_TEST_TOKEN", "secret-canary")
    code = (
        "import os,sys; "
        "sys.stdout.buffer.write(b'\\xff\\xfe'+os.environ['BINARY_TEST_TOKEN'].encode()+b'\\x80'); "
        "sys.stderr.buffer.write(b'\\x81tail')"
    )

    result, receipt_dir, _root = _invoke(
        tmp_path,
        "binary-streams",
        [sys.executable, "-c", code],
        "--secret-env",
        "BINARY_TEST_TOKEN",
    )
    receipt = _receipt(receipt_dir)
    stdout = (receipt_dir / "stdout.txt").read_bytes()
    stderr = (receipt_dir / "stderr.txt").read_bytes()

    assert result == 0
    assert stdout == b"\xff\xfe<redacted>\x80"
    assert stderr == b"\x81tail"
    assert hashlib.sha256(stdout).hexdigest() == receipt["stdout"]["sha256"]
    assert hashlib.sha256(stderr).hexdigest() == receipt["stderr"]["sha256"]


@pytest.mark.parametrize(("secret", "name"), [("1", "one-1"), ("123", "numeric-123")])
def test_low_entropy_secret_does_not_match_unrelated_receipt_metadata(tmp_path, monkeypatch, secret, name):
    monkeypatch.setenv("LOW_ENTROPY_TOKEN", secret)
    code = "import os; print(os.environ['LOW_ENTROPY_TOKEN'])"

    result, receipt_dir, _root = _invoke(
        tmp_path,
        name,
        [sys.executable, "-c", code],
        "--secret-env",
        "LOW_ENTROPY_TOKEN",
    )
    receipt = _receipt(receipt_dir)

    assert result == 0
    assert (receipt_dir / "stdout.txt").read_bytes().strip() == b"<redacted>"
    assert receipt["redaction"]["replacement_count"] >= 1
    assert receipt["receipt_name"] == name


def test_nul_argv_rejection_leaves_name_rerunnable(tmp_path):
    result, receipt_dir, artifact_root = _invoke(
        tmp_path, "rerunnable", [sys.executable, "-c", "pass", "bad\x00arg"]
    )

    assert result == 2
    assert not receipt_dir.exists()
    assert not list(artifact_root.glob(".rerunnable.tmp-*"))

    retry, retry_dir, _root = _invoke(tmp_path, "rerunnable", [sys.executable, "-c", "print('ok')"])
    assert retry == 0
    assert _receipt(retry_dir)["outcome"] == "EXITED"


def test_missing_executable_gets_complete_typed_launch_receipt(tmp_path):
    result, receipt_dir, artifact_root = _invoke(
        tmp_path, "launch-failure", ["missing-acceptance-command-744dca"]
    )
    receipt = _receipt(receipt_dir)

    assert result == 127
    assert receipt["outcome"] == "LAUNCH_FAILED"
    assert receipt["launch_error"] is True
    assert receipt["timed_out"] is False
    assert (receipt_dir / "stdout.txt").exists()
    assert (receipt_dir / "stderr.txt").exists()
    assert not list(artifact_root.glob(".launch-failure.tmp-*"))


def test_stale_incomplete_stage_does_not_poison_rerun(tmp_path):
    artifact_root = tmp_path / "evidence" / "run"
    stale = artifact_root / ".interrupted.tmp-stale"
    stale.mkdir(parents=True)
    (stale / "partial").write_text("incomplete", encoding="utf-8")

    result, receipt_dir, _root = _invoke(tmp_path, "interrupted", [sys.executable, "-c", "pass"])

    assert result == 0
    assert _receipt(receipt_dir)["outcome"] == "EXITED"
    assert stale.exists()
    assert not [path for path in artifact_root.glob(".interrupted.tmp-*") if path != stale]


def test_hanging_child_times_out_with_typed_receipt(tmp_path):
    started = time.monotonic()
    result, receipt_dir, _root = _invoke(
        tmp_path,
        "timeout",
        [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(2)"],
        "--timeout-seconds",
        "0.15",
    )
    elapsed = time.monotonic() - started
    receipt = _receipt(receipt_dir)

    assert result == 124
    assert elapsed < 1.5
    assert receipt["outcome"] == "TIMED_OUT"
    assert receipt["timed_out"] is True
    assert receipt["timeout_seconds"] == 0.15
    assert b"started" in (receipt_dir / "stdout.txt").read_bytes()


def test_descendant_held_pipe_is_terminated_at_deadline(tmp_path):
    marker = tmp_path / "descendant-survived"
    descendant = f"import time; from pathlib import Path; time.sleep(0.7); Path({str(marker)!r}).touch()"
    parent = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c',{descendant!r}], stdout=sys.stdout, stderr=sys.stderr, close_fds=False); "
        "print('parent exited', flush=True)"
    )
    started = time.monotonic()
    result, receipt_dir, _root = _invoke(
        tmp_path,
        "descendant-timeout",
        [sys.executable, "-c", parent],
        "--timeout-seconds",
        "0.15",
    )
    elapsed = time.monotonic() - started
    time.sleep(0.8)

    assert result == 124
    assert elapsed < 1.5
    assert _receipt(receipt_dir)["outcome"] == "TIMED_OUT"
    assert not marker.exists()
