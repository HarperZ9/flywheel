#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from proof_surface.packet import format_validation, validate_packet_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check proof-surface v0.1 packet conformance fixtures."
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=ROOT / "conformance" / "proof-surface" / "v0.1",
        help="Fixture root containing valid/ and invalid/ packet JSON files.",
    )
    return parser


def expected_cases(fixtures: Path) -> list[tuple[Path, bool]]:
    manifest_path = fixtures / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fixture_rows = manifest.get("fixtures")
        if not isinstance(fixture_rows, list):
            raise ValueError(f"{manifest_path} fixtures must be an array")
        return [_case_from_manifest(fixtures, row) for row in fixture_rows]

    valid = sorted((fixtures / "valid").glob("*.packet.json"))
    invalid = sorted((fixtures / "invalid").glob("*.packet.json"))
    return [(path, True) for path in valid] + [(path, False) for path in invalid]


def _case_from_manifest(fixtures: Path, row: object) -> tuple[Path, bool]:
    if not isinstance(row, dict):
        raise ValueError("manifest fixture row must be an object")
    path = row.get("path")
    expected = row.get("expected")
    if not isinstance(path, str) or not path:
        raise ValueError("manifest fixture path must be a non-empty string")
    if expected not in {"valid", "invalid"}:
        raise ValueError("manifest fixture expected must be valid or invalid")
    return fixtures / path, expected == "valid"


def check_case(path: Path, expected_valid: bool) -> tuple[bool, str]:
    issues = validate_packet_file(path)
    actual_valid = not issues
    status = "PASS" if actual_valid == expected_valid else "FAIL"
    expected = "valid" if expected_valid else "invalid"
    actual = "valid" if actual_valid else "invalid"
    lines = [f"{status} {path.as_posix()} expected={expected} actual={actual}"]
    if status == "FAIL":
        lines.append(format_validation(path, issues))
    return actual_valid == expected_valid, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = expected_cases(args.fixtures)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not cases:
        print(f"error: no conformance fixtures found under {args.fixtures}", file=sys.stderr)
        return 1

    ok = True
    for path, expected_valid in cases:
        case_ok, output = check_case(path, expected_valid)
        ok = ok and case_ok
        print(output)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
