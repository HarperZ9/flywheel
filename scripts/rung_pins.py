#!/usr/bin/env python3
"""rung_pins.py -- read the ladder's pins out of the FROZEN preregistration.

This is the "what did we promise" half of the rung check; `verify_rung_digests.py`
is the "what do we actually have" half. Separating them keeps one honest job per
file: this module never looks at a model store, and it is the only place that
decides where a pin comes from.

The pins are read from the hashed document rather than transcribed into code. A
pin copied into a Python dict would be a second place to go stale, and the whole
value of a preregistration is that its contents cannot quietly change after the
fact. So this module recomputes the prereg's sha256 first and refuses to hand out
any pin if the bytes no longer match `artifacts/prereg/FREEZE.json`.

Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FREEZE = REPO / "artifacts" / "prereg" / "FREEZE.json"

BLOB_PIN = re.compile(r"^sha256-[0-9a-f]{64}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class FreezeMismatch(RuntimeError):
    """The prereg bytes no longer hash to the frozen value."""


def blob_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def frozen_prereg(repo: Path, freeze: Path | None = None) -> tuple[str, dict]:
    """Return (prereg text, freeze record), having confirmed the bytes match.

    The freeze recorded "sha256 of the git blob content (LF)", so the bytes are
    normalized to LF before hashing. That makes the check platform-stable: a
    CRLF checkout on Windows hashes to the same value as the committed blob.
    """
    record = json.loads((freeze or FREEZE).read_text(encoding="utf-8"))
    path = repo / record["prereg_path"]
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    got = blob_sha256(raw)
    want = record["frozen_sha256"]
    if got != want:
        raise FreezeMismatch(
            f"{record['prereg_path']} hashes to {got}, freeze says {want}. "
            "The preregistration has been edited since it was frozen; the pins "
            "in it are no longer the pins that were committed to."
        )
    return raw.decode("utf-8"), record


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _first_code(cell: str) -> str:
    m = re.search(r"`([^`]+)`", cell)
    return m.group(1) if m else ""


def parse_pins(text: str) -> dict[str, dict]:
    """Pull the rung tables out of the prereg.

    Tables are identified by their header cells, not by position, so inserting
    prose or reordering sections does not silently drop a table. A rung that
    appears in no table is not checked; a rung that appears twice is an error,
    since two pins for one rung means the document contradicts itself.
    """
    pins: dict[str, dict] = {}
    kind = None
    for line in text.splitlines():
        if not line.startswith("|"):
            kind = None
            continue
        cells = _cells(line)
        head = [c.lower() for c in cells]
        if head[:1] == ["rung"]:
            if "blob digest" in head:
                kind = "blob"
            elif "manifest sha256" in head:
                kind = "manifest"
            elif "weight sha256" in head:
                kind = "weight"
            else:
                kind = None
            continue
        if kind is None or set("".join(cells)) <= set("-: "):
            continue
        rung = cells[0]
        if not re.fullmatch(r"R\d+", rung):
            continue
        if rung in pins:
            raise ValueError(f"{rung} is pinned twice in the prereg")
        entry = {"rung": rung, "kind": kind, "model": _first_code(cells[1])}
        if kind == "blob":
            entry["blob"] = _first_code(cells[2])
        elif kind == "manifest":
            entry["manifest_sha256"] = _first_code(cells[2])
            entry["model_layer"] = _first_code(cells[3])
            entry["size_text"] = cells[4]
        else:
            entry["weight_sha256"] = _first_code(cells[2])
            entry["bytes"] = int(cells[3].replace(",", "").strip())
        pins[rung] = entry
    return pins


def pins_in_order(pins: dict[str, dict]) -> list[dict]:
    """Rungs by id, never by size: ordering by size would invite a reader to see
    a trend across rungs where the prereg forbids computing one."""
    return [pins[r] for r in sorted(pins, key=lambda s: int(s[1:]))]
