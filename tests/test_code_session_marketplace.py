"""Falsifiers for plugin marketplaces: add, search, install NAME@MARKET, path safety."""
import json

import pytest

from harness.code_session import plugin_cli
from harness.code_session.marketplace import add, resolve, search
from harness.code_session.plugins import PluginError, plugin_roots


def _market(tmp_path, entries, name="team"):
    m = tmp_path / "market"
    (m / ".claude-plugin").mkdir(parents=True)
    (m / "plugins" / "rev" / "commands").mkdir(parents=True)
    (m / "plugins" / "rev" / "plugin.json").write_text(json.dumps({"name": "rev"}), encoding="utf-8")
    (m / "plugins" / "rev" / "commands" / "review.md").write_text("Review it.", encoding="utf-8")
    (m / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": name, "plugins": entries}), encoding="utf-8")
    return m


def test_add_search_and_install_from_a_marketplace(tmp_path, monkeypatch, capsys):
    home = str(tmp_path / "home")
    m = _market(tmp_path, [{"name": "rev", "description": "reviews diffs",
                            "source": "./plugins/rev"}])
    info = add(str(m), home)
    assert info == {"name": "team", "source": str(m.resolve()), "plugins": 1}
    assert search(home, "review") == [("rev@team", "reviews diffs")]
    assert search(home, "nothing-like-this") == []
    monkeypatch.setattr(plugin_cli, "_home", lambda: home)
    assert plugin_cli.main(["install", "rev@team", "--yes"]) == 0
    assert [p.name for p in plugin_roots(home)] == ["rev"]


def test_path_sources_cannot_leave_the_marketplace(tmp_path):
    home = str(tmp_path / "home")
    add(str(_market(tmp_path, [{"name": "evil", "source": "../../outside"}])), home)
    with pytest.raises(PluginError):
        resolve("evil@team", home)


def test_github_and_url_sources_resolve_to_git_urls(tmp_path):
    home = str(tmp_path / "home")
    add(str(_market(tmp_path, [{"name": "a", "source": {"source": "github", "repo": "org/a"}},
                               {"name": "b", "source": {"source": "url",
                                                        "url": "https://host/b.git"}}])), home)
    assert resolve("a@team", home) == "https://github.com/org/a.git"
    assert resolve("b@team", home) == "https://host/b.git"
    with pytest.raises(PluginError):
        resolve("c@team", home)
    with pytest.raises(PluginError):
        resolve("a@nowhere", home)


def test_a_folder_without_a_catalog_is_refused(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(PluginError):
        add(str(tmp_path / "empty"), str(tmp_path / "home"))
