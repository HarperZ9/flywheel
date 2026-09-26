"""The frozen engine's own lane child modes.

``--lane-mcp writing`` serves the Writing Workspace MCP from the engine itself,
pinned to the Flywheel home. ``--bundled-lane-cli <lane> ...`` runs a payload
lane's CLI for the native screens: only listed subcommands, ``--version`` and
``index router-job --help``, after the same admission as ``--bundled-lane-mcp``,
with stdout and stderr in UTF-8 so a non-ASCII feed title cannot crash it on a
Windows code page.
"""
from __future__ import annotations

import ast
import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest

from harness import frozen_lane_modes as flm
from harness.bundled_lane_admission import BundledLaneAdmission

REPO = Path(__file__).resolve().parents[1]


def _load_gateway_entry():
    spec = importlib.util.spec_from_file_location(
        "gateway_entry_lane_modes_test", REPO / "packaging" / "gateway_entry.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def admitted(monkeypatch):
    calls = []

    def admit(name, **kwargs):
        calls.append(name)
        return BundledLaneAdmission(object(), {"name": name}, ())
    monkeypatch.setattr(flm, "admit_bundled_lane", admit)
    return calls


@pytest.fixture
def fake_cli(monkeypatch):
    """Replace each lane CLI module with a recorder."""
    seen = []
    for lane, (module_name, _callable, _subs) in flm.LANE_CLIS.items():
        module = ModuleType(module_name)
        module.main = lambda argv, lane=lane: seen.append((lane, list(argv))) or 0
        monkeypatch.setitem(sys.modules, module_name, module)
    return seen


def _cp1252_streams(monkeypatch):
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    err = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    return out, err


def test_lane_mcp_writing_serves_pinned_to_the_flywheel_home(monkeypatch, tmp_path):
    import harness.writing_mcp as writing_mcp
    seen = {}
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(writing_mcp, "serve",
                        lambda **kw: seen.update(kw) or 17)
    assert flm.dispatch_lane_mcp(["--lane-mcp", "writing"]) == 17
    assert Path(seen["operator_home"]) == (tmp_path / "home").resolve()


@pytest.mark.parametrize("argv", [
    ["--lane-mcp"], ["--lane-mcp", "gather"], ["--lane-mcp", "writing", "--home", "x"],
    ["--lane-mcp", "../writing"],
])
def test_lane_mcp_refuses_anything_but_the_exact_writing_mode(argv):
    assert flm.dispatch_lane_mcp(argv) == 2


def test_other_argv_is_not_a_lane_mode():
    assert flm.dispatch_lane_mcp(["--port", "0"]) is None
    assert flm.dispatch_bundled_lane_cli(["--port", "0"]) is None
    assert flm.dispatch_bundled_lane_cli([]) is None


def test_writing_mcp_is_a_static_import_so_it_enters_the_frozen_archive():
    tree = ast.parse((REPO / "harness" / "frozen_lane_modes.py").read_text(encoding="utf-8"))
    names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
             for alias in node.names}
    assert "writing_mcp" in names
    entry = ast.parse((REPO / "packaging" / "gateway_entry.py").read_text(encoding="utf-8"))
    imported = {f"{node.module}.{alias.name}" for node in ast.walk(entry)
                if isinstance(node, ast.ImportFrom) for alias in node.names}
    assert "harness.frozen_lane_modes" in imported


@pytest.mark.parametrize("lane,args", [
    ("gather", ["feed", "https://example.invalid/feed", "--json"]),
    ("gather", ["arxiv", "q", "--json"]),
    ("crucible", ["assess", "t.md", "--json"]),
    ("chorus", ["run", "corpus", "--verify"]),
    ("chorus", ["corpora", "root"]),
    ("chorus", ["digests", "store", "--limit", "5"]),
    ("index", ["map", "--json", "--root", "r"]),
    ("index", ["graph", "--json"]),
    ("index", ["symbols", "--json"]),
    ("index", ["router-job", "--help"]),
    ("index", ["--version"]),
    ("gather", ["--version"]),
])
def test_listed_subcommands_run_after_admission(lane, args, admitted, fake_cli):
    assert flm.dispatch_bundled_lane_cli(["--bundled-lane-cli", lane, *args]) == 0
    assert admitted == [lane]
    assert fake_cli == [(lane, args)]


