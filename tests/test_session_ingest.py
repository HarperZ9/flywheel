"""F7 falsifier — session history becomes scout-consumable, verified corpus.

normalize_sessions turns Claude Code / OpenCode session records into catalog rows
the scout can classify and the wiki can ground — one row per session, deduped,
provenance kept. Composes with intake (digest) end to end.
"""
from harness import feeds
from harness.intake import validate_catalog, digest

SESSIONS = [
    {"id": "ses-1", "title": "verified-inference harness build",
     "summary": "built the M1 oracle loop; decision: no learned model in accept path",
     "theme": "harness"},
    {"id": "ses-2", "title": "scout calibration fix",
     "summary": "coverage-saturation relevance + word-boundary matching; benchmark pass-rate improved"},
    {"id": "ses-3", "title": "verified-inference harness build",   # dup text vs ses-1? no, distinct
     "summary": "wired proof-addressed memory into run_loop as opt-in"},
]


def test_rows_are_scout_consumable():
    rows = feeds.normalize_sessions(SESSIONS, captured="2026-07-06")
    assert rows and validate_catalog(rows) == []


def test_provenance_and_dedup():
    rows = feeds.normalize_sessions(SESSIONS + SESSIONS)   # duplicates collapse
    assert len(rows) == len(SESSIONS)
    for r in rows:
        assert r["ref"].startswith("session:") and r["source"].startswith("session/")


def test_sessions_flow_through_intake():
    rows = feeds.normalize_sessions(SESSIONS)
    d = digest(rows, feed_id="sessions")
    # the calibration session names a measurable mechanism -> should not all be noise
    assert d.n_sources == len(SESSIONS)
    assert d.verdict_counts["ACTIONABLE"] + d.verdict_counts["INSPIRATION"] >= 1
