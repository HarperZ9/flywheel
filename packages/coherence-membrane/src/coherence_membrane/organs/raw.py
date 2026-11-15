"""RawFrameOrgan -- sight on the high-rate fast path.

The VisualArtifactOrgan perceives an *encoded* image (a PNG): it decodes, then
hashes.  At high capture rates the encode/decode round-trip is pure overhead --
the OS already handed us raw pixels.  This organ perceives those raw pixels
directly: it witnesses the identity of the raw bytes and computes the perceptual
hash straight from them, with NO PNG encode and NO decode.

It emits the SAME Observation shape as the visual organ (identity_sha256, width,
height, format, perceptual_hash), so baseline memory, the gate bridge, and the
continuity loop all consume it unchanged.  Its subject is a `Frame` (raw bytes
plus a descriptor carrying width/height/pixel_format) -- raw bytes with no
geometry are not perceivable, and the organ says so honestly rather than
guessing dimensions.

Two honesty notes:
  * The raw identity (sha256 of BGRA bytes) is NOT equal to the PNG identity for
    the same pixels -- different byte streams.  Only the perceptual fingerprint is
    cross-comparable between the raw and PNG paths.  That equality is exactly what
    the selftest proves: the fast path changes the cost, never the answer.
  * Same modality as the eye, not a new sense -- a different intake for sight.

Inert and fail-closed like every organ: it reads bytes and reports; it never
mutates anything; a missing descriptor, unknown format, or short buffer yields
identity-only + UNVERIFIED, never a crash and never a fabricated hash.
"""

from __future__ import annotations

from ..capture import Frame, FrameDescriptor
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult
from ..phash import perceptual_hash, perceptual_hash_raw, raw_channels
from ..pngencode import bgra_to_rgb, encode_png
from ..pngview import decode_png


