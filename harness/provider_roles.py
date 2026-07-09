"""Shared provider role normalization for benchmark and harness artifacts."""

from __future__ import annotations

from typing import Any


PROVIDER_ROLES = [
    {
        "role_id": "flywheel",
        "display_name": "Flywheel harness",
        "aliases": ["serve", "flywheel", "local-serve", "flywheel-serve"],
    },
    {
        "role_id": "codex",
        "display_name": "Codex harness / 5.3-Codex-Spark",
        "aliases": ["codex", "gpt-5.3-codex-spark", "5.3-codex-spark", "5.3-Codex-Spark"],
    },
    {
        "role_id": "ollama_local",
        "display_name": "Ollama/local model endpoint",
        "aliases": ["ollama", "local", "local-ollama", "ollama-local"],
    },
    {
        "role_id": "claude_code",
        "display_name": "Claude Code harness",
        "aliases": ["claude", "claude-code", "claude_code"],
    },
    {
        "role_id": "opencode",
        "display_name": "OpenCode harness",
        "aliases": ["opencode", "open-code", "open_code"],
    },
    {
        "role_id": "dry_fixture",
        "display_name": "Dry fixture baseline",
        "aliases": ["dry", "fixture", "dry-fixture"],
    },
]


def provider_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for row in PROVIDER_ROLES:
        role_id = str(row["role_id"])
        aliases[role_id.lower()] = role_id
        for alias in row.get("aliases", []):
            aliases[str(alias).strip().lower()] = role_id
    return aliases


def provider_role(provider: Any) -> str:
    raw = str(provider or "").strip()
    if not raw:
        return ""
    return provider_alias_map().get(raw.lower(), raw)


def provider_roles_for(providers: list[Any]) -> list[str]:
    roles: list[str] = []
    for provider in providers:
        role = provider_role(provider)
        if role and role not in roles:
            roles.append(role)
    return roles


def annotate_provider_roles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        if not isinstance(row, dict):
            continue
        role = provider_role(row.get("provider_role") or row.get("provider"))
        if role:
            row["provider_role"] = role
    return rows
