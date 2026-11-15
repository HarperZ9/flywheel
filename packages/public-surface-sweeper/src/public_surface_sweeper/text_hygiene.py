from __future__ import annotations

import re
from pathlib import Path

from .models import Finding

SECRET_PATTERNS = (
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
        "private key block marker",
    ),
    (
        "github-token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
        "GitHub token shaped value",
    ),
    (
        "openai-key",
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        "OpenAI key shaped value",
    ),
    (
        "aws-access-key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS access key shaped value",
    ),
    (
        "slack-token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        "Slack token shaped value",
    ),
)
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"""
    (?<![A-Za-z0-9_])
    ["']?
    (?P<name>
        api[_-]?key|
        api[_-]?token|
        access[_-]?token|
        auth[_-]?token|
        client[_-]?secret|
        password|
        passwd|
        secret|
        token
    )
    ["']?
    \s*(?:=|:)\s*
    ["']?
    (?P<value>[A-Za-z0-9][A-Za-z0-9._~+/=-]{15,})
    ["']?
    """,
    re.IGNORECASE | re.VERBOSE,
)
PLACEHOLDER_MARKERS = (
    "changeme",
    "dummy",
    "example",
    "placeholder",
    "redacted",
    "sample",
    "test",
    "your",
)


def text_findings(root: Path, path: Path, text: str) -> list[Finding]:
    rel_path = _relative(path, root)
    findings: list[Finding] = []

    for match in re.finditer("\u2014", text):
        findings.append(
            Finding(
                path=rel_path,
                line=_line_number(text, match.start()),
                rule="em-dash",
                severity="error",
                message="replace em dash with plain punctuation",
            )
        )

    provider_spans: list[tuple[int, int]] = []
    for rule, pattern, message in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            provider_spans.append(match.span())
            findings.append(
                Finding(
                    path=rel_path,
                    line=_line_number(text, match.start()),
                    rule=rule,
                    severity="error",
                    message=message,
                )
            )
    for match in SECRET_ASSIGNMENT_PATTERN.finditer(text):
        if _overlaps_any(match.span("value"), provider_spans):
            continue
        if _is_placeholder_value(match.group("value")):
            continue
        findings.append(
            Finding(
                path=rel_path,
                line=_line_number(text, match.start("value")),
                rule="secret-assignment",
                severity="error",
                message=(
                    f"{match.group('name')} appears to contain a "
                    "credential-shaped value"
                ),
            )
        )
    return findings


def secret_rules() -> set[str]:
    return {rule for rule, _, _ in SECRET_PATTERNS} | {"secret-assignment"}


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _overlaps_any(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < other_end and other_start < end for other_start, other_end in spans)


def _is_placeholder_value(value: str) -> bool:
    normalized = value.strip("\"'<>[](){}").strip()
    if len(normalized) < 16:
        return True
    lowered = normalized.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return True
    variable_part = re.sub(r"[^A-Za-z0-9]", "", normalized)
    return len(set(variable_part)) <= 3
