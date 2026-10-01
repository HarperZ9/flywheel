"""_common.py -- shared pieces for the per-provider capture adapters.

Each adapter reads one provider response that the caller already received and
returns a Capture: a ReasoningRecord, the gaps the response itself shows, and
the adapter's field map. The field map names every response path the adapter
reads, the access-gap source that documents it, and a confidence. A path the
access-gap record does not document is marked "adapter-unverified" so a reader
knows to re-read the provider's raw page before trusting it on a live call.

Opaque reasoning fields (encrypted content, signatures, thought signatures,
redacted thinking) are handled by opaque_ref only: it hashes the value exactly
as received and records {name, sha256, bytes}. It never decodes, decrypts,
parses or forwards the value, and nothing else in this package touches it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..channel import GapRecord, ReasoningRecord, canonical_bytes, sha256_hex

UNVERIFIED = "adapter-unverified"


@dataclass
class Capture:
    record: ReasoningRecord
    gaps: list = field(default_factory=list)
    field_map: dict = field(default_factory=dict)

    def gap_codes(self) -> list:
        return sorted({g.gap_code for g in self.gaps})


def opaque_ref(name: str, value) -> dict:
    """Digest of an opaque provider field, exactly as received. Never parsed."""
    data = value.encode("utf-8", "surrogatepass") if isinstance(value, str) else canonical_bytes(value)
    return {"name": name, "sha256": sha256_hex(data), "bytes": str(len(data))}


def opaque_gap(component: str, name: str, provider: str) -> GapRecord:
    return GapRecord("PROVIDER_ENCRYPTED", component, required_class="A1r", available_class="A0",
                     evidence=f"{provider} response carried opaque field {name}; stored by digest only")


def find_count(obj, key: str):
    """First integer value under `key` anywhere in a usage object (depth-first).
    Used where a provider documents the count but not its exact path."""
    if isinstance(obj, dict):
        if isinstance(obj.get(key), int) and not isinstance(obj.get(key), bool):
            return obj[key]
        for v in obj.values():
            got = find_count(v, key)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = find_count(v, key)
            if got is not None:
                return got
    return None


def truncation_gap(provider: str, component: str = "capture") -> GapRecord:
    return GapRecord("REASONING_TRUNCATED", component, evidence=(
        f"{provider} run stopped at its token limit inside the reasoning span; "
        "excluded from every faithfulness denominator and counted separately"))


def omitted_gap(provider: str, display: str) -> GapRecord:
    return GapRecord("REASONING_OMITTED_BY_DEFAULT", "capture", required_class="A1s",
                     available_class="A0",
                     evidence=f"{provider} display setting {display!r}; reasoning text was not requested "
                              "or came back empty, which records a configuration, not an absence of reasoning")


def joined(texts) -> str:
    return "\n".join(t for t in texts if isinstance(t, str) and t)
