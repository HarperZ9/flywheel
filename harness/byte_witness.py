"""byte_witness.py -- witness exact bytes into a chain-linked, offline-checkable record.

Everything else in this repository seals a *structure*: a receipt, a verdict, a
stage. This seals the bytes themselves, which is the one thing a verification
pipeline in any domain needs and cannot get from a typed receipt. The instrument
frame that came off the device. The Lean file a kernel accepted. The statute text
a citation points into. The exact prompt bytes a model was handed.

A witness records the digest of the bytes, how many there were, and what came
before it in the chain. It never carries the bytes. The caller keeps those
wherever they live and hands them back to the verifier, so a record can travel
where the content may not, and a record over material nobody may republish is
still a record somebody can check.

Sealing refuses loudly: a witness that cannot be taken honestly raises. Checking
never raises, and lives in byte_witness_verify.

What a witness does not establish is in does_not_prove(), which is never empty.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .evidence_json import canonical_sha256
from .tool_call_receipt import _digest_well_formed, _sha256_hex

WITNESS_SCHEMA = "flywheel.byte-witness/v1"
GENESIS = ""
_CHUNK = 1 << 20


class WitnessError(ValueError):
    """A witness that could not be taken honestly."""


def _bytes_or_raise(data: object) -> bytes:
    """str is refused on purpose. Text has no bytes until an encoding is chosen,
    and choosing one here is exactly how a byte witness stops being byte-level."""
    if isinstance(data, str):
        raise WitnessError("witness bytes, not text; encode it and say which encoding")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise WitnessError("a witness is taken over bytes")
    return bytes(data)


@dataclass(frozen=True)
class Span:
    """A byte range inside witnessed bytes, carrying its own digest.

    This is what binds a claim to a place: the sentence a citation quotes, the
    field inside an instrument frame, the theorem statement inside a source file.
    A span is half-open, so end is the first byte outside it.
    """

    start: int
    end: int
    sha256: str
    note: str = ""

    def record(self) -> dict:
        return {"start": self.start, "end": self.end,
                "sha256": self.sha256, "note": self.note}


def cite(data: object, start: int, end: int, note: str = "") -> Span:
    """Seal one byte range of ``data``. Refuses a range that is not inside it."""
    raw = _bytes_or_raise(data)
    if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool):
        raise WitnessError("a span is bounded by integers")
    if not 0 <= start < end <= len(raw):
        raise WitnessError(f"span [{start}, {end}) is not inside {len(raw)} bytes")
    if not isinstance(note, str):
        raise WitnessError("a span note is text")
    return Span(start=start, end=end, sha256=_sha256_hex(raw[start:end]), note=note)


@dataclass(frozen=True)
class Witness:
    """One witnessed byte sequence, linked to the one before it."""

    label: str
    sha256: str
    length: int
    observed_at: str
    prev: str
    spans: tuple[Span, ...] = ()
    context: dict = field(default_factory=dict)

    def record(self) -> dict:
        """The record as it travels. Keys sort, so no reader needs a field order."""
        return {"schema": WITNESS_SCHEMA, "label": self.label,
                "sha256": self.sha256, "length": self.length,
                "observed_at": self.observed_at, "prev": self.prev,
                "spans": [span.record() for span in self.spans],
                "context": self.context}

    def link(self) -> str:
        """The digest the next witness points back at.

        It folds in prev, so the same bytes witnessed twice in one chain produce
        two different links. A replayed record is not a valid continuation.
        """
        return canonical_sha256(self.record())


def _checked_fields(label: str, observed_at: str, prev: str, context: dict | None) -> dict:
    if not isinstance(label, str) or not label:
        raise WitnessError("a witness needs a label saying what these bytes are")
    if not isinstance(observed_at, str):
        # Empty is allowed and means no time was claimed, which is honest for a
        # deterministic replay. A wrong time asserted as fact is not.
        raise WitnessError("observed_at is the caller's stamp, as text")
    if prev != GENESIS and not _digest_well_formed(prev):
        raise WitnessError("prev is the previous record's 64-character link")
    if context is not None and not isinstance(context, dict):
        raise WitnessError("context is a JSON object of the caller's own facts")
    return dict(context or {})


def _sealed(label: str, digest: str, length: int, observed_at: str, prev: str,
            spans: tuple[Span, ...], context: dict) -> Witness:
    witness = Witness(label=label, sha256=digest, length=length,
                      observed_at=observed_at, prev=prev, spans=spans,
                      context=context)
    try:
        witness.link()  # refuses a context that is outside the JSON data model
    except ValueError as exc:
        raise WitnessError(f"the witness does not canonicalize: {exc}") from exc
    return witness


def witness_bytes(data: object, *, label: str, observed_at: str = "",
                  prev: str = GENESIS, spans: tuple[Span, ...] | list[Span] = (),
                  context: dict | None = None) -> Witness:
    """Seal an exact byte sequence. Empty bytes are a legitimate witness: it
    records that nothing was there, which is a fact a pipeline often needs."""
    raw = _bytes_or_raise(data)
    held = _checked_fields(label, observed_at, prev, context)
    ordered = tuple(spans)
    for span in ordered:
        if not isinstance(span, Span):
            raise WitnessError("spans are built by cite() over the same bytes")
        if not 0 <= span.start < span.end <= len(raw):
            raise WitnessError(f"span [{span.start}, {span.end}) is outside these bytes")
        if _sha256_hex(raw[span.start:span.end]) != span.sha256:
            raise WitnessError(f"span [{span.start}, {span.end}) was cited over other bytes")
    return _sealed(label, _sha256_hex(raw), len(raw), observed_at, prev,
                   ordered, held)


def witness_file(path: str | Path, *, label: str, observed_at: str = "",
                 prev: str = GENESIS, context: dict | None = None) -> Witness:
    """Seal a file's bytes without holding them in memory.

    Spans are not offered here on purpose: citing a range means reading it, and
    a caller who has read the range can witness the bytes directly.
    """
    held = _checked_fields(label, observed_at, prev, context)
    source = Path(path)
    digest, length = hashlib.sha256(), 0
    try:
        with source.open("rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
                length += len(chunk)
    except OSError as exc:
        raise WitnessError(f"the file could not be read: {exc}") from exc
    return _sealed(label, digest.hexdigest(), length, observed_at, prev, (), held)


def append(chain: list[Witness], data: object, *, label: str,
           observed_at: str = "", spans: tuple[Span, ...] | list[Span] = (),
           context: dict | None = None) -> Witness:
    """Witness ``data`` onto the end of ``chain``, linking it to what is there."""
    if not isinstance(chain, list) or any(not isinstance(item, Witness) for item in chain):
        raise WitnessError("a chain is a list of witnesses")
    witness = witness_bytes(data, label=label, observed_at=observed_at,
                            prev=chain[-1].link() if chain else GENESIS,
                            spans=spans, context=context)
    chain.append(witness)
    return witness


def records(chain: list[Witness]) -> list[dict]:
    """The chain as it travels, in order."""
    return [witness.record() for witness in chain]


def does_not_prove(*, signed: bool = False, anchored: bool = False) -> list[str]:
    """What a byte witness leaves open. Never empty, whatever the arguments say."""
    lines = [
        "a digest says the bytes did not change after they were witnessed; it "
        "says nothing about whether they were true, or correct, or complete",
        "a chain proves the order and integrity of the records it holds; it "
        "cannot show that a record was never written, so an omitted step "
        "leaves no broken link behind",
        "a span proves a range hashes to what was recorded; it does not show "
        "that the range is the right one for the claim it was cited for",
    ]
    lines.append(
        "the signature binds this record to a key; it says nothing about who "
        "holds that key, or whether the bytes were witnessed at their source"
        if signed else
        "nothing is signed here, so anyone who can rewrite a record can "
        "recompute every link after it and leave the chain reading as intact")
    lines.append(
        "the anchor dates the chain no earlier than the anchored head; it does "
        "not date any single record inside it"
        if anchored else
        "observed_at is what the caller wrote down, and no clock here checked "
        "it; only an external anchor dates a chain")
    return lines
