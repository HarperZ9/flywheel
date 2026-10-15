"""Falsifiers for `flywheel plugin` and plugin loading in `flywheel code`."""
import json
import subprocess
import sys

from harness.code_session import plugin_cli, slash
from harness.code_session.agents import load_agents
from harness.code_session.commands import load_commands
from harness.code_session.hooks import load as load_hooks
from harness.code_session.mcp_config import load_specs
from harness.code_session.plugins import PluginError, install, plugin_roots, remove
from harness.code_session.skills import load_skills


def _plugin(tmp_path, name="kit"):
    src = tmp_path / "src"
    (src / ".claude-plugin").mkdir(parents=True)
    (src / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    (src / "commands").mkdir()
    (src / "commands" / "ship.md").write_text("Ship it: $ARGUMENTS", encoding="utf-8")
    (src / "agents").mkdir()
    (src / "agents" / "rev.md").write_text("---\nname: rev\n---\nReview.", encoding="utf-8")
    (src / "skills" / "deploy").mkdir(parents=True)
    (src / "skills" / "deploy" / "SKILL.md").write_text("---\nname: deploy\ndescription: d\n---\nx",
                                                       encoding="utf-8")
    (src / "hooks").mkdir()
    (src / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "echo done"}]}]}}), encoding="utf-8")
    (src / ".mcp.json").write_text(json.dumps({"mcpServers": {"kitsrv": {"command": "kit-mcp"}}}),
                                   encoding="utf-8")
    return src


def test_install_shows_programs_and_everything_loads(tmp_path):
    home = str(tmp_path / "home")
    seen = {}
    rec = install(str(_plugin(tmp_path)), home, confirm=lambda n, info: seen.update(info) or True)
    assert rec["name"] == "kit" and seen["hooks"] == ["Stop: echo done"]
    assert seen["mcp_servers"] == ["kitsrv: kit-mcp"] and seen["commands"] == 1
    work = tmp_path / "work"
    work.mkdir()
    assert "ship" in load_commands(str(work), home)
    assert "rev" in load_agents(str(work), home)
    assert "deploy" in load_skills(str(work), home)
    specs, _ = load_specs(str(work), home)
    assert [(s.name, s.trusted) for s in specs] == [("kitsrv", True)]
    entries, _, _ = load_hooks(str(work), home)
    assert [e.command for e in entries] == ["echo done"]


def test_declining_installs_nothing(tmp_path):
    home = str(tmp_path / "home")
    try:
        install(str(_plugin(tmp_path)), home, confirm=lambda n, i: False)
    except PluginError:
        pass
    assert plugin_roots(home) == []


def test_remove_and_unsafe_names(tmp_path):
    home = str(tmp_path / "home")
    install(str(_plugin(tmp_path)), home)
    assert remove("kit", home) and plugin_roots(home) == []
    assert not remove("../etc", home)
    bad = _plugin(tmp_path / "b", name="../escape")
    try:
        install(str(bad), home)
    except PluginError as e:
        assert "safe folder name" in str(e)
    else:
        raise AssertionError("unsafe name accepted")


def test_install_from_a_git_repository_records_the_commit(tmp_path):
    src = _plugin(tmp_path)
    for args in (["init", "-q"], ["config", "user.email", "t@e.org"], ["config", "user.name", "t"],
                 ["add", "-A"], ["commit", "-qm", "p"]):
        subprocess.run(["git", *args], cwd=src, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True,
                          text=True).stdout.strip()
    rec = install(src.as_uri(), str(tmp_path / "home"))
    assert rec["source"].endswith("@" + head) and rec["commands"] == 1
    assert not (tmp_path / "home" / "code-plugins" / "kit" / ".git").exists()


def test_cli_list_and_yes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(plugin_cli, "_home", lambda: str(tmp_path / "home"))
    assert plugin_cli.main(["install", str(_plugin(tmp_path)), "--yes"]) == 0
    capsys.readouterr()
    plugin_cli.main(["list"])
    assert "kit" in capsys.readouterr().out
    from harness import cli_entry
    assert cli_entry._PACKAGED["plugin"] == "harness.code_session.plugin_cli"
