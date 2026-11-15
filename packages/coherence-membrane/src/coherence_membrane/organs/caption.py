"""CaptionOrgan -- the membrane reads what was said.

A subtitle/transcript line is a cheap, time-alignable text witness of a moment:
composed per-timestamp with a frame organ (via CompositeObservation), it lets the
membrane ground "what was on screen AND what was said" as one instant. This organ
perceives that text -- a caption line, an .srt/.vtt cue, a transcript chunk.

It witnesses the raw-byte identity AND a CANONICAL text identity (Unicode NFC +
collapsed whitespace), so two captions that differ only in spacing/encoding form
share one canonical identity and slot into baseline memory's canonical rung. Same
honest discipline as the structured organ: canonicalisation normalises Unicode
form and insignificant whitespace ONLY -- not case, not punctuation, and certainly
not meaning. It is text identity, not comprehension.

Inert and fail-closed: subject is a path or bytes (pass caption text as bytes).
Non-UTF-8 bytes yield identity-only + UNVERIFIED, never a crash.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from ..observation import Observation, Provenance, Status, sha256_hex

_WHITESPACE = re.compile(r"\s+")


def canonical_caption(text: str) -> str:
    """Normalise a caption to its canonical form: Unicode NFC, runs of whitespace
    collapsed to a single space, leading/trailing whitespace stripped. Case and
    punctuation are preserved (they can be meaningful)."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


class CaptionOrgan:
    name = "caption-text"

    def observe(self, subject) -> list[Observation]:
        path_str, payload = self._read(subject)
        if payload is None:
            return [Observation(
                self.name, path_str, "artifact unreadable", Status.UNVERIFIED,
                Provenance.witness_bytes(path_str, b"", "low"),
                {"format": "unknown", "canonical_sha256": None, "decoded": False},
            )]

        identity = sha256_hex(payload)
        data: dict = {"identity_sha256": identity, "bytes": len(payload)}
        status = Status.PASS
        summary = "caption observed"

        try:
            # utf-8-sig strips a leading BOM (common on Windows .srt/.vtt), so a
            # BOM-prefixed caption and the plain text share one canonical identity.
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            data.update({"format": "unknown", "canonical_sha256": None,
                         "decoded": False, "decode_note": str(exc)})
            return [Observation(self.name, path_str,
                                "caption observed (identity only; not UTF-8 text)",
                                Status.UNVERIFIED,
                                Provenance.witness_bytes(path_str, payload, "high"), data)]

        canonical = canonical_caption(text)
        data.update({
            "format": "text",
            "canonical_sha256": sha256_hex(canonical.encode("utf-8")),
            "char_count": len(text),
            "word_count": len(canonical.split()) if canonical else 0,
            "decoded": True,
        })
        return [Observation(self.name, path_str, summary, status,
                            Provenance.witness_bytes(path_str, payload, "high"), data)]

    @staticmethod
    def _read(subject) -> tuple[str, bytes | None]:
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
            return repr(subject)[:64], None
        try:
            return str(path), path.read_bytes()
        except (OSError, ValueError):
            return str(path), None

    # --- selftest ---------------------------------------------------------

    def selftest(self):
        from ..organ import Check, SelftestResult
        checks: list[Check] = []
        base = "Hello,  world!\n".encode("utf-8")
        reformatted = "  Hello, world!  ".encode("utf-8")  # same text, different whitespace
        changed = "Hello, there!".encode("utf-8")
        invalid = b"\xff\xfe not utf-8 \x80"

        ob = self.observe(base)[0]
        orf = self.observe(reformatted)[0]
        och = self.observe(changed)[0]
        oinv = self.observe(invalid)[0]

        checks.append(Check(
            "canonical equal for whitespace-different captions",
            ob.data.get("canonical_sha256") == orf.data.get("canonical_sha256")
            and ob.data.get("identity_sha256") != orf.data.get("identity_sha256"),
        ))
        checks.append(Check("canonical differs on a changed caption",
                            ob.data.get("canonical_sha256") != och.data.get("canonical_sha256")))
        rederived = sha256_hex(base)
        checks.append(Check("identity re-derives", ob.data.get("identity_sha256") == rederived))
        checks.append(Check("provenance digest full-width",
                            ob.provenance.digest == "sha256:" + rederived and len(rederived) == 64))
        checks.append(Check("word count from canonical text", ob.data.get("word_count") == 2))
        checks.append(Check("non-UTF-8 fails closed",
                            oinv.status == Status.UNVERIFIED and oinv.data.get("canonical_sha256") is None))
        checks.append(Check("status is advisory (not authority)",
                            ob.status in {Status.PASS, Status.WARN, Status.UNVERIFIED,
                                          Status.NEEDS_HUMAN, Status.BLOCK}))
        return SelftestResult(self.name, checks)
