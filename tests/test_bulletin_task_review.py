"""The portable check uses existing Journey definitions and safe publication."""
import pytest
import json
import subprocess
import sys
from pathlib import Path

from harness.bulletin_task_review import build_review, write_review
from harness.journey_projection import reduce_events
from harness.private_artifact_fs import PrivateArtifactError
from test_bulletin_task_contract import fixture


def test_journey_is_valid_and_null_coverage_stays_visible():
    c, o = fixture()
    review = build_review(c, o)
    p = reduce_events(review["journey_events"])
    assert p["checks"][0]["verdict"] == "PASS"
    assert p["checks"][0]["denominator"] == 1
    assert "native_host_actions_unobserved" in review["result"]["coverage_gaps"]


def test_conflicting_artifact_cannot_replace_original(tmp_path):
    c, o = fixture()
    r = build_review(c, o)
    write_review(tmp_path, r)
    before = (tmp_path / "review.json").read_bytes()
    r["result"]["verdict"] = "FAIL"
    with pytest.raises(PrivateArtifactError):
        write_review(tmp_path, r)
    assert (tmp_path / "review.json").read_bytes() == before


def test_recheck_runs_without_site_packages(tmp_path):
    c, o = fixture()
    (tmp_path / "contract.json").write_text(json.dumps(c), encoding="utf-8")
    (tmp_path / "observation.json").write_text(json.dumps(o), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-S", str(root / "scripts/run_bulletin_task_check.py"),
        "--contract", str(tmp_path / "contract.json"),
        "--observation", str(tmp_path / "observation.json")],
        capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["verdict"] == "PASS"
