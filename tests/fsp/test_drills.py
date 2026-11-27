"""The drills themselves: each conformance drill passes, and the lapse drill behaves."""

from __future__ import annotations

import pytest

from harness.fsp import drills_conformance, drills_lapse, drills_review


@pytest.mark.parametrize("drill", drills_conformance.ALL + drills_review.ALL,
                         ids=lambda f: f.__name__)
def test_conformance_drill_passes(drill):
    result = drill()
    assert result["pass"], result


def test_cut_renewal_path_lapses_every_device_and_file_channel_saves_them(tmp_path):
    cut = drills_lapse.run(n_sites=1, per_site=2, cut_days=8, run_dir=tmp_path)
    assert cut["failed_closed"] == cut["devices"] == 2
    assert cut["warning_lead_h"] is not None and cut["warning_lead_h"] >= 72
    assert cut["restored_within_h_after_path_returns"] is not None
    saved = drills_lapse.run(n_sites=1, per_site=2, cut_days=8, file_channel=True,
                             run_dir=tmp_path)
    assert saved["failed_closed"] == 0
    acct = drills_lapse.false_halt_accounting([cut, saved])
    assert acct["false_halt_events"] == 1 and acct["events"][0]["devices"] == 2
