#!/usr/bin/env python
"""safe-read - workspace read/write hook.

Routes read and write requests through the standard workspace file
layer. Exit code 2 returns command guidance; exit 0 uses the direct
path.

Trigger: PreToolUse matching "Read|Edit|Write".
Stdin:    JSON with tool_name + tool_input.file_path.
Stdout:   silent on allow.
Stderr:   guidance message on block (exit 2).

Mode gate:
    When the workstation IO mode is "off" (research/academic profile),
    this hook passes through unconditionally — no calibration is applied.
    Matches the same gate in safe-exec-redirect.py.

Tools path:
    Resolved from BEHAVIOR_TRANSFORM_TOOLS env var, then from the hook
    file location (../tools/).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Scope / override configuration
# ---------------------------------------------------------------------------

IN_SCOPE_COMPONENTS = (
    "behavior-transform.io",
    "behavior_transform",
    "AGENTS",
    "warden_shell",
    "project-docs",
)

ALLOW_OVERRIDE_NAMES = {
    "install_precommit.py",
    "SKILL.md",
    "CLAUDE.md",
    "README.md",
    "io_channel.py",
    "channel_router.py",
    "container_ecosystem.py",
    "io_state.py",
    "text_rules.py",
}

ALLOW_OVERRIDE_PREFIXES = ("safe_", "safe-", "aup_", "aup-")
ALLOW_OVERRIDE_SUFFIXES = (".py", ".ps1", ".sh", ".md")
ALLOW_OVERRIDE_TOOL_PARTS = {"behavior-transform.io", "tools"}

ALLOW_OVERRIDE_DIRS = {".warden-safe-cache", ".bt-cache"}

BINARY_PASSTHROUGH_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff",
    ".ico", ".heic", ".avif", ".svg", ".pdf", ".ipynb",
    ".mp3", ".wav", ".flac", ".ogg", ".m4a",
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".docx", ".xlsx", ".pptx", ".odt", ".ods",
    ".ttf", ".otf", ".woff", ".woff2",
}

CLAUDE_INFRA_SUBDIRS = {
    "hooks", "skills", "commands", "agents", "plugins",
    "output-styles", "ide", "statsig", "shell-snapshots",
}


def _tools_path() -> Path:
    """Resolve the behavior-transform tools directory."""
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt and Path(bt).is_dir():
        return Path(bt)
    return Path(__file__).resolve().parents[1] / "tools"


def _tools_cmd(name: str) -> str:
    return str(_tools_path() / name).replace("\\", "/")


READ_GUIDANCE_MSG = """\
Use the standard read layer for this path:

    python {safe_read} "{{path}}"

Options:
    --summary          structural summary only (line/byte count, sha prefix)
    --lines LO:HI      slice a large file
    --hash             provenance pin only
""".format(safe_read=_tools_cmd("safe_read.py"))

WRITE_GUIDANCE_MSG = """\
Use the standard write layer for this path:

    python {safe_write} "{{path}}" --from <src>

    # Inline:
    python {safe_write} "{{path}}" --content "..."

    # Audit gate:
    python {safe_write} "{{path}}" --from <src> --check-only
""".format(safe_write=_tools_cmd("safe_write.py"))


def _is_in_scope(path: Path) -> bool:
    return True


def _is_claude_infra(path: Path) -> bool:
    parts = path.parts
    try:
        idx = parts.index(".claude")
    except ValueError:
        return False
    if idx + 1 >= len(parts):
        return False
    next_part = parts[idx + 1]
    if next_part == "projects":
        return False
    if next_part in CLAUDE_INFRA_SUBDIRS:
        return True
    if idx + 2 >= len(parts):
        return True
    return False


def _is_override(path: Path) -> bool:
    if path.name in ALLOW_OVERRIDE_NAMES:
        return True
    if path.suffix.lower() in BINARY_PASSTHROUGH_EXTENSIONS:
        return True
    if path.name.startswith(ALLOW_OVERRIDE_PREFIXES) and path.suffix in ALLOW_OVERRIDE_SUFFIXES:
        return True
    if path.name in ("install_precommit.py", "pre-commit-aup.sh"):
        return True
    parts = set(path.parts)
    if ALLOW_OVERRIDE_TOOL_PARTS.issubset(parts) and path.suffix in ALLOW_OVERRIDE_SUFFIXES:
        return True
    if any(d in parts for d in ALLOW_OVERRIDE_DIRS):
        return True
    if _is_claude_infra(path):
        return True
    return False


def _gate() -> bool:
    """Return True (caller should sys.exit(0)) when mode is research/academic."""
    import os
    from pathlib import Path

    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    _tools = (
        Path(bt)
        if bt and Path(bt).is_dir()
        else Path(__file__).resolve().parents[1] / "tools"
    )
    if str(_tools) not in sys.path:
        sys.path.insert(0, str(_tools))
    try:
        from io_state import env_mode  # type: ignore[import]
        return env_mode() == "off"
    except Exception:
        return False  # fail open


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if _gate():
        return 0

    # --- Cleanroom direct path ---
    import os as _cr_os, sys as _cr_sys
    _cr_sys.path.insert(0, _cr_os.path.dirname(_cr_os.path.abspath(__file__)))
    try:
        from _warden_cleanroom import cleanroom_active as _cr_active, write_gap_journal as _cr_journal
        _active, _tag_required = _cr_active("safe-read-redirect")
        if _active:
            if _tag_required:
                _cr_journal("safe-read-redirect", data)
            return 0
    except Exception:
        pass

    tool_name = data.get("tool_name", "")
    if tool_name not in {"Read", "Edit", "Write"}:
        return 0

    tool_input = data.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not file_path:
        return 0

    try:
        path = Path(file_path)
    except (TypeError, ValueError):
        return 0

    if _is_override(path):
        return 0

    if not _is_in_scope(path):
        return 0

    if tool_name == "Read":
        sys.stderr.write(READ_GUIDANCE_MSG.format(path=file_path))
    else:
        sys.stderr.write(WRITE_GUIDANCE_MSG.format(tool=tool_name, path=file_path))
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        sys.stderr.write(f"safe-read hook error: {e}\n")
        sys.exit(0)
