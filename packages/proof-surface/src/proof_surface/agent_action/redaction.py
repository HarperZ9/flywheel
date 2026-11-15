"""Redaction boundary + leak scan: a proof packet is not a data lake.

Model-facing artifacts carry only digest-bound refs (``redacted:sha256:<hex>``);
raw payloads live in a separate store (an uncommitted temp store in production) and
are recoverable by digest for replay. ``scan_for_leaks`` asserts that no raw
payload appears verbatim in a model-facing artifact. Stdlib-only.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterator


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def redact(raw: str) -> dict[str, str]:
    """Return a digest-bound ref for a raw payload; the raw never appears in the ref."""
    sha = sha256_text(raw)
    return {"ref": f"redacted:sha256:{sha}", "raw_payload_sha256": sha}


class RawStore:
    """Raw payloads keyed by digest -- stands in for an uncommitted temp store.

    The point of the boundary: raw payloads are recoverable here by digest for
    replay, but are never carried inside a packet.
    """

    def __init__(self) -> None:
        self._by_sha: dict[str, str] = {}

    def put(self, raw: str) -> str:
        sha = sha256_text(raw)
        self._by_sha[sha] = raw
        return sha

    def get(self, sha: str) -> str | None:
        return self._by_sha.get(sha)


def _walk_strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                yield key
            yield from _walk_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_strings(value)


def scan_for_leaks(artifact: Any, *, secrets: list[str]) -> list[dict[str, str]]:
    """Return one finding per secret that appears verbatim in the artifact."""
    strings = [artifact] if isinstance(artifact, str) else list(_walk_strings(artifact))
    findings: list[dict[str, str]] = []
    for secret in secrets:
        if not secret:
            continue
        for text in strings:
            if secret in text:
                findings.append(
                    {"secret_sha256": sha256_text(secret), "where": text[:80]}
                )
                break
    return findings


def leak_count(artifact: Any, *, secrets: list[str]) -> int:
    return len(scan_for_leaks(artifact, secrets=secrets))
