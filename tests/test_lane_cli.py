"""Native screens run lane CLIs through one launcher, dev and frozen alike.

In a source or pip install the feeds, science bench, discourse and workspace map
screens run the lane's console script (or ``python -m <module>``). A frozen
engine has neither, so the same calls go through ``<engine.exe>
--bundled-lane-cli <lane> ...``. Every run starts in ``<home>/lanes/<lane>/``,
hides its console window on Windows, decodes stdout as UTF-8 and tells a Python
child to write UTF-8, so a non-ASCII feed title survives a Windows code-page
pipe. No test uses a real key: the planted value below is a fake.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from harness import lane_cli
from harness.frozen_lane_modes import LANE_CLI_FLAG, LANE_CLIS

FAKE_KEY = "sk-test-planted-not-a-real-key"
TITLE = "Caf\u00e9 \u2013 na\u00efve \u6f22\u5b57 \u00fcber"
_FEED_CHILD = (
    "import json, os, sys\n"
    "doc = {'items': [{'id': 'n1', 'title': %r, 'url': 'https://x/n1'}],\n"
    "       'cwd': os.getcwd(), 'argv': sys.argv[1:],\n"
    "       'path': os.environ.get('PATH', ''),\n"
    "       'key': 'OPENROUTER_API_KEY' in os.environ}\n"
    "print(json.dumps(doc, ensure_ascii=False))\n" % TITLE)


class _Capture:
    """Stands in for subprocess.run and keeps each call's argv and kwargs."""

    def __init__(self, stdout="{}"):
        self.calls, self.stdout = [], stdout

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append((list(cmd), kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=self.stdout, stderr="")


@pytest.fixture
def registry(tmp_path, monkeypatch):
    import harness.lanes as ln
    path = tmp_path / "lanes.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", path)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    for name in ("PYTHONUTF8", "PYTHONIOENCODING"):
        monkeypatch.delenv(name, raising=False)
    return path


def _feed_child(tmp_path) -> Path:
    script = tmp_path / "fake_lane_cli.py"
    script.write_text(_FEED_CHILD, encoding="utf-8")
    return script


def _home() -> Path:
    return Path(os.environ["FLYWHEEL_HOME"]).resolve()


# -- which argv each mode runs -------------------------------------------------

def test_dev_argv_prefers_the_console_script_then_the_module():
    found = lane_cli.lane_cli_argv("gather", frozen=False, which=lambda n: f"/bin/{n}")
    assert found == ["/bin/gather"]
    module = lane_cli.lane_cli_argv("index", frozen=False, which=lambda n: None,
                                    importable=lambda m: True)
    assert module == [sys.executable, "-m", "index_graph.cli"]
    assert lane_cli.lane_cli_argv("chorus", frozen=False, which=lambda n: None,
                                  importable=lambda m: False) is None


@pytest.mark.parametrize("lane", sorted(LANE_CLIS))
def test_frozen_argv_is_the_engine_self_child(lane):
    exe = "C:/Program Files/Flywheel/flywheel-gateway.exe"
    argv = lane_cli.lane_cli_argv(lane, frozen=True, executable=exe)
    assert argv == [exe, LANE_CLI_FLAG, lane]
    assert "-m" not in argv
    assert lane_cli.module_argv(lane, frozen=True) is None


def test_frozen_argv_for_a_lane_without_a_cli_mode_is_none():
    assert lane_cli.lane_cli_argv("mneme", frozen=True, executable="x.exe") is None
    assert lane_cli.lane_cli_argv("mneme", frozen=False, which=lambda n: "/bin/x") is None


# -- how a run starts ------------------------------------------------------------

def test_run_starts_in_the_lane_folder_hidden_and_utf8(registry, monkeypatch):
    capture = _Capture()
    monkeypatch.setattr(lane_cli.subprocess, "run", capture)
    lane_cli.run_lane_cli("gather", ["feed", "https://x", "--json"], timeout=5,
                          prefix=["gather"])
    ((argv, kwargs),) = capture.calls
    assert argv == ["gather", "feed", "https://x", "--json"]
    folder = _home() / "lanes" / "gather"
    assert Path(kwargs["cwd"]) == folder and folder.is_dir()
    assert kwargs["encoding"] == "utf-8" and kwargs["timeout"] == 5
    assert kwargs["env"]["PYTHONUTF8"] == "1"
    assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
    assert "OPENROUTER_API_KEY" not in kwargs["env"]
    if os.name == "nt":
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_bundled_run_refuses_an_unlisted_subcommand_without_spawning(registry, monkeypatch):
    capture = _Capture()
    monkeypatch.setattr(lane_cli.subprocess, "run", capture)
    prefix = ["C:/F/flywheel-gateway.exe", LANE_CLI_FLAG, "index"]
    with pytest.raises(lane_cli.LaneCliUnavailable) as err:
        lane_cli.run_lane_cli("index", ["router-job", "start"], timeout=5, prefix=prefix)
    assert err.value.code == "not_in_build"
    assert capture.calls == []
    lane_cli.run_lane_cli("index", ["router-job", "--help"], timeout=5, prefix=prefix)
    assert len(capture.calls) == 1


def test_frozen_run_without_a_cli_mode_is_not_in_build(registry, monkeypatch):
    monkeypatch.setattr(lane_cli, "lane_cli_argv", lambda lane, **kw: None)
    monkeypatch.setattr(lane_cli, "is_frozen", lambda: True)
    with pytest.raises(lane_cli.LaneCliUnavailable) as err:
        lane_cli.run_lane_cli("gather", ["feed", "u"], timeout=5)
    assert err.value.code == "not_in_build"


