#!/usr/bin/env python3
"""Shared IO-channel state for WARDEN safe_* tools.

The channel switch remains binary for existing hooks and wrappers:

* IO-on  -> supported channels use the standard workspace path.
* IO-off -> supported channels use the direct native-state text path.

Research and academic commands are aliases for IO-off; standard is an
alias for IO-on. The state file stays intentionally small.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Iterable
from typing import Literal

IOMode = Literal["on", "off"]
IOProfile = Literal["ops", "research", "academic", "standard"]

ENV_NAME = "WARDEN_IO_CHANNEL"
LEGACY_ENV_NAME = "WARDEN_IO"
STATE_FILE_ENV_NAME = "WARDEN_IO_STATE_FILE"
ON_VALUES = {
    "1",
    "true",
    "yes",
    "on",
    "full",
    "transform",
    "transformed",
    "standard",
    "standard-mode",
    "ops",
    "ops-mode",
    "security",
    "security-mode",
    "defense",
    "defense-mode",
    "offense",
    "offense-mode",
    "opsec",
    "opsec-mode",
    "discretion",
    "discretion-mode",
}
OFF_VALUES = {
    "0",
    "false",
    "no",
    "off",
    "raw",
    "plain",
    "direct",
    "none",
    "native",
    "research",
    "research-mode",
    "academic",
    "academic-mode",
}

PROFILE_ALIASES: dict[str, IOProfile] = {
    "1": "ops",
    "true": "ops",
    "yes": "ops",
    "on": "ops",
    "full": "ops",
    "transform": "ops",
    "transformed": "ops",
    "ops": "ops",
    "ops-mode": "ops",
    "security": "ops",
    "security-mode": "ops",
    "defense": "ops",
    "defense-mode": "ops",
    "offense": "ops",
    "offense-mode": "ops",
    "opsec": "ops",
    "opsec-mode": "ops",
    "discretion": "ops",
    "discretion-mode": "ops",
    "0": "research",
    "false": "research",
    "no": "research",
    "off": "research",
    "raw": "research",
    "plain": "research",
    "direct": "research",
    "none": "research",
    "native": "research",
    "research": "research",
    "research-mode": "research",
    "academic": "academic",
    "academic-mode": "academic",
    "standard": "standard",
    "standard-mode": "standard",
}


def normalize_mode(value: object, default: IOMode | None = None) -> IOMode | None:
    """Normalize a user/env value to ``on`` / ``off``."""
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ON_VALUES:
        return "on"
    if text in OFF_VALUES:
        return "off"
    return default


def normalize_profile(value: object, default: IOProfile | None = None) -> IOProfile | None:
    """Normalize a user/env value to a named runtime profile."""
    if value is None:
        return default
    text = str(value).strip().lower()
    return PROFILE_ALIASES.get(text, default)


def profile_for_mode(mode: IOMode) -> IOProfile:
    """Return the default named profile for a binary IO mode."""
    return "ops" if normalize_mode(mode) == "on" else "research"


def state_file_path() -> Path:
    """Return the workstation-level IO mode state path."""
    override = os.environ.get(STATE_FILE_ENV_NAME)
    if override:
        return Path(override).expanduser()
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if home:
        return Path(home) / ".warden" / "io-mode.json"
    return Path.home() / ".warden" / "io-mode.json"


def read_state(default: dict | None = None) -> dict | None:
    """Read the persisted workstation IO state, if present."""
    path = state_file_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return payload if isinstance(payload, dict) else {"mode": payload}


def read_state_mode(default: IOMode | None = None) -> IOMode | None:
    """Read the persisted workstation IO mode, if present."""
    payload = read_state()
    if isinstance(payload, dict):
        return normalize_mode(payload.get("mode"), default)
    return normalize_mode(payload, default)


def read_state_profile(default: IOProfile | None = None) -> IOProfile | None:
    """Read the persisted workstation runtime profile, if present."""
    payload = read_state()
    if not isinstance(payload, dict):
        return normalize_profile(payload, default)
    profile = normalize_profile(payload.get("profile"))
    if profile is not None:
        return profile
    mode = normalize_mode(payload.get("mode"))
    if mode is not None:
        return profile_for_mode(mode)
    return default


def write_state_mode(
    mode: IOMode,
    *,
    source: str = "io_state",
    profile: IOProfile | str | None = None,
) -> Path:
    """Persist the workstation IO mode for future tool invocations."""
    normalized = normalize_mode(mode)
    if normalized is None:
        raise ValueError(f"invalid IO mode: {mode!r}")
    normalized_profile = normalize_profile(profile) or normalize_profile(mode) or profile_for_mode(normalized)
    path = state_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": normalized,
        "profile": normalized_profile,
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": source,
        "pid": os.getpid(),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def env_mode(default: IOMode = "on") -> IOMode:
    """Return the active IO mode: env override, state file, then default."""
    return (
        normalize_mode(os.environ.get(ENV_NAME))
        or normalize_mode(os.environ.get(LEGACY_ENV_NAME))
        or read_state_mode()
        or default
    )


def env_profile(default: IOProfile = "ops") -> IOProfile:
    """Return the active named runtime profile."""
    return (
        normalize_profile(os.environ.get(ENV_NAME))
        or normalize_profile(os.environ.get(LEGACY_ENV_NAME))
        or read_state_profile()
        or default
    )


def set_env_mode(mode: IOMode) -> None:
    """Set current-process environment toggles used by wrappers/hooks."""
    normalized = normalize_mode(mode)
    if normalized is None:
        raise ValueError(f"invalid IO mode: {mode!r}")
    os.environ[ENV_NAME] = normalized
    os.environ[LEGACY_ENV_NAME] = normalized


def add_io_toggle_args(parser: argparse.ArgumentParser) -> None:
    """Add common ``--IO-on`` / ``--IO-off`` options to a parser."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--IO-on",
        dest="io_channel",
        action="store_const",
        const="on",
        default=None,
        help="Force standard workspace IO for this invocation.",
    )
    group.add_argument(
        "--IO-off",
        dest="io_channel",
        action="store_const",
        const="off",
        default=None,
        help="Use the direct native-state text path for this invocation.",
    )


def mode_from_args(args: object, default: IOMode = "on") -> IOMode:
    """Resolve explicit CLI toggle first, then environment."""
    explicit = normalize_mode(getattr(args, "io_channel", None))
    return explicit or env_mode(default=default)


def transforms_enabled(args: object | None = None, default: IOMode = "on") -> bool:
    """True when the active invocation should apply IO transforms."""
    if args is None:
        return env_mode(default=default) == "on"
    return mode_from_args(args, default=default) == "on"


def split_io_toggles(argv: Iterable[str]) -> tuple[IOMode | None, list[str]]:
    """Remove ``--IO-on`` / ``--IO-off`` from an argv vector.

    The last toggle wins so wrappers can accept the flag anywhere in the
    command line, including after the wrapped CLI name.
    """
    mode: IOMode | None = None
    rest: list[str] = []
    for item in argv:
        if item == "--IO-on":
            mode = "on"
        elif item == "--IO-off":
            mode = "off"
        else:
            rest.append(item)
    return mode, rest
