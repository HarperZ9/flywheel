from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", "build", "dist", "htmlcov", "tests", ".ruff_cache"}
TEXT_SUFFIXES = {".cfg", ".in", ".ini", ".json", ".md", ".py", ".toml", ".txt", ".yml", ".yaml"}
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]
PRIVATE_FRAGMENTS = [
    "\\".join(["C:", "Users", "Zain", "AGENTS"]),
    "warden" + "-ops",
    "." + "authority-pill",
    "contracts" + "-executed",
]


def main(argv: list[str] | None = None) -> int:
    roots = [Path(arg).resolve() for arg in (argv if argv is not None else sys.argv[1:])]
    if not roots:
        roots = [ROOT]
    findings: list[str] = []
    for root in roots:
        findings.extend(_scan_root(root))
    for finding in findings:
        print(finding)
    return 1 if findings else 0


def _scan_root(root: Path) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        if path.name.startswith(".env") and path.name != ".env.example":
            findings.append(f"{rel}: environment file must not be public")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore", ".dockerignore"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for fragment in PRIVATE_FRAGMENTS:
            if fragment in text:
                findings.append(f"{rel}: private path or ops fragment found")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{rel}: secret-shaped literal found")
                break
    return findings


if __name__ == "__main__":
    raise SystemExit(main())
