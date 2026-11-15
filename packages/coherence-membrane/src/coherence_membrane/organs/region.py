"""RegionArtifactOrgan -- a finer-grained eye: perception with a region grid.

The VisualArtifactOrgan answers "did this image change". This answers "which part
of it changed" -- it emits the same whole-image facts (identity, dimensions,
perceptual hash, so it still slots into baseline memory and the gate) PLUS a
row-major grid of per-tile dHashes. compare_region_drift() then localises a
change to the tiles that actually moved.

Same modality as the eye, a different granularity. Inert and fail-closed exactly
like every organ: it reads bytes and reports; an unreadable file or an
unsupported/malformed PNG yields identity-only + UNVERIFIED with no region grid,
never a crash and never a fabricated hash.
"""

from __future__ import annotations

from pathlib import Path

from ..observation import Observation, Provenance, Status, sha256_hex
from ..organ import Check, SelftestResult
from ..phash import perceptual_hash
from ..pngencode import encode_png
from ..pngview import PngDecodeError, decode_png, is_png, read_ihdr
from ..region import compare_region_drift, tile_hashes

_DEFAULT_ROWS = 4
_DEFAULT_COLS = 4


class RegionArtifactOrgan:
    name = "region-visual"

    def __init__(self, rows: int = _DEFAULT_ROWS, cols: int = _DEFAULT_COLS):
        if rows <= 0 or cols <= 0:
            raise ValueError("rows and cols must be positive")
        self.rows = rows
        self.cols = cols

    def observe(self, subject) -> list[Observation]:
        """Observe an image artifact with a region grid. `subject` is a path,
        bytes, or a Frame-like (descriptor + read)."""
        path_str, payload = self._read(subject)
        if payload is None:
            return [Observation(
                self.name, path_str, "artifact unreadable", Status.UNVERIFIED,
                Provenance.witness_bytes(path_str, b"", "low"),
                {"format": "unknown", "perceptual_hash": None, "region_hashes": None,
                 "decoded": False},
            )]

        identity = sha256_hex(payload)
        data: dict = {"identity_sha256": identity, "bytes": len(payload),
                      "grid_rows": self.rows, "grid_cols": self.cols}
        status = Status.PASS
        summary = "artifact observed (region grid)"

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
            data["perceptual_hash"] = format(perceptual_hash(img), "016x")
            data["region_hashes"] = [format(t, "016x")
                                     for t in tile_hashes(img, self.rows, self.cols)]
            data["decoded"] = True
        except PngDecodeError as exc:
            data.update({"perceptual_hash": None, "region_hashes": None,
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

    def _make_png(self, *, altered_tile: int | None = None) -> bytes:
        """An RGB image sized to the grid (each tile 4x4 px) with per-tile
        horizontal structure; optionally flip exactly one tile so a localized
        change is detectable. The canvas SCALES with rows/cols so the selftest
        works for any grid (a fixed 16x16 canvas could not represent >16 tiles
        per axis and divided by zero)."""
        tile_w = tile_h = 4
        w = self.cols * tile_w
        h = self.rows * tile_h
        px = bytearray()
        for y in range(h):
            tr = y // tile_h
            for x in range(w):
                tc = x // tile_w
                idx = tr * self.cols + tc
                local = x % tile_w
                v = (local * 255) // (tile_w - 1)  # 0, 85, 170, 255 across the tile
                if altered_tile is not None and idx == altered_tile:
                    v = 255 - v  # flip this tile's horizontal gradient
                px += bytes([v, v, v])
        return encode_png(w, h, bytes(px), channels=3)

    def selftest(self) -> SelftestResult:
        checks: list[Check] = []
        payload = self._make_png()
        obs = self.observe(payload)[0]

        n = self.rows * self.cols
        region_hashes = obs.data.get("region_hashes")
        checks.append(Check("region grid has rows*cols tiles",
                            region_hashes is not None and len(region_hashes) == n,
                            f"{len(region_hashes) if region_hashes else 0} of {n}"))

        rederived = sha256_hex(payload)
        checks.append(Check("identity re-derives",
                            obs.data.get("identity_sha256") == rederived))
        checks.append(Check("provenance digest full-width",
                            obs.provenance.digest == "sha256:" + rederived
                            and len(rederived) == 64))

        obs2 = self.observe(payload)[0]
        checks.append(Check("region hashes stable",
                            obs.data.get("region_hashes") == obs2.data.get("region_hashes")))

        # The load-bearing check: a change confined to ONE tile is localized to
        # exactly that tile -- "where it changed", not just "it changed". Alter an
        # interior tile when the grid has one, so all four tile boundaries are
        # exercised (a corner tile can't catch a left/up under-read).
        interior = (self.rows // 2) * self.cols + (self.cols // 2)
        altered = self.observe(self._make_png(altered_tile=interior))[0]
        report = compare_region_drift(region_hashes, altered.data.get("region_hashes"),
                                      self.rows, self.cols)
        checks.append(Check("localized change is isolated to its tile",
                            report.verdict == "DRIFT" and report.changed_regions == [interior],
                            f"changed={report.changed_regions} (altered {interior})"))

        checks.append(Check("status is advisory (not authority)",
                            obs.status in {Status.PASS, Status.WARN, Status.UNVERIFIED,
                                           Status.NEEDS_HUMAN, Status.BLOCK}))
        return SelftestResult(self.name, checks)
