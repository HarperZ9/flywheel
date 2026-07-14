"""worktree_preflight.py -- a tripwire on two verified harness bugs.

Credit: the failure modes and the tripwire idea are from moui72
(peckenpaugh.us, "bugs I could only find by running it") and the
Claude Code issue tracker (anthropics/claude-code #75045, #69802),
frozen in this repo's snapshot store on 2026-07-14.

Two bugs affect isolated fan-outs:
1. isolation:worktree agents are cut from the default-branch lineage
   (origin/HEAD / main), not the session HEAD, and non-deterministically,
   so a delegated agent can start blind to unmerged session work. Pushing
   the working branch does NOT help, because the worktree comes off main.
2. worktree teardown (ExitWorktree) can flip the primary checkout's
   core.bare to true, which breaks ordinary git in that checkout until
   reverted by hand.

This assesses both over injectable git state so the logic is testable
without a live repo. The CLI wrapper gathers the real state. It fixes
nothing (the mutations live in the harness, not in git); it refuses to
be silent when either occurs, which is the only honest posture toward an
unexplained upstream bug: verify, do not assume.
"""
from __future__ import annotations

SCHEMA = "flywheel.worktree-preflight/v1"


def assess_worktree_health(*, core_bare: bool, session_head: str,
                           worktrees: list) -> dict:
    """Judge the worktree state. `worktrees` is a list of
    {path, head, descends_from_session}. Returns ok plus a list of
    alerts, each naming its level and what to do. Every problem is
    reported, not just the first."""
    alerts = []
    if core_bare:
        alerts.append({
            "level": "critical", "kind": "core-bare",
            "message": "core.bare is true in the primary checkout: ordinary "
                       "git is broken here. Revert with `git config "
                       "core.bare false` and check refs did not advance "
                       "while the tree was frozen (issue 69802)."})
    for wt in worktrees or []:
        if not wt.get("descends_from_session"):
            alerts.append({
                "level": "critical", "path": wt.get("path"),
                "kind": "stale-base",
                "message": f"worktree {wt.get('path')!r} HEAD "
                           f"{str(wt.get('head'))[:12]} does not descend from "
                           "the session HEAD: it was cut from the default "
                           "branch, not your work (issue 75045). Fast-forward "
                           "it to the session HEAD before trusting its output, "
                           "or do not delegate unmerged-dependent work to an "
                           "isolated worktree."})
    return {"schema": SCHEMA, "ok": not alerts, "core_bare": bool(core_bare),
            "session_head": session_head, "worktree_count": len(worktrees or []),
            "alerts": alerts,
            "note": "a tripwire, not a fix: the mutations live in the harness. "
                    "verify the base, never assume it (the bug flips direction "
                    "between runs)."}


def _gather_and_assess(repo_dir: str = ".") -> dict:
    """CLI path: read the real git state and assess it. Zero-dep, shells
    out to git; a git failure is reported, not swallowed."""
    import subprocess

    def git(*args):
        return subprocess.run(["git", "-C", repo_dir, *args],
                              capture_output=True, text=True).stdout.strip()

    core_bare = git("config", "--get", "core.bare").lower() == "true"
    session_head = git("rev-parse", "HEAD")
    worktrees = []
    path = None
    for line in git("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.startswith("HEAD ") and path:
            head = line[len("HEAD "):]
            if head != session_head:
                anc = subprocess.run(
                    ["git", "-C", repo_dir, "merge-base",
                     "--is-ancestor", session_head, head],
                    capture_output=True)
                descends = anc.returncode == 0
            else:
                descends = True
            worktrees.append({"path": path, "head": head,
                              "descends_from_session": descends})
            path = None
    return assess_worktree_health(core_bare=core_bare,
                                  session_head=session_head,
                                  worktrees=worktrees)


if __name__ == "__main__":
    import json
    import sys
    doc = _gather_and_assess(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(json.dumps(doc, indent=1))
    sys.exit(0 if doc["ok"] else 1)
