"""ColorQuantizeOrgan -- witnessed OKLab palette perception of a PNG."""
from __future__ import annotations

from pathlib import Path

from ..color_field import color_field_from_png
from ..color_quantize import palette_to_hex, quantization_error, quantize
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult
from ..pngencode import encode_png
from ..pngview import PngDecodeError


class ColorQuantizeOrgan:
    name = "color-quantize"

    def __init__(self, k: int = 16):
        if k < 1:
            raise ValueError("k must be >= 1")
        self.k = k

    def _read(self, subject) -> tuple[str, bytes]:
        if isinstance(subject, (bytes, bytearray)):
            return "<bytes>", bytes(subject)
        if isinstance(subject, Path):
            return str(subject), subject.read_bytes()
        if isinstance(subject, str):
            return subject, Path(subject).read_bytes()
        raise TypeError(f"unsupported subject: {type(subject)!r}")

    def observe(self, subject) -> list[Observation]:
        try:
            source, payload = self._read(subject)
        except (OSError, TypeError, ValueError) as exc:
            return [Observation(
                self.name, str(subject), "unreadable subject",
                Status.UNVERIFIED,
                Provenance.witness_bytes(str(subject), b"", "low"),
                {"reason": f"unreadable: {exc}"},
            )]
        identity = sha256_hex(payload)
        try:
            cf = color_field_from_png(payload)
        except PngDecodeError as exc:
            return [Observation(
                self.name, source, "artifact not decodable (identity only)",
                Status.UNVERIFIED,
                Provenance.witness_bytes(source, payload, "low"),
                {"identity_sha256": identity, "reason": f"undecodable: {exc}"},
            )]
        indices, palette = quantize(cf, self.k)
        err = quantization_error(cf, indices, palette)
        return [Observation(
            self.name, source, "artifact observed (OKLab quantized palette)",
            Status.PASS,
            Provenance.witness_bytes(source, payload, "high"),
            {
                "format": "png",
                "algo": "oklab-medcut-v1",
                "identity_sha256": identity,
                "palette_hex": list(palette_to_hex(palette)),
                "num_colors": len(palette),
                "delta_e_mean": err["mean"],
                "delta_e_max": err["max"],
                "unknown_cells": sum(1 for u in cf.unknown if u),
            },
        )]

    def _make_png(self) -> bytes:
        """Deterministic 2x2: two blacks + two whites."""
        return encode_png(2, 2, bytes([0, 0, 0, 255, 255, 255, 0, 0, 0, 255, 255, 255]), channels=3)

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        payload = self._make_png()
        obs = self.observe(payload)[0]
        checks.append(Check(
            "emits a palette",
            obs.status == Status.PASS and obs.data.get("num_colors", 0) >= 1,
            str(obs.data.get("palette_hex", "")),
        ))
        checks.append(Check(
            "identity re-derives",
            obs.data.get("identity_sha256") == sha256_hex(payload),
            obs.data.get("identity_sha256", ""),
        ))
        checks.append(Check(
            "provenance digest full-width",
            obs.provenance.digest.startswith("sha256:")
            and len(obs.provenance.digest) == len("sha256:") + 64,
            obs.provenance.digest,
        ))
        bad = self.observe(b"not a png")[0]
        checks.append(Check(
            "fail-closed on undecodable",
            bad.status == Status.UNVERIFIED
            and bad.data.get("identity_sha256") == sha256_hex(b"not a png"),
            bad.data.get("reason", ""),
        ))
        return SelftestResult(self.name, checks)
