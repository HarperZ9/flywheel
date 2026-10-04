"""The frozen gateway carries every adapter-lane module (scripts/frozen_adapter_imports.py).

``harness.lanes`` imports an adapter lane's module from its registry string, so
PyInstaller does not see it. In 1.3.3 the raw lane's adapter was left out of the
Windows freeze, ``/api/lanes`` failed there, and the tag-only frozen smoke
reported ``RELAY_ROSTER_HTTP``. These checks run in PR CI: they tie the hidden
imports to the registry and to the spec, and show that the roster does fail
when the adapter module cannot be imported, which is the frozen failure.
"""
from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness.lanes_registry import LANES
from scripts.frozen_adapter_imports import adapter_lane_hidden_imports

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "packaging" / "flywheel-gateway.spec"


def _module_path(name: str) -> Path:
    parts = name.split(".")
    package = REPO.joinpath(*parts) / "__init__.py"
    return package if package.exists() else REPO.joinpath(*parts[:-1]) / f"{parts[-1]}.py"


def _spec_hidden_block() -> str:
    tree = ast.parse(SPEC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "hiddenimports":
            return ast.unparse(node.value)
    raise AssertionError("spec has no hiddenimports keyword")


def test_raw_adapter_and_installer_are_listed():
    names = adapter_lane_hidden_imports()
    assert {"harness.raw_lane", "harness.raw_lane_install"} <= set(names)


def test_every_registry_adapter_is_listed():
    adapters = {lane.adapter_module for lane in LANES.values() if lane.adapter_module}
    assert adapters, "the registry has no adapter lane; this test checks nothing"
    names = set(adapter_lane_hidden_imports())
    assert adapters <= names
    assert {f"{a}_install" for a in adapters} <= names


def test_every_listed_module_exists_and_imports():
    for name in adapter_lane_hidden_imports():
        assert _module_path(name).is_file(), name
        importlib.import_module(name)


def test_the_spec_adds_the_list_to_its_hidden_imports():
    spec = SPEC.read_text(encoding="utf-8")
    assert "from scripts.frozen_adapter_imports import adapter_lane_hidden_imports" in spec
    assert "*adapter_lane_hidden_imports()" in _spec_hidden_block()


@dataclass(frozen=True)
class _FakeLane:
    adapter_module: str = ""


def test_control_a_new_adapter_lane_is_derived():
    """False-success control: the list follows the registry, not a literal."""
    lanes = {"plain": _FakeLane(), "new": _FakeLane("harness.new_lane")}
    assert adapter_lane_hidden_imports(lanes) == [
        "harness.new_lane", "harness.new_lane_install"]


def test_control_roster_fails_without_the_adapter_module(monkeypatch):
    """The frozen failure, reproduced in-process: when the adapter module is
    absent, as it was from the 1.3.3 freeze, the roster raises, and the
    gateway answers ``/api/lanes`` with an error instead of 200."""
    from harness import lanes

    real_import_module = importlib.import_module

    def _no_adapter(name, package=None):
        if name == "harness.raw_lane":
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", _no_adapter)
    with pytest.raises(ModuleNotFoundError):
        lanes.lane_status("raw", probe=False)
    monkeypatch.undo()
    assert lanes.lane_status("raw", probe=False)["name"] == "raw"
