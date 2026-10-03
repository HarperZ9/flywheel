"""Verification share over time, the outpacing flag and the cost-to-verify meter.

Success criteria: weekly shares are weighted by size and bucketed by ISO week
(Monday start); the flag fires only when the unchecked share rose two weeks
running and output grew over the same weeks; the meter gives an unchecked
share with a Wilson interval, marks hold-on-completion only above 0.5, and
counts reviewer minutes and how many person-checked items logged them; bad
items are refused; receipt lanes map to routes.
"""
from __future__ import annotations

import pytest

from harness.verification_meter import meter, report
from harness.verification_share import Item, flag_weeks, item_from_dict, weekly

MONDAYS = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28"]


def _week(day, sizes, n0=0):
    """sizes: {route: size}; one item per route on that day."""
    return [Item(f"{day}-{r}-{n0}", f"{day}T12:00:00Z", "fam", r, s) for r, s in sizes.items()]


def test_shares_are_size_weighted_and_iso_weeks_start_monday():
    items = [Item("a", "2026-09-13T23:00:00Z", "f", "machine", 30),   # Sunday: W37
             Item("b", "2026-09-14T01:00:00Z", "f", "unchecked", 10),  # Monday: W38
             Item("c", "2026-09-14T02:00:00Z", "f", "machine", 30)]
    w = weekly(items)
    assert [x["week"] for x in w] == ["2026-W37", "2026-W38"]
    assert w[1]["share"]["unchecked"] == 0.25 and w[1]["items"] == 2 and w[1]["size"] == 40


def _series(unchecked, machine):
    items = []
    for day, u, m in zip(MONDAYS, unchecked, machine):
        items += _week(day, {"unchecked": u, "machine": m})
    return weekly(items)


def test_flag_fires_when_unchecked_share_rises_twice_while_output_grows():
    weeks = _series([10, 30, 80], [90, 90, 100])  # shares 0.10, 0.25, 0.44; size 100, 120, 180
    flags = flag_weeks(weeks)
    assert [f["week"] for f in flags] == ["2026-W39"]


def test_no_flag_when_output_does_not_grow():
    assert flag_weeks(_series([10, 30, 50], [90, 70, 50])) == []  # sizes 100, 100, 100


def test_no_flag_after_a_single_rise():
    assert flag_weeks(_series([10, 10, 80], [90, 110, 100])) == []  # shares 0.10, 0.083, 0.44


def test_no_flag_when_share_rises_but_output_shrinks():
    assert flag_weeks(_series([50, 45, 40], [150, 90, 40])) == []  # sizes 200, 135, 80


def test_meter_unchecked_share_interval_and_hold_on_completion():
    items = [Item(str(n), "2026-09-14T00:00:00Z", "docs", "unchecked", 1) for n in range(6)]
    items += [Item(f"m{n}", "2026-09-14T00:00:00Z", "docs", "machine", 1) for n in range(4)]
    row = meter(items)["docs"]
    assert row["unchecked_share"][0] == 0.6 and row["unchecked_share"][1] < 0.6 < row["unchecked_share"][2]
    assert row["hold_on_completion"] is True


def test_exactly_half_unchecked_is_not_marked():
    items = [Item(str(n), "2026-09-14T00:00:00Z", "f", r, 1) for n, r in enumerate(["unchecked", "machine"])]
    assert meter(items)["f"]["hold_on_completion"] is False


def test_reviewer_minutes_and_their_coverage():
    items = [Item("p1", "2026-09-14T00:00:00Z", "f", "person", 5, 12),
             Item("p2", "2026-09-14T00:00:00Z", "f", "person", 5, 8),
             Item("p3", "2026-09-14T00:00:00Z", "f", "person", 5, None),
             Item("m1", "2026-09-14T00:00:00Z", "f", "machine", 5, 99)]
    row = meter(items)["f"]
    assert row["reviewer_minutes"] == 20 and row["minutes_logged"] == [2, 3]
    assert row["minutes_per_person_item"] == 10.0
    assert report(items)["minutes_coverage"] == [2, 3]


@pytest.mark.parametrize("kw", [dict(route="maybe"), dict(size=-1), dict(size=1.5),
                                dict(reviewer_minutes=2.5), dict(shipped_at="last week")])
def test_bad_items_are_refused(kw):
    base = dict(item_id="x", shipped_at="2026-09-14T00:00:00Z", family="f", route="machine", size=1)
    base.update(kw)
    with pytest.raises(ValueError):
        Item(**base)


def test_receipt_lanes_map_to_routes():
    got = [item_from_dict({"id": n, "shipped_at": "2026-09-14T00:00:00Z", "lane": lane}).route
           for n, lane in enumerate(["A", "H", "UNVERIFIABLE"])]
    assert got == ["machine", "person", "unchecked"]
    with pytest.raises(ValueError):
        item_from_dict({"schema": "other/v1", "id": 1, "shipped_at": "2026-09-14", "route": "machine"})
