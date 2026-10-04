"""Shared fixtures for the raw lane tests.

The committed renders under ``tests/fixtures/raw_native`` came from the
raw-native 0.5.0 release binaries with ``--width 40 --height 40``:
``windows-x64`` and ``linux-x64`` (the same view, verified at the default 0.12
tolerance) and ``windows-x64-refuted`` (``--tolerance 0.05``). Each folder's
``run.json`` names the platform and the flags. Each also holds raw-native's own
``receipt.json``; the two platforms wrote every file byte-identical except
``arena_certificate.json``.

``installed_home`` installs the real binary once per session through the lane's
own installer (fetch by URL, check against SHA256SUMS and the pins). Where that
cannot happen, the test that needs it is skipped with the installer's stated
reason, never silently. CI sets ``RAW_LANE_REQUIRE_BINARY=1`` on the job that
must exercise the binary, and there a missing binary is a failure, not a skip.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harness import raw_lane_install as inst

FIX = Path(__file__).resolve().parent / "fixtures" / "raw_native"
RENDERS = ("windows-x64", "linux-x64", "windows-x64-refuted")
_INSTALLED: dict = {}


def files(name: str) -> dict:
    return {p.name: p.read_bytes() for p in (FIX / name).iterdir() if p.is_file()}


def cert(name: str) -> dict:
    return json.loads((FIX / name / "certificate.json").read_text(encoding="utf-8"))


def run_record(name: str) -> dict:
    return json.loads((FIX / name / "run.json").read_text(encoding="utf-8"))


def _require_or_skip(reason: str) -> None:
    if os.environ.get("RAW_LANE_REQUIRE_BINARY") == "1":
        pytest.fail(f"RAW_LANE_REQUIRE_BINARY=1 and the binary is unavailable: {reason}")
    pytest.skip(f"raw-native {inst.VERSION} binary unavailable on this host: {reason}")


@pytest.fixture(scope="session")
def installed_home(tmp_path_factory) -> dict:
    """An environ whose FLYWHEEL_HOME holds the installed, pin-checked binary."""
    if "environ" not in _INSTALLED:
        home = tmp_path_factory.mktemp("raw-lane-home")
        environ = {"FLYWHEEL_HOME": str(home)}
        _INSTALLED["row"] = inst.install(environ)
        _INSTALLED["environ"] = environ
    row = _INSTALLED["row"]
    if not row.get("installed"):
        _require_or_skip(f"{row.get('code')}: {row.get('detail')}")
    return dict(_INSTALLED["environ"])
