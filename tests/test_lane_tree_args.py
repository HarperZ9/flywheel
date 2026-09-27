"""gather.run's inline config gets the same path guard as a path argument.

Product-truth review of the 1.1.0 change, PT-9. The engine checked the
arguments the policy names as paths, and for gather.run that was config_path
alone. An inline ``config`` whose source target or store named a network
share or a file in Flywheel's own state reached the lane unchecked. The
policy now names ``config`` as a tree argument: every string inside it,
through objects, lists and JSON text, is checked as a path argument is.
"""
from __future__ import annotations

import json

import pytest

from harness import path_identity
from harness.lane_tier_gate import argument_refusal
from harness.lane_tool_policy import tool_policy


@pytest.fixture()
def home(tmp_path, monkeypatch):
    root = tmp_path / "home"
    (root / "state").mkdir(parents=True)
    (root / "state" / "secret.json").write_text("{}", encoding="utf-8")
    (root / "lanes" / "gather").mkdir(parents=True)
    monkeypatch.setenv("FLYWHEEL_HOME", str(root))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    return root


def _config(target, store="corpus"):
    return {"sources": [{"type": "docs", "target": target, "tags": ["a", "b"]},
                        {"type": "web", "target": "https://example.invalid/feed"}],
            "store": store, "name": "weekly digest"}


def _refused(config) -> bool:
    refusal = argument_refusal("gather", "gather.run", {"config": config})
    return bool(refusal) and refusal["reason"] == "argument_refused"


def test_gather_run_names_config_as_a_tree_argument():
    entry = tool_policy("gather", "gather.run")
    assert "config" in entry.tree_args and "config_path" in entry.path_args
    assert entry.guarded


def test_a_nested_target_in_flywheel_state_is_refused(home):
    assert _refused(_config(str(home / "state" / "secret.json")))
    assert _refused(_config("docs", store=str(home / "state")))


def test_config_given_as_json_text_is_walked_too(home):
    assert _refused(json.dumps(_config(str(home / "state" / "secret.json"))))


@pytest.mark.parametrize("share", ["\\\\host.invalid\\share\\docs", "//host.invalid/share/docs",
                                   "\\\\?\\C:\\docs"])
def test_a_nested_network_or_device_path_is_refused(home, monkeypatch, share):
    monkeypatch.setattr(path_identity, "_WINDOWS", True)
    assert _refused(_config(share))


def test_an_ordinary_config_passes(home, tmp_path):
    (tmp_path / "work").mkdir()
    assert not _refused(_config(str(tmp_path / "work")))
    assert not _refused(_config("docs"))
    assert not _refused(json.dumps(_config("docs")))
