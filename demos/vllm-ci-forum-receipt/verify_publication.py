from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


EXCLUDED_PARTS = {"__pycache__", ".ruff_cache", ".git"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_publication(root: Path) -> dict[str, Any]:
    root = Path(root)
    inventory_path = root / "PUBLICATION.txt"
    sums_path = root / "SHA256SUMS.txt"
    inventory = {
        line.strip()
        for line in inventory_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and not EXCLUDED_PARTS.intersection(path.parts)
        and path.suffix.lower() != ".pyc"
    }
    if actual != inventory:
        missing = sorted(inventory - actual)
        undeclared = sorted(actual - inventory)
        raise ValueError(f"publication inventory mismatch: missing={missing}, undeclared={undeclared}")

    expected: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or len(digest) != 64 or not relative:
            raise ValueError(f"malformed SHA256SUMS line: {line!r}")
        if relative in expected:
            raise ValueError(f"duplicate SHA256SUMS path: {relative}")
        expected[relative] = digest
    required = inventory - {"SHA256SUMS.txt"}
    if set(expected) != required:
        raise ValueError("SHA256SUMS paths do not match the publication inventory")
    for relative, digest in expected.items():
        if _sha256(root / relative) != digest:
            raise ValueError(f"SHA-256 mismatch: {relative}")
    return {
        "schema": "vllm-ci-publication-verification/1",
        "status": "verified",
        "inventory_files": len(inventory),
        "hashed_files": len(expected),
        "sha256sums_sha256": _sha256(sums_path),
    }


def main() -> int:
    print(json.dumps(verify_publication(Path(__file__).resolve().parent), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
