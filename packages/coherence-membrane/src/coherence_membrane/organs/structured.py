"""StructuredDataOrgan -- the membrane's third sense: reading structured data.

Sight perceives pixels and hearing perceives sound; this perceives DATA -- a JSON
document the operator owns or has authorised. It witnesses two identities:

  * identity_sha256   -- the raw bytes (exact, re-derivable), like every organ.
  * canonical_sha256  -- the SHA-256 of the document re-serialised in a normal
                        form (sorted keys, no insignificant whitespace), so two
                        byte-different but canonically-equivalent documents share
                        one canonical identity.

Why the second hash: for an image, byte drift IS the change you care about. For
structured data byte drift is too sensitive -- reformatting or reordering object
keys flips the raw identity while the document is unchanged. The canonical
identity lets baseline memory judge drift on the document's *normal form* rather
than its exact bytes: a canonically-equivalent change is MATCH, a canonical
difference is a real DRIFT.

This is STRUCTURAL canonicalisation (key order + whitespace + escaping), NOT an
understanding of the content's meaning. Canonical-equal is a sufficient-but-not-
necessary proxy for "the same data": equal canonical forms are genuinely
equivalent, but two values that mean the same thing can still differ canonically
(see the numeric caveats below). Like the dHash and the audio envelope, the
canonical hash is honest evidence, not comprehension.

Inert and fail-closed like every organ: it reads bytes and reports; it never
mutates, parses-and-evaluates, or executes anything; invalid JSON -- or a value
that has no canonical form, e.g. NaN/Infinity -- yields identity-only + UNVERIFIED,
never a crash and never a fabricated canonical hash. Canonicalisation runs
entirely in memory with no size cap, so peak RAM is a small multiple of the
document size; bound the artifact size upstream before observing untrusted input.

Honesty about canonicalisation: the canonical form normalises object-key order
and insignificant whitespace and escapes non-ASCII consistently. It does NOT
normalise numeric spelling (1 vs 1.0) or representation (1e3 vs 1000), and it
inherits IEEE-754 float limits -- extreme/sub-normal magnitudes can round (e.g.
1e-400 -> 0.0), so the canonical form reflects the PARSED float, which may not
equal the source literal's value. -0.0 and 0.0 differ; duplicate object keys
collapse to the last value (RFC-8259 parse). Array order is preserved because it
is meaningful. Stdlib `json` only -- no third-party parser in the trust path.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult


def canonical_json_bytes(obj) -> bytes:
    """Serialise a parsed JSON value to its canonical byte form.

    Sorted keys, compact separators, ASCII-escaped. Raises ValueError on values
    with no canonical form (NaN/Infinity) via allow_nan=False -- callers degrade
    to identity-only rather than emit a non-canonical hash.
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _typename(obj) -> str:
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "boolean"
    if isinstance(obj, (int, float)):
        return "number"
    if isinstance(obj, str):
        return "string"
    if isinstance(obj, list):
        return "array"
    if isinstance(obj, dict):
        return "object"
    return type(obj).__name__


