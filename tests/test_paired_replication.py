"""The negative result has to survive being recomputed.

The comparison between the base weights and the continued-pretrained weights
is the project's clearest capability number and it is unfavourable. It is
published, so it is checked: the per-task outcomes are committed, this
recounts them, and the count is compared against the separately recorded
comparison artifact that was written at the time.

If the two ever disagree, one of them is wrong and neither should be on a
page.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from harness.paired_replication import (ARTIFACTS,  # noqa: E402
                                        run_paired_replication)

RECORDED = ARTIFACTS / "he_base_comparison.json"


def test_the_recount_matches_the_comparison_recorded_at_the_time():
    fresh = run_paired_replication()
    old = json.loads(RECORDED.read_text(encoding="utf-8"))
    assert fresh["base"]["passed"] == old["base"]["passed"]
    assert fresh["treatment"]["passed"] == old["flywheel"]["passed"]
    assert fresh["delta_points"] == old["delta_points"]
    assert fresh["paired"]["regressions"] == (
        old["paired"]["regressions_flywheel_fail_base_pass"])
    assert fresh["paired"]["gains"] == old["paired"]["gains_flywheel_pass_base_fail"]
    assert fresh["mcnemar"]["chi2_cc"] == old["mcnemar"]["chi2_cc"]


def test_the_result_is_a_regression_and_is_not_significant():
    """The two facts that make this a null rather than a finding.

    Pinned because they are the two a later pass would be tempted to soften:
    the sign of the difference, and that the test does not reject.
    """
    r = run_paired_replication()
    assert r["delta_points"] < 0
    assert r["mcnemar"]["p_exact"] > 0.05
    assert r["mcnemar"]["significant_at_05"] is False


def test_the_arms_ran_the_same_tasks():
    """A paired test on unpaired task sets is not a paired test."""
    r = run_paired_replication()
    p = r["paired"]
    assert (p["both_pass"] + p["both_fail"] + p["regressions"] + p["gains"]
            == r["n_tasks"])


def test_the_caveats_travel_with_the_number():
    """Three of them, and each says what the number does not show."""
    r = run_paired_replication()
    assert len(r["caveats"]) == 3
    assert all(isinstance(c, str) and c.strip() for c in r["caveats"])
