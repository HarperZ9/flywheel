#!/usr/bin/env python3
"""Read a workspace file.

The original file is never modified. Use range, summary, hash, or cache
options when only a slice or metadata is needed.

Usage
-----
    python tools/safe_read.py <path>                # full read to stdout
    python tools/safe_read.py <path> --to-cache     # write .warden-safe-cache/<path>.safe
    python tools/safe_read.py <path> --lines 100:200
    python tools/safe_read.py <path> --summary      # structural summary only
    python tools/safe_read.py <path> --hash         # SHA-256 + line/byte metadata
    python tools/safe_read.py <path> --diff-only    # audit counters only

Non-destructive: never writes to the source file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from io_state import add_io_toggle_args, transforms_enabled
from _core import build_engine


_ROOT = Path(__file__).resolve().parent


def _read_source(path: Path, lines: tuple[int, int] | None) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if lines is None:
        return raw
    lo, hi = lines
    chunks = raw.splitlines(keepends=True)
    lo_idx = max(0, lo - 1)
    hi_idx = min(len(chunks), hi)
    return "".join(chunks[lo_idx:hi_idx])


def _summary(text: str, path: Path) -> dict:
    line_count = text.count("\n") + (0 if text.endswith("\n") else 1 if text else 0)
    byte_len = len(text.encode("utf-8"))
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    def_count = len(re.findall(r"^\s*def\s+\w+", text, re.MULTILINE))
    class_count = len(re.findall(r"^\s*class\s+\w+", text, re.MULTILINE))
    import_count = len(
        re.findall(r"^\s*(?:from\s+\S+\s+import|import\s+\S+)", text, re.MULTILINE)
    )
    return {
        "path": str(path),
        "line_count": line_count,
        "byte_length": byte_len,
        "sha256_prefix": sha,
        "structure": {
            "def_count": def_count,
            "class_count": class_count,
            "import_count": import_count,
        },
    }


def _parse_lines(spec: str) -> tuple[int, int]:
    if ":" not in spec:
        raise argparse.ArgumentTypeError(
            "--lines must be LO:HI, e.g. 100:200"
        )
    lo_s, hi_s = spec.split(":", 1)
    return (int(lo_s), int(hi_s))


def _emit(text: str, dest: Path | None) -> None:
    if dest is None:
        # Reconfigure stdout to UTF-8 so Unicode glyphs in payload text
        # don't crash on Windows cp1252 consoles.
        # `errors="replace"` keeps the write atomic on legacy terminals.
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
        try:
            sys.stdout.write(text)
        except UnicodeEncodeError:
            # Last-resort: write through the raw byte buffer.
            buf = getattr(sys.stdout, "buffer", None)
            if buf is not None:
                buf.write(text.encode("utf-8", errors="replace"))
            else:
                sys.stdout.write(text.encode("ascii", errors="replace").decode("ascii"))
        if not text.endswith("\n"):
            try:
                sys.stdout.write("\n")
            except UnicodeEncodeError:
                buf = getattr(sys.stdout, "buffer", None)
                if buf is not None:
                    buf.write(b"\n")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")


def _calibrated_view(text: str, counter: dict) -> str:
    """Add the standard calibrated-view header for full IO-on reads."""
    header = (
        "# CALIBRATED VIEW\n"
        f"# audit_counts: {json.dumps(dict(counter), sort_keys=True)}\n"
        "#\n"
    )
    return header + text


def _cache_path(src: Path) -> Path:
    base = Path.cwd() / ".warden-safe-cache"
    rel = src.resolve().as_posix().replace(":", "_").lstrip("/")
    return base / (rel + ".safe")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read a workspace file through the selected IO text mode."
    )
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--to-cache",
        action="store_true",
        help="Write to .warden-safe-cache/<path>.safe instead of stdout.",
    )
    parser.add_argument(
        "--lines",
        type=_parse_lines,
        default=None,
        help="Read only lines LO:HI (1-indexed, inclusive).",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Emit structural summary only (line/byte count, def/class/import count, hash).",
    )
    parser.add_argument(
        "--hash",
        action="store_true",
        help="Emit SHA-256 prefix + line/byte metadata only.",
    )
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Emit audit counters only.",
    )
    add_io_toggle_args(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)

    src = args.path
    if not src.is_file():
        print(f"error: not a file: {src}", file=sys.stderr)
        return 2

    raw = _read_source(src, args.lines)

    if args.hash:
        out = _summary(raw, src)
        sys.stdout.write(json.dumps({"hash_only": out}, indent=2) + "\n")
        return 0

    io_on = transforms_enabled(args)
    if io_on:
        engine = build_engine()
        payload_text, t1_hits, t2_hits = engine.apply(raw)
        counter = {"tier1": t1_hits, "tier2": t2_hits}
    else:
        payload_text, counter = raw, {"tier1": 0, "tier2": 0}

    if args.diff_only:
        sys.stdout.write(
            json.dumps(
                {
                    "path": str(src),
                    "audit_counts": dict(counter),
                    "total": sum(counter.values()),
                    "io_channel": "on" if io_on else "off",
                },
                indent=2,
            )
            + "\n"
        )
        return 0

    if args.summary:
        summary = _summary(payload_text, src)
        sys.stdout.write(json.dumps(summary, indent=2) + "\n")
        return 0

    if not io_on:
        dest = _cache_path(src) if args.to_cache else None
        _emit(raw, dest)
        if dest is not None:
            sys.stderr.write(f"wrote: {dest}\n")
        return 0

    payload = _calibrated_view(payload_text, counter)
    dest = _cache_path(src) if args.to_cache else None
    _emit(payload, dest)
    if dest is not None:
        sys.stderr.write(f"wrote: {dest}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
