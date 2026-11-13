"""model_redaction.py -- taking a credential out of text that has to be kept.

A provider's error message is evidence. It is also the one place at this
boundary where a credential is routinely quoted back at you: several vendors
echo the rejected key, or a recognizable prefix of it, into the body of a 401
so an operator can tell which key failed. A fault record that keeps the message
verbatim therefore writes a live credential into whatever durable store the
record lands in, and the record is exactly the thing a debugging layer is built
to keep.

So the message is scrubbed on the way in, not on the way out. Scrubbing at the
display layer leaves the secret in the store, where the next reader is a log
shipper rather than a person.

Two pattern sets, in this order:

- BOUNDARY_PATTERNS, the key shapes this boundary sees most, which the shared
  set below does not catch. Its ``openai_api_key`` rule is ``sk-`` followed by
  an alphanumeric run, and every modern OpenAI key is ``sk-proj-...``: the dash
  ends the run after four characters, so the rule matches nothing that would
  survive. The same hole swallows ``sk-ant-`` and ``sk-or-v1-``, and there is
  no rule at all for a Google ``AIza`` key. These run first so the specific
  shape names the match instead of a generic rule swallowing it.
- SECRET_PATTERNS, imported rather than copied, so there is one definition in
  this repo of what a secret looks like and a rule added there arrives here.

A fingerprint is attached only to matches that are structurally random. Twelve
hex characters is forty-eight bits, which is not invertible for a key drawn
from a vendor's generator and is a wordlist lookup for a human-chosen password.
So a key gets a digest, by which two records can be shown to name the same
leaked credential, and a password gets a bare label and nothing else. A
``private_key`` match is the BEGIN header alone, identical in every key ever
issued, so digesting it would assert an identity it does not have.

Standard library only. This module never reads a clock and never makes a call.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .infra.credential_scanner import SECRET_PATTERNS

BOUNDARY_PATTERNS: "list[tuple[str, str]]" = [
    ("anthropic_api_key", r"sk-ant-[A-Za-z0-9_-]{16,}"),
    ("openrouter_api_key", r"sk-or-[A-Za-z0-9_-]{16,}"),
    ("openai_project_key", r"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{16,}"),
    ("google_api_key", r"AIza[A-Za-z0-9_-]{16,}"),
    ("groq_api_key", r"gsk_[A-Za-z0-9]{20,}"),
    ("huggingface_token", r"hf_[A-Za-z0-9]{20,}"),
    ("xai_api_key", r"xai-[A-Za-z0-9]{20,}"),
    # A vendor not named above, kept last so a named shape wins the match.
    ("vendor_prefixed_key", r"sk-[A-Za-z0-9]{2,16}-[A-Za-z0-9_-]{16,}"),
]

# Match text random enough that a 48-bit digest of it stays non-invertible.
FINGERPRINTED = frozenset({
    "anthropic_api_key", "openrouter_api_key", "openai_project_key",
    "google_api_key", "groq_api_key", "huggingface_token", "xai_api_key",
    "vendor_prefixed_key", "openai_api_key", "github_token", "aws_access_key",
    "jwt",
})

TRUNCATED = "[...truncated]"
DEFAULT_LIMIT = 2048

_COMPILED = [(name, re.compile(pattern))
             for name, pattern in list(BOUNDARY_PATTERNS) + list(SECRET_PATTERNS)]


def _fingerprint(secret_text: str) -> str:
    """The same construction credential_scanner uses, so the two agree.

    Deliberately not re-exported from there: that function is private, and
    matching its construction by hand keeps this module importable without
    reaching into another module's internals.
    """
    return hashlib.sha256(secret_text.encode("utf-8")).hexdigest()[:12]


def _mark(name: str, matched: str) -> str:
    if name in FINGERPRINTED:
        return "[redacted:" + name + ":" + _fingerprint(matched) + "]"
    return "[redacted:" + name + "]"


def scrub(text: Any, *, limit: int = DEFAULT_LIMIT) -> dict:
    """One string with every recognized secret replaced, and what was found.

    Truncation happens AFTER scrubbing, never before. Cutting first would leave
    a secret that begins past the cut untouched in the part that was kept, and
    a secret that straddles the cut half-printed, which is a disclosure dressed
    as a bound.

    ``original_chars`` is None for an input that was not text at all, because
    there was nothing to measure rather than nothing there.
    """
    if not isinstance(text, str):
        return {"text": "", "redacted": False, "kinds": [], "truncated": False,
                "original_chars": None}
    kinds: "list[str]" = []

    def replace(match, name=""):
        if name not in kinds:
            kinds.append(name)
        return _mark(name, match.group())

    out = text
    for name, expression in _COMPILED:
        out = expression.sub(lambda m, n=name: replace(m, n), out)
    ceiling = limit if type(limit) is int and limit >= 0 else DEFAULT_LIMIT
    truncated = len(out) > ceiling
    if truncated:
        out = out[:ceiling] + TRUNCATED
    return {"text": out, "redacted": bool(kinds), "kinds": kinds,
            "truncated": truncated, "original_chars": len(text)}


def scrub_value(value: Any, *, depth: int = 6, items: int = 32,
                limit: int = DEFAULT_LIMIT) -> dict:
    """A nested structure with every string in it scrubbed, within bounds.

    A proxy hands back the upstream provider's raw error body, which is an
    arbitrary object from a party this repo has no schema for. It is worth
    keeping and it cannot be trusted to be small, shallow, or free of
    credentials, so the walk is bounded on all three and says when a bound was
    reached rather than silently returning a partial structure as if complete.
    """
    kinds: "list[str]" = []
    bounded = [False]

    def walk(node: Any, level: int) -> Any:
        if level > depth:
            bounded[0] = True
            return "[depth_exceeded]"
        if isinstance(node, str):
            reading = scrub(node, limit=limit)
            for kind in reading["kinds"]:
                if kind not in kinds:
                    kinds.append(kind)
            if reading["truncated"]:
                bounded[0] = True
            return reading["text"]
        if isinstance(node, dict):
            out = {}
            for index, (key, sub) in enumerate(node.items()):
                if index >= items:
                    bounded[0] = True
                    break
                key_reading = scrub(str(key), limit=limit)
                for kind in key_reading["kinds"]:
                    if kind not in kinds:
                        kinds.append(kind)
                if key_reading["truncated"]:
                    bounded[0] = True
                safe_key = key_reading["text"]
                if safe_key in out:
                    bounded[0] = True
                    continue
                out[safe_key] = walk(sub, level + 1)
            return out
        if isinstance(node, (list, tuple)):
            if len(node) > items:
                bounded[0] = True
            return [walk(sub, level + 1) for sub in list(node)[:items]]
        if node is None or type(node) in (bool, int, float):
            return node
        return walk(repr(node), level)

    return {"value": walk(value, 0), "kinds": kinds, "bounded": bounded[0]}


__all__ = ["BOUNDARY_PATTERNS", "DEFAULT_LIMIT", "FINGERPRINTED", "TRUNCATED",
           "scrub", "scrub_value"]
