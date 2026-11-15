"""AsciiViewOrgan -- sight as compact, model-readable glyphs.

The same eye as VisualArtifactOrgan, but its witnessed projection is an ASCII grid
(plus the usual identity + dHash, so it still slots into baseline memory and the
gate). The ASCII view is the memory-light, in-context-readable representation; the
dHash is the graded baseline fingerprint; compare_ascii_drift gives a per-cell
"where did the glyphs change" signal.

Inert and fail-closed like every organ: an unreadable file or an unsupported PNG
yields identity-only + UNVERIFIED with no view, never a crash and never a
fabricated grid.
"""

from __future__ import annotations

from pathlib import Path

from ..ascii_view import ascii_text, ascii_view, compare_ascii_drift
from ..observation import Observation, Provenance, Status, sha256_hex
from ..phash import perceptual_hash
from ..pngview import PngDecodeError, decode_png, is_png, read_ihdr

_DEFAULT_COLS = 64


class AsciiViewOrgan:
    name = "ascii-view"

    def __init__(self, cols: int = _DEFAULT_COLS, rows: int | None = None):
        if cols <= 0:
            raise ValueError("cols must be positive")
        if rows is not None and rows <= 0:
            raise ValueError("rows must be positive")
        self.cols = cols
        self.rows = rows

    def observe(self, subject) -> list[Observation]:
        path_str, payload = self._read(subject)
        if payload is None:
            return [Observation(
                self.name, path_str, "artifact unreadable", Status.UNVERIFIED,
                Provenance.witness_bytes(path_str, b"", "low"),
                {"format": "unknown", "perceptual_hash": None, "ascii_view": None, "decoded": False},
            )]

        identity = sha256_hex(payload)
        data: dict = {"identity_sha256": identity, "bytes": len(payload)}
        status = Status.PASS
        summary = "artifact observed (ascii view)"

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

        try:
            img = decode_png(payload)
            view = ascii_view(img, self.cols, self.rows)
            data.update({
                "perceptual_hash": format(perceptual_hash(img), "016x"),
                "ascii_cols": len(view[0]) if view else 0,
                "ascii_rows": len(view),
                "ascii_view": view,
                "ascii_sha256": sha256_hex(ascii_text(view).encode("utf-8")),
                "decoded": True,
            })
        except PngDecodeError as exc:
            data.update({"perceptual_hash": None, "ascii_view": None,
                         "decoded": False, "decode_note": str(exc)})
            if status == Status.PASS:
                # identity is witnessed, but the pixels were not perceived -> not a
                # full PASS; downgrade so status alone reflects "not fully perceived".
                summary = "artifact observed (identity only; pixels not decoded)"
                status = Status.UNVERIFIED

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

    def _make_png(self, *, invert: bool = False) -> bytes:
        from ..pngencode import encode_png
        w = h = 16
        px = bytearray()
        for _y in range(h):
            for x in range(w):
                v = (x * 255) // (w - 1)
                if invert:
                    v = 255 - v
                px += bytes([v, v, v])
        return encode_png(w, h, bytes(px), channels=3)

    def selftest(self):
        from ..organ import Check, SelftestResult
        checks: list[Check] = []
        payload = self._make_png()
        obs = self.observe(payload)[0]

        view = obs.data.get("ascii_view")
        checks.append(Check("renders an ascii grid",
                            view is not None and len(view) == obs.data.get("ascii_rows")
                            and all(len(r) == obs.data.get("ascii_cols") for r in view),
                            f"{obs.data.get('ascii_rows')}x{obs.data.get('ascii_cols')}"))

        rederived = sha256_hex(payload)
        checks.append(Check("identity re-derives", obs.data.get("identity_sha256") == rederived))
        checks.append(Check("provenance digest full-width",
                            obs.provenance.digest == "sha256:" + rederived and len(rederived) == 64))

        # ascii_sha256 re-derives from the witnessed grid
        checks.append(Check("ascii digest re-derives from the grid",
                            obs.data.get("ascii_sha256") == sha256_hex(ascii_text(view).encode("utf-8"))))

        obs2 = self.observe(payload)[0]
        checks.append(Check("ascii view stable", obs.data.get("ascii_view") == obs2.data.get("ascii_view")))

        # a real visual change changes the grid (and compare_ascii_drift sees it)
        changed = self.observe(self._make_png(invert=True))[0]
        report = compare_ascii_drift(view, changed.data.get("ascii_view"))
        checks.append(Check("visual change moves the glyphs",
                            report.verdict == "DRIFT" and report.changed_cells > 0,
                            report.reason))

        checks.append(Check("status is advisory (not authority)",
                            obs.status in {Status.PASS, Status.WARN, Status.UNVERIFIED,
                                           Status.NEEDS_HUMAN, Status.BLOCK}))
        return SelftestResult(self.name, checks)
