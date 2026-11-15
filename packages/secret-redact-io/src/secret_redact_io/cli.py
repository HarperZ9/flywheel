from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .exec_io import run_guarded
from .fetch_io import fetch_guarded
from .file_io import read_text_guarded, write_text_guarded


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "read":
        result = read_text_guarded(args.path)
        return _emit({"text": result.text, "receipt": result.receipt.to_dict()}, args.json)
    if args.command == "write":
        content = args.content if args.content is not None else Path(args.from_file).read_text()
        result = write_text_guarded(args.path, content, dry_run=args.dry_run)
        return _emit({"text": result.text, "receipt": result.receipt.to_dict()}, args.json)
    if args.command == "fetch":
        result = fetch_guarded(args.url, timeout=args.timeout)
        return _emit({"text": result.text, "status_code": result.status_code, "receipt": result.receipt.to_dict()}, args.json)
    if args.command == "exec":
        command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        result = run_guarded(command, timeout=args.timeout)
        payload = {
            "receipt": result.receipt.to_dict(),
            "returncode": result.returncode,
            "stderr": result.stderr,
            "stdout": result.stdout,
        }
        return _emit(payload, args.json, exit_code=result.returncode)
    parser.error("unknown command")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="secret-redact-io", description="Guard file, fetch, and exec IO.")
    sub = parser.add_subparsers(dest="command", required=True)
    read = sub.add_parser("read")
    read.add_argument("path")
    read.add_argument("--json", action="store_true")
    write = sub.add_parser("write")
    write.add_argument("path")
    write.add_argument("--content")
    write.add_argument("--from-file")
    write.add_argument("--dry-run", action="store_true")
    write.add_argument("--json", action="store_true")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("url")
    fetch.add_argument("--timeout", type=float, default=10)
    fetch.add_argument("--json", action="store_true")
    exec_parser = sub.add_parser("exec")
    exec_parser.add_argument("--timeout", type=float, default=30)
    exec_parser.add_argument("--json", action="store_true")
    exec_parser.add_argument("argv", nargs=argparse.REMAINDER)
    return parser


def _emit(payload: dict[str, Any], as_json: bool, *, exit_code: int = 0) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            if key != "receipt":
                print(f"{key}: {value}")
    return exit_code
