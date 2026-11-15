"""test_mcp_check.py -- the aggregate check tool.

`canon.check` is the one tool on the door that returns a verdict, so it is the
one that can be wrong in a way nobody notices. The failure it has to refuse is
the vacuous pass: every leg reporting clean because it voted over a pool that
was not the authored set, or over no pool at all.
"""
from __future__ import annotations

from canon.blocks import ENV_BLOCKS_DIR
from canon.local_mcp import ENV_HOME, ENV_WORKSPACE

from ._mcp_helpers import _block, _clean_env, _seed, _tool  # noqa: F401  (autouse fixture)


def test_check_names_the_legs_that_did_not_run(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    report = _tool("canon.check")
    assert report["ok"] is True and report["exit_code"] == 0
    assert report["legs_unwired"] == ["drift", "persona"]
    assert report["legs_run"] == ["vault", "vault_symmetric"]
    assert report["pool_available"] is True and report["pool_complete"] is True
    assert report["does_not_prove"]


def test_check_runs_the_drift_leg_once_the_roots_are_configured(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    monkeypatch.setenv(ENV_HOME, str(tmp_path / "home"))
    monkeypatch.setenv(ENV_WORKSPACE, str(tmp_path / "ws"))
    report = _tool("canon.check")
    assert "drift" in report["legs_run"] and report["legs_unwired"] == ["persona"]


def test_check_fails_when_the_pool_it_ran_over_is_incomplete(tmp_path, monkeypatch):
    # Every leg passes over the records that loaded. If a file did not load, the
    # pool is not the authored set, so a pass is not a verdict about the
    # authored set. This is the false-success this check has to refuse.
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    report = _tool("canon.check")
    assert report["ok"] is False and report["exit_code"] == 1
    assert report["pool_complete"] is False
    assert any("pool incomplete" in r for r in report["reasons"])


def test_check_fails_when_there_was_no_pool_to_check(tmp_path, monkeypatch):
    """The limit case of the same failure: every leg voted over the empty set.

    A vacuous pass is the one answer this check must not give, so `ok` reads
    false and `pool_available` says which of the two pool failures happened.
    """
    monkeypatch.setenv(ENV_BLOCKS_DIR, str(tmp_path / "does-not-exist"))
    report = _tool("canon.check")
    assert report["ok"] is False and report["pool_size"] == 0
    assert report["pool_available"] is False
    assert any("no block pool to check" in r for r in report["reasons"])


def test_the_check_verb_and_the_check_tool_return_the_same_verdict(tmp_path, monkeypatch,
                                                                   capsys):
    """A build gate and a harness question must not disagree about canon.

    The CLI verb calls the same function the tool calls, and this pins that:
    same environment, same payload, and an exit code that follows the verdict.
    """
    import json

    from canon.cli import main

    monkeypatch.setenv(ENV_BLOCKS_DIR, str(_seed(tmp_path, _block("b1"))))
    assert main(["check"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == _tool("canon.check")

    monkeypatch.setenv(ENV_BLOCKS_DIR, str(tmp_path / "does-not-exist"))
    assert main(["check"]) == 1
