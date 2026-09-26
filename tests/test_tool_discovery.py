"""Node and Git discovery for lanes that need a tool the engine does not ship.

Node order: FLYWHEEL_NODE (``none`` means not found), ``<home>/node_path``, the
Node the frozen build bundles, the user PATH then the machine PATH read from the
registry, the engine's own PATH, then ``%ProgramFiles%\\nodejs``. A Node older
than 20 is skipped when discovered and reported when chosen. Git follows the same
shape with FLYWHEEL_GIT and ``%ProgramFiles%\\Git\\cmd``. The registry and
``node --version`` are injected, so nothing here reads the real machine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness import tool_discovery as td


def _exe(folder: Path, name: str = "node.exe") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"")
    return path


def _versions(mapping: dict[Path, str | None]):
    table = {str(path): version for path, version in mapping.items()}
    return lambda path: table.get(str(path))


def _registry(user: str | None = None, machine: str | None = None):
    return lambda scope: {"user": user, "machine": machine}[scope]


def _env(tmp_path, **extra) -> dict[str, str]:
    return {"FLYWHEEL_HOME": str(tmp_path / "home"), "PATH": "", **extra}


def _find(tmp_path, env, **kw):
    kw.setdefault("read_registry_path", _registry())
    kw.setdefault("platform", "nt")
    return td.find_node(env, **kw)


def test_flywheel_node_none_is_not_found_even_with_a_bundled_node(tmp_path):
    bundled = _exe(tmp_path / "bundled")
    found = _find(tmp_path, _env(tmp_path, FLYWHEEL_NODE="none"), bundled=bundled,
                  node_version=_versions({bundled: "v24.21.0"}))
    assert not found.found and found.source == "disabled" and found.path is None


def test_flywheel_node_names_an_executable_or_its_folder(tmp_path):
    node = _exe(tmp_path / "custom")
    versions = _versions({node: "v22.1.0"})
    for value in (str(node), str(node.parent)):
        found = _find(tmp_path, _env(tmp_path, FLYWHEEL_NODE=value), node_version=versions)
        assert found.found and found.source == "FLYWHEEL_NODE"
        assert found.path == str(node) and found.version == "v22.1.0"


def test_an_old_node_named_by_the_operator_is_reported_not_skipped(tmp_path):
    old, bundled = _exe(tmp_path / "old"), _exe(tmp_path / "bundled")
    found = _find(tmp_path, _env(tmp_path, FLYWHEEL_NODE=str(old)), bundled=bundled,
                  node_version=_versions({old: "v18.20.0", bundled: "v24.21.0"}))
    assert not found.found and found.source == "FLYWHEEL_NODE"
    assert "older than 20" in found.detail


def test_node_path_file_in_home_comes_before_the_bundled_node(tmp_path):
    chosen, bundled = _exe(tmp_path / "chosen"), _exe(tmp_path / "bundled")
    home = tmp_path / "home"
    home.mkdir()
    from harness.lane_settings_route import file_sha256
    (home / "node_path").write_text(f"{chosen}\nsha256={file_sha256(chosen)}\n",
                                    encoding="utf-8")
    found = _find(tmp_path, _env(tmp_path), bundled=bundled,
                  node_version=_versions({chosen: "v20.0.0", bundled: "v24.21.0"}))
    assert found.source == "node_path" and found.path == str(chosen)


def test_the_bundled_node_comes_before_the_registry_path(tmp_path):
    bundled, user = _exe(tmp_path / "bundled"), _exe(tmp_path / "user")
    found = _find(tmp_path, _env(tmp_path), bundled=bundled,
                  read_registry_path=_registry(user=str(user.parent)),
                  node_version=_versions({bundled: "v24.21.0", user: "v22.0.0"}))
    assert found.found and found.source == "bundled" and found.path == str(bundled)


def test_user_path_then_machine_path_from_the_registry(tmp_path):
    user, machine = _exe(tmp_path / "user"), _exe(tmp_path / "machine")
    registry = _registry(user=f"{tmp_path / 'empty'};{user.parent}",
                         machine=str(machine.parent))
    versions = _versions({user: "v20.11.0", machine: "v22.0.0"})
    assert _find(tmp_path, _env(tmp_path), read_registry_path=registry,
                 node_version=versions).source == "user_path"
    registry = _registry(user=None, machine=str(machine.parent))
    found = _find(tmp_path, _env(tmp_path), read_registry_path=registry,
                  node_version=versions)
    assert found.source == "machine_path" and found.path == str(machine)


def test_registry_values_expand_percent_variables_from_the_environment(tmp_path):
    node = _exe(tmp_path / "Programs" / "nodejs")
    env = _env(tmp_path, LOCALAPPDATA=str(tmp_path))
    found = _find(tmp_path, env, read_registry_path=_registry(user=r"%LocalAppData%\Programs\nodejs"),
                  node_version=_versions({node: "v24.0.0"}))
    assert found.found and found.path == str(node)


def test_a_discovered_old_node_is_skipped_for_a_newer_one(tmp_path):
    old, new = _exe(tmp_path / "old"), _exe(tmp_path / "new")
    found = _find(tmp_path, _env(tmp_path),
                  read_registry_path=_registry(user=str(old.parent), machine=str(new.parent)),
                  node_version=_versions({old: "v16.0.0", new: "v20.0.0"}))
    assert found.path == str(new) and found.source == "machine_path"


def test_program_files_is_the_last_place_looked(tmp_path):
    node = _exe(tmp_path / "pf" / "nodejs")
    found = _find(tmp_path, _env(tmp_path, ProgramFiles=str(tmp_path / "pf")),
                  node_version=_versions({node: "v24.1.0"}))
    assert found.source == "program_files" and found.path == str(node)


def test_nothing_found_names_what_was_checked_and_the_old_node_seen(tmp_path):
    old = _exe(tmp_path / "old")
    found = _find(tmp_path, _env(tmp_path), read_registry_path=_registry(user=str(old.parent)),
                  node_version=_versions({old: "v18.0.0"}))
    assert not found.found and found.source == "not_found" and found.path is None
    assert "older than 20" in found.detail and str(old) in found.detail


def test_a_node_that_does_not_answer_version_is_not_found(tmp_path):
    silent = _exe(tmp_path / "silent")
    found = _find(tmp_path, _env(tmp_path, FLYWHEEL_NODE=str(silent)),
                  node_version=_versions({silent: None}))
    assert not found.found and "--version" in found.detail


def test_registry_read_failure_falls_back_to_the_engine_path(tmp_path):
    node = _exe(tmp_path / "engine")

    def broken(scope):
        raise OSError("no registry")

    found = _find(tmp_path, _env(tmp_path, PATH=str(node.parent)), read_registry_path=broken,
                  node_version=_versions({node: "v21.0.0"}))
    assert found.source == "engine_path" and found.path == str(node)


def test_posix_reads_the_engine_path_for_a_plain_node(tmp_path):
    node = _exe(tmp_path / "bin", "node")
    found = td.find_node(_env(tmp_path, PATH=str(node.parent)), platform="posix",
                         read_registry_path=_registry(),
                         node_version=_versions({node: "v20.5.0"}))
    assert found.source == "engine_path" and found.path == str(node)


@pytest.mark.parametrize("version,major", [("v24.21.0", 24), ("20.0.0", 20),
                                           ("v9.1.0\n", 9), ("banana", None), (None, None)])
def test_node_major_parse(version, major):
    assert td.node_major(version) == major


def test_git_none_is_not_found(tmp_path):
    _exe(tmp_path / "pf" / "Git" / "cmd", "git.exe")
    found = td.find_git(_env(tmp_path, FLYWHEEL_GIT="none", ProgramFiles=str(tmp_path / "pf")),
                        read_registry_path=_registry(), platform="nt")
    assert not found.found and found.source == "disabled"


def test_git_from_the_registry_path_before_program_files(tmp_path):
    user = _exe(tmp_path / "usergit", "git.exe")
    pf = _exe(tmp_path / "pf" / "Git" / "cmd", "git.exe")
    env = _env(tmp_path, ProgramFiles=str(tmp_path / "pf"))
    found = td.find_git(env, read_registry_path=_registry(user=str(user.parent)), platform="nt")
    assert found.source == "user_path" and found.path == str(user)
    found = td.find_git(env, read_registry_path=_registry(), platform="nt")
    assert found.source == "program_files" and found.path == str(pf)


def test_finding_serializes_without_anything_but_paths_and_versions(tmp_path):
    node = _exe(tmp_path / "custom")
    row = _find(tmp_path, _env(tmp_path, FLYWHEEL_NODE=str(node)),
                node_version=_versions({node: "v24.21.0"})).to_dict()
    assert row == {"tool": "node", "found": True, "path": str(node), "version": "v24.21.0",
                   "source": "FLYWHEEL_NODE", "minimum": "20", "detail": row["detail"]}


def test_real_node_version_probe_reads_a_live_binary_when_one_exists():
    import shutil
    node = shutil.which("node")
    if node is None:
        pytest.skip("no node on this machine's PATH")
    version = td.node_version(node)
    assert version and td.node_major(version) is not None
