"""A pip or npm lane older than its pin does not launch, and install pins it.

Each late pin carries a security fix (relay GHSA-phjr-6qrc-39mw, gather
GHSA-pxvv-rg3f-4v5w, mneme GHSA-j2pw-g7f4-9ppp, canon GHSA-48rq-xjfx-6j4f).
Under the default "auto" profile the engine used to launch whatever version pip
had installed, so an older package ran without those fixes. Now an installed
version below the pin blocks the lane with ``installed_version_below_pin``; a
newer one is recorded and still launches, since O-12 charges T2 for any tool
it adds. ``install_lane`` asks the package manager for the pinned version.
"""
from __future__ import annotations

import subprocess

import pytest

import harness.lanes as ln
from harness import lane_runtime
from harness.lane_runtime_versions import version_below
from harness.lanes_registry import LANES


def _resolve(lane: str, installed: str | None, *, source=None, profile=None):
    registry = {lane: {"runtime_profile": profile}} if profile else {}
    return lane_runtime.resolve_lane_runtime(
        lane, LANES, registry, environ={"PATH": ""}, python_executable="python.exe",
        is_frozen=False, source_resolver=lambda _lane: source,
        extra_roots=lambda _lane: [], importable_fn=lambda _top: True,
        installed_version_fn=lambda _lane: installed,
        package_runtime_version_fn=lambda _lane, _python: installed)


@pytest.mark.parametrize(("lane", "installed"), [
    ("gather", "1.8.2"), ("relay", "0.3.0"), ("canon", "0.4.1"), ("mneme", "0.5.0"),
    ("canon", "0.4.2rc1")])
def test_auto_blocks_an_installed_lane_below_its_pin(lane, installed):
    runtime = _resolve(lane, installed)
    assert runtime.selected_runtime == "package"
    assert "installed_version_below_pin" in runtime.blocking_codes
    assert not runtime.present
    with pytest.raises(lane_runtime.LaneRuntimeError):
        runtime.require_launch()


def test_auto_launches_the_pinned_version_with_no_code():
    runtime = _resolve("gather", LANES["gather"].version)
    assert runtime.present and not runtime.blocking_codes
    assert "installed_version_below_pin" not in runtime.mismatch_codes


def test_auto_records_but_launches_a_newer_version():
    runtime = _resolve("gather", "99.0.0")
    assert runtime.present and not runtime.blocking_codes
    assert "installed_version_mismatch" in runtime.mismatch_codes


def test_a_source_checkout_is_not_judged_by_the_installed_package(tmp_path):
    runtime = _resolve("gather", "1.8.2", source=tmp_path)
    assert runtime.selected_runtime == "source"
    assert "installed_version_below_pin" not in runtime.blocking_codes


def test_the_package_profile_still_requires_the_exact_pin():
    runtime = _resolve("gather", "99.0.0", profile="package")
    assert "installed_version_mismatch" in runtime.blocking_codes


@pytest.mark.parametrize(("installed", "pin", "below"), [
    ("1.8.2", "1.9.0", True), ("1.9.0", "1.9.0", False), ("1.10.0", "1.9.0", False),
    ("0.4.2rc1", "0.4.2", True), ("0.4.2.dev3", "0.4.2", True), ("0.4.2-beta.1", "0.4.2", True),
    ("0.4.2.post1", "0.4.2", False), ("0.4.2+local", "0.4.2", False), ("0.4", "0.4.2", True),
    ("2!0.1.0", "1.9.0", False)])
def test_version_below_orders_release_numbers(installed, pin, below):
    assert version_below(installed, pin) is below


@pytest.mark.parametrize(("lane", "expected"), [
    ("gather", ["pip", "install", f"gather-engine=={LANES['gather'].version}"]),
    ("learn", ["npm", "install", "-g", f"{LANES['learn'].install_name}@{LANES['learn'].version}"])])
def test_install_lane_asks_for_the_pinned_version(lane, expected, tmp_path, monkeypatch):
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", tmp_path / "lanes.json")
    seen = []

    def fake_run(cmd, *args, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(ln.subprocess, "run", fake_run)
    if LANES[lane].package_disabled_reason:
        pytest.skip(f"{lane} has no package distribution")
    assert ln.install_lane(lane, profile="package")["installed"] is True
    assert seen == [expected]
