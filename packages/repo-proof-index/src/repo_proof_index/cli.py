from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from proof_surface.packet import Issue, format_validation, validate_packet

from .indexer import format_summary, format_table, load_rows, summarize_rows
from .strict_json import load_json_object


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index proof contract JSON files into table or JSON output."
    )
    parser.add_argument("paths", nargs="*", type=Path, help="Contract JSON files.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Workspace root used when paths are omitted.",
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=None,
        help="Directory to scan when paths are omitted.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON rows.")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a release-readiness summary instead of individual rows.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate proof-surface packet JSON files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.validate:
        if not args.paths:
            print("error: --validate requires at least one packet path")
            return 1
        validation = [(path, _validate_packet_file(path)) for path in args.paths]
        results = [
            {"path": str(path), "valid": not issues, "errors": [asdict(issue) for issue in issues]}
            for path, issues in validation
        ]
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print("\n".join(format_validation(path, issues) for path, issues in validation))
        return 1 if any(not result["valid"] for result in results) else 0

    try:
        rows = load_rows(args.paths, root=args.root, contracts_dir=args.contracts_dir)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1
    if args.summary:
        summary = summarize_rows(rows)
        if args.json:
            print(json.dumps(asdict(summary), indent=2))
        else:
            print(format_summary(summary))
    elif args.json:
        print(json.dumps([asdict(row) for row in rows], indent=2))
    else:
        print(format_table(rows))
    return 0


def _validate_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_packet(load_json_object(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]
