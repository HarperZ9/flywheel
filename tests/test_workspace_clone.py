"""Giving a task a tree it can ruin, and saying how the copy was made.

The mechanism matters to anyone reading a timing later, so the record carries
it. The fallback order matters more, because a host that quietly produced a
merge of two partial copies would hand a task a workspace nobody wrote.
"""
import sys
from pathlib import Path

import pytest

from harness.workspace_clone import (SCHEMA, SHARED, Clone, clone_workspace,
                                     ladder, measure, perform)


def tree(root, files=(("a.txt", "alpha"), ("sub/b.txt", "beta"))):
    """A small source workspace, including one file in a subdirectory."""
    for name, body in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def names(root):
    return sorted(p.relative_to(root).as_posix()
                  for p in root.rglob("*") if p.is_file())


def test_a_real_copy_lands_on_this_host(tmp_path):
    # No platform override and no injection: whatever this host actually does,
    # it produces the source tree and says which rung got there.
    source = tree(tmp_path / "src")
    result = clone_workspace(source, tmp_path / "dst")
    assert result.ok
    assert result.mechanism in ladder()
    assert names(tmp_path / "dst") == ["a.txt", "sub/b.txt"]
    assert (tmp_path / "dst" / "sub" / "b.txt").read_text() == "beta"
    assert result.files == 2
    assert result.bytes == len("alpha") + len("beta")


def test_the_clone_is_independent_of_the_source(tmp_path):
    # The property a caller is really buying. Copy-on-write makes this true
    # without copying bytes, which is why `shared` is about cost and not about
    # whether one side can see the other's writes.
    source = tree(tmp_path / "src")
    clone_workspace(source, tmp_path / "dst")
    (source / "a.txt").write_text("rewritten", encoding="utf-8")
    (source / "sub" / "b.txt").unlink()
    assert (tmp_path / "dst" / "a.txt").read_text() == "alpha"
    assert (tmp_path / "dst" / "sub" / "b.txt").exists()


def test_a_half_written_attempt_is_not_left_for_the_next_rung(tmp_path):
    # The failure this guards is silent. `cp --reflink=always` can copy part of
    # a tree before refusing, and a plain copy into the same directory would
    # produce a tree that is neither the source nor a clean fallback.
    source = tree(tmp_path / "src")

    def flaky(mechanism, src, dst):
        if mechanism == "reflink":
            dst.mkdir(parents=True)
            (dst / "junk.txt").write_text("half a copy", encoding="utf-8")
            return "exit 1: failed to clone: Invalid cross-device link"
        return perform(mechanism, src, dst)

    result = clone_workspace(source, tmp_path / "dst", platform="linux",
                             attempt=flaky)
    assert result.ok and result.mechanism == "copy"
    assert names(tmp_path / "dst") == ["a.txt", "sub/b.txt"]
    assert not (tmp_path / "dst" / "junk.txt").exists()
    assert [name for name, _ in result.attempts] == ["reflink"]
    assert "cross-device" in result.attempts[0][1]


def test_a_host_with_no_working_mechanism_says_so_and_keeps_every_reason(
        tmp_path):
    # Reporting only the last refusal would hide that the fast path was tried,
    # which is the half an operator needs to know why a run is slow.
    source = tree(tmp_path / "src")
    result = clone_workspace(source, tmp_path / "dst", platform="linux",
                             attempt=lambda m, s, d: f"{m} is not available")
    assert not result.ok
    assert result.mechanism is None
    assert [name for name, _ in result.attempts] == ["reflink", "copy"]
    assert not (tmp_path / "dst").exists()


@pytest.mark.parametrize("platform, rungs", [
    ("linux", ("reflink", "copy")),
    ("darwin", ("clonefile", "copy")),
    ("win32", ("copy",)),
    ("aix7", ("copy",)),
])
def test_the_ladder_is_readable_from_any_host(platform, rungs):
    # A pure function, so what a Linux host would try is assertable from a
    # Windows run. A platform nobody planned for gets the floor rather than an
    # empty ladder, because a slow copy still isolates a task.
    assert ladder(platform) == rungs
    assert ladder() == ladder(sys.platform)


def test_only_the_block_sharing_rungs_claim_to_share(tmp_path):
    # `shared` is written into the receipt, so it may not be a guess about the
    # mechanism's name.
    source = tree(tmp_path / "src")
    for mechanism, platform, expected in (("reflink", "linux", True),
                                          ("clonefile", "darwin", True),
                                          ("copy", "win32", False)):
        dest = tmp_path / f"out-{mechanism}"
        result = clone_workspace(
            source, dest, platform=platform,
            attempt=lambda m, s, d, want=mechanism: (
                perform("copy", s, d) if m == want else f"{m} skipped"))
        assert result.mechanism == mechanism
        assert result.shared is expected
        assert (mechanism in SHARED) is expected


