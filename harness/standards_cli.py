"""Local JSON CLI for standards profile validation and assessment."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .standards_assessment import assess_profile
from .standards_registry import validate_profile

_USAGE = (
    "usage:\n"
    "  python -m harness.standards_cli validate PROFILE.json\n"
    "  python -m harness.standards_cli assess PROFILE.json CONTEXT.json "
    "--as-of YYYY-MM-DD\n")


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key: {key}")
        out[key] = value
    return out


def _load_json(path: str) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(
        text,
        object_pairs_hook=_no_duplicate_pairs,
        parse_constant=_reject_constant,
    )


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, indent=1, sort_keys=True))


def _usage(message: str | None = None) -> int:
    if message:
        print(message, file=sys.stderr)
    print(_USAGE, file=sys.stderr)
    return 2


def _exit_for_assessment(result: dict[str, Any]) -> int:
    if result["verdict"] == "INVALID":
        return 1
    if result["verdict"] == "REVIEWABLE":
        return 0
    return 3


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return _usage()
    command = args[0]
    try:
        if command == "validate":
            if len(args) != 2:
                return _usage()
            result = validate_profile(_load_json(args[1]))
            _emit(result)
            return 0 if result["verdict"] == "VALID" else 1
        if command == "assess":
            if len(args) != 5 or args[3] != "--as-of":
                return _usage()
            result = assess_profile(
                _load_json(args[1]), _load_json(args[2]), as_of=args[4])
            _emit(result)
            return _exit_for_assessment(result)
        return _usage(f"unknown command: {command}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