class StructuredDataOrgan:
    name = "structured-data"

    def observe(self, subject) -> list[Observation]:
        """Observe a JSON artifact. `subject` is a path or bytes."""
        path_str, payload = self._read(subject)
        if payload is None:
            return [self._unreadable(path_str)]

        identity = sha256_hex(payload)
        data: dict = {"identity_sha256": identity, "bytes": len(payload)}
        status = Status.PASS
        summary = "structured data observed"

        try:
            obj = json.loads(payload)
            canonical = canonical_json_bytes(obj)
            data.update({
                "format": "json",
                "canonical_sha256": sha256_hex(canonical),
                "canonical_bytes": len(canonical),
                "top_level_type": _typename(obj),
                "decoded": True,
            })
            if isinstance(obj, dict):
                data["key_count"] = len(obj)
            elif isinstance(obj, list):
                data["item_count"] = len(obj)
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError, RecursionError) as exc:
            data.update({
                "format": "unknown",
                "canonical_sha256": None,
                "decoded": False,
                "decode_note": str(exc),
            })
            status = Status.UNVERIFIED
            summary = "structured data observed (identity only; not canonicalisable JSON)"

        return [
            Observation(
                organ=self.name,
                subject=path_str,
                summary=summary,
                status=status,
                provenance=Provenance.witness_bytes(path_str, payload, "high"),
                data=data,
            )
        ]

    @staticmethod
    def _read(subject) -> tuple[str, bytes | None]:
        # Frame-like (descriptor + callable read): read its bytes and perceive
        # them like any other bytes (JSON carried in a frame is still
        # canonicalised; anything else degrades to identity-only) -- never crash on
        # Path(frame). Keeps all_organs() total over any subject.
        descriptor = getattr(subject, "descriptor", None)
        reader = getattr(subject, "read", None)
        if descriptor is not None and callable(reader):
            sid = f"{getattr(descriptor, 'source_id', '?')}#{getattr(descriptor, 'frame_index', '?')}"
            try:
                return sid, reader()
            except Exception:
                return sid, None
        if isinstance(subject, (bytes, bytearray)):
            return "<bytes>", bytes(subject)
        try:
            path = Path(subject)
        except (TypeError, ValueError, OSError):
            # not bytes, not a Frame, not a path-like -> unperceivable, not a crash
            return repr(subject)[:64], None
        try:
            return str(path), path.read_bytes()
        except (OSError, ValueError):
            return str(path), None

    def _unreadable(self, path_str: str) -> Observation:
        return Observation(
            organ=self.name,
            subject=path_str,
            summary="artifact unreadable",
            status=Status.UNVERIFIED,
            provenance=Provenance.witness_bytes(path_str, b"", "low"),
            data={"format": "unknown", "canonical_sha256": None, "decoded": False},
        )

    # --- selftest ---------------------------------------------------------

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        base = b'{"b": 2, "a": 1, "nested": {"y": 2, "x": 1}, "list": [3, 1, 2]}'
        # Same meaning, different bytes: reordered keys + reformatted whitespace.
        reformatted = (
            b'{\n  "a": 1,\n  "list": [3, 1, 2],\n  "nested": {"x": 1, "y": 2},\n  "b": 2\n}'
        )
        changed = b'{"a": 1, "b": 3, "nested": {"x": 1, "y": 2}, "list": [3, 1, 2]}'
        reordered_list = b'{"a": 1, "b": 2, "nested": {"x": 1, "y": 2}, "list": [1, 2, 3]}'
        invalid = b'{not valid json'

        ob = self.observe(base)[0]
        orf = self.observe(reformatted)[0]
        och = self.observe(changed)[0]
        orl = self.observe(reordered_list)[0]
        oinv = self.observe(invalid)[0]

        # Canonical identity collapses reformatting + key reordering...
        checks.append(Check(
            "canonical equal for reformatted+reordered keys",
            ob.data.get("canonical_sha256") == orf.data.get("canonical_sha256")
            and ob.data.get("identity_sha256") != orf.data.get("identity_sha256"),
            f"identity differs, canonical equal: {ob.data.get('canonical_sha256', '')[:12]}..",
        ))
        # ...but a changed value is a real semantic difference...
        checks.append(Check(
            "canonical differs on a changed value",
            ob.data.get("canonical_sha256") != och.data.get("canonical_sha256"),
        ))
        # ...and array order is semantic, so reordering a list IS a change.
        checks.append(Check(
            "canonical differs on reordered array",
            ob.data.get("canonical_sha256") != orl.data.get("canonical_sha256"),
        ))

        rederived = sha256_hex(base)
        checks.append(Check("identity re-derives", ob.data.get("identity_sha256") == rederived))
        checks.append(Check(
            "provenance digest full-width",
            ob.provenance.digest == "sha256:" + rederived and len(rederived) == 64,
        ))
        checks.append(Check(
            "canonical hash stable",
            ob.data.get("canonical_sha256") == self.observe(base)[0].data.get("canonical_sha256"),
        ))
        checks.append(Check(
            "invalid JSON fails closed",
            oinv.status == Status.UNVERIFIED and oinv.data.get("canonical_sha256") is None,
        ))
        # A value that parses but has no canonical form (NaN) is a distinct path
        # (allow_nan=False) -- prove it fails closed too, so allow_nan can't regress.
        onan = self.observe(b'{"x": NaN}')[0]
        checks.append(Check(
            "non-canonicalisable number (NaN) fails closed",
            onan.status == Status.UNVERIFIED and onan.data.get("canonical_sha256") is None,
        ))
        checks.append(Check(
            "status is advisory (not authority)",
            ob.status in {Status.PASS, Status.WARN, Status.UNVERIFIED,
                          Status.NEEDS_HUMAN, Status.BLOCK},
        ))
        return SelftestResult(self.name, checks)