class RawFrameOrgan:
    name = "raw-frame"

    def observe(self, subject) -> list[Observation]:
        """Observe a raw-pixel Frame.  Non-Frame subjects (a path, loose bytes)
        carry no geometry, so this organ can perceive nothing about them and
        returns [] -- sight on raw pixels needs to know the shape of the buffer."""
        info = self._read_frame(subject)
        if info is None:
            return []
        subject_str, payload, width, height, fmt = info

        identity = sha256_hex(payload)
        data: dict = {
            "identity_sha256": identity,
            "bytes": len(payload),
            "format": fmt,
            "width": width,
            "height": height,
        }
        provenance = Provenance.witness_bytes(subject_str, payload, "high")

        ch = raw_channels(fmt)
        # None checks must precede the comparisons (short-circuit) so a missing
        # dimension never reaches `<= 0` as a TypeError.  Zero/negative dims are
        # as unperceivable as missing ones -- fail closed, never crash.
        if width is None or height is None or ch is None or width <= 0 or height <= 0:
            data.update({"perceptual_hash": None, "decoded": False,
                         "decode_note": "raw frame lacks valid width/height or a known pixel_format"})
            return [Observation(self.name, subject_str,
                                "raw frame observed (identity only; geometry/format unknown)",
                                Status.UNVERIFIED, provenance, data)]

        needed = width * height * ch
        if len(payload) < needed:
            data.update({"perceptual_hash": None, "decoded": False,
                         "decode_note": f"buffer {len(payload)}B < width*height*channels ({needed}B)"})
            return [Observation(self.name, subject_str,
                                "raw frame observed (identity only; buffer too small to perceive)",
                                Status.UNVERIFIED, provenance, data)]

        phash_hex = format(perceptual_hash_raw(payload, width, height, fmt), "016x")
        data.update({"perceptual_hash": phash_hex, "decoded": True})
        return [Observation(self.name, subject_str, "raw frame observed",
                            Status.PASS, provenance, data)]

    @staticmethod
    def _read_frame(subject):
        """Return (subject_str, payload, width, height, pixel_format) for a
        Frame-like subject, else None.  Duck-typed on the Frame contract
        (a `descriptor` plus a callable `read`)."""
        descriptor = getattr(subject, "descriptor", None)
        reader = getattr(subject, "read", None)
        if descriptor is None or not callable(reader):
            return None
        try:
            payload = reader()
        except Exception:
            payload = b""
        sid = f"{getattr(descriptor, 'source_id', '?')}#{getattr(descriptor, 'frame_index', '?')}"
        return (sid, payload, getattr(descriptor, "width", None),
                getattr(descriptor, "height", None), getattr(descriptor, "pixel_format", None))

    # --- selftest ---------------------------------------------------------

    @staticmethod
    def _make_frame(width: int, height: int) -> tuple[Frame, bytes]:
        """A deterministic BGRA frame whose channels have DIFFERENT horizontal
        profiles, on purpose.

        R (byte 2) is a centre-peak "tent" -- non-monotonic, so the dHash is
        non-trivial (not all-zeros) -- and B (byte 0) is a left-to-right ramp.
        Because R and B differ horizontally, swapping them (the exact mistake a
        wrong _RAW_LAYOUTS entry would make) changes the luma profile and so the
        hash.  That is what makes the cross-path equality check AND the byte-order
        check below actually bite, rather than passing vacuously on a symmetric
        pattern.  (A symmetric tent would survive an R<->B swap unchanged.)
        """
        cx = (width - 1) / 2 if width > 1 else 0.0
        bgra = bytearray()
        for _y in range(height):
            for x in range(width):
                r = int(255 * (1 - abs(x - cx) / cx)) if cx else 0  # tent: peak centre
                b = (x * 255) // (width - 1) if width > 1 else 0     # ramp: differs from R
                bgra += bytes([b, 64, r, 255])  # B, G, R, A
        payload = bytes(bgra)
        frame = Frame(
            descriptor=FrameDescriptor(source_id="selftest", frame_index=0,
                                       width=width, height=height, pixel_format="bgra"),
            payload=payload,
        )
        return frame, payload

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        w, h = 9, 8
        frame, payload = self._make_frame(w, h)
        obs = self.observe(frame)[0]

        checks.append(Check("perceives raw BGRA", obs.data.get("decoded") is True,
                            f"{obs.data.get('width')}x{obs.data.get('height')} fmt={obs.data.get('format')}"))
        rederived = sha256_hex(payload)
        checks.append(Check("identity re-derives", obs.data.get("identity_sha256") == rederived))
        checks.append(Check("provenance digest full-width",
                            obs.provenance.digest == "sha256:" + rederived and len(rederived) == 64))

        obs2 = self.observe(frame)[0]
        ph1 = obs.data.get("perceptual_hash")
        ph2 = obs2.data.get("perceptual_hash")
        checks.append(Check("perceptual hash stable", ph1 is not None and ph1 == ph2, f"{ph1}"))

        # The load-bearing check: the raw fast path produces the SAME perceptual
        # hash as the encode->decode path for the same pixels.  If this fails, the
        # fast path is changing the answer, not just the cost -- net-negative.
        rgb = bgra_to_rgb(payload, w, h)
        png_ph = format(perceptual_hash(decode_png(encode_png(w, h, rgb, channels=3))), "016x")
        checks.append(Check("raw fast-path hash equals PNG-path hash", ph1 == png_ph,
                            f"raw={ph1} png={png_ph}"))

        # ...and that equality is not vacuous: byte order genuinely matters.
        # Reading the SAME bytes with R<->B swapped (as 'rgba') yields a DIFFERENT
        # hash, so a wrong _RAW_LAYOUTS entry would be caught by the check above.
        swapped = format(perceptual_hash_raw(payload, w, h, "rgba"), "016x")
        checks.append(Check("perceptual hash is byte-order sensitive", swapped != ph1,
                            f"bgra={ph1} rgba={swapped}"))

        # Honest degradation: a frame with no geometry is identity-only, never a guess.
        no_geom = Frame(descriptor=FrameDescriptor(source_id="selftest", frame_index=1,
                                                   pixel_format="bgra"), payload=payload)
        degraded = self.observe(no_geom)[0]
        checks.append(Check("fails closed without geometry",
                            degraded.status == Status.UNVERIFIED
                            and degraded.data.get("perceptual_hash") is None))

        checks.append(Check("status is advisory (not authority)",
                            obs.status in {Status.PASS, Status.WARN, Status.UNVERIFIED,
                                           Status.NEEDS_HUMAN, Status.BLOCK}))
        return SelftestResult(self.name, checks)
