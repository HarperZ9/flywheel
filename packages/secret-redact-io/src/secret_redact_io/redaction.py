from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Pattern


Replacement = str | Callable[[re.Match[str]], str]


@dataclass(frozen=True)
class RedactionRule:
    name: str
    pattern: Pattern[str]
    replacement: Replacement


@dataclass(frozen=True)
class RedactionResult:
    text: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


class GuardrailPolicy:
    def __init__(self, rules: list[RedactionRule]) -> None:
        self.rules = rules

    @classmethod
    def default(cls) -> "GuardrailPolicy":
        def field_replace(match: re.Match[str]) -> str:
            return f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED:credential_field]{match.group(5)}"

        return cls(
            [
                RedactionRule(
                    "private_key",
                    re.compile(
                        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                        re.DOTALL,
                    ),
                    "[REDACTED:private_key]",
                ),
                RedactionRule(
                    "openai_api_key",
                    re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
                    "[REDACTED:openai_api_key]",
                ),
                RedactionRule(
                    "github_token",
                    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
                    "[REDACTED:github_token]",
                ),
                RedactionRule(
                    "aws_access_key",
                    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
                    "[REDACTED:aws_access_key]",
                ),
                RedactionRule(
                    "jwt",
                    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
                    "[REDACTED:jwt]",
                ),
                RedactionRule(
                    "bearer_token",
                    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}\b"),
                    "Bearer [REDACTED:bearer_token]",
                ),
                RedactionRule(
                    "credential_field",
                    re.compile(
                        r"(?i)\b(password|passwd|api[_-]?key|secret|token)\b"
                        r"(\s*[:=]\s*)(['\"]?)(?!\[REDACTED:)([^\s,;'\"\]]+)(['\"]?)"
                    ),
                    field_replace,
                ),
            ]
        )

    def redact_text(self, text: str) -> RedactionResult:
        counts: dict[str, int] = {}
        current = text
        for rule in self.rules:
            current, count = rule.pattern.subn(rule.replacement, current)
            if count:
                counts[rule.name] = count
        return RedactionResult(text=current, counts=counts)
