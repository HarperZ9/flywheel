"""BrailleViewOrgan -- witnessed 'negatives -> braille' perception of a PNG."""
from __future__ import annotations

from pathlib import Path

from ..braille import braille_text, sparse_braille
from ..lowering import field_from_png
from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult
from ..pngencode import encode_png
from ..pngview import PngDecodeError


class BrailleViewOrgan:
    name = "braille-view"

    def __init__(self, cols: int = 64, rows: int | None = None):
        if cols <= 0:
            raise ValueError("cols must be positive")
        if rows is not None and rows <= 0:
            raise ValueError("rows must be positive")
        self.cols = cols
        self.rows = rows

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
        view = sparse_braille(field, cols=self.cols, rows=self.rows)
        unknown_cells = sum(1 for u in field.unknown if u)
        return [Observation(
            self.name, source, "artifact observed (braille negative-space view)",
            Status.PASS,
            Provenance.witness_bytes(source, payload, "high"),
            {
                "format": "png",
                "identity_sha256": identity,
                "braille": braille_text(view),
                "glyph_rows": len(view),
                "glyph_cols": len(view[0]) if view else 0,
                "source_unknown_cells": unknown_cells,
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
            "emits a braille view",
            obs.status == Status.PASS and bool(obs.data.get("braille")),
            obs.data.get("braille", "")[:32],
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
