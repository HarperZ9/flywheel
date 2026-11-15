"""The plugin scripts' own hygiene: what a build copies, when a build counts as
a release, and which program the scripts start.

A build copies only the files git tracks, so an ignored .env or an untracked
note in the source folders never ships. A release build also refuses a working
tree with untracked or changed files, and refuses package code that differs
from the release its version names, since Claude Code keeps a user on a plugin
until the version string changes. The scripts start git and python3 only from
an absolute PATH entry outside the working folder.

These cases run in a scratch clone with the user's and the system's git
configuration switched off, so they depend on no local git setting.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from claude_plugin_helpers import ROOT, TEMPLATE, load

build = load("build_claude_plugin")
rules = load("claude_plugin_rules")
smoke = load("smoke_claude_plugin")

FAKE_KEY = "ANTHROPIC_API_KEY=sk-" + "ant-" + "PLANTED-for-a-test-0000\n"
SOURCES = ("claude-plugin", "src/articulate", "LICENSE", ".gitignore")
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "Plugin Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Plugin Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}


def _find():
    return load("find_program")


def _git(repo, *args):
    run = subprocess.run([_find().find_program("git"), *args], cwd=repo, timeout=60,
                         capture_output=True, env=dict(os.environ, **GIT_ENV))
    assert run.returncode == 0, run.stderr.decode("utf-8", "replace")
    return run.stdout.decode("utf-8")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """A git repository holding this repository's tracked plugin sources."""
    repo = tmp_path_factory.mktemp("source") / "repo"
    names = _git(ROOT, "ls-files", "-z", "--", *SOURCES).split("\0")
    for name in filter(None, names):
        if (ROOT / name).is_file():
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_bytes((ROOT / name).read_bytes())
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


@pytest.fixture
def repo(base, tmp_path, monkeypatch):
    for name, value in GIT_ENV.items():
        monkeypatch.setenv(name, value)
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(base), str(clone))
    return clone


def _shipped(out):
    return {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}


def test_untracked_and_ignored_files_do_not_ship(repo, tmp_path):
    (repo / "src" / "articulate" / ".env").write_text(FAKE_KEY, encoding="utf-8")
    (repo / "claude-plugin" / "scratch-notes.md").write_text("draft\n", encoding="utf-8")
    assert "src/articulate/.env" not in _git(repo, "status", "--porcelain")
    out = tmp_path / "out"
    build.build(out, repo=repo)
    shipped = _shipped(out)
    assert "src/articulate/.env" not in shipped and "scratch-notes.md" not in shipped
    assert "server/serve.py" in shipped and "src/articulate/local_mcp.py" in shipped
    assert rules.check_bundle(out) == []


def test_a_release_build_names_untracked_and_changed_files(repo):
    _git(repo, "tag", "v" + rules.bundled_version(repo))
    assert build.release_problems(repo) == []
    (repo / "claude-plugin" / "scratch-notes.md").write_text("draft\n", encoding="utf-8")
    with open(repo / "src" / "articulate" / "mcp_server.py", "a", encoding="utf-8") as fh:
        fh.write("# an edit\n")
    problems = " ".join(build.release_problems(repo))
    assert "claude-plugin/scratch-notes.md" in problems
    assert "src/articulate/mcp_server.py" in problems


def test_a_release_build_refuses_a_missing_version_tag(repo, monkeypatch, tmp_path,
                                                     capsys):
    tag = "v" + rules.bundled_version(repo)
    assert not _git(repo, "tag", "--list", tag).strip()
    monkeypatch.setattr(build, "REPO", repo)
    out = tmp_path / "out"
    assert build.main([str(out)]) == 1
    assert not out.exists(), "a missing release tag must stop before writing"
    diagnostic = capsys.readouterr().out
    assert tag in diagnostic and "fetch" in diagnostic
    assert "--dev" in diagnostic


def test_a_release_build_refuses_code_that_differs_from_its_version_tag(repo):
    tag = "v" + rules.bundled_version(repo)
    _git(repo, "tag", tag)
    assert build.release_problems(repo) == [], "a build at its own tag must pass"
    with open(repo / "src" / "articulate" / "mcp_server.py", "a", encoding="utf-8") as fh:
        fh.write("# a change after the release\n")
    _git(repo, "commit", "-q", "-am", "change after the release")
    problems = " ".join(build.release_problems(repo))
    assert f"differs from the {tag} release" in problems, problems


def test_the_command_stops_before_writing_when_a_release_check_fails(monkeypatch,
                                                                      tmp_path):
    monkeypatch.setattr(build, "release_problems", lambda repo: ["planted problem"])
    out = tmp_path / "out"
    assert build.main([str(out)]) == 1
    assert not out.exists()


def test_a_dev_build_skips_the_release_checks(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "release_problems", lambda repo: ["planted problem"])
    out = tmp_path / "out"
    assert build.main([str(out), "--dev"]) == 0
    assert rules.check_bundle(out) == []


def _plant(folder, name):
    """A file named like a program that writes nothing and exits 1."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + (".exe" if os.name == "nt" else ""))
    path.write_bytes(b"#!/bin/sh\nexit 1\n")
    path.chmod(0o755)
    return path


def test_program_lookup_skips_the_working_folder(tmp_path, monkeypatch):
    planted = _plant(tmp_path, "python3")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", os.pathsep.join([".", str(tmp_path), os.environ["PATH"]]))
    found = _find().find_program("python3")
    assert found is None or Path(found).resolve() != planted.resolve(), found


def test_program_lookup_finds_a_program_on_an_absolute_entry(tmp_path, monkeypatch):
    """Control: the same planted file is found when the working folder is elsewhere,
    so the case above tests the working-folder rule."""
    planted = _plant(tmp_path / "bin", "python3")
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.setenv("PATH", os.pathsep.join([str(tmp_path / "bin"), os.environ["PATH"]]))
    assert Path(_find().find_program("python3")).resolve() == planted.resolve()


def test_the_smoke_run_never_starts_python3_from_the_working_folder(tmp_path, monkeypatch):
    planted = _plant(tmp_path, "python3")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", os.pathsep.join([".", os.environ["PATH"]]))
    try:
        argv, _env = smoke.launch_spec(TEMPLATE)
    except SystemExit as stop:          # no python3 on this PATH at all
        assert "python3" in str(stop)
        return
    assert Path(argv[0]).is_absolute(), argv[0]
    assert Path(argv[0]).resolve() != planted.resolve()


def test_the_smoke_run_takes_an_explicit_interpreter_as_given():
    argv, _env = smoke.launch_spec(TEMPLATE, command=sys.executable)
    assert argv[0] == sys.executable


def test_the_server_closure_follows_every_import_statement(tmp_path):
    """Control for the bundle's module list: an import inside a function counts,
    a chain of imports is followed, and a module nothing imports stays out."""
    package = tmp_path / "articulate"
    package.mkdir()
    files = {"__init__.py": "from .version import VERSION\n",
             "version.py": "VERSION = '1'\n",
             "local_mcp.py": "import json\n\ndef run():\n    from . import cli\n",
             "cli.py": "from .util import helper\nimport articulate.extra as extra\n",
             "util.py": "helper = 1\n", "extra.py": "", "orphan.py": "import os\n"}
    for name, text in files.items():
        (package / name).write_text(text, encoding="utf-8")
    found = build.server_closure(package, sorted(files), skip=())
    assert found == {"__init__", "version", "local_mcp", "cli", "util", "extra"}
    # A skipped module stays out, and so does what only it imports.
    assert build.server_closure(package, sorted(files), skip=("cli",)) == {
        "__init__", "version", "local_mcp"}
