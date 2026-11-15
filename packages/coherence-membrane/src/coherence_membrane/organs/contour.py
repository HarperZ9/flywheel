"""ContourViewOrgan -- witnessed vector (marching-squares) perception of a PNG."""
from __future__ import annotations

from pathlib import Path

from ..geometry_encode import to_coords, to_svg
from ..geometry_ops import contour, simplify_geometry, stitch
from ..lowering import field_from_png
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult
from ..pngencode import encode_png
from ..pngview import PngDecodeError


class ContourViewOrgan:
    name = "contour-view"

    def __init__(self, level: float = 0.5, epsilon: float = 1.0):
        if not 0.0 <= level <= 1.0:
            raise ValueError("level must be in [0,1] for a luminance contour")
        if epsilon < 0:
            raise ValueError("epsilon must be >= 0")
        self.level = level
        self.epsilon = epsilon

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
            field = field_from_png(payload)
        except PngDecodeError as exc:
            return [Observation(
                self.name, source, "artifact not decodable (identity only)",
                Status.UNVERIFIED,
                Provenance.witness_bytes(source, payload, "low"),
                {"identity_sha256": identity, "reason": f"undecodable: {exc}"},
            )]
        geom = simplify_geometry(stitch(contour(field, self.level)), self.epsilon)
        return [Observation(
            self.name, source, "artifact observed (marching-squares vector view)",
            Status.PASS,
            Provenance.witness_bytes(source, payload, "high"),
            {
                "format": "png",
                "algo": "marching-squares-v1",
                "identity_sha256": identity,
                "svg": to_svg(geom),
                "coords": to_coords(geom),
                "path_count": len(geom.paths),
                "unknown_cells": len(geom.unknown),
            },
        )]

    def _make_png(self) -> bytes:
        """Deterministic 16x16: left half dark, right half bright (one edge)."""
        w = h = 16
        px = bytearray()
        for y in range(h):
            for x in range(w):
                v = 0 if x < w // 2 else 255
                px += bytes([v, v, v])
        return encode_png(w, h, bytes(px), channels=3)

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        payload = self._make_png()
        obs = self.observe(payload)[0]
        checks.append(Check(
            "emits a contour vector",
            obs.status == Status.PASS and obs.data.get("path_count", 0) >= 1
            and "<path" in obs.data.get("svg", ""),
            obs.data.get("coords", "")[:32],
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
