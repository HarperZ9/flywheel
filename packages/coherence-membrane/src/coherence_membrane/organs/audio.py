"""AudioArtifactOrgan -- the membrane's second sense: hearing.

Given an audio artifact (a WAV the operator owns or has authorised), it emits ONE
witnessed Observation:
  * identity   -- full SHA-256 of the raw bytes (exact, re-derivable),
  * format     -- channels, sample rate, frame count, duration, sample width,
  * perception -- a 64-bit perceptual fingerprint of the loudness envelope over
                 time (a coarse "shape of the sound", dHash-style).

Inert and fail-closed, exactly like the visual organ: it reads bytes and reports;
it never plays, transcodes, or mutates anything; a non-WAV or unsupported sample
width yields identity-only + UNVERIFIED, never a crash and never a fabricated
fingerprint.

Honesty: the fingerprint is a coarse amplitude-envelope hash (is the loudness
shape the same?), NOT acoustic content recognition. Distance is advisory evidence
of "the sound changed", not of "the meaning changed".  Stdlib only (`wave`,
`array`) -- no third-party audio stack in the trust path.
"""

from __future__ import annotations

import io
import wave
from array import array

from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult

# Envelope fingerprint: BUCKETS buckets -> BUCKETS-1 adjacent comparisons = 64 bits.
BUCKETS = 65


def _mono_int16(frames: bytes, channels: int) -> list[int]:
    """Decode 16-bit PCM frame bytes to a mono int sequence (channels averaged)."""
    samples = array("h")
    samples.frombytes(frames[: (len(frames) // 2) * 2])
    if channels <= 1:
        return list(samples)
    mono: list[int] = []
    for i in range(0, len(samples) - channels + 1, channels):
        mono.append(sum(samples[i : i + channels]) // channels)
    return mono


def audio_envelope_hash(samples: list[int]) -> int:
    """64-bit fingerprint of the loudness envelope (dHash over amplitude buckets)."""
    n = len(samples)
    if n == 0:
        return 0
    env = []
    for b in range(BUCKETS):
        lo = (b * n) // BUCKETS
        hi = max(lo + 1, ((b + 1) * n) // BUCKETS)
        seg = samples[lo:hi]
        env.append(sum(abs(s) for s in seg) // len(seg) if seg else 0)
    bits = 0
    for i in range(BUCKETS - 1):
        bits = (bits << 1) | (1 if env[i] > env[i + 1] else 0)
    return bits


class AudioArtifactOrgan:
    name = "audio-artifact"

    def observe(self, subject) -> list[Observation]:
        path_str, payload = self._read(subject)
        if payload is None:
            return [self._unreadable(path_str)]

        identity = sha256_hex(payload)
        data: dict = {"identity_sha256": identity, "bytes": len(payload)}
        status = Status.PASS
        summary = "audio observed"
        fingerprint = None

        try:
            with wave.open(io.BytesIO(payload), "rb") as w:
                channels = w.getnchannels()
                sampwidth = w.getsampwidth()
                rate = w.getframerate()
                nframes = w.getnframes()
                raw = w.readframes(nframes)
            data.update({
                "format": "wav", "channels": channels, "sample_rate": rate,
                "frames": nframes, "sample_width": sampwidth,
                "duration_s": round(nframes / rate, 6) if rate else None,
            })
            if sampwidth == 2:
                samples = _mono_int16(raw, channels)
                fingerprint = format(audio_envelope_hash(samples), "016x")
                data["perceptual_audio_hash"] = fingerprint
                data["decoded"] = True
            else:
                # Honest: only 16-bit PCM is perceptually hashed for now.
                data["perceptual_audio_hash"] = None
                data["decoded"] = False
                data["decode_note"] = f"unsupported sample width {sampwidth} (only 16-bit PCM)"
                status = Status.UNVERIFIED
                summary = "audio observed (identity only; samples not hashed)"
        except (wave.Error, EOFError, ValueError) as exc:
            data.update({"format": "unknown", "perceptual_audio_hash": None,
                         "decoded": False, "decode_note": str(exc)})
            status = Status.UNVERIFIED
            summary = "audio observed (identity only; not a supported WAV)"

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
    def _read(subject):
        # Frame-like (descriptor + callable read): read its bytes and perceive
        # them like any other bytes (a WAV carried in a frame is still hashed;
        # anything else degrades to identity-only) -- never crash on Path(frame).
        # Keeps all_organs() total over any subject.
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
        from pathlib import Path

        try:
            p = Path(subject)
        except (TypeError, ValueError, OSError):
            return repr(subject)[:64], None
        try:
            return str(p), p.read_bytes()
        except (OSError, ValueError):
            return str(p), None

    def _unreadable(self, path_str: str) -> Observation:
        return Observation(
            organ=self.name,
            subject=path_str,
            summary="artifact unreadable",
            status=Status.UNVERIFIED,
            provenance=Provenance.witness_bytes(path_str, b"", "low"),
            data={"perceptual_audio_hash": None, "decoded": False},
        )

    # --- selftest ---------------------------------------------------------

    @staticmethod
    def _make_wav() -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            # A deterministic rising-then-falling envelope.
            samples = array("h", [((i % 200) - 100) * 100 for i in range(1600)])
            w.writeframes(samples.tobytes())
        return buf.getvalue()

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        payload = self._make_wav()
        obs = self.observe(payload)[0]

        checks.append(Check("decodes 16-bit WAV", obs.data.get("decoded") is True,
                            f"sw={obs.data.get('sample_width')} rate={obs.data.get('sample_rate')}"))
        rederived = sha256_hex(payload)
        checks.append(Check("identity re-derives",
                            obs.data.get("identity_sha256") == rederived))
        checks.append(Check("provenance digest full-width",
                            obs.provenance.digest == "sha256:" + rederived and len(rederived) == 64))
        obs2 = self.observe(payload)[0]
        ph1 = obs.data.get("perceptual_audio_hash")
        ph2 = obs2.data.get("perceptual_audio_hash")
        checks.append(Check("perceptual fingerprint stable", ph1 is not None and ph1 == ph2,
                            f"{ph1}"))
        checks.append(Check("status is advisory (not authority)",
                            obs.status in {Status.PASS, Status.WARN, Status.UNVERIFIED,
                                           Status.NEEDS_HUMAN, Status.BLOCK}))
        return SelftestResult(self.name, checks)
