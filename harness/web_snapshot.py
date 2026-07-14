"""web_snapshot.py -- the citation, frozen. Zero-dep.

Kage (new-entrant sweep) packs deterministic byte-identical website
archives; the import for a research platform is sharper and smaller: when
gather cites a source, freeze the EXACT BYTES that were read as a
content-addressed archive. The hash is the receipt; any quotation or
extraction is re-checkable against those bytes offline, forever, even
after the page changes or dies. Same bytes, same hash, same file:
idempotent by construction. A failed fetch is a named error -- an empty
archive pretending to be evidence would be worse than none.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

SCHEMA = "flywheel.web-snapshot/v1"
_TIMEOUT = 60
_MAX_BYTES = 25_000_000


def _fetch(url: str) -> tuple:
    req = urllib.request.Request(url, headers={
        "User-Agent": "flywheel-gather/1.0 (+receipted research intake)"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        body = r.read(_MAX_BYTES + 1)
        return (r.status, dict(r.headers), body, r.geturl())


def snapshot_url(url: str, dest_dir, *, runner=None) -> dict:
    """Freeze `url` into dest_dir as <sha256>.bin plus a sidecar meta
    record. `runner(url) -> (status, headers, bytes, final_url)` is
    injectable so the falsifiers never touch the network."""
    runner = runner or _fetch
    try:
        status, headers, body, final_url = runner(url)
    except Exception as e:
        return {"error": f"fetch failed: {type(e).__name__}: {e}",
                "url": url}
    if status != 200:
        return {"error": f"fetch returned HTTP {status}", "url": url}
    if len(body) > _MAX_BYTES:
        return {"error": f"body exceeds the {_MAX_BYTES}-byte cap; "
                         "a truncated archive would be a lie", "url": url}
    sha = hashlib.sha256(body).hexdigest()
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    blob = dest / f"{sha}.bin"
    if not blob.exists():
        blob.write_bytes(body)
    doc = {"schema": SCHEMA, "url": url, "final_url": final_url,
           "sha256": sha, "bytes": len(body),
           "content_type": str(headers.get("Content-Type", "")).split(";")[0],
           "path": str(blob),
           "note": "the hash IS the receipt: any quotation from this "
                   "source is re-checkable against these bytes offline"}
    (dest / f"{sha}.json").write_text(
        json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    return doc
