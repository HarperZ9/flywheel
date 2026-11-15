"""Falsifiers for optional git integration (aider-style auto-commit).

Load-bearing: (1) a run's changes are committed only inside an existing repo with
actual changes; (2) the commit message carries the ledger checkpoint (the
provenance bridge); (3) not-a-repo and no-changes are reported, never fatal, and
never create a repo. Hermetic: git is injected, no real repo touched.
"""
from types import SimpleNamespace

from relay.local_git import GitRepo, commit_run


class FakeGit:
    def __init__(self, script):
        self.script = script
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        key = " ".join(args)
        for prefix, (rc, out, err) in self.script.items():
            if key.startswith(prefix):
                return SimpleNamespace(returncode=rc, stdout=out, stderr=err)
        return SimpleNamespace(returncode=0, stdout="", stderr="")


_REPO_DIRTY = {
    "rev-parse --is-inside-work-tree": (0, "true", ""),
    "status --porcelain": (0, "M app.py\n", ""),
    "add -A": (0, "", ""),
    "commit -m": (0, "", ""),
    "rev-parse --short HEAD": (0, "abc1234", ""),
}


def test_commit_run_commits_and_binds_the_checkpoint():
    g = FakeGit(_REPO_DIRTY)
    result = commit_run("/x", "change the greeting", "CHECK123", run=g)
    assert result["committed"] and result["sha"] == "abc1234"
    commit_call = next(c for c in g.calls if c[0] == "commit")
    assert "CHECK123" in commit_call[-1]                 # checkpoint in the message
    assert "change the greeting" in commit_call[-1]


def test_commit_stages_only_the_witnessed_edit_paths():
    # With an explicit witnessed edit set, the commit stages exactly those paths,
    # never `add -A` — so a dirty file or a shell-written file the ledger did not
    # record as content is not swept into a commit that claims ledger provenance.
    g = FakeGit(_REPO_DIRTY)
    commit_run("/x", "goal", "CHK", paths=["src/app.py", "src/util.py"], run=g)
    add_call = next(c for c in g.calls if c[0] == "add")
    assert add_call == ["add", "--", "src/app.py", "src/util.py"]
    assert not any(c == ["add", "-A"] for c in g.calls)


def test_witnessed_commit_message_notes_the_edit_set():
    g = FakeGit(_REPO_DIRTY)
    commit_run("/x", "change greeting", "CHK", paths=["src/app.py"], run=g)
    msg = next(c for c in g.calls if c[0] == "commit")[-1]
    assert "CHK" in msg and "witnessed-edits" in msg


def test_commit_refuses_when_no_edits_were_witnessed():
    # The working tree is dirty, but the ledger recorded no write/edit targets.
    # Committing arbitrary tree state would attribute it to the trajectory falsely.
    g = FakeGit(_REPO_DIRTY)
    result = commit_run("/x", "goal", "CHK", paths=[], run=g)
    assert result["committed"] is False and "witnessed" in result["reason"]
    assert not any(c[0] == "commit" for c in g.calls)


def test_not_a_repo_is_reported_not_fatal():
    g = FakeGit({"rev-parse --is-inside-work-tree": (128, "", "fatal: not a git repo")})
    result = commit_run("/x", "goal", "CHK", run=g)
    assert result["committed"] is False and "not a git repo" in result["reason"]
    assert not any(c[0] == "commit" for c in g.calls)    # never attempted a commit


def test_no_changes_is_reported():
    g = FakeGit({"rev-parse --is-inside-work-tree": (0, "true", ""),
                 "status --porcelain": (0, "", "")})
    result = commit_run("/x", "goal", "CHK", run=g)
    assert result["committed"] is False and "no changes" in result["reason"]


def test_failed_commit_surfaces_stderr():
    g = FakeGit({**_REPO_DIRTY, "commit -m": (1, "", "nothing to commit, working tree clean")})
    result = GitRepo("/x", run=g).commit_all("msg")
    assert result["committed"] is False and "nothing to commit" in result["reason"]
