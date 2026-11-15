"""Token-efficient prompt shaping for pre-model hooks.

The optimizer is deterministic and stdlib-only. It preserves the operator's
likely objective, constraints, targets, commands, and provenance-bearing
references while removing repeated surface text before a prompt reaches
expensive model context.

Includes the section extraction helpers (formerly _token_sections.py).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_MAX_OUTPUT_CHARS = 3_000
DEFAULT_MIN_CHARS = 2_000
DEFAULT_MIN_SAVINGS_RATIO = 0.20

_ACTION_WORDS = (
    "assess", "build", "change", "commit", "continue", "create", "deliver",
    "fix", "implement", "integrate", "need", "prepare", "push", "research",
    "run", "ship", "test", "verify", "want",
)
_CONSTRAINT_WORDS = (
    "always", "avoid", "cannot", "do not", "don't", "must", "never",
    "only", "require", "should", "without",
)
_COMMAND_RE = re.compile(
    r"^\s*(?:cargo|deno|docker|gh|git|go|kubectl|mypy|node|npm|pnpm|prefire|pytest|"
    r"python|ruff|terraform|uv|yarn)\b",
    re.IGNORECASE,
)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]{2,180})`")
_URL_RE = re.compile(r"https?://[^\s)>\"']+")
_WINDOWS_PATH_RE = re.compile(r"(?:[A-Za-z]:\\|\\\\)[^\s\"'<>|]+")
_QUOTED_PATH_RE = re.compile(r"\"([A-Za-z]:\\[^\"]+)\"")
_PATHLIKE_RE = re.compile(r"(?:\.{0,2}/)?[\w.-]+(?:/[\w.@() -]+)+")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PromptDigest:
    """Compact prompt digest and extraction statistics."""
    optimized: str
    duplicate_lines: int
    duplicate_sentences: int
    code_blocks: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class TokenOptimizationResult:
    """Result emitted by the deterministic token optimizer."""
    optimized: str
    original_chars: int
    optimized_chars: int
    original_tokens: int
    optimized_tokens: int
    saved_tokens: int
    savings_ratio: float
    beneficial: bool
    level: str
    duplicate_lines: int
    duplicate_sentences: int
    preserved_code_blocks: int
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "optimized": self.optimized,
            "original_chars": self.original_chars,
            "optimized_chars": self.optimized_chars,
            "original_tokens": self.original_tokens,
            "optimized_tokens": self.optimized_tokens,
            "saved_tokens": self.saved_tokens,
            "savings_ratio": self.savings_ratio,
            "beneficial": self.beneficial,
            "level": self.level,
            "duplicate_lines": self.duplicate_lines,
            "duplicate_sentences": self.duplicate_sentences,
            "preserved_code_blocks": self.preserved_code_blocks,
            "warnings": list(self.warnings),
        }


def estimate_tokens(text: str) -> int:
    """Estimate token count cheaply for mixed prose/code input."""
    if not text:
        return 0
    char_estimate = math.ceil(len(text) / 4)
    word_estimate = math.ceil(len(re.findall(r"\S+", text)) * 1.3)
    return max(1, char_estimate, word_estimate)


def optimize_prompt(
    text: str,
    *,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
    min_savings_ratio: float = DEFAULT_MIN_SAVINGS_RATIO,
) -> TokenOptimizationResult:
    """Create a compact operator-intent digest from a raw prompt."""
    normalized = normalize_prompt(text)
    original_chars = len(text)
    if not normalized:
        return _result("", original_chars, min_savings_ratio, min_chars)

    digest = build_prompt_digest(
        normalized,
        max_output_chars=max_output_chars,
        estimate_tokens=estimate_tokens,
    )
    return _result(
        digest.optimized,
        original_chars,
        min_savings_ratio,
        min_chars,
        duplicate_lines=digest.duplicate_lines,
        duplicate_sentences=digest.duplicate_sentences,
        code_blocks=digest.code_blocks,
        warnings=digest.warnings,
    )


def hook_payload_for_prompt(
    text: str,
    *,
    mode: str = "context",
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
    min_savings_ratio: float = DEFAULT_MIN_SAVINGS_RATIO,
) -> dict[str, object] | None:
    """Return a Claude Code hook payload for token optimization, if useful."""
    normalized_mode = mode.strip().lower()
    if normalized_mode in {"0", "false", "none", "off", "disabled"}:
        return None

    result = optimize_prompt(
        text,
        max_output_chars=max_output_chars,
        min_chars=min_chars,
        min_savings_ratio=min_savings_ratio,
    )
    if not result.beneficial:
        return None

    replacement = _hook_message(result)
    if normalized_mode == "context":
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": replacement,
            }
        }

    if normalized_mode in {"block", "block-large"}:
        return {
            "decision": "block",
            "suppressOriginalPrompt": True,
            "reason": replacement,
        }

    return None


def normalize_prompt(text: str) -> str:
    """Normalize line endings and collapse blank-line runs."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in cleaned.split("\n")]
    collapsed: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip():
            blank_run = 0
            collapsed.append(line)
            continue
        blank_run += 1
        if blank_run <= 1:
            collapsed.append("")
    return "\n".join(collapsed).strip()


