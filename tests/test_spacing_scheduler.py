"""The spacing scheduler: item history in, dated review queue out. The
priors are the CLASSROOM numbers, not the lab's (d = 0.54, not 0.85),
re-exposures cap at three (the marginal gain curve, not a habit tread),
and the module claims scheduling only: no learning-lift claim rides a
schedule. Deterministic: the clock is a parameter, never a global."""

from harness.spacing_scheduler import DAY, schedule_reviews

NOW = 1_784_000_000.0


def _item(eid, days_ago, exposures=1):
    return {"eid": eid, "last_shown": NOW - days_ago * DAY,
            "exposures": exposures}


def test_due_upcoming_and_capped_are_disjoint_and_complete():
    items = [_item("a", 8), _item("b", 2), _item("c", 30, exposures=3)]
    q = schedule_reviews(items, now=NOW)
    assert [d["eid"] for d in q["due"]] == ["a"]
    assert [u["eid"] for u in q["upcoming"]] == ["b"]
    assert [c["eid"] for c in q["capped"]] == ["c"]
    assert q["schema"] == "flywheel.spacing-queue/v1"


def test_upcoming_names_its_date():
    q = schedule_reviews([_item("b", 2)], now=NOW)
    assert q["upcoming"][0]["due_at"] == NOW - 2 * DAY + 7 * DAY


def test_oldest_due_first():
    q = schedule_reviews([_item("late", 9), _item("later", 20)], now=NOW)
    assert [d["eid"] for d in q["due"]] == ["later", "late"]


def test_the_priors_are_classroom_not_lab():
    q = schedule_reviews([], now=NOW)
    assert q["priors"]["classroom_spacing_d"] == 0.54
    assert q["priors"]["retrieval_math_g"] == 0.18
    assert "crosses zero" in q["priors"]["retrieval_math_note"]
    assert "scheduling only" in q["note"]


def test_malformed_items_are_named_not_crashed():
    q = schedule_reviews([{"eid": "x"}, _item("ok", 8)], now=NOW)
    assert [d["eid"] for d in q["due"]] == ["ok"]
    assert q["skipped"][0]["eid"] == "x"
