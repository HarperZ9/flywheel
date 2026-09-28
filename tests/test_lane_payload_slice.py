"""A lane payload slice must be closed under the imports that run at load time.

These cases use synthetic sources, so they run on every runner. The real
calibrate-pro slice is checked by the regeneration test.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _lane_payload_slice import (  # noqa: E402
    PAYLOAD_SLICES,
    check_slice_closure,
    split_runtime_dependencies,
)
from _lane_payload_source import GeneratorError  # noqa: E402

BASE = {
    "pkg/__init__.py": b"__version__ = '1'\n",
    "pkg/mcp.py": b"from pkg import __version__\nfrom pkg.sub.data import TABLE\n",
    "pkg/sub/__init__.py": b"",
    "pkg/sub/data.py": b"import json\nTABLE = {}\n",
    "pkg/heavy.py": b"import numpy\n",
}
SLICE = ("pkg", "pkg.mcp", "pkg.sub", "pkg.sub.data")


def _check(sources, modules=SLICE):
    check_slice_closure(sources, pkg="pkg", pkg_dir="pkg", modules=modules,
                        excluded_imports={"numpy", "scipy"})


def test_closed_slice_passes():
    _check(BASE)


def test_load_time_import_outside_the_slice_is_refused():
    sources = {**BASE, "pkg/mcp.py": b"from pkg import heavy\n"}
    with pytest.raises(GeneratorError, match="pkg.heavy"):
        _check(sources)


def test_load_time_import_of_an_excluded_dependency_is_refused():
    sources = {**BASE, "pkg/sub/data.py": b"import numpy as np\n"}
    with pytest.raises(GeneratorError, match="numpy"):
        _check(sources)


def test_deferred_and_type_checking_imports_are_allowed():
    sources = {**BASE, "pkg/sub/data.py": (
        b"from typing import TYPE_CHECKING\n"
        b"if TYPE_CHECKING:\n    import numpy\n"
        b"def f():\n    import numpy\n    from pkg import heavy\n")}
    _check(sources)


def test_relative_import_resolves_inside_the_package():
    sources = {**BASE, "pkg/sub/data.py": b"from .. import heavy\n"}
    with pytest.raises(GeneratorError, match="pkg.heavy"):
        _check(sources)


def test_slice_module_without_its_parent_package_is_refused():
    with pytest.raises(GeneratorError, match="pkg.sub"):
        _check(BASE, modules=("pkg", "pkg.mcp", "pkg.sub.data"))


def test_slice_module_missing_from_the_source_is_refused():
    with pytest.raises(GeneratorError, match="pkg.absent"):
        _check(BASE, modules=(*SLICE, "pkg.absent"))


def test_reviewed_exclusions_must_match_the_pinned_dependencies():
    kept, excluded = split_runtime_dependencies(
        "calibrate-pro", ["numpy>=1.24", "scipy>=1.10", "build-color>=1.0.0"])
    assert kept == []
    assert [item["requirement"] for item in excluded] == [
        "numpy>=1.24", "scipy>=1.10", "build-color>=1.0.0"]
    with pytest.raises(GeneratorError, match="numpy>=1.24"):
        split_runtime_dependencies("calibrate-pro", ["scipy>=1.10", "build-color>=1.0.0"])
    assert split_runtime_dependencies("gather", ["x>=1"]) == (["x>=1"], [])


def test_every_reviewed_exclusion_states_a_reason():
    for lane, spec in PAYLOAD_SLICES.items():
        assert spec["reason"].strip(), lane
        for item in spec["excluded_runtime_dependencies"]:
            assert item["reason"].strip(), (lane, item)
