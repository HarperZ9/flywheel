#!/usr/bin/env python3
"""warden_safe_input - operator-input companion to safe_read / safe_write.

The Claude Code UserPromptSubmit hook can detect Tier-1 vocabulary in the
operator's prompt and inject advisory calibration context, but it cannot
rewrite the prompt itself before it reaches the assistant. This standalone
tool fills the gap: the operator runs it BEFORE pasting their prompt; the
calibrated form goes to stdout (or the clipboard) for direct paste.

Usage
-----
    # Stdin pipe:
    Get-Clipboard | python tools/safe_input.py
    echo "raw text" | python tools/safe_input.py

    # Inline:
    python tools/safe_input.py --content "raw text"

    # From a file:
    python tools/safe_input.py --from draft.txt

    # Substitution counter only (no calibrated body):
    python tools/safe_input.py --diff-only --content "raw text"

    # Audit trail without emitting calibrated text (CI / scoring):
    python tools/safe_input.py --check-only --content "raw text"

    # Copy calibrated form to clipboard (Windows / macOS):
    python tools/safe_input.py --to-clipboard --from draft.txt

Behavior
--------
* Default: emits calibrated text to stdout with a one-line header.
* Idempotent on already-calibrated text.
* Archives raw input to .warden-safe-cache/prompts/<sha>.raw unless --no-archive.
* Never sends the prompt anywhere -- purely a local string transformation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from io_state import add_io_toggle_args, transforms_enabled
from _core import build_engine


_ROOT = Path(__file__).resolve().parent


def _apply_calibration(text: str) -> str:
    """Apply calibration engine and return the calibrated text."""
    engine = build_engine()
    calibrated, _, _ = engine.apply(text)
    return calibrated


def _from_clipboard() -> str:
    """Best-effort clipboard read on Windows / macOS / Linux. Returns "" on failure."""
    if sys.platform.startswith("win"):
        # PowerShell's Get-Clipboard is the most reliable Windows path; avoids
        # depending on a Python-side clipboard package.
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0:
                return proc.stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError):
            pass
        return ""
    if sys.platform == "darwin":
        try:
            proc = subprocess.run(["pbpaste"], capture_output=True, timeout=5, check=False)
            if proc.returncode == 0:
                return proc.stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError):
            pass
        return ""
    # Linux: try xclip then xsel.
    for args in (
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ):
        try:
            proc = subprocess.run(args, capture_output=True, timeout=5, check=False)
            if proc.returncode == 0:
                return proc.stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError):
            continue
    return ""


def _read_input(*, from_path: Path | None, content: str | None, from_clipboard: bool) -> str:
    if from_clipboard:
        return _from_clipboard()
    if from_path is not None:
        return from_path.read_text(encoding="utf-8", errors="replace")
    if content is not None:
        return content
    buf = getattr(sys.stdin, "buffer", None)
    if buf is not None:
        return buf.read().decode("utf-8", errors="replace")
    return sys.stdin.read()


def _archive_raw(raw: str) -> Path:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    base = Path.cwd() / ".warden-safe-cache" / "prompts"
    base.mkdir(parents=True, exist_ok=True)
    archive = base / f"{digest}.raw"
    archive.write_text(raw, encoding="utf-8")
    return archive


def _to_clipboard(text: str) -> bool:
    """Best-effort clipboard copy on Windows / macOS. Returns True on success."""
    if sys.platform.startswith("win"):
        try:
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-16le"))
            return proc.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    if sys.platform == "darwin":
        try:
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"))
            return proc.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    # Linux: try xclip then xsel; do not fail hard if neither is present.
    for tool, args in (("xclip", ["xclip", "-selection", "clipboard"]),
                       ("xsel", ["xsel", "--clipboard", "--input"])):
        try:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate operator-typed text before pasting into the chat. "
            "Local-only transformation; nothing is sent anywhere."
        )
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--from", dest="from_path", type=Path, default=None,
                     help="Read raw text from this file.")
    src.add_argument("--content", type=str, default=None,
                     help="Inline raw text (small strings).")
    src.add_argument("--from-clipboard", dest="from_clipboard", action="store_true",
                     help="Read raw text from the system clipboard.")
    parser.add_argument("--diff-only", action="store_true",
                        help="Emit only the substitution counter.")
    parser.add_argument("--check-only", action="store_true",
                        help="Audit-only: archive + emit substitution counter; exit 1 if Tier-1 hits found.")
    parser.add_argument("--to-clipboard", action="store_true",
                        help="Copy calibrated form to the system clipboard.")
    parser.add_argument("--no-archive", action="store_true",
                        help="Do not archive the raw input under .warden-safe-cache/prompts/.")
    parser.add_argument("--no-header", action="store_true",
                        help="Suppress the leading '# CALIBRATED INPUT' header line.")
    add_io_toggle_args(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)

    raw = _read_input(
        from_path=args.from_path,
        content=args.content,
        from_clipboard=getattr(args, "from_clipboard", False),
    )
    if not raw.strip():
        sys.stderr.write("safe_input: empty input\n")
        return 2

    if not args.no_archive:
        try:
            _archive_raw(raw)
        except OSError:
            pass

    io_on = transforms_enabled(args)
    if io_on:
        engine = build_engine()
        calibrated, t1_hits, t2_hits = engine.apply(raw)
        counts = {"tier1": t1_hits, "tier2": t2_hits}
    else:
        calibrated = raw
        counts = {"tier1": 0, "tier2": 0}
    total = sum(counts.values())

    if args.diff_only:
        sys.stdout.write(json.dumps({
            "substitutions": counts,
            "total": total,
            "io_channel": "on" if io_on else "off",
        }, indent=2) + "\n")
        return 0

    if args.check_only:
        sys.stdout.write(json.dumps({
            "substitutions": counts,
            "total": total,
            "io_channel": "on" if io_on else "off",
            "status": "FAIL" if counts.get("tier1", 0) else "OK",
        }, indent=2) + "\n")
        return 1 if counts.get("tier1", 0) else 0

    if args.to_clipboard:
        ok = _to_clipboard(calibrated)
        sys.stderr.write(
            f"safe_input: clipboard {'updated' if ok else 'unavailable'} - "
            f"substitutions={counts} total={total}\n"
        )
        return 0 if ok else 3

    header = "" if args.no_header or not io_on else (
        f"# CALIBRATED INPUT - substitutions: {counts} (total={total})\n"
    )
    sys.stdout.write(header + calibrated)
    if not calibrated.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
