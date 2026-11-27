"""Shared schemas, constants, text normalization, and AST hashing for Data Forge."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from typing import Any

FLYWHEEL_MODULES_LINKED = True

SCHEMA_CARD = "flywheel.data-forge-card/1"
SCHEMA_MERKLE = "flywheel.data-forge-merkle/1"

ALLOWED_LICENSES = frozenset({
    "AGPL-3.0-only",
    "Apache-2.0",
    "BSD-3-Clause",
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
    "CC0-1.0",
    "MIT",
    "clean-room-synthetic",
    "curated-open",
})

DENIED_LICENSES = frozenset({
    "ALL-RIGHTS-RESERVED",
    "CLOSED",
    "CONFIDENTIAL",
    "PROPRIETARY",
    "UNLICENSED",
})

DISALLOWED_COLLECTION_MODES = frozenset({
    "BIOMETRIC_HARVEST",
    "COVERT_TRACKING",
    "DOXXING",
    "MASS_CITIZEN_PROFILING",
    "NON_CONSENSUAL_PII",
})

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("github_pat", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{24,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("hf_token", re.compile(r"\bhf_[A-Za-z0-9]{24,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("email_pii", re.compile(r"\b[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("ssn_pii", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("windows_user_path", re.compile(r"(?i)[A-Z]:\\Users\\[A-Za-z0-9._-]+\\")),
    ("unix_home_path", re.compile(r"/home/[a-zA-Z0-9._-]+/")),
)

SLOP_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdelve(?:s|d|ing)?\s+into\b", re.IGNORECASE),
    re.compile(r"\bit'?s\s+important\s+to\s+note\b", re.IGNORECASE),
    re.compile(r"\bin\s+today'?s\s+fast-paced\b", re.IGNORECASE),
    re.compile(r"\bunlock(?:s|ed|ing)?\s+the\s+(?:full\s+)?power\b", re.IGNORECASE),
    re.compile(r"\bseamlessly\b", re.IGNORECASE),
    re.compile(r"\bleverag(?:e|es|ed|ing)\s+the\s+power\b", re.IGNORECASE),
    re.compile(r"\bgame-chang(?:er|ing)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+just\s+[^.,;]{2,40},\s+but\s+(?:also\s+)?\b", re.IGNORECASE),
)

_WORD_RE = re.compile(r"[a-z0-9_]+")
_CODE_FENCE_RE = re.compile(r"```(?:python|py|buildlang|bld)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_BLD_KEYWORDS = frozenset({
    "fn", "let", "mut", "if", "else", "while", "return", "struct",
    "f64", "i64", "i32", "u64", "usize", "bool",
})


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize an object to deterministic compact UTF-8 JSON bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def extract_row_text(row: dict[str, Any]) -> str:
    """Normalize heterogeneous row schemas (chat messages, Q/A, prompt/target, text)."""
    parts: list[str] = []
    if isinstance(row.get("messages"), list):
        for msg in row["messages"]:
            if isinstance(msg, dict) and msg.get("content"):
                parts.append(str(msg["content"]))
    for key in ("prompt", "question", "text", "input", "reference_code", "target", "output", "response"):
        val = row.get(key)
        if val is not None and val != "":
            if isinstance(val, (dict, list)):
                parts.append(json.dumps(val, sort_keys=True, ensure_ascii=True))
            else:
                parts.append(str(val))
    return "\n".join(parts).strip()


def extract_code_snippet(row: dict[str, Any], text: str) -> str:
    """Extract an explicit code field or fenced code block from a candidate row."""
    if row.get("reference_code"):
        return str(row["reference_code"])
    if row.get("code"):
        return str(row["code"])
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return ""


def normalize_text(text: str) -> str:
    """Lowercase alphanumeric whitespace-normalized projection."""
    return " ".join(_WORD_RE.findall(text.lower()))


def word_tokens(text: str) -> list[str]:
    """Return lowercase alphanumeric word tokens."""
    return _WORD_RE.findall(text.lower())


def normalized_ast_hash(code: str) -> str | None:
    """Alpha-renamed structural hash for Python code or token skeleton for BuildLang."""
    stripped = code.strip()
    if len(stripped) < 20:
        return None
    try:
        tree = ast.parse(stripped)

        class _AlphaRenamer(ast.NodeTransformer):
            def __init__(self) -> None:
                self.mapping: dict[str, str] = {}

            def _var(self, name: str) -> str:
                if name not in self.mapping:
                    self.mapping[name] = f"v{len(self.mapping)}"
                return self.mapping[name]

            def visit_Name(self, node: ast.Name) -> ast.AST:
                return ast.copy_location(ast.Name(id=self._var(node.id), ctx=node.ctx), node)

            def visit_arg(self, node: ast.arg) -> ast.AST:
                node.arg = self._var(node.arg)
                node.annotation = None
                return node

            def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
                node.name = "fn"
                self.generic_visit(node)
                return node

        norm = _AlphaRenamer().visit(tree)
        dumped = ast.dump(norm, include_attributes=False)
        return "pyast:" + hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:24]
    except SyntaxError:
        if "fn " in stripped and "{" in stripped and "}" in stripped:
            no_comments = re.sub(r"//.*", "", stripped)
            skeleton = re.sub(
                r"\b[a-z_][a-z0-9_]*\b",
                lambda m: m.group(0) if m.group(0) in _BLD_KEYWORDS else "ID",
                no_comments,
            )
            compact = re.sub(r"\s+", " ", skeleton).strip()
            return "bldskel:" + hashlib.sha256(compact.encode("utf-8")).hexdigest()[:24]
    return None
