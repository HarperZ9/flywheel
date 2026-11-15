#!/usr/bin/env python3
"""Workstation-level WARDEN IO mode switch.

The shell commands ``--IO-on``, ``--IO-off``, ``--research-mode``,
``--academic-mode``, and ``--standard-mode`` are installed as shims that
call this module. The module writes one user-scoped mode value; wrappers
and hooks read that state when no per-process ``WARDEN_IO_CHANNEL``
override is present.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Iterable

from io_state import (
    ENV_NAME,
    LEGACY_ENV_NAME,
    IOProfile,
    IOMode,
    env_mode,
    env_profile,
    normalize_mode,
    normalize_profile,
    read_state_mode,
    read_state_profile,
    set_env_mode,
    state_file_path,
    write_state_mode,
)

_SCRIPT_PATH = Path(__file__).resolve()
CLEANROOM_CONFIG_ENV = "WARDEN_CLEANROOM_CONFIG"
CLEANROOM_SENTINEL_ENV = "WARDEN_CLEANROOM_SENTINEL"


def default_bin_dir() -> Path:
    """Return the per-user shim directory."""
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if home:
        return Path(home) / ".warden" / "bin"
    return Path.home() / ".warden" / "bin"


def _python_cmd() -> str:
    return sys.executable or "python"


def _cmd_shim(action: str) -> str:
    return (
        "@echo off\r\n"
        f"\"{_python_cmd()}\" \"{_SCRIPT_PATH}\" {action} %*\r\n"
    )


def _sh_shim(action: str) -> str:
    return (
        "#!/usr/bin/env sh\n"
        f"exec \"{_python_cmd()}\" \"{_SCRIPT_PATH}\" {action} \"$@\"\n"
    )


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")
    try:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def install_shims(bin_dir: Path | None = None, *, update_path: bool = True) -> dict:
    """Install mode shims into a user PATH directory."""
    target = (bin_dir or default_bin_dir()).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    shim_actions = {
        "--IO-on": "on",
        "--IO-off": "off",
        "--research-mode": "research",
        "--academic-mode": "academic",
        "--standard-mode": "standard",
        "--ops-mode": "ops",
        "--security-mode": "security",
    }
    for stem, action in shim_actions.items():
        cmd_path = target / f"{stem}.cmd"
        sh_path = target / stem
        cmd_path.write_text(_cmd_shim(action), encoding="ascii", newline="")
        _write_executable(sh_path, _sh_shim(action))
        written.extend([str(cmd_path), str(sh_path)])

    path_updated = False
    path_update_supported = os.name == "nt"
    if update_path and os.name == "nt":
        path_updated = _ensure_windows_user_path(target)

    return {
        "bin_dir": str(target),
        "written": written,
        "path_updated": path_updated,
        "path_update_supported": path_update_supported,
    }


def _action_mode(action: str) -> IOMode:
    """Resolve a CLI action into the binary IO mode."""
    if action in ("on", "standard", "ops", "security", "defense", "offense", "opsec"):
        return "on"
    if action in ("off", "research", "academic"):
        return "off"
    raise ValueError(f"unsupported IO action: {action!r}")


def _action_profile(action: str) -> IOProfile:
    """Resolve a CLI action into the named runtime profile."""
    profile = normalize_profile(action)
    if profile is not None:
        return profile
    return "ops" if _action_mode(action) == "on" else "research"


def _cleanroom_config_path() -> Path:
    override = os.environ.get(CLEANROOM_CONFIG_ENV)
    if override:
        return Path(override).expanduser()
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if home:
        return Path(home) / ".claude" / "cleanroom.json"
    return Path.home() / ".claude" / "cleanroom.json"


def _cleanroom_sentinel_path() -> Path:
    override = os.environ.get(CLEANROOM_SENTINEL_ENV)
    if override:
        return Path(override).expanduser()
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if home:
        return Path(home) / ".claude" / ".warden-cleanroom"
    return Path.home() / ".claude" / ".warden-cleanroom"


def _read_cleanroom_config() -> dict:
    try:
        payload = json.loads(_cleanroom_config_path().read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _sync_cleanroom_state(mode: IOMode, profile: IOProfile) -> Path:
    """Mirror the runtime profile into the legacy hook gate config."""
    path = _cleanroom_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = _read_cleanroom_config()
    cfg["active"] = mode == "off"
    cfg["runtime_mode"] = mode
    cfg["runtime_profile"] = profile
    cfg["updated_by"] = "io_mode"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)

    sentinel = _cleanroom_sentinel_path()
    if mode == "off":
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("warden clean-room active via runtime profile\n", encoding="utf-8")
    else:
        try:
            sentinel.unlink()
        except FileNotFoundError:
            pass
    return path


def _ensure_windows_user_path(bin_dir: Path) -> bool:
    """Add the shim directory to the current user's Windows PATH."""
    import winreg

    wanted = str(bin_dir)
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_READ | winreg.KEY_WRITE,
    ) as key:
        try:
            current, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, value_type = "", winreg.REG_EXPAND_SZ

        parts = [p for p in str(current).split(os.pathsep) if p]
        if any(Path(p).expanduser().resolve() == bin_dir for p in parts if p.strip()):
            return False

        new_value = wanted if not current else wanted + os.pathsep + str(current)
        if value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
            value_type = winreg.REG_EXPAND_SZ
        winreg.SetValueEx(key, "Path", 0, value_type, new_value)

    try:
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            None,
        )
    except Exception:
        pass
    return True


