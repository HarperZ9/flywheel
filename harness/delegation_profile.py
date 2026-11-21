"""delegation_profile.py -- operator delegation profiles for Flywheel.

Evaluates whether an action is covered by the active delegation profile
loaded from ~/.flywheel/settings.json. Receipts remain mandatory under
every profile, and credential-scraping or ToS-bypass actions are refused
regardless of profile or channel opt-in.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

DELEGATION_SCHEMA = "flywheel.delegation-profile/v1"
DELEGATION_PROFILES: tuple[str, ...] = (
    "supervised",
    "workstation-native",
    "outbound-delegated",
)
DEFAULT_PROFILE = "supervised"
OUTBOUND_CHANNELS: frozenset[str] = frozenset({"email", "social", "blog"})

_OUTBOUND_PREFIXES: tuple[str, ...] = (
    "outbound.", "send.", "publish.", "post.",
    "email.", "mail.", "social.", "blog.",
)
_PROHIBITED_BOUNDARY = re.compile(
    r"(password[_.-]?scrap|credential[_.-]?scrap|scrap\w*[_.-]?(password|credential|cookie|token)|"
    r"cookie[_.-]?scrap|token[_.-]?harvest|tos[_.-]?bypass|bypass[_.-]?tos|"
    r"secret[_.-]?exfil|account[_.-]?takeover|login[_.-]?impersonat)",
    re.IGNORECASE,
)


def _read_settings(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _normalize_channels(raw: Any) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return {}
    return {
        key.strip().lower(): value
        for key, value in raw.items()
        if isinstance(key, str) and key.strip().lower() in OUTBOUND_CHANNELS and isinstance(value, bool)
    }


def load_delegation_profile(flywheel_home: Path | str | None = None) -> dict[str, Any]:
    """Load delegation_profile and outbound_channels from settings.json."""
    home = (
        Path(flywheel_home)
        if flywheel_home is not None
        else Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))
    )
    settings = _read_settings(home / "settings.json")
    raw_profile = settings.get("delegation_profile")
    profile = raw_profile if isinstance(raw_profile, str) and raw_profile in DELEGATION_PROFILES else DEFAULT_PROFILE
    return {
        "schema": DELEGATION_SCHEMA,
        "profile": profile,
        "outbound_channels": _normalize_channels(settings.get("outbound_channels")),
    }


def _resolve_profile(
    profile: str | dict[str, Any],
    outbound_channels: dict[str, bool] | None,
) -> tuple[str, dict[str, bool], bool]:
    if isinstance(profile, dict):
        raw_name = profile.get("profile") or profile.get("delegation_profile")
        channels = _normalize_channels(profile.get("outbound_channels"))
        if outbound_channels is not None:
            channels.update(_normalize_channels(outbound_channels))
    else:
        raw_name = profile
        channels = _normalize_channels(outbound_channels)
    if isinstance(raw_name, str) and raw_name in DELEGATION_PROFILES:
        return raw_name, channels, True
    return DEFAULT_PROFILE, channels, False


def _infer_channel(action: str, channel: str | None) -> str | None:
    if isinstance(channel, str) and channel.strip():
        return channel.strip().lower()
    for name in OUTBOUND_CHANNELS:
        if action.startswith(f"{name}."):
            return name
    return "email" if action.startswith("mail.") else None


def _decision(allowed: bool, prompt: bool, profile: str, reason: str) -> dict[str, Any]:
    return {
        "allowed_by_profile": allowed,
        "requires_per_action_prompt": prompt,
        "receipt_required": True,
        "profile": profile,
        "reason": reason,
    }


def _evaluate_outbound(name: str, chan: str | None, channels: dict[str, bool]) -> dict[str, Any]:
    if name == "workstation-native":
        return _decision(False, True, name, "workstation-native does not cover outbound actions")
    if chan not in OUTBOUND_CHANNELS:
        return _decision(False, True, name, "outbound channel is missing or outside allowed channels")
    if channels.get(chan) is not True:
        return _decision(False, True, name, f"outbound channel {chan!r} is not explicitly opted in")
    return _decision(True, False, name, f"outbound-delegated covers opted-in channel {chan!r} with receipts")


def evaluate_delegation(
    action: str,
    profile: str | dict[str, Any],
    *,
    channel: str | None = None,
    outbound_channels: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Evaluate action coverage under the active delegation profile."""
    name, channels, known = _resolve_profile(profile, outbound_channels)
    act = str(action or "").strip().lower()
    chan = _infer_channel(act, channel)

    if not known:
        return _decision(False, True, DEFAULT_PROFILE, "unknown delegation profile; defaulting to supervised")
    if not act:
        return _decision(False, True, name, "empty action requires explicit operator approval")
    if _PROHIBITED_BOUNDARY.search(act) or (chan and _PROHIBITED_BOUNDARY.search(chan)):
        return _decision(False, True, name, "blocked by credential-boundary and ToS policy")
    if name == "supervised":
        return _decision(False, True, name, "supervised profile requires per-action operator approval")
    is_outbound = chan is not None or any(act.startswith(p) for p in _OUTBOUND_PREFIXES)
    if not is_outbound:
        return _decision(True, False, name, f"{name} covers local workstation actions with receipts")
    return _evaluate_outbound(name, chan, channels)
