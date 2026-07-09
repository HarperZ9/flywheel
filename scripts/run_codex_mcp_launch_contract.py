"""Emit a metadata-only Codex MCP launch and fallback contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback is not expected here
    tomllib = None  # type: ignore[assignment]

from harness.file_backed_store import FileBackedHarnessStore

SCHEMA = "harness.codex-mcp-launch-contract/v1"
DEFAULT_CODEX_CONFIG = Path("C:/Users/Zain/.codex/config.toml")
DEFAULT_PYTHON = "C:/Users/Zain/AppData/Local/Programs/Python/Python313/python.exe"
DEFAULT_TOOLS = ["index", "forum", "gather", "crucible", "telos"]

EXPECTED: dict[str, dict[str, Any]] = {
    "index": {
        "role": "workspace structure and context map",
        "command": DEFAULT_PYTHON,
        "args": ["-m", "index_graph", "mcp"],
        "cwd": "C:/dev/public/index",
        "env_keys": ["PYTHONPATH", "PYTHONIOENCODING"],
        "fallback_commands": [
            "set PYTHONPATH=C:/dev/public/index/src && python -m index_graph map --root C:/dev --output C:/tmp/index_map.json",
            "set PYTHONPATH=C:/dev/public/index/src && python -m index_graph router --root C:/dev/local-model",
        ],
        "reload_hint": "Restart the Codex MCP server/session after source or config changes; use direct index CLI until the host reloads stale transports.",
    },
    "forum": {
        "role": "routing, escalation, and communication contract",
        "command": DEFAULT_PYTHON,
        "args": ["-m", "forum", "mcp", "--ledger", "C:/Users/Zain/.codex/forum-ledger"],
        "cwd": "C:/dev/public/forum",
        "env_keys": ["PYTHONPATH", "PYTHONIOENCODING"],
        "fallback_commands": [
            "set PYTHONPATH=C:/dev/public/forum/src && python -m forum route --text \"continue local-model harness architecture\"",
        ],
        "reload_hint": "Forum currently responds in this Codex session; still keep the source-checkout profile explicit for package portability.",
    },
    "gather": {
        "role": "research/source intake",
        "command": DEFAULT_PYTHON,
        "args": ["-m", "gather", "mcp"],
        "cwd": "C:/dev/public/gather",
        "env_keys": ["PYTHONPATH", "PYTHONIOENCODING"],
        "fallback_commands": ["set PYTHONPATH=C:/dev/public/gather/src && python -m gather --help"],
        "reload_hint": "Use source-checkout MCP profile; do not copy browser/session credentials into package artifacts.",
    },
    "crucible": {
        "role": "verification and pressure receipts",
        "command": DEFAULT_PYTHON,
        "args": ["-m", "crucible.cli", "mcp"],
        "cwd": "C:/dev/public/crucible",
        "env_keys": ["PYTHONPATH", "PYTHONIOENCODING"],
        "fallback_commands": ["set PYTHONPATH=C:/dev/public/crucible/src && python -m crucible.cli --help"],
        "reload_hint": "Use source-checkout MCP profile for live verification; package stores launch metadata only.",
    },
    "telos": {
        "role": "shared room, manifest, and MCP freshness receipts",
        "command": "node",
        "args": ["C:/dev/public/telos/demo/telos-mcp.mjs"],
        "cwd": "C:/dev/public/telos",
        "env_keys": [],
        "fallback_commands": ["node C:/dev/public/telos/demo/telos-mcp.mjs"],
        "reload_hint": "Telos receipts define expected MCP freshness and restart hints for the flagship tools.",
    },
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _exists(path_text: str) -> bool:
    return bool(path_text) and Path(path_text).exists()


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists() or tomllib is None:
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _normalize_args(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _server_contract(name: str, config: dict[str, Any]) -> dict[str, Any]:
    expected = EXPECTED[name]
    configured = ((config.get("mcp_servers") or {}).get(name) or {}) if isinstance(config, dict) else {}
    env = configured.get("env") or {}
    command = str(configured.get("command", ""))
    args = _normalize_args(configured.get("args"))
    cwd = str(configured.get("cwd", ""))
    checks = {
        "configured": bool(configured),
        "command_present": bool(command),
        "args_match_expected": args == expected["args"],
        "cwd_present": bool(cwd),
        "cwd_matches_expected": cwd.replace("\\", "/") == str(expected["cwd"]).replace("\\", "/"),
        "cwd_exists": _exists(cwd or expected["cwd"]),
        "expected_env_keys_present": all(key in env for key in expected["env_keys"]),
    }
    verdict = "READY" if all(checks.values()) else "DRIFT"
    if not configured:
        verdict = "MISSING_CONFIG"
    return {
        "schema": "harness.codex-mcp-launch.server/v1",
        "name": name,
        "role": expected["role"],
        "verdict": verdict,
        "expected": {
            "command": expected["command"],
            "args": expected["args"],
            "cwd": expected["cwd"],
            "env_keys": expected["env_keys"],
        },
        "configured": {
            "present": bool(configured),
            "command_present": bool(command),
            "args": args,
            "cwd": cwd,
            "env_keys": sorted(str(key) for key in env.keys()),
            "env_values_recorded": False,
        },
        "checks": checks,
        "fallback_commands": expected["fallback_commands"],
        "reload_hint": expected["reload_hint"],
    }


def build_contract(*, codex_config: Path, tools: list[str], observed: list[str]) -> dict[str, Any]:
    config = _load_toml(codex_config)
    selected = [tool for tool in tools if tool in EXPECTED]
    servers = [_server_contract(tool, config) for tool in selected]
    ready = sum(1 for server in servers if server["verdict"] == "READY")
    return {
        "schema": SCHEMA,
        "created_utc": _now(),
        "codex_config": {
            "path": str(codex_config),
            "exists": codex_config.exists(),
            "values_recorded": False,
        },
        "dependency_posture": "metadata-only Codex MCP launch contract; no provider calls, endpoint probes, token stores, source bodies, or credentials are read",
        "secret_policy": "records command paths, args, cwd, env key names, booleans, and fallback commands only; env values and credentials are not recorded",
        "servers": servers,
        "observations": [{"text": item, "source": "operator-or-wrapper", "values_recorded": False} for item in observed],
        "session_reload_boundary": {
            "active_mcp_hosts_may_cache_dead_transports": True,
            "code_or_config_fix_requires_host_reload": True,
            "fallback_until_reload": "use packaged direct CLI commands from fallback_commands",
        },
        "summary": {
            "servers_expected": len(selected),
            "servers_ready": ready,
            "servers_drift": len(servers) - ready,
            "all_selected_known": len(selected) == len(tools),
        },
    }


def render_markdown(contract: dict[str, Any]) -> str:
    lines = [
        "# Codex MCP launch contract",
        "",
        f"Schema: `{contract['schema']}`",
        f"Config: `{contract['codex_config']['path']}`",
        "",
        "## Summary",
        "",
        f"- Servers expected: {contract['summary']['servers_expected']}",
        f"- Servers ready: {contract['summary']['servers_ready']}",
        f"- Servers drift: {contract['summary']['servers_drift']}",
        "- Env values recorded: false",
        "",
        "## Servers",
        "",
        "| Server | Verdict | Expected cwd | Configured cwd | Fallback |",
        "| --- | --- | --- | --- | --- |",
    ]
    for server in contract["servers"]:
        fallback = server["fallback_commands"][0] if server["fallback_commands"] else ""
        lines.append(
            f"| {server['name']} | {server['verdict']} | `{server['expected']['cwd']}` | "
            f"`{server['configured']['cwd']}` | `{fallback}` |"
        )
    lines.extend([
        "",
        "## Reload boundary",
        "",
        "Codex MCP hosts can cache a dead stdio transport. If direct CLI works but the exposed MCP tool still reports transport closed, restart/reload the MCP host and use the fallback command until reload completes.",
    ])
    return "\n".join(lines) + "\n"


def _store_outputs(store_root: Path, contract: dict[str, Any], markdown: str, run_id: str) -> dict[str, str]:
    if not run_id:
        return {}
    store = FileBackedHarnessStore(store_root)
    json_record = store.write_json(run_id, "codex_mcp_launch_contract", contract)
    markdown_record = store.write_text(run_id, "codex_mcp_launch_contract_md", markdown)
    return {"json": str(json_record.path), "markdown": str(markdown_record.path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-config", default=str(DEFAULT_CODEX_CONFIG))
    parser.add_argument("--tools", default=",".join(DEFAULT_TOOLS))
    parser.add_argument("--observation", action="append", default=[])
    parser.add_argument("--store-root", default="C:/tmp/harness_file_store")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    tools = [item.strip() for item in args.tools.split(",") if item.strip()]
    contract = build_contract(
        codex_config=Path(args.codex_config),
        tools=tools,
        observed=args.observation,
    )
    markdown = render_markdown(contract)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8")
    if args.markdown_out:
        md = Path(args.markdown_out)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(markdown, encoding="utf-8")
    store_outputs = _store_outputs(Path(args.store_root), contract, markdown, args.run_id)
    result = {**contract["summary"], "schema": contract["schema"]}
    if store_outputs:
        result["store_outputs"] = store_outputs
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
