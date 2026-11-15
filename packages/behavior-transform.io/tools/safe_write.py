#!/usr/bin/env python3
"""Write content to a workspace file.

Use stdin, ``--from``, or ``--content`` as the input source. Writes are
atomic and parent directories are created when needed.

Usage
-----
    # Pipe content via stdin:
    echo "<payload>" | python tools/safe_write.py dest.md

    # Copy from another file:
    python tools/safe_write.py dest.md --from src.md

    # Inline payload (small content):
    python tools/safe_write.py dest.md --content "..."

    # Preview only:
    python tools/safe_write.py dest.md --from src.md --dry-run

    # Audit counter only:
    python tools/safe_write.py dest.md --from src.md --diff-only

    # Append rather than overwrite:
    python tools/safe_write.py log.md --append --content "new entry"

    # Audit-only mode (no write; exit 1 if blocking audit hits are found):
    python tools/safe_write.py dest.md --from src.md --check-only

Behavior
--------
* Default mode WRITES to ``dest_path``.
* Source-side bytes are archived to
  ``.warden-safe-cache/<dest>.pre`` for the auditor unless
  ``--no-archive`` is set.
* Non-destructive on errors: writes go to a tempfile + atomic rename.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from io_state import add_io_toggle_args, transforms_enabled
from text_rules import is_rule_source_path
from _core import build_engine


_ROOT = Path(__file__).resolve().parent


def _read_input(
    *,
    from_path: Path | None,
    content: str | None,
) -> str:
    """Gather the payload from --from, --content, or stdin."""
    if from_path is not None:
        return from_path.read_text(encoding="utf-8", errors="replace")
    if content is not None:
        return content
    # Stdin: read as bytes then decode so Windows line-ending translation
    # doesn't corrupt the payload.
    buf = getattr(sys.stdin, "buffer", None)
    if buf is not None:
        return buf.read().decode("utf-8", errors="replace")
    return sys.stdin.read()


def _atomic_write(dest: Path, text: str, *, append: bool) -> None:
    """Write atomically via tempfile + rename. Creates parent dirs."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if append and dest.exists():
        existing = dest.read_text(encoding="utf-8", errors="replace")
        text = existing + text
    # Tempfile in the same directory so rename is atomic on every FS.
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=".safe_write.",
        suffix=".tmp",
        dir=str(dest.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp_path, dest)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _archive_pre_write(dest: Path, original: str) -> Path:
    """Stash the input payload under .warden-safe-cache for auditing.

    The cache layout mirrors safe_read's: full path with ':' -> '_' so it
    is portable across Windows/Linux. Suffix ``.pre`` distinguishes
    write-side archives from safe_read's ``.safe`` artifacts.
    """
    cache_root = Path.cwd() / ".warden-safe-cache"
    rel = dest.resolve().as_posix().replace(":", "_").lstrip("/")
    archive = cache_root / (rel + ".pre")
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(original, encoding="utf-8")
    return archive


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Write content to a workspace file."
        )
    )
    parser.add_argument(
        "dest",
        type=Path,
        help="Destination path. Parent dirs are created if missing.",
    )
    src_group = parser.add_mutually_exclusive_group()
    src_group.add_argument(
        "--from",
        dest="from_path",
        type=Path,
        default=None,
        help="Read payload from this file instead of stdin.",
    )
    src_group.add_argument(
        "--content",
        type=str,
        default=None,
        help="Inline payload (small strings). Mutually exclusive with --from.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to destination instead of overwriting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print content to stdout; do not write the destination.",
    )
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Emit audit counters as JSON (no write, no payload).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help=(
            "Audit-only: do not write. Exit 1 if any blocking audit hits "
            "would have been recorded."
        ),
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not archive the input payload to .warden-safe-cache/.",
    )
    add_io_toggle_args(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.append and args.dry_run:
        parser.error("--append and --dry-run are mutually exclusive")
    if args.check_only and (args.append or args.dry_run):
        parser.error("--check-only conflicts with --append/--dry-run")

    original = _read_input(from_path=args.from_path, content=args.content)

    io_on = transforms_enabled(args)
    # Rule-source files keep their own terminology intact.
    if not io_on or is_rule_source_path(args.dest):
        final_text, counter = original, {"tier1": 0, "tier2": 0}
    else:
        engine = build_engine()
        final_text, t1_hits, t2_hits = engine.apply(original)
        counter = {"tier1": t1_hits, "tier2": t2_hits}
    counts = {tier: int(n) for tier, n in counter.items()}
    total = sum(counts.values())

    if args.diff_only:
        payload = {
            "dest": str(args.dest),
            "audit_counts": counts,
            "total": total,
            "io_channel": "on" if io_on else "off",
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0

    if args.check_only:
        if counts.get("tier1", 0):
            sys.stderr.write(
                json.dumps(
                    {
                        "dest": str(args.dest),
                        "status": "FAIL",
                        "audit_counts": counts,
                        "io_channel": "on" if io_on else "off",
                        "message": (
                            "Blocking audit hit would have been recorded; "
                            "payload is not write-clean."
                        ),
                    },
                    indent=2,
                )
                + "\n"
            )
            return 1
        sys.stdout.write(
            json.dumps(
                {
                    "dest": str(args.dest),
                    "status": "OK",
                    "audit_counts": counts,
                    "io_channel": "on" if io_on else "off",
                },
                indent=2,
            )
            + "\n"
        )
        return 0

    if args.dry_run:
        sys.stdout.write(
            f"# safe_write DRY-RUN — dest: {args.dest}\n"
            f"# audit_counts: {counts} (total={total})\n"
            f"# io_channel: {'on' if io_on else 'off'}\n"
        )
        sys.stdout.write(final_text)
        if not final_text.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    archived_path: Path | None = None
    if total > 0 and not args.no_archive:
        archived_path = _archive_pre_write(args.dest, original)

    _atomic_write(args.dest, final_text, append=args.append)

    report = {
        "dest": str(args.dest),
        "wrote_bytes": len(final_text.encode("utf-8")),
        "audit_counts": counts,
        "total": total,
        "io_channel": "on" if io_on else "off",
        "append": bool(args.append),
        "archived_pre": str(archived_path) if archived_path else None,
    }
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
