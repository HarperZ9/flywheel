"""Baseline-to-ceiling score scaling in findings.

Success criteria:
- scaled() gives 0 at the baseline, 1 at the ceiling, 0.5 halfway, and refuses a
  ceiling at or below the baseline and non-finite input;
- an artifact with both anchors (value, source, sha256) renders a measured
  finding that names both anchor sources;
- false-success control: an artifact with only a raw score renders "pending"
  and the finding carries no number anywhere in its value;
- a run root with no scaled/ folder leaves the findings document's root hash
  unchanged, so existing findings documents stay verifiable.
"""
from __future__ import annotations

import json
import re

import pytest

from harness.findings import project_findings
from harness.findings_scaled import SCHEMA, scaled_value
from harness.findings_stats import scaled


def test_scaled_anchors():
    assert scaled(0.458, 0.458, 0.82) == 0
    assert scaled(0.82, 0.458, 0.82) == 1
    assert scaled(0.5, 0.0, 1.0) == pytest.approx(0.5)


@pytest.mark.parametrize("args", [(0.5, 0.6, 0.6), (0.5, 0.7, 0.6), (float("nan"), 0, 1),
                                  (0.5, None, 1), (True, 0, 1)])
def test_scaled_refuses_bad_anchors(args):
    with pytest.raises(ValueError):
        scaled(*args)


def _artifact(**kw):
    doc = {"schema": SCHEMA, "key": "red", "claim": "red check share", "score": 0.64,
           "baseline": {"value": 0.458, "source": "exp1/touched.json", "sha256": "a" * 64},
           "ceiling": {"value": 0.82, "source": "exp1/rerun.json", "sha256": "b" * 64}}
    doc.update(kw)
    return doc


def test_both_anchors_give_a_measured_value_naming_both_sources():
    value, bounds = scaled_value(_artifact())
    assert value.startswith("0.503 of the way")
    assert "exp1/touched.json" in bounds and "exp1/rerun.json" in bounds


def test_control_raw_score_only_is_pending_with_no_number(tmp_path):
    raw = {"schema": SCHEMA, "key": "raw", "claim": "raw only", "score": 0.64}
    value, _ = scaled_value(raw)
    assert value is None
    (tmp_path / "scaled").mkdir()
    (tmp_path / "scaled" / "raw.json").write_text(json.dumps(raw))
    doc = project_findings(tmp_path)
    f = next(x for x in doc["findings"] if x["key"] == "scaled:raw")
    assert f["status"] == "pending" and f["value"] is None
    assert not re.search(r"\d", json.dumps(f["value"]))


def test_anchor_without_hash_is_pending():
    doc = _artifact()
    doc["ceiling"] = {"value": 0.82, "source": "exp1/rerun.json"}
    assert scaled_value(doc)[0] is None


def test_measured_artifact_in_the_findings_document(tmp_path):
    (tmp_path / "scaled").mkdir()
    (tmp_path / "scaled" / "red.json").write_text(json.dumps(_artifact()))
    f = next(x for x in project_findings(tmp_path)["findings"] if x["key"] == "scaled:red")
    assert f["status"] == "measured" and f["value"].startswith("0.503")


def test_ceiling_below_baseline_artifact_is_pending_not_a_crash(tmp_path):
    (tmp_path / "scaled").mkdir()
    bad = _artifact(ceiling={"value": 0.3, "source": "x", "sha256": "c" * 64})
    (tmp_path / "scaled" / "bad.json").write_text(json.dumps(bad))
    f = next(x for x in project_findings(tmp_path)["findings"] if x["key"] == "scaled:bad")
    assert f["status"] == "pending" and "ceiling must be above baseline" in f["bounds"]


def test_no_scaled_folder_keeps_the_root_hash(tmp_path):
    before = project_findings(tmp_path)["root_hash"]
    (tmp_path / "scaled").mkdir()
    assert project_findings(tmp_path)["root_hash"] == before