def build_prompt_digest(
    normalized: str,
    *,
    max_output_chars: int,
    estimate_tokens: Callable[[str], int],
) -> PromptDigest:
    """Build a compact intent/constraint digest from normalized text."""
    analysis_text, code_blocks = _extract_code_blocks(normalized)
    raw_lines = _line_items(analysis_text)
    unique_lines, duplicate_lines = _dedupe(raw_lines)
    raw_sentences = _sentence_items(analysis_text)
    unique_sentences, duplicate_sentences = _dedupe(raw_sentences)

    goal = _pick_goal(unique_lines, unique_sentences)
    actions = _pick_matching(unique_lines, _ACTION_WORDS, limit=8)
    constraints = _pick_matching(unique_lines, _CONSTRAINT_WORDS, limit=8)
    urls = _unique_matches(_URL_RE, normalized, limit=10)
    paths = _extract_paths(normalized, limit=12)
    commands = _extract_commands(unique_lines, normalized, limit=10)
    code_notes, code_warnings = _summarize_code_blocks(code_blocks, estimate_tokens)
    context = _pick_context(
        unique_sentences,
        protected=tuple(actions + constraints + urls + paths + commands),
        limit=6,
    )

    parts: list[str] = []
    if goal:
        parts.append(f"Goal: {_clip(goal, 260)}")
    parts.extend(_section("Do", actions))
    parts.extend(_section("Constraints", constraints))
    parts.extend(_section("Targets", paths + urls))
    parts.extend(_section("Commands", commands))
    parts.extend(_section("Code", code_notes))
    parts.extend(_section("Context", context))

    omitted = duplicate_lines + duplicate_sentences
    if omitted or code_blocks:
        summary = f"{omitted} repeated items compressed"
        if code_blocks:
            summary += f"; {len(code_blocks)} fenced code block(s) summarized"
        parts.append(f"Omitted: {summary}.")

    optimized = "\n".join(parts).strip() or _clip_block(normalized, max_output_chars)
    return PromptDigest(
        optimized=_clip_block(optimized, max_output_chars),
        duplicate_lines=duplicate_lines,
        duplicate_sentences=duplicate_sentences,
        code_blocks=len(code_blocks),
        warnings=tuple(code_warnings),
    )


def _extract_code_blocks(text: str) -> tuple[str, list[str]]:
    blocks: list[str] = []

    def replace(match: re.Match[str]) -> str:
        blocks.append(match.group(0))
        return f"\n[code block {len(blocks)} omitted from prose scan]\n"

    return _CODE_FENCE_RE.sub(replace, text), blocks


def _line_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = re.sub(r"^\s*(?:[-*+>]|\d+[.)])\s*", "", line).strip()
        if stripped:
            items.append(stripped)
    return items