def _status_payload() -> dict:
    env_override = (
        normalize_mode(os.environ.get(ENV_NAME))
        or normalize_mode(os.environ.get(LEGACY_ENV_NAME))
    )
    state_mode = read_state_mode()
    state_profile = read_state_profile()
    active_mode = env_mode()
    active_profile = env_profile()
    return {
        "mode": active_mode,
        "profile": active_profile,
        "env_override": env_override,
        "state_mode": state_mode,
        "state_profile": state_profile,
        "state_file": str(state_file_path()),
        "hook_layer": "armed" if active_mode == "on" else "passthrough",
        "cleanroom_config": str(_cleanroom_config_path()),
    }


def _emit(payload: dict, *, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return
    if "mode" in payload:
        sys.stdout.write(f"WARDEN IO Channel: {payload['mode']}\n")
    if payload.get("profile"):
        sys.stdout.write(f"profile: {payload['profile']}\n")
    if payload.get("hook_layer"):
        sys.stdout.write(f"hook_layer: {payload['hook_layer']}\n")
    if payload.get("state_file"):
        sys.stdout.write(f"state_file: {payload['state_file']}\n")
    if payload.get("cleanroom_config"):
        sys.stdout.write(f"cleanroom_config: {payload['cleanroom_config']}\n")
    if payload.get("bin_dir"):
        sys.stdout.write(f"bin_dir: {payload['bin_dir']}\n")
    if payload.get("path_updated"):
        sys.stdout.write("path: updated for future terminals\n")
    elif payload.get("path_update_supported") is False:
        sys.stdout.write("path: manual PATH update required on this shell family\n")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set, inspect, or install the workstation-level WARDEN IO switch."
    )
    parser.add_argument(
        "action",
        choices=(
            "on",
            "off",
            "research",
            "academic",
            "standard",
            "ops",
            "security",
            "defense",
            "offense",
            "opsec",
            "status",
            "install",
        ),
        help="Set IO mode, print status, or install mode shims.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--mode-only",
        action="store_true",
        help="Print only the resolved mode; intended for shell startup scripts.",
    )
    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=None,
        help="Shim install directory for the install action.",
    )
    parser.add_argument(
        "--no-path",
        action="store_true",
        help="Install shims without updating the user PATH.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.action in (
        "on",
        "off",
        "research",
        "academic",
        "standard",
        "ops",
        "security",
        "defense",
        "offense",
        "opsec",
    ):
        mode = _action_mode(args.action)
        profile = _action_profile(args.action)
        path = write_state_mode(mode, source="io_mode", profile=profile)
        cleanroom_path = _sync_cleanroom_state(mode, profile)
        set_env_mode(mode)
        if args.mode_only:
            sys.stdout.write(mode + "\n")
            return 0
        _emit(
            {
                "mode": mode,
                "profile": profile,
                "state_file": str(path),
                "hook_layer": "armed" if mode == "on" else "passthrough",
                "cleanroom_config": str(cleanroom_path),
            },
            as_json=args.json,
        )
        return 0

    if args.action == "status":
        payload = _status_payload()
        if args.mode_only:
            sys.stdout.write(str(payload["mode"]) + "\n")
            return 0
        _emit(payload, as_json=args.json)
        return 0

    result = install_shims(args.bin_dir, update_path=not args.no_path)
    if args.json:
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
    else:
        _emit(result, as_json=False)
        sys.stdout.write(
            "commands: --IO-on, --IO-off, --research-mode, --academic-mode, --standard-mode, --ops-mode, --security-mode\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
