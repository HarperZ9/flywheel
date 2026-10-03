"""Each shipped spawn and lookup site against every way a PATH can reach a plant.

test_spawn_sites_resolve plants a program in the working folder and in one PATH
folder. Here the plant sits behind each PATH form that leads back into the
working folder on Windows: a relative entry, a ``.`` entry, a junction, a
drive-relative entry (``C:tools``), a quoted entry, a quoted relative entry, a
long-path (``\\\\?\\``) entry and a case-changed entry. subprocess is replaced by a
recorder, so nothing starts; every recorded argv must name the copy in the
absolute PATH folder that follows. Each vector first shows shutil.which finding
the plant, so a pass is not an unreachable plant. Sites whose program name comes
from configuration also get a drive-relative and a relative name, and must not
start anything from the working folder.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from test_spawn_sites_resolve import NAMES, SITES, _exe, same
from test_which_sites_resolve import LOOKUPS

WINDOWS = os.name == "nt"
pytestmark = pytest.mark.skipif(not WINDOWS, reason="Windows PATH forms")


def _junction(link: Path, target: Path) -> None:
    import _winapi
    _winapi.CreateJunction(str(target), str(link))


def _entry(vector: str, work: Path, tmp: Path) -> str:
    """The PATH entry for ``vector``; the plant sits in work/rel."""
    rel = work / "rel"
    if vector == "relative":
        return "rel"
    if vector == "dot":
        return "."
    if vector == "junction":
        _junction(tmp / "jn", rel)
        return str(tmp / "jn")
    if vector == "drive-relative":
        return f"{work.drive}rel"
    if vector == "quoted":
        return f'"{rel}"'
    if vector == "quoted-relative":
        return '"rel"'
    if vector == "long-path":
        return "\\\\?\\" + str(rel)
    if vector == "case":
        return str(rel).upper()
    raise AssertionError(vector)


VECTORS = ("relative", "dot", "junction", "drive-relative", "quoted", "quoted-relative",
           "long-path", "case")


def _plant_folder(vector: str, work: Path) -> Path:
    return work if vector == "dot" else work / "rel"


def _reaches(vector: str, entry: str, work: Path, tmp: Path) -> bool:
    """Control: an unguarded reader follows ``entry`` to the plant folder.

    shutil.which reads most forms. It keeps the quotes of a quoted entry, which
    cmd.exe strips, so a quoted form is shown by cmd.exe starting a batch file
    planted there, from a working folder outside the plant.
    """
    folder = _plant_folder(vector, work)
    if not vector.startswith("quoted"):
        (folder / "fwreach.exe").write_bytes(b"MZ")
        return bool(shutil.which("fwreach", path=entry))
    marker = tmp / "reach.txt"
    (folder / "fwreach.cmd").write_text(f'@echo ran> "{marker}"\r\n', encoding="utf-8")
    env = {**os.environ, "PATH": entry}
    env.pop("NoDefaultCurrentDirectoryInExePath", None)
    subprocess.run("fwreach", shell=True, cwd=str(work if vector != "quoted" else tmp),
                   env=env, capture_output=True)
    return marker.exists()


@pytest.fixture
def recorder(monkeypatch):
    """Call it to replace subprocess with a recorder; it returns the recorded argvs."""
    seen: list = []

    class FakeProc:
        def __init__(self, args, *rest, **kwargs):
            import io
            seen.append(args)
            text = bool(kwargs.get("text") or kwargs.get("encoding")
                        or kwargs.get("universal_newlines"))
            self.args, self.pid, self.returncode = args, 0, 0
            self.stdin = io.StringIO() if text else io.BytesIO()
            self.stdout = io.StringIO("") if text else io.BytesIO(b"")
            self.stderr = io.StringIO("") if text else io.BytesIO(b"")

        def communicate(self, input=None, timeout=None):
            return self.stdout.read(), self.stderr.read()

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

        terminate = kill

    def fake_run(args, *rest, **kwargs):
        seen.append(args)
        text = bool(kwargs.get("text") or kwargs.get("encoding"))
        return subprocess.CompletedProcess(args, 0, stdout="" if text else b"",
                                           stderr="" if text else b"")

    def install() -> list:
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(subprocess, "Popen", FakeProc)
        monkeypatch.setattr(subprocess, "check_output",
                            lambda args, *a, **k: seen.append(args) or (
                                "" if k.get("text") else b""))
        return seen
    return install


@pytest.fixture
def layout(tmp_path, monkeypatch):
    work, bin_ = tmp_path / "work", tmp_path / "bin"
    (work / "rel").mkdir(parents=True)
    monkeypatch.chdir(work)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return work, bin_, tmp_path


@pytest.mark.parametrize("vector", VECTORS)
@pytest.mark.parametrize("site", sorted(SITES))
def test_a_spawn_site_skips_every_path_form_that_reaches_the_plant(site, vector, layout,
                                                                  recorder, monkeypatch):
    work, bin_, tmp = layout
    for name in NAMES:
        _exe(_plant_folder(vector, work), name)
        _exe(bin_, name)
    entry = _entry(vector, work, tmp)
    monkeypatch.setenv("PATH", os.pathsep.join((entry, str(bin_))))
    name, call = SITES[site]
    assert _reaches(vector, entry, work, tmp), f"control: {vector} must reach the plant"
    seen = recorder()
    try:
        call(work)
    except Exception:
        pass  # the recorded argv is the evidence
    assert seen, f"{site} never reached subprocess"
    for argv in seen:
        assert not isinstance(argv, str), f"{site} ran a shell string: {argv!r}"
        assert same(argv[0], bin_ / f"{name}.exe"), f"{site} via {vector} started {argv[0]!r}"


@pytest.mark.parametrize("vector", VECTORS)
@pytest.mark.parametrize("site", sorted(LOOKUPS))
def test_a_lookup_site_skips_every_path_form_that_reaches_the_plant(site, vector, layout,
                                                                   monkeypatch):
    work, _bin, tmp = layout
    name, lookup = LOOKUPS[site]
    _exe(_plant_folder(vector, work), name)
    empty = tmp / "empty"
    empty.mkdir()
    entry = _entry(vector, work, tmp)
    monkeypatch.setenv("PATH", os.pathsep.join((entry, str(empty))))
    if site == "tool discovery git":
        pytest.skip("reads its own PATH argument; covered by the next test")
    assert _reaches(vector, entry, work, tmp), f"control: {vector} must reach the plant"
    assert not lookup(), f"{site} found the planted {name} via {vector}"


@pytest.mark.parametrize("vector", VECTORS)
def test_tool_discovery_walks_no_path_form_that_reaches_the_plant(vector, layout):
    from harness import tool_discovery
    work, _bin, tmp = layout
    _exe(_plant_folder(vector, work), "git")
    env = {"PATH": _entry(vector, work, tmp)}
    assert _reaches(vector, env["PATH"], work, tmp), f"control: {vector} must reach the plant"
    found = tool_discovery.find_git(env, read_registry_path=lambda _scope: None).found
    assert not found, f"tool discovery found the planted git via {vector}"


def _configured(name: str):
    """Sites whose program name comes from configuration, given ``name``."""
    from harness.accountable_hooks import subprocess_runner
    from harness.authority_registry import _command_resolver
    from harness.child_stdio import spawn
    from harness.dap_policy import _spawn_detached
    from harness.endpoints import CliBackend
    from harness.lane_cli import run_lane_cli
    from harness.lean_replay import run_killable
    from harness.mcp_client import LaunchSpec, StdioTransport
    from harness.verified_bench import subprocess_gate
    root = Path.cwd()
    return {
        "mcp launch spec": lambda: StdioTransport(LaunchSpec((name, "serve"), cwd=str(root))),
        "mcp argv": lambda: StdioTransport([name, "serve"]),
        "stdio protocol server": lambda: spawn([name], root),
        "debug adapter launch": lambda: _spawn_detached([name], root, None),
        "cli endpoint": lambda: CliBackend("probe", [name, "{prompt}"]).chat(
            [{"role": "user", "content": "hi"}], system="", max_tokens=1,
            temperature=0.0, seed=0),
        "accountable hook": lambda: subprocess_runner()([name]),
        "command authority": lambda: _command_resolver(
            {"argv": [name]}, root, True, 5.0, None)("answer"),
        "verified bench gate": lambda: subprocess_gate(f"{name} --check", "p", workspace=root),
        "lane cli": lambda: run_lane_cli("gather", ["--version"], prefix=[name], timeout=5),
        "lean replay": lambda: run_killable([name]),
    }


@pytest.mark.parametrize("form", ["drive-relative", "relative", "dot-relative"])
@pytest.mark.parametrize("site", sorted(_configured("x")))
def test_a_configured_name_that_points_into_the_working_folder_starts_nothing_there(
        site, form, layout, recorder, monkeypatch):
    work, bin_, _tmp = layout
    _exe(work / "rel", "fwprog")
    _exe(work, "fwprog")
    _exe(bin_, "fwprog")
    monkeypatch.setenv("PATH", str(bin_))
    name = {"drive-relative": f"{work.drive}fwprog",
            "relative": "rel\\fwprog", "dot-relative": ".\\fwprog"}[form]
    seen = recorder()
    for program in (name, "fwprog"):  # the second is the control: the site does start
        try:
            _configured(program)[site]()
        except Exception:
            pass
    assert seen, f"{site} never reached subprocess"
    inside = os.path.normcase(os.path.realpath(work))
    for argv in seen:
        started = os.path.normcase(os.path.realpath(argv[0] if not isinstance(argv, str)
                                                    else argv.split()[0]))
        assert not started.startswith(inside), f"{site} started {started} from the working folder"
        assert same(started, bin_ / "fwprog.exe"), f"{site} started {started}"