def _sentence_items(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [chunk.strip(" \t-*+") for chunk in chunks if len(chunk.strip()) >= 24]


def _dedupe(items: list[str]) -> tuple[list[str], int]:
    seen: set[str] = set()
    out: list[str] = []
    duplicates = 0
    for item in items:
        key = _SPACE_RE.sub(" ", item.lower()).strip()
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        out.append(item)
    return out, duplicates


def _pick_goal(lines: list[str], sentences: list[str]) -> str:
    candidates = lines + sentences
    for item in candidates:
        if _contains_any(item, _ACTION_WORDS):
            return item
    return candidates[0] if candidates else ""


def _pick_matching(lines: list[str], words: tuple[str, ...], *, limit: int) -> list[str]:
    out: list[str] = []
    for line in lines:
        if _contains_any(line, words):
            out.append(_clip(line, 220))
        if len(out) >= limit:
            break
    return out


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    haystack = text.lower()
    return any(word in haystack for word in words)


def _unique_matches(pattern: re.Pattern[str], text: str, *, limit: int) -> list[str]:
    cleaned = [match.strip(".,;") for match in pattern.findall(text) if match]
    unique, _ = _dedupe(cleaned)
    return unique[:limit]


def _extract_paths(text: str, *, limit: int) -> list[str]:
    candidates: list[str] = []
    candidates.extend(_WINDOWS_PATH_RE.findall(text))
    candidates.extend(_QUOTED_PATH_RE.findall(text))
    candidates.extend(_PATHLIKE_RE.findall(text))
    cleaned = [item.strip(".,;") for item in candidates if len(item.strip()) >= 4]
    unique, _ = _dedupe(cleaned)
    return unique[:limit]


def _extract_commands(lines: list[str], text: str, *, limit: int) -> list[str]:
    commands = [_clip(line, 220) for line in lines if _COMMAND_RE.match(line)]
    inline = [item for item in _INLINE_CODE_RE.findall(text) if _COMMAND_RE.match(item)]
    commands.extend(_clip(item, 220) for item in inline)
    unique, _ = _dedupe(commands)
    return unique[:limit]


def _summarize_code_blocks(
    blocks: list[str],
    estimate_tokens: Callable[[str], int],
) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    warnings: list[str] = []
    for index, block in enumerate(blocks, start=1):
        body = block.strip("`")
        lines = [line for line in body.splitlines() if line.strip()]
        token_estimate = estimate_tokens(block)
        notes.append(f"block {index}: {len(lines)} nonblank lines, ~{token_estimate} tokens")
        if token_estimate > 600:
            warnings.append(
                "Large pasted code was summarized; prefer a file path for lossless review."
            )
    return notes[:6], warnings


def _pick_context(
    sentences: list[str],
    *,
    protected: tuple[str, ...],
    limit: int,
) -> list[str]:
    protected_keys = {_SPACE_RE.sub(" ", item.lower()).strip() for item in protected}
    out: list[str] = []
    for sentence in sentences:
        key = _SPACE_RE.sub(" ", sentence.lower()).strip()
        if key in protected_keys:
            continue
        if sentence.startswith("[code block "):
            continue
        out.append(_clip(sentence, 240))
        if len(out) >= limit:
            break
    return out


def _section(name: str, items: list[str]) -> list[str]:
    if not items:
        return []
    lines = [f"{name}:"]
    lines.extend(f"- {_clip(item, 240)}" for item in items)
    return lines


def _clip(text: str, limit: int) -> str:
    compact = _SPACE_RE.sub(" ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def _clip_block(text: str, limit: int) -> str:
    compact = text.strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def _result(
    optimized: str,
    original_chars: int,
    min_savings_ratio: float,
    min_chars: int,
    *,
    duplicate_lines: int = 0,
    duplicate_sentences: int = 0,
    code_blocks: int = 0,
    warnings: tuple[str, ...] = (),
) -> TokenOptimizationResult:
    original_tokens = estimate_tokens("x" * original_chars)
    optimized_tokens = estimate_tokens(optimized)
    saved_tokens = max(0, original_tokens - optimized_tokens)
    savings_ratio = saved_tokens / original_tokens if original_tokens else 0.0
    beneficial = (
        original_chars >= min_chars
        and optimized_tokens < original_tokens
        and savings_ratio >= min_savings_ratio
    )
    if not beneficial:
        level = "unchanged"
    elif savings_ratio >= 0.60:
        level = "aggressive"
    else:
        level = "compact"
    return TokenOptimizationResult(
        optimized=optimized,
        original_chars=original_chars,
        optimized_chars=len(optimized),
        original_tokens=original_tokens,
        optimized_tokens=optimized_tokens,
        saved_tokens=saved_tokens,
        savings_ratio=round(savings_ratio, 4),
        beneficial=beneficial,
        level=level,
        duplicate_lines=duplicate_lines,
        duplicate_sentences=duplicate_sentences,
        preserved_code_blocks=code_blocks,
        warnings=warnings,
    )


def _hook_message(result: TokenOptimizationResult) -> str:
    saved = f"Saved ~{result.saved_tokens} tokens ({result.savings_ratio:.0%})."
    warnings = "\n".join(f"Warning: {warning}" for warning in result.warnings)
    body = (
        "Token optimizer blocked a large prompt before model ingestion.\n"
        f"{saved} Resubmit this compact replacement if it preserves intent:\n\n"
        f"{result.optimized}"
    )
    if warnings:
        body += f"\n\n{warnings}"
    return body