def test_bundled_env_is_the_small_child_set_plus_the_grant(registry, monkeypatch):
    registry.write_text(json.dumps({"gather": {"env_allow": ["ANTHROPIC_API_KEY"]}}),
                        encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("FLYWHEEL_GIT", "none")
    env = lane_cli.lane_cli_environment("gather", {"JOB_DIR": "j"}, bundled=True)
    assert env["ANTHROPIC_API_KEY"] == FAKE_KEY          # granted by name
    assert "OPENROUTER_API_KEY" not in env                 # never granted
    assert Path(env["FLYWHEEL_HOME"]) == _home()
    assert env["JOB_DIR"] == "j" and env["PYTHONUTF8"] == "1"
    if os.name == "nt":
        assert env["PATH"].lower().endswith("system32")


# -- a non-ASCII feed title end to end ---------------------------------------------

def test_non_ascii_feed_title_reaches_live_feeds_intact(registry, tmp_path, monkeypatch):
    from harness import live_feeds
    script = _feed_child(tmp_path)
    monkeypatch.setattr(lane_cli, "lane_cli_argv",
                        lambda lane, **kw: [sys.executable, str(script)])
    doc = live_feeds.live_feeds(domain="art")
    assert doc["errors"] == {}
    assert [item["title"] for item in doc["items"]] == [TITLE]


@pytest.mark.skipif(os.name != "nt", reason="the code-page pipe is Windows only")
def test_control_the_same_child_fails_on_a_code_page_pipe(registry, tmp_path):
    """The fixture is strong enough: run bare, with no UTF-8 setting, it breaks."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    proc = subprocess.run([sys.executable, str(_feed_child(tmp_path))],
                          capture_output=True, env=env)
    broken = proc.returncode != 0 or TITLE.encode("utf-8") not in proc.stdout
    assert broken


def test_frozen_shaped_child_gets_utf8_lane_folder_and_system_path(registry, tmp_path,
                                                                    monkeypatch):
    monkeypatch.setenv("FLYWHEEL_GIT", "none")
    script = _feed_child(tmp_path)
    prefix = [sys.executable, str(script), LANE_CLI_FLAG, "gather"]
    proc = lane_cli.run_lane_cli("gather", ["feed", "https://x", "--json"],
                                 timeout=30, prefix=prefix)
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["items"][0]["title"] == TITLE
    assert Path(doc["cwd"]).resolve() == _home() / "lanes" / "gather"
    assert doc["argv"][-3:] == ["feed", "https://x", "--json"]
    assert doc["key"] is False
    if os.name == "nt":
        assert doc["path"].lower().endswith("system32")


# -- the bridges use it ------------------------------------------------------------

def test_science_bench_and_feeds_route_through_the_launcher(registry, monkeypatch):
    from harness import live_feeds, science_bench
    seen = []
    monkeypatch.setattr(lane_cli, "run_lane_cli", lambda lane, args, **kw: seen.append(
        (lane, list(args))) or subprocess.CompletedProcess(args, 0, "{}", ""))
    live_feeds._shell(["gather", "feed", "u", "--json"])
    science_bench._shell(["crucible", "assess", "t.json", "--json"])
    assert seen == [("gather", ["feed", "u", "--json"]),
                    ("crucible", ["assess", "t.json", "--json"])]


def test_bridges_pass_absolute_paths_since_the_child_runs_elsewhere(registry, tmp_path,
                                                                     monkeypatch):
    from harness import chorus_bridge, index_bridge
    (tmp_path / "repo").mkdir()
    (tmp_path / "corpus.jsonl").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    capture = _Capture(stdout=json.dumps({"verified": True}))
    monkeypatch.setattr(lane_cli.subprocess, "run", capture)
    monkeypatch.setattr(index_bridge, "_index_argv", lambda: ["index"])
    monkeypatch.setattr(chorus_bridge, "_chorus_argv", lambda: ["chorus"])
    index_bridge.index_view("repo", "map")
    chorus_bridge.discourse_digest("corpus.jsonl")
    (index_argv, _), (chorus_argv, _) = capture.calls
    assert index_argv[-1] == str((tmp_path / "repo").resolve())
    assert chorus_argv[2] == str((tmp_path / "corpus.jsonl").resolve())


def test_index_jobs_report_not_in_build_on_a_frozen_engine(registry, tmp_path, monkeypatch):
    from harness import index_jobs
    capture = _Capture(stdout="index 2.12.0")
    monkeypatch.setattr(lane_cli.subprocess, "run", capture)
    monkeypatch.setattr(index_jobs, "_index_argv",
                        lambda: ["C:/F/flywheel-gateway.exe", LANE_CLI_FLAG, "index"])
    monkeypatch.setattr(index_jobs, "_module_argv", lambda: None)
    (tmp_path / "repo").mkdir()
    out = index_jobs.start_workspace_map(tmp_path / "repo", run_root=tmp_path / "run")
    assert out["error_type"] == "NOT_IN_BUILD"
    assert all(argv[3:4] != ["router-job"] or argv[4:5] == ["--help"]
               for argv, _ in capture.calls)


def test_frozen_index_module_fallback_is_never_dash_m(monkeypatch):
    from harness import index_jobs
    monkeypatch.setattr(lane_cli, "is_frozen", lambda: True)
    assert index_jobs._module_argv() is None
