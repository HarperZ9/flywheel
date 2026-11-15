from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from proof_surface.packet import validate_packet

from .sweeper import (
    SEVERITY_ORDER,
    Finding,
    format_summary,
    format_text,
    proof_surface_packet,
    scan,
    summarize_findings,
)
from .workspace import build_delivery_matrix, format_delivery_matrix


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check a repository for public release hygiene issues."
    )
    parser.add_argument("root", nargs="?", default=".", help="Repository root to scan.")
    parser.add_argument("--json", action="store_true", help="Print JSON findings.")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a release-readiness summary instead of individual findings.",
    )
    parser.add_argument(
        "--proof-packet",
        action="store_true",
        help="Print a proof-surface interop packet as JSON.",
    )
    parser.add_argument(
        "--workspace",
        action="store_true",
        help="Discover GitHub-facing repos under ROOT and print a delivery matrix.",
    )
    parser.add_argument(
        "--fail-on",
        choices=["none", "warning", "error"],
        default="error",
        help="Minimum severity that returns a failing exit code.",
    )
    return parser


def _should_fail(findings: list[Finding], fail_on: str) -> bool:
    if fail_on == "none":
        return False
    threshold = SEVERITY_ORDER[fail_on]
    return any(SEVERITY_ORDER[item.severity] >= threshold for item in findings)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    if args.workspace:
        matrix = build_delivery_matrix([root])
        if args.json:
            print(json.dumps(matrix, indent=2))
        else:
            print(format_delivery_matrix(matrix))
        if args.fail_on == "none":
            return 0
        return 1 if matrix["workspace_status"] != "MATCH" else 0

    findings = scan(root)
    if args.proof_packet:
        packet = proof_surface_packet(root, findings)
        issues = validate_packet(packet)
        if issues:
            print("error: generated proof-surface packet failed validation", file=sys.stderr)
            for issue in issues:
                print(f"  {issue.path}: {issue.message}", file=sys.stderr)
            return 1
        print(json.dumps(packet, indent=2))
    elif args.summary:
        summary = summarize_findings(findings)
        if args.json:
            print(json.dumps(asdict(summary), indent=2))
        else:
            print(format_summary(summary))
    elif args.json:
        print(json.dumps([asdict(item) for item in findings], indent=2))
    else:
        print(format_text(findings))
    return 1 if _should_fail(findings, args.fail_on) else 0
