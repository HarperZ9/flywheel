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

# How long the hanging child sleeps. A run that outlasts this waited for the
# child instead of killing it, which is the failure the test exists to catch.
CHILD_SLEEP_SECONDS = 5.0

# Headroom over one measured invocation, for scheduling noise on a shared
# runner. Generous on purpose: a promptness check that fails under load is
# reporting the runner, not the code.
PROMPTNESS_SLACK_SECONDS = 1.5

# How long a descendant holding the pipe sleeps before it would touch its
# marker. Comfortably past the 1.0s deadline, so it is alive when the kill
# lands and the marker means what the test says it means.
DESCENDANT_SLEEP_SECONDS = 2.0


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


def _harness_cost(tmp_path: Path) -> float:
    """What one _invoke costs on this machine with nothing to wait for.

    The promptness assertions below are about the deadline, not about how
    fast the runner is. A fixed ceiling conflates the two, and at 2.5s this
    file failed on a loaded Windows CI runner that took 3.46s to do work it
    does correctly. Measuring the harness's own spawn-and-capture cost here,
    in the same process on the same machine, keeps the checks falsifiable
    without pinning them to one machine's speed.
    """
    started = time.monotonic()
    _invoke(tmp_path / "cost", "cost", [sys.executable, "-c", "pass"])
    return time.monotonic() - started


def test_hanging_child_times_out_with_typed_receipt(tmp_path):
    # The timeout budget must clear interpreter STARTUP, not just the print.
    # At 0.15s this asserted the impossible on any platform where spawning
    # CPython costs more than that (~0.19s on Windows, well under it on the
    # Linux CI runners), so the child was killed before it could write and
    # the "partial output survives" assertion failed for a reason that had
    # nothing to do with capture. 1.0s against a 5s sleep keeps every
    # property this test exists to prove -- killed, typed TIMED_OUT receipt,
    # exit 124, promptness, and the output written before the kill -- with
    # room for a slow spawn. Do not tighten it back toward startup cost.
    cost = _harness_cost(tmp_path)
    started = time.monotonic()
    result, receipt_dir, _root = _invoke(
        tmp_path,
        "timeout",
        [sys.executable, "-c",
         f"import time; print('started', flush=True); time.sleep({CHILD_SLEEP_SECONDS})"],
        "--timeout-seconds",
        "1.0",
    )
    elapsed = time.monotonic() - started
    receipt = _receipt(receipt_dir)

    assert result == 124
    # Two ceilings, neither of them a guess about machine speed. The child
    # sleeps 5s, so finishing under that at all proves it was killed rather
    # than waited out; finishing near the 1.0s deadline plus what this
    # machine charges for one invocation proves the kill was prompt.
    assert elapsed < CHILD_SLEEP_SECONDS
    assert elapsed < cost + 1.0 + PROMPTNESS_SLACK_SECONDS
    assert receipt["outcome"] == "TIMED_OUT"
    assert receipt["timed_out"] is True
    assert receipt["timeout_seconds"] == 1.0
    assert b"started" in (receipt_dir / "stdout.txt").read_bytes()


def test_descendant_held_pipe_is_terminated_at_deadline(tmp_path):
    # An absent marker proves the descendant was terminated only if the
    # descendant was ever started. At the 0.15s deadline this used, that was
    # a race against CPython startup: win it and the test means what it says,
    # lose it and the parent dies before its Popen, the marker is absent for
    # a reason this test is not about, and the check passes without
    # exercising descendant termination at all. Which way the race goes was
    # never asserted. Now the parent's own line is required as evidence that
    # it got past the spawn, and the deadline is wide enough to reach it.
    marker = tmp_path / "descendant-survived"
    descendant = (f"import time; from pathlib import Path; "
                  f"time.sleep({DESCENDANT_SLEEP_SECONDS}); Path({str(marker)!r}).touch()")
    parent = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c',{descendant!r}], stdout=sys.stdout, stderr=sys.stderr, close_fds=False); "
        "print('parent exited', flush=True)"
    )
    cost = _harness_cost(tmp_path)
    started = time.monotonic()
    result, receipt_dir, _root = _invoke(
        tmp_path,
        "descendant-timeout",
        [sys.executable, "-c", parent],
        "--timeout-seconds",
        "1.0",
    )
    elapsed = time.monotonic() - started
    # Long enough that a descendant left alive would have touched by now.
    time.sleep(DESCENDANT_SLEEP_SECONDS)

    assert result == 124
    # The parent reached its Popen, so there was a descendant to terminate.
    assert b"parent exited" in (receipt_dir / "stdout.txt").read_bytes()
    # Two invocations' worth of spawning: the harness's own, and the parent's.
    assert elapsed < 2 * cost + 1.0 + PROMPTNESS_SLACK_SECONDS
    assert _receipt(receipt_dir)["outcome"] == "TIMED_OUT"
    assert not marker.exists()
