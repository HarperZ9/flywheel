"""Emit a non-secret Claude/Codex endpoint auth status receipt.

The harness has four distinct account lanes:

- Claude subscription account through the official Claude CLI.
- Claude API through ANTHROPIC_API_KEY.
- Codex subscription account through the official Codex CLI.
- Codex/OpenAI API through OPENAI_API_KEY.

This command does not sign in, read token stores, print secrets, or invoke
provider CLIs. It only reports whether the harness can see each lane's local
activation prerequisite.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.endpoints import build_endpoints  # noqa: E402
from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


LANES = [
    {
        "id": "claude_subscription",
        "provider": "claude",
        "mode": "plan",
        "kind": "subscription_cli",
        "cli_env": "CLAUDE_CLI",
        "fallback_commands": ["claude.exe", "claude"] if os.name == "nt" else ["claude"],
        "next_action": (
            "Authenticate the official Claude CLI in an operator-controlled "
            "terminal. Set CLAUDE_CLI only if the command is nonstandard."
        ),
    },
    {
        "id": "claude_api",
        "provider": "claude",
        "mode": "api",
        "kind": "api_key",
        "key_env": "ANTHROPIC_API_KEY",
        "next_action": "Set ANTHROPIC_API_KEY in the local secret environment.",
    },
    {
        "id": "codex_subscription",
        "provider": "codex",
        "mode": "plan",
        "kind": "subscription_cli",
        "cli_env": "CODEX_CLI",
        "fallback_commands": ["codex.cmd", "codex"] if os.name == "nt" else ["codex"],
        "next_action": (
            "Authenticate the official Codex CLI in an operator-controlled "
            "terminal. Set CODEX_CLI only if the command is nonstandard."
        ),
    },
    {
        "id": "codex_api",
        "provider": "codex",
        "mode": "api",
        "kind": "api_key",
        "key_env": "OPENAI_API_KEY",
        "next_action": "Set OPENAI_API_KEY in the local secret environment.",
    },
]


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _command_head(raw: str) -> str:
    if not raw:
        return ""
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()
    return parts[0] if parts else ""


def _resolve_cli(cli_env: str, fallback_commands: list[str]) -> dict:
    override = os.environ.get(cli_env, "")
    candidates = []
    head = _command_head(override)
    if head:
        candidates.append(head)
    candidates.extend(fallback_commands)
    seen = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.append(candidate)
    for candidate in seen:
        path = shutil.which(candidate)
        if path:
            return {
                "cli_env": cli_env,
                "cli_env_set": bool(override),
                "command": candidate,
                "path": path,
                "found": True,
            }
    return {
        "cli_env": cli_env,
        "cli_env_set": bool(override),
        "command": seen[0] if seen else "",
        "path": "",
        "found": False,
    }


def _lane_status(lane: dict) -> dict:
    if lane["kind"] == "api_key":
        key_env = lane["key_env"]
        configured = bool(os.environ.get(key_env))
        return {
            "id": lane["id"],
            "provider": lane["provider"],
            "mode": lane["mode"],
            "kind": lane["kind"],
            "configured": configured,
            "secret_value_exposed": False,
            "evidence": {
                "key_env": key_env,
                "key_env_set": configured,
            },
            "next_action": "" if configured else lane["next_action"],
        }
    cli = _resolve_cli(lane["cli_env"], lane["fallback_commands"])
    configured = bool(cli["found"])
    return {
        "id": lane["id"],
        "provider": lane["provider"],
        "mode": lane["mode"],
        "kind": lane["kind"],
        "configured": configured,
        "secret_value_exposed": False,
        "evidence": cli,
        "next_action": "" if configured else lane["next_action"],
    }


def _endpoint_ladder_snapshot() -> list[dict]:
    rows = []
    for lane in LANES:
        backends = build_endpoints(
            providers=[lane["provider"]],
            modes=(lane["mode"],),
            only_configured=True,
        )
        rows.append({
            "lane_id": lane["id"],
            "provider": lane["provider"],
            "mode": lane["mode"],
            "backend_count": len(backends),
            "backends": [
                {
                    "name": getattr(backend, "name", ""),
                    "class": backend.__class__.__name__,
                    "model": getattr(backend, "model", ""),
                }
                for backend in backends
            ],
        })
    return rows


def build_status() -> dict:
    lanes = [_lane_status(lane) for lane in LANES]
    configured = [lane for lane in lanes if lane["configured"]]
    return {
        "schema": "harness.endpoint-auth-status/v1",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "secret_policy": "presence-only; no token, key, or credential values emitted",
        "lanes": lanes,
        "endpoint_ladder": _endpoint_ladder_snapshot(),
        "summary": {
            "lanes": len(lanes),
            "configured_lanes": len(configured),
            "missing_lanes": len(lanes) - len(configured),
            "all_configured": len(configured) == len(lanes),
        },
    }


def render_markdown(status: dict) -> str:
    lines = [
        "# Harness endpoint auth status",
        "",
        f"- Schema: `{status['schema']}`",
        f"- Timestamp UTC: `{status['timestamp_utc']}`",
        f"- Secret policy: {status['secret_policy']}",
        "",
        "| Lane | Provider | Mode | Kind | Configured | Evidence |",
        "|---|---|---|---|---:|---|",
    ]
    for lane in status["lanes"]:
        evidence = lane["evidence"]
        if lane["kind"] == "api_key":
            detail = f"{evidence['key_env']} set={evidence['key_env_set']}"
        else:
            detail = (
                f"{evidence['command']} found={evidence['found']} "
                f"path={evidence['path'] or 'missing'}"
            )
        lines.append(
            "| {id} | {provider} | {mode} | {kind} | {configured} | {detail} |".format(
                id=lane["id"],
                provider=lane["provider"],
                mode=lane["mode"],
                kind=lane["kind"],
                configured=str(lane["configured"]).lower(),
                detail=detail.replace("|", "\\|"),
            )
        )
    lines.extend(["", "## Next actions", ""])
    for lane in status["lanes"]:
        if lane["next_action"]:
            lines.append(f"- `{lane['id']}`: {lane['next_action']}")
    if all(not lane["next_action"] for lane in status["lanes"]):
        lines.append("- All account lanes are visible to the harness.")
    return "\n".join(lines) + "\n"


def _status_verdict(status: dict) -> str:
    return "AUTH_READY" if status.get("summary", {}).get("all_configured") else "AUTH_PARTIAL"


def _store_status_outputs(
    status: dict,
    *,
    store_root: str,
    run_id: str = "",
    artifact_paths: list[tuple[str, str]] | None = None,
) -> list[dict]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="endpoint_auth_status",
            body=status,
            run_id=run_id,
            verdict=_status_verdict(status),
        )
    ]
    for path_text, label in artifact_paths or []:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument(
        "--require",
        default="",
        help="comma-separated lane ids to require, or 'all'",
    )
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    status = build_status()
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(status, indent=2), encoding="utf-8")
    if args.markdown_out:
        md = Path(args.markdown_out)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(status), encoding="utf-8")
    store_outputs = _store_status_outputs(
        status,
        store_root=args.store_root,
        run_id=args.run_id,
        artifact_paths=[
            (args.out, "endpoint-auth-status-json"),
            (args.markdown_out, "endpoint-auth-status-markdown"),
        ],
    )
    if store_outputs:
        status = {**status, "store_outputs": store_outputs}
    print(json.dumps(status, indent=2))

    required = set()
    requested = set(_split_csv(args.require))
    if "all" in requested:
        required = {lane["id"] for lane in status["lanes"]}
    else:
        required = requested
    missing = [
        lane["id"] for lane in status["lanes"]
        if lane["id"] in required and not lane["configured"]
    ]
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
