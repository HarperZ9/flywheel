"""Preflight for isolated-worktree fan-outs. Two verified Claude Code
harness bugs (crediting moui72 / peckenpaugh.us, and anthropics/claude-code
issues 75045 and 69802): (1) isolation:worktree agents branch from the
default-branch lineage (origin/HEAD / main), not the session HEAD, so they
start blind to unmerged session work; (2) worktree teardown can flip the
primary checkout's core.bare to true, breaking ordinary git there. This
guard is a tripwire on both, over injectable git state so the logic is
tested without a live repo."""

from harness.worktree_preflight import assess_worktree_health

SESSION_HEAD = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _wt(path, head, descends):
    return {"path": path, "head": head, "descends_from_session": descends}


def test_core_bare_true_is_critical():
    r = assess_worktree_health(core_bare=True, session_head=SESSION_HEAD,
                               worktrees=[])
    assert r["ok"] is False
    assert any(a["level"] == "critical" and "core.bare" in a["message"]
               for a in r["alerts"])


def test_a_worktree_off_the_default_lineage_is_flagged():
    # a worktree whose HEAD does not descend from the session HEAD is the
    # origin/main-not-HEAD bug: it started stale
    r = assess_worktree_health(
        core_bare=False, session_head=SESSION_HEAD,
        worktrees=[_wt("wt-impl", "bbbb", descends=False)])
    assert r["ok"] is False
    a = next(x for x in r["alerts"] if x["path"] == "wt-impl")
    assert a["level"] in ("critical", "warning")
    assert "session HEAD" in a["message"] or "stale" in a["message"]


def test_an_aligned_worktree_passes():
    r = assess_worktree_health(
        core_bare=False, session_head=SESSION_HEAD,
        worktrees=[_wt("wt-ok", "cccc", descends=True)])
    assert r["ok"] is True
    assert r["alerts"] == []


def test_clean_repo_no_worktrees_is_ok():
    r = assess_worktree_health(core_bare=False, session_head=SESSION_HEAD,
                               worktrees=[])
    assert r["ok"] is True


def test_mixed_state_reports_every_problem_not_just_the_first():
    r = assess_worktree_health(
        core_bare=True, session_head=SESSION_HEAD,
        worktrees=[_wt("good", "x", True), _wt("stale", "y", False)])
    assert r["ok"] is False
    levels = {a.get("path", "core"): a["level"] for a in r["alerts"]}
    assert "core" in levels and "stale" in levels
    assert "good" not in levels
