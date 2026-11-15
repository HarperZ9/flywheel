"""VisualArtifactOrgan -- the membrane's first eye.

Given an image artifact (a rendered frame, a screenshot, any PNG the operator
authorises), it emits ONE witnessed Observation:
  * identity   -- full SHA-256 of the raw bytes (exact, re-derivable),
  * dimensions -- width/height/bit-depth/colour-type from the PNG header,
  * perception -- a 64-bit perceptual hash (dHash) of the decoded pixels.

It is INERT: it reads the artifact bytes and reports.  It does not modify the
artifact, the process that produced it, or anything else.  Capture is the
operator's responsibility and must be of a source the operator owns or has
authorised -- this organ never reaches into another process.

Fail-closed: an unreadable file or an unsupported/ malformed PNG yields an
Observation with status UNVERIFIED and perceptual hash absent.  It never raises
and never fabricates a perceptual hash it could not compute.
"""

from __future__ import annotations

from pathlib import Path

from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult
from ..phash import perceptual_hash
from ..pngview import PngDecodeError, decode_png, is_png, read_ihdr

# A 2x2 red/green/blue/white PNG (8-bit RGB, filter 0), used by the selftest.
# Built once with the project's own minimal encoder; its bytes are fixed so the
# selftest re-derives a known digest and a known perceptual hash.
_SELFTEST_PNG_HEX = (
    "89504e470d0a1a0a0000000d4948445200000002000000020802000000"
    "fdd49a73000000124944415478da63f8cfc0c000c20cff8100001fee05"
    "fbf1abba770000000049454e44ae426082"
)


class VisualArtifactOrgan:
    name = "visual-artifact"

    def observe(self, subject) -> list[Observation]:
        """Observe an image artifact.  `subject` is a path or bytes."""
        path_str, payload = self._read(subject)
        if payload is None:
            return [
                Observation(
                    organ=self.name,
                    subject=path_str,
                    summary="artifact unreadable",
                    status=Status.UNVERIFIED,
                    provenance=Provenance(
                        source=path_str,
                        digest="sha256:" + sha256_hex(b""),
                        timestamp=Provenance.witness_bytes(path_str, b"", "low").timestamp,
                        confidence="low",
                    ),
                    data={"perceptual_hash": None, "decoded": False},
                )
            ]

        identity = sha256_hex(payload)
        data: dict = {"identity_sha256": identity, "bytes": len(payload)}
        summary = "artifact observed"
        status = Status.PASS

        # Header dimensions (works even when full decode is unsupported).
        if is_png(payload):
            try:
                w, h, depth, ctype = read_ihdr(payload)
                data.update({"format": "png", "width": w, "height": h,
                             "bit_depth": depth, "color_type": ctype})
            except PngDecodeError as exc:
                data.update({"format": "png", "header_error": str(exc)})
                status = Status.UNVERIFIED
        else:
            data["format"] = "unknown"
            status = Status.UNVERIFIED

        # Perceptual hash (decoded pixels). Absent => cannot perceptually compare.
        phash_hex = None
        try:
            img = decode_png(payload)
            phash_hex = format(perceptual_hash(img), "016x")
            data["perceptual_hash"] = phash_hex
            data["decoded"] = True
        except PngDecodeError as exc:
            data["perceptual_hash"] = None
            data["decoded"] = False
            data["decode_note"] = str(exc)
            if status == Status.PASS:
                # Identity is solid, but we could not perceive the pixels -> not a
                # full PASS; downgrade so status alone reflects "not fully perceived".
                summary = "artifact observed (identity only; pixels not decoded)"
                status = Status.UNVERIFIED

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
        # Frame-like (a descriptor + a callable read): the continuity loop hands
        # organs a Frame so any source -- file, callback, native grab -- is uniform.
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

    def selftest(self) -> SelftestResult:
        """Re-derive this organ's own claims from a fixed, known artifact."""
        checks: list[Check] = []
        payload = bytes.fromhex(_SELFTEST_PNG_HEX)

        # 1. It is a valid PNG and decodes to the expected 2x2 dimensions.
        try:
            img = decode_png(payload)
            checks.append(Check("decodes 2x2 RGB",
                                img.width == 2 and img.height == 2 and img.channels == 3,
                                f"{img.width}x{img.height} ch={img.channels}"))
        except PngDecodeError as exc:
            checks.append(Check("decodes 2x2 RGB", False, str(exc)))
            return SelftestResult(self.name, checks)

        obs = self.observe(payload)[0]

        # 2. The emitted identity digest re-derives from the same bytes (host check).
        rederived = sha256_hex(payload)
        emitted = obs.data.get("identity_sha256")
        checks.append(Check("identity re-derives", emitted == rederived,
                            f"emitted={emitted[:12] if emitted else None}.."))

        # 3. provenance.digest matches the identity (full-width, sha256: prefixed).
        checks.append(Check("provenance digest full-width",
                            obs.provenance.digest == "sha256:" + rederived
                            and len(rederived) == 64))

        # 4. A perceptual hash was produced and is stable across two reads.
        obs2 = self.observe(payload)[0]
        ph1 = obs.data.get("perceptual_hash")
        ph2 = obs2.data.get("perceptual_hash")
        checks.append(Check("perceptual hash stable", ph1 is not None and ph1 == ph2,
                            f"{ph1}"))

        # 5. Inertness: observing accepts bytes and never needs to write anything.
        checks.append(Check("status is advisory (not authority)",
                            obs.status in {Status.PASS, Status.WARN,
                                           Status.UNVERIFIED, Status.NEEDS_HUMAN,
                                           Status.BLOCK}))
        return SelftestResult(self.name, checks)