@pytest.mark.parametrize("kind, reason", [
    ("missing", "not a directory"),
    ("occupied", "destination exists"),
])
def test_a_clone_that_cannot_start_refuses_before_touching_anything(
        tmp_path, kind, reason):
    source = tree(tmp_path / "src")
    dest = tmp_path / "dst"
    if kind == "missing":
        source = tmp_path / "no-such-tree"
    else:
        dest.mkdir()
        (dest / "existing.txt").write_text("mine", encoding="utf-8")
    result = clone_workspace(source, dest)
    assert not result.ok
    assert reason in result.attempts[0][1]
    if kind == "occupied":
        # The refusal has to leave the caller's directory alone. Removing it to
        # make room would delete work on the strength of a path argument.
        assert (dest / "existing.txt").read_text() == "mine"


def test_the_record_carries_what_a_later_reader_needs(tmp_path):
    # A receipt naming a mechanism nobody can look up explains nothing, so the
    # refused rungs travel with the one that worked.
    source = tree(tmp_path / "src")
    result = clone_workspace(source, tmp_path / "dst", platform="linux",
                             attempt=lambda m, s, d: (
                                 "no reflink here" if m == "reflink"
                                 else perform(m, s, d)))
    record = result.record()
    assert record["schema"] == SCHEMA
    assert record["mechanism"] == "copy"
    assert record["shared"] is False
    assert record["files"] == 2
    assert record["seconds"] >= 0
    assert record["attempts"] == [
        {"mechanism": "reflink", "refused": "no reflink here"}]


def test_measure_counts_files_and_skips_symlinks(tmp_path):
    # Counting a symlink's target would report a tree larger than the one that
    # was copied, and on a tree with a loop it would not finish.
    source = tree(tmp_path / "src")
    try:
        (source / "link.txt").symlink_to(source / "a.txt")
    except (OSError, NotImplementedError):
        pytest.skip("this host does not allow creating symlinks")
    files, size = measure(source)
    assert files == 2
    assert size == len("alpha") + len("beta")


def test_an_unmade_clone_is_falsy_by_name():
    # `ok` is what callers branch on, and an empty Clone is what a refusal
    # returns, so the two have to agree.
    assert Clone().ok is False
    assert Clone(mechanism="copy").ok is True


def stub_loop(monkeypatch, captured):
    """Replace the model and the agent loop so the test reads wiring only."""
    from harness import local_agent_cli as cli

    class Agent:
        def live_backend(self):
            return object()

    def fake_run(agent, prompt, executor, ledger, **kw):
        captured["root"] = executor.root
        captured["ledger"] = ledger
        return {"final": "done", "steps": 0, "entries": len(ledger.entries),
                "verified": True, "checkpoint": "0" * 64}

    monkeypatch.setattr(cli, "_build_agent", lambda args: Agent())
    monkeypatch.setattr(cli, "run_agent", fake_run)
    return cli


def test_the_agent_runs_in_the_clone_and_the_ledger_says_which_one(
        tmp_path, monkeypatch):
    # The wiring claim, and the reason it is tested here. A module nobody calls
    # still passes its own unit tests, so the capability is only real if a
    # shipped entry point reaches it.
    source = tree(tmp_path / "src")
    captured = {}
    cli = stub_loop(monkeypatch, captured)
    assert cli.main(["--agent", "summarise this", "--isolate",
                     "--root", str(source)]) == 0
    assert captured["root"] != str(source)
    assert names(Path(captured["root"])) == ["a.txt", "sub/b.txt"]
    first = captured["ledger"].entries[0]
    assert first.kind == "workspace"
    assert first.meta["schema"] == SCHEMA
    assert first.meta["mechanism"] in ladder()
    assert names(source) == ["a.txt", "sub/b.txt"]


def test_without_the_flag_the_run_stays_where_it_was_pointed(
        tmp_path, monkeypatch):
    # The control. Isolation is opt-in, and a default that quietly moved the
    # run somewhere else would break every caller that reads --root afterwards.
    source = tree(tmp_path / "src")
    captured = {}
    cli = stub_loop(monkeypatch, captured)
    assert cli.main(["--agent", "summarise this", "--root", str(source)]) == 0
    assert captured["root"] == str(source)
    assert captured["ledger"].entries == []


def test_a_clone_that_cannot_be_made_stops_the_run(tmp_path, monkeypatch):
    # Fail closed. A run that asked to be isolated and silently was not reports
    # exactly the way a real one does, which is the failure worth refusing.
    captured = {}
    cli = stub_loop(monkeypatch, captured)
    assert cli.main(["--agent", "summarise this", "--isolate",
                     "--root", str(tmp_path / "no-such-tree")]) == 1
    assert "root" not in captured


def test_a_commit_inside_a_disposable_copy_is_refused_at_the_flag(tmp_path):
    # The sha would name a commit in a tree nobody keeps, so the run would
    # report work that cannot be fetched.
    from harness import local_agent_cli as cli
    with pytest.raises(SystemExit) as stop:
        cli.main(["--agent", "x", "--isolate", "--auto-commit",
                  "--root", str(tmp_path)])
    assert stop.value.code == 2