@pytest.mark.parametrize("argv", [
    ["--bundled-lane-cli"],
    ["--bundled-lane-cli", "gather"],
    ["--bundled-lane-cli", "relay", "--version"],
    ["--bundled-lane-cli", "Gather", "--version"],
    ["--bundled-lane-cli", "gather", "run", "x"],
    ["--bundled-lane-cli", "gather", "mcp"],
    ["--bundled-lane-cli", "index", "router-job", "start", "r"],
    ["--bundled-lane-cli", "index", "router-job"],
    ["--bundled-lane-cli", "index", "--version", "extra"],
    ["--bundled-lane-cli", "crucible", "-m", "os"],
])
def test_unlisted_argv_is_refused_before_admission(argv, admitted, fake_cli):
    assert flm.dispatch_bundled_lane_cli(argv) == 2
    assert admitted == [] and fake_cli == []


def test_a_lane_that_fails_admission_never_runs_its_cli(monkeypatch, fake_cli):
    monkeypatch.setattr(flm, "admit_bundled_lane", lambda name, **kw: BundledLaneAdmission(
        None, None, ("bundled_descriptor_digest_mismatch",)))
    assert flm.dispatch_bundled_lane_cli(["--bundled-lane-cli", "gather", "--version"]) == 2
    assert fake_cli == []


def test_cli_exit_through_system_exit_returns_its_code(monkeypatch, admitted):
    module = ModuleType("gather.cli")

    def main(argv):
        raise SystemExit(0 if argv == ["--version"] else 3)
    module.main = main
    monkeypatch.setitem(sys.modules, "gather.cli", module)
    assert flm.dispatch_bundled_lane_cli(["--bundled-lane-cli", "gather", "--version"]) == 0
    assert flm.dispatch_bundled_lane_cli(["--bundled-lane-cli", "gather", "arxiv", "q"]) == 3


def test_non_ascii_output_survives_a_cp1252_pipe(monkeypatch, admitted):
    out, err = _cp1252_streams(monkeypatch)
    module = ModuleType("gather.cli")
    title = "Überblick ✓ 漢字"

    def main(argv):
        print(title)
        print(title, file=sys.stderr)
        return 0
    module.main = main
    monkeypatch.setitem(sys.modules, "gather.cli", module)
    assert flm.dispatch_bundled_lane_cli(
        ["--bundled-lane-cli", "gather", "feed", "u", "--json"]) == 0
    sys.stdout.flush()
    sys.stderr.flush()
    assert out.buffer.getvalue().decode("utf-8").strip() == title
    assert err.buffer.getvalue().decode("utf-8").strip() == title


def test_gateway_entry_routes_the_lane_modes_before_the_gateway(monkeypatch):
    import harness.bundled_lane_admission as bundled
    import harness.gateway as gateway
    monkeypatch.setattr(bundled, "dispatch_bundled_lane_mcp", lambda argv: None)
    monkeypatch.setattr(gateway, "main", lambda argv: (_ for _ in ()).throw(
        AssertionError("a lane mode reached the gateway")))
    monkeypatch.setattr(flm, "dispatch_lane_mcp",
                        lambda argv: 5 if argv[:1] == ["--lane-mcp"] else None)
    monkeypatch.setattr(flm, "dispatch_bundled_lane_cli",
                        lambda argv: 6 if argv[:1] == ["--bundled-lane-cli"] else None)
    module = _load_gateway_entry()
    assert module.main(["--lane-mcp", "writing"]) == 5
    assert module.main(["--bundled-lane-cli", "gather", "--version"]) == 6
    assert module.main(["-m", "harness.writing_mcp"]) == 2
