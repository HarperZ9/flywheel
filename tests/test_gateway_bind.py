import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from harness import gateway

BAD_LOCAL_BIND = "203.0.113.1"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _close_all(servers):
    for server in servers:
        server.server_close()


def test_default_bind_preserves_partial_loopback_when_remote_bind_fails():
    port = _free_port()
    servers = gateway._bind_hosts(["127.0.0.1", BAD_LOCAL_BIND], port)
    try:
        assert len(servers) == 1
        assert servers[0].server_address[0] == "127.0.0.1"
    finally:
        _close_all(servers)


def test_strict_bind_cleans_up_loopback_when_planned_remote_bind_fails():
    port = _free_port()

    servers = gateway._bind_hosts(["127.0.0.1", BAD_LOCAL_BIND], port, strict=True)

    assert servers == []
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


def test_gateway_parser_exposes_opt_in_strict_bind_only():
    parser = gateway._build_parser()

    assert parser.parse_args([]).strict_bind is False
    assert parser.parse_args(["--strict-bind"]).strict_bind is True


def test_tailnet_only_launcher_passes_strict_bind_and_writes_prebind_plan(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell is required for launcher coverage")
    if os.name != "nt":
        # The launcher is stubbed with a Windows .cmd shim below. A Linux
        # runner has pwsh, so a presence check alone admits the test and then
        # the shim cannot execute, which sends the launcher down its browser
        # path and fails on a missing www-browser.
        pytest.skip("the launcher stub is a Windows .cmd shim")
    calls_path = tmp_path / "calls.jsonl"
    receipt_path = tmp_path / "receipt.json"
    fake_py = tmp_path / "fake_python.py"
    fake_py.write_text(
        """
import json, os, sys
args = sys.argv[1:]
with open(os.environ['FLYWHEEL_FAKE_PY_CALLS'], 'a', encoding='utf-8') as fh:
    fh.write(json.dumps(args) + '\\n')
if args[:2] == ['-m', 'harness.tailscale_station']:
    print(json.dumps({
        'schema': 'flywheel.tailnet-station-plan/v1',
        'transport': 'tailnet',
        'ok': True,
        'reason': 'ok',
        'connection_url': 'http://100.88.1.2:8799',
        'bind_hosts': ['127.0.0.1', '100.88.1.2'],
        'allow_hosts': ['100.88.1.2'],
        'token_present': False,
    }))
    raise SystemExit(0)
if args and args[0] == 'harness/gateway.py':
    raise SystemExit(0)
raise SystemExit(9)
""".lstrip(), encoding="utf-8")
    fake_cmd = tmp_path / "fake_python.cmd"
    fake_cmd.write_text(f'@echo off\r\n"{sys.executable}" "{fake_py}" %*\r\n', encoding="utf-8")
    env = dict(os.environ)
    env["FLYWHEEL_FAKE_PY_CALLS"] = str(calls_path)

    completed = subprocess.run([
        pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "scripts/launch_gateway_mobile.ps1",
        "-TailnetOnly", "-ReceiptPath", str(receipt_path),
        "-Python", str(fake_cmd),
    ], cwd=Path(__file__).resolve().parents[1], env=env,
       capture_output=True, text=True, timeout=120)

    assert completed.returncode == 0, completed.stderr + completed.stdout
    calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
    gateway_call = next(call for call in calls if call and call[0] == "harness/gateway.py")
    assert "--strict-bind" in gateway_call
    assert "0.0.0.0" not in gateway_call
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    assert receipt["schema"] == "flywheel.mobile-gateway-plan/v1"
    assert receipt["status"] == "planned"
    assert receipt["gateway_started"] is False
    assert "ok" not in receipt
