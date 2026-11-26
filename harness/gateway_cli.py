"""CLI argument parsing, host binding, and startup orchestration for harness/gateway.py."""
from __future__ import annotations

import argparse
import os
import threading
from pathlib import Path

from harness.gateway_auth import DEFAULT_HOSTS
from harness.gateway_bind import ExclusiveThreadingHTTPServer
from harness.run_paths import run_root_default


def build_parser(repo: Path) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="flywheel superapp gateway (one origin)")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--root", default=str(repo))
    ap.add_argument("--serve-url", default="http://127.0.0.1:8765")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--run-root", default=run_root_default())
    ap.add_argument("--cors", action="store_true",
                    help="allow cross-origin browser clients (off by default; the gateway is local)")
    ap.add_argument("--host", action="append", default=None, dest="host", metavar="ADDR",
                    help="bind address, repeatable (default 127.0.0.1, loopback only)")
    ap.add_argument("--allow-host", action="append", default=[], dest="allow_host",
                    help="add a Host header value to the DNS-rebinding allowlist (repeatable)")
    ap.add_argument("--strict-bind", action="store_true",
                    help="fail startup if any requested bind host cannot be opened")
    from harness.codex_managed_gateway_config import add_managed_codex_arguments
    add_managed_codex_arguments(ap)
    from harness.lane_probe_cache import add_desktop_flag
    add_desktop_flag(ap)
    return ap


def resolve_hosts(requested) -> list[str]:
    hosts, seen = [], set()
    for h in (requested or ["127.0.0.1"]):
        if h not in seen:
            seen.add(h)
            hosts.append(h)
    return ["0.0.0.0"] if "0.0.0.0" in hosts else hosts


def bind_hosts(hosts, port, handler_cls, *, strict: bool = False):
    servers = []
    for h in hosts:
        try:
            servers.append(ExclusiveThreadingHTTPServer((h, port), handler_cls))
        except OSError as e:
            print(f"  {'ABORT' if strict else 'SKIP '}     cannot bind {h}:{port}: {e}")
            if strict:
                for server in servers:
                    server.server_close()
                return []
    return servers


def serve_all(servers, handler_cls) -> None:
    for s in servers[:-1]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        servers[-1].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        from harness.gateway_lane_calls import _stop_serving
        _stop_serving(handler_cls.operation_service, servers)


def _init_runtime_state(handler_cls, args, flywheel_home: Path, servers) -> list[str]:
    from harness.codex_managed_gateway_config import managed_config_from_args
    from harness.credential_handles import CredentialHandleStore
    from harness.gateway_endpoint_file import publish_endpoint
    from harness.gateway_operation_recovery import recover_gateway_operations
    from harness.journey_recovery import recover_store
    from harness.keychain import keychain_get
    from harness.lane_probe_cache import start_probe
    from harness.session_token import SessionTokenStore
    from harness.trace_bench_replay import sweep_all
    from harness.trace_enc_probe import startup as custody_startup
    from harness.trace_retention_schedule import start_if_adopted

    publish_endpoint(flywheel_home, servers)
    custody_startup(flywheel_home)
    start_if_adopted(flywheel_home)
    sweep_all(flywheel_home)
    bound = [s.server_address[0] for s in servers]
    remote = [h for h in bound if h not in ("127.0.0.1", "localhost", "::1")]
    if remote:
        print(f"  REMOTE    binding {', '.join(remote)}: reachable off-box. Front a routable "
              f"bind with a TLS tunnel; allowlisted hosts = {sorted(handler_cls.allowed_hosts)}")
    state_root = flywheel_home / "state"
    handler_cls.native_codex_config = managed_config_from_args(args, state_root=state_root)
    handler_cls._configure_operation_components(state_root)
    handler_cls.session_token_store = SessionTokenStore(CredentialHandleStore(state_root, keychain_get=keychain_get))
    handler_cls._session_token_state_root = state_root
    start_probe(desktop_launch=args.desktop_launch)
    handler_cls.startup_recovery = {
        "journeys": recover_store(state_root, now=handler_cls.clock()),
        "gateway_operations": recover_gateway_operations(state_root, now=handler_cls.clock()),
    }
    return bound


def _print_banner(port: int, root: Path, bound: list[str], flywheel_home: Path, router_ledger_fn) -> None:
    print(f"flywheel gateway: http://127.0.0.1:{port}  root={root}")
    print(f"  bound     {', '.join(f'{h}:{port}' for h in bound)}")
    print(f"  token     {flywheel_home / 'gateway.token'}  (send as: Authorization: Bearer <token>)")
    from harness.gateway_ledger_gate import startup as ledger_startup
    ledger_startup(router_ledger_fn)
    print("  surface   Flywheel Desktop (the native client) talks to this gateway")
    print(f"  dev shell http://127.0.0.1:{port}/site/index.html  (dev/CI fallback only)")
    print(f"  world     http://127.0.0.1:{port}/api/world")
    print(f"  health    http://127.0.0.1:{port}/api/endpoints/health")
    print(f"  openai    POST /v1/chat/completions  +  GET /v1/models  (drop-in, model=any provider, stream ok)")


def run_main(
    argv,
    handler_cls,
    *,
    build_parser_fn,
    resolve_hosts_fn,
    bind_hosts_fn,
    serve_all_fn,
    load_token_fn,
    router_ledger_fn,
) -> int:
    a = build_parser_fn().parse_args(argv)
    handler_cls.root = Path(a.root).resolve()
    from harness.local_agent_grants import pin_gateway_workspace
    pin_gateway_workspace(handler_cls.root)
    handler_cls.serve_url, handler_cls.ollama_url = a.serve_url, a.ollama_url
    handler_cls.run_root = os.environ["FLYWHEEL_RUN_ROOT"] = a.run_root
    handler_cls.cors = a.cors
    from harness.telos_browser_registration import configure_telos_browser
    if configure_telos_browser(os.environ.get("FLYWHEEL_TELOS_BROWSER_CONFIG"))["available"] is None:
        raise SystemExit("browser registration state unknown; gateway not started")
    handler_cls.allowed_hosts = DEFAULT_HOSTS | frozenset(a.allow_host)
    flywheel_home = Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))
    handler_cls.flywheel_home = flywheel_home
    handler_cls.auth_token = load_token_fn(flywheel_home)
    servers = bind_hosts_fn(resolve_hosts_fn(a.host), a.port, strict=a.strict_bind)
    if not servers:
        print(f"no interface bound on port {a.port}; nothing to serve")
        return 1
    bound = _init_runtime_state(handler_cls, a, flywheel_home, servers)
    _print_banner(a.port, handler_cls.root, bound, flywheel_home, router_ledger_fn)
    serve_all_fn(servers)
    return 0
