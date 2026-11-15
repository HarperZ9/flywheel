#!/usr/bin/env python3
"""Fail closed on high-signal leaks in tracked public repository surfaces.

Discovery comes from ``git ls-files`` so untracked build output and local state
cannot change the result. Every tracked file is scanned as bounded UTF-8 unless
its suffix explicitly classifies it as a known binary. Build roots, caches, and
Git metadata stay out of scope. The scanner reports locations and rule
identifiers, but never echoes a matched secret value.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent

_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "artifacts",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "tmp",
        "venv",
    }
)
_KNOWN_BINARY_SUFFIXES = frozenset(
    {
        ".avi",
        ".bmp",
        ".gif",
        ".gz",
        ".ico",
        ".jpeg",
        ".jpg",
        ".mov",
        ".mp3",
        ".mp4",
        ".otf",
        ".pdf",
        ".png",
        ".pyc",
        ".tar",
        ".ttf",
        ".wav",
        ".webm",
        ".whl",
        ".woff",
        ".woff2",
        ".zip",
    }
)
MAX_SCAN_BYTES = 2_000_000
_ROOT_PUBLIC_FILES = frozenset(
    {
        "AGENTS.md",
        "AUTHORS.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "README.md",
        "USAGE.md",
        "pyproject.toml",
    }
)
_PROSE_ROOTS = frozenset(
    {".github", "conformance", "docs", "examples", "project-docs", "schemas"}
)

_WINDOWS_PATH_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'<>|]+")
_POSIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])/(?:Users|home|tmp|var/tmp|mnt/[A-Za-z])/[A-Za-z0-9._~+/@%=-]+"
    r"(?:/[A-Za-z0-9._~+/@%=-]+)*"
)
_TOKEN_RE = re.compile(
    r"(?:"
    r"sk-[A-Za-z0-9_-]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|hf_[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{35}"
    r"|xox[baprs]-[A-Za-z0-9-]{20,}"
    r")"
)
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)(?:api[_-]?(?:key|token)|access[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|password|passwd|secret|token)\s*(?:=|:)\s*"
    r"[\"']?[A-Za-z0-9._~+/=-]{16,}"
)
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"
)
_PLACEHOLDER_RE = re.compile(
    r"\b(?:TODO|TBD|FIXME|CHANGEME|REPLACE_ME)\b"
    r"|\b(?:YOUR|INSERT)_[A-Z0-9_]+(?:_HERE)?\b"
    r"|\{\{\s*[A-Z][A-Z0-9_. -]*\s*\}\}"
)
_PRIVATE_REFERENCE_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:\.scratch|scratch|protected|secrets|"
    r"dispatch-ready|job-applications-private|deliverables)[\\/]"
    r"|(?<![A-Za-z0-9_.-])state[\\/][^\s\"']*warden-ops[^\s\"']*"
)
_EM_DASH = "\u2014"
_MOJIBAKE_MARKERS = (
    "\u00e2\u20ac\u201d",
    "\u00e2\u20ac\u201c",
    "\u00e2\u20ac\u02dc",
    "\u00e2\u20ac\u2122",
    "\u00c2",
    "\u00c3",
    "\u00ef\u00bf\u00bd",
    "\ufffd",
)
_MOJIBAKE_RE = re.compile("|".join(re.escape(item) for item in _MOJIBAKE_MARKERS))

_LEGACY_PATH = (
    "/".join(("C:", "dev", "public", "proof-surface", "conformance")) + "/"
)
_LEGACY_MACHINE_PATH_ALLOWANCES: dict[str, dict[str, int]] = {
    "conformance/authorization-receipt/v0.1/valid/minimal.receipt.json": {
        _LEGACY_PATH: 1
    },
    "conformance/pre-execution-gate/v0.1/valid/minimal.request.json": {
        _LEGACY_PATH: 2
    },
    "conformance/pre-execution-gate/v0.1/invalid/bad-digest-format.request.json": {
        _LEGACY_PATH: 1
    },
    "conformance/pre-execution-gate/v0.1/invalid/forbidden-field-nested-in-authorization.request.json": {
        _LEGACY_PATH: 1
    },
    "conformance/pre-execution-gate/v0.1/invalid/forbidden-prefire-root.request.json": {
        _LEGACY_PATH: 1
    },
    "conformance/pre-execution-gate/v0.1/invalid/invalid-state-verdict.request.json": {
        _LEGACY_PATH: 1
    },
    "conformance/pre-execution-gate/v0.1/invalid/negative-estimated-cost.request.json": {
        _LEGACY_PATH: 1
    },
    "conformance/pre-execution-gate/v0.1/invalid/unknown-root-field.request.json": {
        _LEGACY_PATH: 1
    },
}
_LEGACY_EM_DASH_ALLOWANCES: dict[str, int] = {
    "src/proof_surface/agent_action/README.md": 7,
    "src/proof_surface/ai4science/README.md": 5,
    "src/proof_surface/conservation/README.md": 2,
    "src/proof_surface/eval_attempt/README.md": 6,
    "src/proof_surface/model_eval/README.md": 2,
    "src/proof_surface/optimization_workflow/README.md": 3,
    "src/proof_surface/research_claim/README.md": 4,
    "src/proof_surface/rollout_receipt/README.md": 7,
    "src/proof_surface/visual_measurement/README.md": 1,
}


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    column: int
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}:{self.column} [{self.code}] {self.message}"


class GateError(RuntimeError):
    """A deterministic discovery or read failure."""


def _is_excluded(relative: Path) -> bool:
    lowered = tuple(part.lower() for part in relative.parts)
    return any(
        part in _EXCLUDED_PARTS or part.endswith(".egg-info") for part in lowered
    )


def _is_known_binary(relative: Path) -> bool:
    return relative.suffix.lower() in _KNOWN_BINARY_SUFFIXES


def is_public_prose(relative: Path) -> bool:
    if relative.as_posix() in _ROOT_PUBLIC_FILES:
        return True
    if relative.parts and relative.parts[0] in _PROSE_ROOTS:
        if relative.parts[:2] == ("project-docs", "records"):
            return False
        return True
    return relative.suffix.lower() in {".md", ".rst", ".html"}


def discover_public_surfaces(repo: Path) -> list[Path]:
    repo = repo.resolve()
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:  # pragma: no cover - platform launch failure
        raise GateError(f"git discovery failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise GateError(f"git discovery failed ({result.returncode}): {detail}")

    paths: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            relative = Path(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise GateError("git returned a non-UTF-8 tracked path") from exc
        if _is_excluded(relative):
            continue
        paths.append(repo / relative)
    return sorted(paths, key=lambda path: path.relative_to(repo).as_posix())


def _finding(
    path: Path, line: int, match: re.Match[str], code: str, message: str
) -> Finding:
    return Finding(path.as_posix(), line, match.start() + 1, code, message)


def scan_text(path: Path, text: str, *, public_prose: bool) -> list[Finding]:
    relative = path.as_posix()
    allowances = _LEGACY_MACHINE_PATH_ALLOWANCES.get(relative, {})
    allowance_use: dict[str, int] = {}
    em_dash_allowance = _LEGACY_EM_DASH_ALLOWANCES.get(relative, 0)
    em_dash_use = 0
    findings: list[Finding] = []

    for line_number, line in enumerate(text.splitlines(), 1):
        secret_spans: list[tuple[int, int]] = []
        for match in _TOKEN_RE.finditer(line):
            findings.append(
                _finding(
                    path,
                    line_number,
                    match,
                    "secret-material",
                    "credential-shaped token material",
                )
            )
            secret_spans.append(match.span())
        for match in _CREDENTIAL_ASSIGNMENT_RE.finditer(line):
            if any(
                match.start() < end and match.end() > start
                for start, end in secret_spans
            ):
                continue
            findings.append(
                _finding(
                    path,
                    line_number,
                    match,
                    "secret-material",
                    "credential-shaped assignment",
                )
            )
            secret_spans.append(match.span())
        for match in _PRIVATE_KEY_RE.finditer(line):
            findings.append(
                _finding(
                    path,
                    line_number,
                    match,
                    "private-key-material",
                    "private key material",
                )
            )

        if not public_prose:
            continue
        for pattern in (_WINDOWS_PATH_RE, _POSIX_PATH_RE):
            for match in pattern.finditer(line):
                matched = match.group(0)
                used = allowance_use.get(matched, 0)
                if used < allowances.get(matched, 0):
                    allowance_use[matched] = used + 1
                    continue
                findings.append(
                    _finding(
                        path,
                        line_number,
                        match,
                        "machine-path",
                        "machine-absolute path on a public surface",
                    )
                )
        for match in re.finditer(_EM_DASH, line):
            if em_dash_use < em_dash_allowance:
                em_dash_use += 1
                continue
            findings.append(
                _finding(
                    path,
                    line_number,
                    match,
                    "em-dash",
                    "em dash in public prose",
                )
            )
        for match in _MOJIBAKE_RE.finditer(line):
            findings.append(
                _finding(path, line_number, match, "mojibake", "corrupted text encoding")
            )
        for match in _PLACEHOLDER_RE.finditer(line):
            findings.append(
                _finding(
                    path,
                    line_number,
                    match,
                    "unresolved-placeholder",
                    "unresolved placeholder marker",
                )
            )
        for match in _PRIVATE_REFERENCE_RE.finditer(line):
            findings.append(
                _finding(
                    path,
                    line_number,
                    match,
                    "private-reference",
                    "unsupported private-tree reference",
                )
            )
    return sorted(findings)


def scan_repository(repo: Path) -> tuple[list[Path], list[Finding]]:
    repo = repo.resolve()
    surfaces = discover_public_surfaces(repo)
    findings: list[Finding] = []
    for path in surfaces:
        relative = path.relative_to(repo)
        if _is_known_binary(relative):
            continue
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_SCAN_BYTES + 1)
        except OSError as exc:
            findings.append(
                Finding(
                    relative.as_posix(),
                    1,
                    1,
                    "unreadable-unclassified",
                    f"tracked unclassified file could not be read: {type(exc).__name__}",
                )
            )
            continue
        if len(raw) > MAX_SCAN_BYTES:
            findings.append(
                Finding(
                    relative.as_posix(),
                    1,
                    1,
                    "oversized-unclassified",
                    "tracked unclassified file exceeds the scan byte limit",
                )
            )
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            findings.append(
                Finding(
                    relative.as_posix(),
                    1,
                    1,
                    "unreadable-unclassified",
                    f"tracked unclassified file is not UTF-8: {type(exc).__name__}",
                )
            )
            continue
        findings.extend(
            scan_text(relative, text, public_prose=is_public_prose(relative))
        )
    return surfaces, sorted(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(REPO))
    args = parser.parse_args(argv)
    repo = Path(args.root)

    try:
        surfaces, findings = scan_repository(repo)
    except GateError as exc:
        print(f"public surface gate: UNVERIFIABLE: {exc}")
        return 2

    print(f"public surface gate: scanned {len(surfaces)} tracked file(s)")
    for finding in findings:
        print(finding.render())
    if findings:
        print(f"public surface gate: {len(findings)} finding(s)")
        return 1
    print("public surface gate: no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
