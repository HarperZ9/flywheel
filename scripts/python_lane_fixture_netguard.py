"""Network guard for Python lane installed-wheel fixtures."""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

BLOCK_MESSAGE = "network disabled by flywheel python lane fixture"


def create_network_guard(root: Path) -> dict[str, str]:
    guard = root / "network-guard"
    guard.mkdir(parents=True, exist_ok=True)
    (guard / "sitecustomize.py").write_text(textwrap.dedent(f"""
        import ipaddress
        import socket
        _MSG = {BLOCK_MESSAGE!r}
        _create_connection = socket.create_connection
        _getaddrinfo = socket.getaddrinfo
        def _blocked(*_args, **_kwargs):
            raise RuntimeError(_MSG)
        def _host(value):
            return value[0] if isinstance(value, tuple) and value else value
        def _allowed(value):
            host = _host(value)
            if host in ("localhost",):
                return True
            try:
                return ipaddress.ip_address(host).is_loopback
            except Exception:
                return False
        def _guarded_create_connection(address, *args, **kwargs):
            if _allowed(address):
                return _create_connection(address, *args, **kwargs)
            _blocked()
        def _guarded_getaddrinfo(host, *args, **kwargs):
            if _allowed(host):
                return _getaddrinfo(host, *args, **kwargs)
            _blocked()
        socket.create_connection = _guarded_create_connection
        socket.getaddrinfo = _guarded_getaddrinfo
        _Socket = socket.socket
        class GuardedSocket(_Socket):
            def connect(self, address):
                if _allowed(address):
                    return super().connect(address)
                raise RuntimeError(_MSG)
            def connect_ex(self, address):
                if _allowed(address):
                    return super().connect_ex(address)
                raise RuntimeError(_MSG)
        socket.socket = GuardedSocket
    """).lstrip(), encoding="utf-8")
    return {"path": str(guard.as_posix()), "mechanism": "python sitecustomize socket guard"}


def guarded_env(base: dict[str, str] | None, guard_dir: Path) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(guard_dir) if not existing else str(guard_dir) + os.pathsep + existing
    env["PYTHON_LANE_FIXTURE_NETWORK_GUARD"] = BLOCK_MESSAGE
    return env


def prove_network_guard(python: str, guard_dir: Path, cwd: Path) -> dict[str, object]:
    probe = (
        "import json, socket, sys\n"
        "try:\n"
        "    socket.create_connection(('192.0.2.1', 9), timeout=0.01)\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'blocked': str(exc)}))\n"
        f"    sys.exit(0 if {BLOCK_MESSAGE!r} in str(exc) else 2)\n"
        "else:\n"
        "    print(json.dumps({'blocked': False}))\n"
        "    sys.exit(3)\n"
    )
    proc = subprocess.run(
        [python, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=guarded_env(None, guard_dir),
        timeout=10,
        check=False,
    )
    payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return {
        "enforced": proc.returncode == 0,
        "returncode": proc.returncode,
        "probe": payload,
        "stderr": proc.stderr,
        "path": str(guard_dir.as_posix()),
    }
