"""Fail closed on stale Relay release metadata.

The guard is intentionally local-only. It does not query GitHub or PyPI; it checks
that the source tree about to be packaged names one version consistently and keeps
Relay's GitHub-only distribution boundary visible.
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


_VERSION_RE = re.compile(r"__version__\s*=\s*['\"]([^'\"]+)['\"]")
_CHANGELOG_RE = re.compile(r"^##\s+([^\n]+)", re.MULTILINE)


class GuardError(Exception):
    pass


def _read(root: Path, relative: str) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GuardError(f"{relative}: cannot read: {exc}") from exc


def _project_version(root: Path) -> str:
    try:
        data = tomllib.loads(_read(root, "pyproject.toml"))
    except tomllib.TOMLDecodeError as exc:
        raise GuardError(f"pyproject.toml: invalid TOML: {exc}") from exc
    try:
        return str(data["project"]["version"])
    except KeyError as exc:
        raise GuardError("pyproject.toml: missing project.version") from exc


def _module_version(root: Path, relative: str) -> str:
    match = _VERSION_RE.search(_read(root, relative))
    if not match:
        raise GuardError(f"{relative}: missing __version__")
    return match.group(1)


def _top_changelog_section(changelog: str) -> tuple[str, str]:
    matches = list(_CHANGELOG_RE.finditer(changelog))
    if not matches:
        raise GuardError("CHANGELOG.md: missing release heading")
    first = matches[0]
    end = matches[1].start() if len(matches) > 1 else len(changelog)
    return first.group(1).strip(), changelog[first.end():end]


def _collapse(text: str) -> str:
    """Whitespace-normalized text, so a needle can span a wrapped line.

    Prose in these documents is hard-wrapped, so a phrase the guard cares about
    is regularly split across two lines. Matching the raw text makes the guard
    fail on a reflow that changed no words, which trains people to weaken the
    needle rather than fix the document. Collapsing runs of whitespace to single
    spaces keeps the guard about wording and not about line width.
    """
    return " ".join(text.split())


def _require_contains(text: str, needle: str, relative: str) -> None:
    if _collapse(needle) not in _collapse(text):
        raise GuardError(f"{relative}: expected {needle!r}")


def check(root: Path, expected_version: str | None = None) -> list[str]:
    errors: list[str] = []

    try:
        project_version = _project_version(root)
        if expected_version and project_version != expected_version:
            errors.append(
                f"pyproject.toml: project.version is {project_version!r}, expected {expected_version!r}"
            )
    except GuardError as exc:
        errors.append(str(exc))
        project_version = expected_version or ""

    version = expected_version or project_version
    if not version:
        return errors

    for relative in ("src/relay/__init__.py", "src/relay/local_mcp.py"):
        try:
            module_version = _module_version(root, relative)
            if module_version != version:
                errors.append(f"{relative}: __version__ is {module_version!r}, expected {version!r}")
        except GuardError as exc:
            errors.append(str(exc))

    try:
        heading, top_section = _top_changelog_section(_read(root, "CHANGELOG.md"))
        if not heading.startswith(f"{version},"):
            errors.append(f"CHANGELOG.md: top release heading {heading!r} does not start with {version!r}")
        flat_section = _collapse(top_section)
        for needle in (
            "Source version metadata is not release",
            "availability proof",
            "accepted Git tag",
            "GitHub Release assets",
            "matching hash readback",
            "Do not publish",
            "bare PyPI name `relay-agent`",
        ):
            if _collapse(needle) not in flat_section:
                errors.append(f"CHANGELOG.md: top {version} section expected release availability boundary {needle!r}")
        for forbidden in (
            "Prospective GitHub-only patch release",
            "source metadata only",
            "latest already published",
            "remains 0.2.4",
        ):
            if _collapse(forbidden) in flat_section:
                errors.append(f"CHANGELOG.md: top {version} section has stale availability wording {forbidden!r}")
    except GuardError as exc:
        errors.append(str(exc))

    try:
        readme = _read(root, "README.md")
        for needle in (
            "docs/GITHUB-ONLY-INSTALL.md",
            # Relay publishes as flywheel-relay. relay-agent on PyPI belongs to
            # an unrelated project, so the README has to keep saying so even now
            # that we own a name: the hazard did not go away, it just stopped
            # being the only option.
            "python -m pip install flywheel-relay",
            "`relay-agent` belongs to an unrelated project",
            "a missing checksum entry or a hash",
        ):
            _require_contains(readme, needle, "README.md")
    except GuardError as exc:
        errors.append(str(exc))

    try:
        install = _read(root, "docs/GITHUB-ONLY-INSTALL.md")
        for needle in (
            "Do not run `pip install relay-agent`",
            f"tag: v{version}",
            f"wheel: flywheel_relay-{version}-py3-none-any.whl",
            f"sdist: flywheel_relay-{version}.tar.gz",
            f"https://github.com/HarperZ9/relay/releases/download/v{version}/<asset-name>",
            "Do not continue to `pip install` if the wheel has no checksum line or the computed hash differs.",
            "& {",
            "$ErrorActionPreference = \"Stop\"",
            "expected exactly one SHA256SUMS entry",
            "$matches.Count -ne 1",
            "sha256 mismatch",
            "python -m pip install --no-index",
            "\\$wheel",
        ):
            _require_contains(install, needle, "docs/GITHUB-ONLY-INSTALL.md")
    except GuardError as exc:
        errors.append(str(exc))

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="check Relay release metadata alignment")
    parser.add_argument("--root", default=".", help="repository root to check")
    parser.add_argument("--expected-version", default="", help="expected release version")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    errors = check(root, args.expected_version or None)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"release metadata aligned for relay {args.expected_version or _project_version(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
