"""The export manifest and README (7.5).

`manifest.json` holds the header (schema, time, Flywheel version, redaction
catalog version and mode, selection, inventory snapshot, trace heads,
lineage, redaction counts, omissions, excluded stores, what verification does
not prove), the `files` list with each file's sha256 and size, and
`root_sha256` over both. The root is computed by the same function the
standard-library verifier runs, so the two cannot disagree.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .trace_export_verify import SCHEMA, UNHASHED, root_digest

DOES_NOT_PROVE = [
    "that the export holds everything custody held: excluded stores and omissions are listed",
    "that custody recorded what really happened; only that these files are unchanged since "
    "the export was written",
    "who made the export, unless it was signed",
]


def file_entry(rel: str, data: bytes, store: str, item_ref: str | None) -> dict:
    return {"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "store": store, "item_ref": item_ref}


def build(header: dict, files: list[dict]) -> dict:
    manifest = {"schema": SCHEMA, **header, "does_not_prove": DOES_NOT_PROVE,
                "files": sorted(files, key=lambda f: f["path"])}
    manifest["root_sha256"] = root_digest(manifest)
    return manifest


def rehash(folder) -> dict:
    """Recompute every file entry and the root from the files on disk."""
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_bytes())
    for entry in manifest["files"]:
        data = (folder / entry["path"]).read_bytes()
        entry.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    manifest["root_sha256"] = root_digest(manifest)
    (folder / "manifest.json").write_bytes(json.dumps(manifest, indent=1, sort_keys=True,
                                                      ensure_ascii=False).encode("utf-8"))
    return manifest


def readme(header: dict) -> str:
    mode = header["redaction"]["mode"]
    redaction = ("Credentials were redacted" + (" and personal data too" if mode["personal"]
                                                else "; personal data was not")
                 if mode["credentials"] else "Nothing was redacted (--no-redact)")
    lines = [
        "Flywheel trace export", "",
        "What it holds: your gateway traces (stores/S1), captured turns (stores/CT), pages",
        "frozen for them (stores/S8b), imported client transcripts (stores/IM) and the",
        "deletion tombstones (tombstones.jsonl). manifest.json lists every file with its",
        "sha256, the stores left out and why, and the omissions.", "",
        "Verify it with nothing but Python:", "",
        "    python verify.py .", "",
        "MATCH means every file is the one the manifest names and each gateway trace",
        "chain re-derives. It does not prove the export is complete, that custody",
        "recorded what really happened, or who made the export.", "",
        f"Redaction: {redaction}. Placeholders read [REDACTED:<rule>:<tag>]. In a",
        "redacted export, paths under your home folder read ~.",
        "Gateway traces are unredacted, because redaction would break their chain;",
        "manifest.json lists each unredacted trace that holds a catalog hit, with counts.", "",
        "This copy is plaintext and outside Flywheel custody: deleting a trace later",
        "does not reach it. Encrypt or move it with a tool you choose.",
    ]
    return "\n".join(lines) + "\n"


__all__ = ["DOES_NOT_PROVE", "UNHASHED", "build", "file_entry", "readme", "rehash",
           "root_digest"]
