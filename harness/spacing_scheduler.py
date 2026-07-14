"""spacing_scheduler.py -- item history in, dated review queue out.

The learning-academy dossier's measured priors, not the lab's: spaced
review in classrooms runs d = 0.54 (the lab's 0.85 does not transfer),
and retrieval practice for math sits at g = 0.18 with an interval that
crosses zero, so this module schedules and claims nothing more. Fixed
seven-day intervals, re-exposures capped at three (the marginal-gain
curve, not a habit treadmill), oldest debt first, the clock always a
parameter. Composes with retention_due: retention lists what has no
retest yet; this schedules the re-exposures that come before one.
"""
from __future__ import annotations

SCHEMA = "flywheel.spacing-queue/v1"
DAY = 86400.0
INTERVAL_DAYS = 7
MAX_EXPOSURES = 3

PRIORS = {
    "classroom_spacing_d": 0.54,
    "classroom_spacing_note": "classroom meta-analytic effect; the lab "
                              "prior near 0.85 does not transfer",
    "retrieval_math_g": 0.18,
    "retrieval_math_note": "retrieval practice for math: interval "
                           "crosses zero; unproven there",
}


def schedule_reviews(items: list, *, now: float) -> dict:
    """Sort item histories into due / upcoming / capped. An item needs
    {eid, last_shown, exposures}; malformed items are named in
    `skipped`, never guessed at."""
    due, upcoming, capped, skipped = [], [], [], []
    for it in items or []:
        eid = str(it.get("eid", ""))
        try:
            last = float(it["last_shown"])
            exposures = int(it.get("exposures", 1))
        except (KeyError, TypeError, ValueError):
            skipped.append({"eid": eid, "reason": "missing or non-numeric "
                                                  "last_shown/exposures"})
            continue
        if exposures >= MAX_EXPOSURES:
            capped.append({"eid": eid, "exposures": exposures})
            continue
        due_at = last + INTERVAL_DAYS * DAY
        row = {"eid": eid, "due_at": due_at, "exposures": exposures}
        (due if due_at <= now else upcoming).append(row)
    due.sort(key=lambda r: r["due_at"])
    upcoming.sort(key=lambda r: r["due_at"])
    return {"schema": SCHEMA, "due": due, "upcoming": upcoming,
            "capped": capped, "skipped": skipped, "priors": dict(PRIORS),
            "interval_days": INTERVAL_DAYS,
            "max_exposures": MAX_EXPOSURES,
            "note": "this module claims scheduling only; no learning "
                    "lift is asserted by a calendar"}
