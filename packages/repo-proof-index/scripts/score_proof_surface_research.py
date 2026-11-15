#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from proof_surface.packet import validate_packet

DEFAULT_CASES = ROOT / "research" / "proof-surface" / "v0.1" / "cases.json"
DIMENSIONS = (
    "schema_valid",
    "evidence_coverage",
    "actionability",
    "non_authority_language",
    "witness_or_provenance_presence",
)
AUTHORITY_TERMS = {
    "approved",
    "authorized",
    "certified",
    "compliant",
    "safe",
    "trusted",
}
SUPPORT_TERMS = {"emet", "provenance", "receipt", "witness"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score proof-surface research cases against v0.1 dimensions."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Case JSON file.")
    parser.add_argument("--json", action="store_true", help="Print JSON results.")
    return parser


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} root must be a JSON array")
    cases: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"{path}[{index}] must be an object")
        cases.append(item)
    return cases


def score_packet(packet: dict[str, Any]) -> dict[str, bool]:
    return {
        "schema_valid": not validate_packet(packet),
        "evidence_coverage": evidence_coverage(packet),
        "actionability": actionability(packet),
        "non_authority_language": non_authority_language(packet),
        "witness_or_provenance_presence": witness_or_provenance_presence(packet),
    }


def evidence_coverage(packet: dict[str, Any]) -> bool:
    claims = packet.get("claims")
    if not isinstance(claims, list) or not claims:
        return False
    for claim in claims:
        if not isinstance(claim, dict):
            return False
        evidence = claim.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            return False
    return True


def actionability(packet: dict[str, Any]) -> bool:
    status = packet.get("status")
    actions = packet.get("action_items")
    if status in {"blocked", "needs-polish"}:
        return isinstance(actions, list) and any(
            isinstance(action, str) and action.strip() for action in actions
        )
    return isinstance(actions, list)


def non_authority_language(packet: dict[str, Any]) -> bool:
    text = json.dumps(packet, sort_keys=True).lower()
    return not any(term in text for term in AUTHORITY_TERMS)


def witness_or_provenance_presence(packet: dict[str, Any]) -> bool:
    checks = packet.get("checks")
    if not isinstance(checks, list):
        return False
    for check in checks:
        if not isinstance(check, dict):
            continue
        if check.get("status") != "pass":
            continue
        text = " ".join(
            str(check.get(field, "")).lower() for field in ("tool", "summary")
        )
        if any(term in text for term in SUPPORT_TERMS):
            return True
    return False


def compare_case(case: dict[str, Any]) -> dict[str, Any]:
    packet = case.get("packet")
    expected = case.get("expected")
    if not isinstance(packet, dict):
        raise ValueError(f"{case.get('case_id', 'unknown')} packet must be an object")
    if not isinstance(expected, dict):
        raise ValueError(f"{case.get('case_id', 'unknown')} expected must be an object")
    observed = score_packet(packet)
    mismatches = [
        name for name in DIMENSIONS if observed.get(name) != expected.get(name)
    ]
    return {
        "case_id": case.get("case_id", "unknown"),
        "pass": not mismatches,
        "observed": observed,
        "expected": {name: expected.get(name) for name in DIMENSIONS},
        "mismatches": mismatches,
    }


def format_result(result: dict[str, Any]) -> str:
    status = "PASS" if result["pass"] else "FAIL"
    if result["pass"]:
        return f"{status} {result['case_id']}"
    mismatches = ", ".join(result["mismatches"])
    return f"{status} {result['case_id']} mismatches={mismatches}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        results = [compare_case(case) for case in load_cases(args.cases)]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("\n".join(format_result(result) for result in results))
    return 0 if all(result["pass"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
