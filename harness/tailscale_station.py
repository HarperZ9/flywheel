"""Read-only Tailscale station planning for the mobile gateway launcher."""
from __future__ import annotations

import argparse
import ipaddress
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

TAILNET_IPV4 = ipaddress.ip_network("100.64.0.0/10")
DEFAULT_PORT = 8799
SCHEMA = "flywheel.tailnet-station-plan/v1"


def _base_plan(reason: str, *, token_present: bool = False) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "transport": "tailnet",
        "ok": False,
        "reason": reason,
        "connection_url": None,
        "bind_hosts": [],
        "allow_hosts": [],
        "token_present": bool(token_present),
    }


def _valid_port(port: int) -> bool:
    return isinstance(port, int) and 0 < port <= 65535


def _tailnet_ipv4(value: Any) -> str | None:
    try:
        ip = ipaddress.ip_address(str(value or ""))
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv4Address) and ip in TAILNET_IPV4:
        return str(ip)
    return None


def _self_tailnet_ipv4(status: Any) -> tuple[str | None, str]:
    if not isinstance(status, dict):
        return None, "invalid_status"
    if str(status.get("BackendState", "")) != "Running":
        return None, "tailscale_not_running"
    self_node = status.get("Self")
    if not isinstance(self_node, dict):
        return None, "tailscale_self_unavailable"
    if self_node.get("Online") is not True:
        return None, "tailscale_self_offline"
    raw_ips = self_node.get("TailscaleIPs")
    if not isinstance(raw_ips, list):
        return None, "no_tailnet_ipv4"
    for raw in raw_ips:
        ip = _tailnet_ipv4(raw)
        if ip:
            return ip, "ok"
    return None, "no_tailnet_ipv4"


def plan_tailnet_gateway(status: Any, *, port: int = DEFAULT_PORT,
                         token_present: bool = False) -> dict[str, Any]:
    """Return a redacted plan for binding gateway control over tailnet.

    The plan intentionally excludes account names, DNS names, peer inventory,
    token values, token hashes, and filesystem paths. The gateway's existing
    bearer token and Host allowlist remain the security boundary.
    """
    if not _valid_port(port):
        return _base_plan("invalid_port", token_present=token_present)
    ip, reason = _self_tailnet_ipv4(status)
    if not ip:
        return _base_plan(reason, token_present=token_present)
    return {
        "schema": SCHEMA,
        "transport": "tailnet",
        "ok": True,
        "reason": "ok",
        "connection_url": f"http://{ip}:{port}",
        "bind_hosts": ["127.0.0.1", ip],
        "allow_hosts": [ip],
        "token_present": bool(token_present),
    }


def parse_status_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def find_tailscale() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    candidate = Path(r"C:\Program Files\Tailscale\tailscale.exe")
    return str(candidate) if candidate.exists() else None


def read_status_json(*, exe: str | None = None, timeout: float = 2.0
                     ) -> tuple[Any, str]:
    tailscale = exe or find_tailscale()
    if not tailscale:
        return None, "tailscale_cli_unavailable"
    try:
        completed = subprocess.run(
            [tailscale, "status", "--json"],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "tailscale_status_unavailable"
    if completed.returncode != 0:
        return None, "tailscale_status_unavailable"
    status = parse_status_json(completed.stdout)
    if status is None:
        return None, "invalid_status"
    return status, "ok"


def plan_from_cli(*, port: int = DEFAULT_PORT, token_present: bool = False,
                  exe: str | None = None, timeout: float = 2.0) -> dict[str, Any]:
    status, reason = read_status_json(exe=exe, timeout=timeout)
    if reason != "ok":
        return _base_plan(reason, token_present=token_present)
    return plan_tailnet_gateway(status, port=port, token_present=token_present)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan Flywheel gateway tailnet binding without changing Tailscale state.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--status-file", help="read a saved tailscale status --json fixture")
    parser.add_argument("--token-present", action="store_true")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    if args.status_file:
        text = Path(args.status_file).read_text(encoding="utf-8")
        plan = plan_tailnet_gateway(parse_status_json(text), port=args.port,
                                    token_present=args.token_present)
    else:
        plan = plan_from_cli(port=args.port, token_present=args.token_present,
                             timeout=args.timeout)
    indent = 2 if args.pretty else None
    print(json.dumps(plan, sort_keys=True, indent=indent))
    return 0 if plan.get("ok") else 2


if __name__ == "__main__":  # pragma: no cover - exercised by launcher/manual use.
    raise SystemExit(_main())
