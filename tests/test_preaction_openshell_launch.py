"""OASP R1: the optional OpenShell launcher for hooked sessions.

No OpenShell binary runs here. Outcomes asserted: the generated policy sets
`enforcement: enforce` on every endpoint (OpenShell's default is audit, which
allows), keeps /etc read-only so a managed hook settings file cannot be
edited, and lists only the owner's hosts; detection reports native, WSL or
unavailable without guessing; on Windows the commands use WSL paths; and the
launcher refuses to run when OpenShell is absent.
"""
from __future__ import annotations

import io
import json
import subprocess

from harness.preaction import cli
from harness.preaction import openshell_launch as osl
from harness.preaction.owner import OwnerConfig


def test_policy_enforces_every_endpoint_and_keeps_etc_read_only():
    owner = OwnerConfig(fetch_hosts=("docs.python.org", "pypi.org"), allow_hosts=("ci.example",))
    text = osl.policy_yaml(owner)
    assert text.count("enforcement: enforce") == 3 and "enforcement: audit" not in text
    assert "read_only: [/usr, /lib, /etc, /proc, /dev/urandom]" in text
    assert "/etc" not in text.split("read_write:")[1].splitlines()[0]
    assert "host: docs.python.org" in text and "host: ci.example" in text
    assert text.count("access: read-only") == 2 and text.count("access: read-write") == 1


def test_policy_with_no_hosts_denies_all_network():
    text = osl.policy_yaml(OwnerConfig(fetch_hosts=()))
    assert "network_policies: {}" in text and "host:" not in text


def test_detect_native_and_absent():
    assert osl.detect(which=lambda n: "/usr/bin/openshell", platform="linux")["route"] == "native"
    off = osl.detect(which=lambda n: None, platform="linux")
    assert not off["available"] and "PATH" in off["reason"]


def test_detect_through_wsl():
    def runner(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout="/home/u/.local/bin/openshell\n")
    det = osl.detect(which=lambda n: "C:/Windows/System32/wsl.exe", platform="win32",
                     runner=runner)
    assert det["available"] and det["prefix"] == ["wsl.exe", "-e", "/home/u/.local/bin/openshell"]


def test_detect_wsl_without_openshell():
    def runner(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="")
    det = osl.detect(which=lambda n: "wsl.exe", platform="win32", runner=runner)
    assert not det["available"] and "inside WSL" in det["reason"]


def test_windows_plan_uses_wsl_paths(tmp_path):
    det = {"available": False, "route": "none", "prefix": [], "windows": True, "reason": "x"}
    p = osl.plan("claude-code", owner=OwnerConfig(), workspace="C:\\dev\\proj",
                 out_dir=tmp_path, detected=det)
    create = p["commands"]["create"]
    assert create[:3] == ["wsl.exe", "-e", "openshell"]
    assert "/mnt/c/dev/proj:/sandbox/work" in create
    policy = osl.wsl_path(str(tmp_path / "flywheel-hooked.policy.yaml"))
    assert policy in create
    assert osl.wsl_path("D:\\w\\p.yaml") == "/mnt/d/w/p.yaml"
    assert p["commands"]["start"][-1] == "claude"


def test_run_refuses_without_openshell_and_runs_both_steps_with_it(tmp_path):
    det = {"available": True, "route": "native", "prefix": ["/usr/bin/openshell"]}
    p = osl.plan("codex", owner=OwnerConfig(), workspace="/w", out_dir=tmp_path, detected=det)
    seen = []
    assert osl.run(p, runner=lambda argv: (seen.append(argv),
                                           subprocess.CompletedProcess(argv, 0))[1]) == 0
    assert [a[1:3] for a in seen] == [["sandbox", "create"], ["sandbox", "exec"]]
    assert osl.run({**p, "available": False}) == 3


def test_cli_sandbox_prints_plan_without_running(tmp_path, monkeypatch):
    monkeypatch.setattr(osl, "detect", lambda: {"available": False, "route": "none",
                                                "prefix": [], "reason": "not installed"})
    out = io.StringIO()
    code = cli.main(["sandbox", "claude-code", "--workspace", str(tmp_path), "--out",
                     str(tmp_path / "plan")], stdout=out, stderr=io.StringIO())
    plan = json.loads(out.getvalue())
    assert code == 0 and not plan["available"]
    assert (tmp_path / "plan" / "flywheel-hooked.policy.yaml").exists()
    err = io.StringIO()
    code = cli.main(["sandbox", "claude-code", "--workspace", str(tmp_path), "--out",
                     str(tmp_path / "plan"), "--run"], stdout=io.StringIO(), stderr=err)
    assert code == 3 and "not available" in err.getvalue()
