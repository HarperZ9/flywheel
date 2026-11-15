from __future__ import annotations

import re
from pathlib import Path

from .file_io import read_text_file
from .models import Finding

PUBLIC_DELIVERY_HEADINGS = (
    "why it matters",
    "what it does",
    "overview",
    "use cases",
    "current status",
    "who it is for",
    "who it's for",
)
DEVELOPER_ENTRY_HEADINGS = (
    "install",
    "installation",
    "quickstart",
    "try it",
    "usage",
)
DEVELOPER_WORK_HEADINGS = (
    "api",
    "contributing",
    "development",
    "for developers",
    "testing",
)
SUBSTANTIVE_IMAGE_EXTENSIONS = (".gif", ".jpg", ".jpeg", ".png", ".svg", ".webp")
BADGE_ALT_MARKERS = ("badge", "ci", "license", "version")
BADGE_TARGET_MARKERS = ("badge", "badgen.net", "shields.io")
MARKDOWN_IMAGE_PATTERN = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
)
HTML_IMAGE_PATTERN = re.compile(
    r"<img\b[^>]*\bsrc=[\"'](?P<target>[^\"']+)[\"'][^>]*>",
    re.IGNORECASE,
)


def readme_delivery_findings(root: Path) -> list[Finding]:
    text = read_text_file(root / "README.md")
    if text is None:
        return []

    findings: list[Finding] = []
    if not _has_any_heading(text, PUBLIC_DELIVERY_HEADINGS):
        findings.append(
            Finding(
                path="README.md",
                line=0,
                rule="readme-public-delivery",
                severity="warning",
                message="README should explain the public value, status, or use case",
            )
        )

    has_entry = _has_any_heading(text, DEVELOPER_ENTRY_HEADINGS)
    has_workflow = _has_any_heading(text, DEVELOPER_WORK_HEADINGS)
    has_command = "```" in text and _looks_like_command_block(text)
    if not (has_entry and has_workflow and has_command):
        findings.append(
            Finding(
                path="README.md",
                line=0,
                rule="readme-developer-delivery",
                severity="warning",
                message=(
                    "README should include developer entry points, workflow "
                    "notes, and runnable commands"
                ),
            )
        )

    if not _has_substantive_readme_image(root, text):
        findings.append(
            Finding(
                path="README.md",
                line=0,
                rule="readme-visual-asset",
                severity="warning",
                message="README should include a substantive non-badge visual asset",
            )
        )
    return findings


def _has_any_heading(text: str, terms: tuple[str, ...]) -> bool:
    headings = [
        match.group("heading").strip().lower()
        for match in re.finditer(r"^#{1,4}\s+(?P<heading>.+?)\s*$", text, re.MULTILINE)
    ]
    return any(any(term in heading for term in terms) for heading in headings)


def _looks_like_command_block(text: str) -> bool:
    command_block_pattern = (
        r"```(?:bash|console|powershell|ps1|shell|sh|text)?\s*\n(.*?)```"
    )
    command_word_pattern = (
        r"\b(python|pip|pytest|npm|pnpm|node|cargo|cmake|make|git|"
        r"public-surface-sweeper)\b"
    )
    for block in re.findall(command_block_pattern, text, re.DOTALL | re.IGNORECASE):
        if re.search(command_word_pattern, block):
            return True
    return False


def _has_substantive_readme_image(root: Path, text: str) -> bool:
    for match in MARKDOWN_IMAGE_PATTERN.finditer(text):
        alt = match.group("alt").lower()
        target = match.group("target").strip("<>").split("#", 1)[0].split("?", 1)[0]
        if _is_substantive_image_target(root, target, alt):
            return True
    for match in HTML_IMAGE_PATTERN.finditer(text):
        target = match.group("target").strip("<>").split("#", 1)[0].split("?", 1)[0]
        if _is_substantive_image_target(root, target):
            return True
    return False


def _is_substantive_image_target(root: Path, target: str, alt: str = "") -> bool:
    lowered_target = target.lower()
    lowered_alt = alt.lower()
    if any(marker in lowered_alt for marker in BADGE_ALT_MARKERS):
        return False
    if any(marker in lowered_target for marker in BADGE_TARGET_MARKERS):
        return False
    if lowered_target.startswith(("http://", "https://")):
        return lowered_target.endswith(SUBSTANTIVE_IMAGE_EXTENSIONS)
    if not lowered_target.endswith(SUBSTANTIVE_IMAGE_EXTENSIONS):
        return False
    return (root / target).is_file()
