"""URL freezing for captured turns, a separate opt-in (7.2, SP-04, N-11, S8b).

With `freeze_urls` in effect, the prompt hook sends only the URLs it found
(at most five). Before fetching, the catalog's credential rules run on each
URL; a URL with userinfo or a credential-bearing parameter is not fetched and
is counted as refused, and nothing of it is echoed. Each page is fetched by
the pinned fetcher and stored as an encrypted snapshot under
`state/capture-snapshots/v1/owners/<owner>/`. The freeze envelope (snapshot
refs, digests, counts) is kept with the pending prompt, so the Stop reuses it
and never fetches again.
"""
from __future__ import annotations

import base64
import hashlib
import secrets

from .evidence_json import canonical_bytes

MAX_URLS = 5
STORE = "S8b"


def _snapshot(store, url: str, fetched) -> dict:
    status, headers, body, final_url = fetched
    ref = "snap_" + secrets.token_hex(16)
    digest = hashlib.sha256(body).hexdigest()
    doc = {"schema": "flywheel.capture-snapshot/v1", "snap_ref": ref, "url": url,
           "final_url": final_url, "sha256": digest,
           "content_type": str(headers.get("Content-Type", "")).split(";")[0],
           "body": base64.b64encode(body).decode("ascii")}
    path = store.state / "capture-snapshots" / "v1" / "owners" / store.owner_ref / f"{ref}.enc"
    path.parent.mkdir(parents=True, exist_ok=True)
    from .trace_enc_write import ItemCipher
    cipher = ItemCipher(store.state, store.owner_ref, STORE, ref, provider=store.provider,
                        keystore=store.keystore)
    path.write_bytes(cipher.seal("record", canonical_bytes(doc)))
    return {"snap_ref": ref, "sha256": digest, "url": url}


def _waiting(store, session_ref, prompt_key):
    waiting = [(p, d) for p, d in store._pendings(session_ref) if d["state"] == "pending"
               and d["prompt_key"] == prompt_key]
    return waiting[-1] if waiting else (None, None)


def _fetch_all(urls, manifest) -> list:
    """Fetch outside the custody lock; returns (url, fetched) for each page kept."""
    from . import web_fetch_pinned
    from .trace_redact import first_credential_rule
    pages = []
    for url in [u for u in urls if type(u) is str][:MAX_URLS]:
        if first_credential_rule(url) != "unclassified":
            manifest["refused"] += 1
            continue
        try:
            fetched = web_fetch_pinned.fetch_pinned(url, timeout=20, max_bytes=25_000_000)
        except (OSError, ValueError):
            fetched = None
        if not fetched or fetched[0] != 200 or len(fetched[2]) > 25_000_000:
            manifest["failed"] += 1
            continue
        pages.append((url, fetched))
    return pages


def freeze(store, client: str, session_id, prompt_key, urls) -> dict:
    """Fetch and store the URLs of the newest waiting prompt of this session.

    The fetches run without the custody lock (a slow page must not block
    capture, key writes or deletion). The snapshots and the envelope are
    written under it, and only when the same prompt record still waits."""
    from .trace_custody_lock import custody_lock
    manifest = {"frozen": 0, "refused": 0, "failed": 0, "sources": []}
    session_ref = store._session_ref(client, session_id)
    with custody_lock(store.state):
        path, _ = _waiting(store, session_ref, prompt_key)
    if path is None:
        return {**manifest, "reason": "NO_PENDING_PROMPT"}
    pages = _fetch_all(urls, manifest)
    with custody_lock(store.state):
        again, pending = _waiting(store, session_ref, prompt_key)
        if again != path:
            return {**manifest, "reason": "PROMPT_NO_LONGER_WAITING"}
        kept = [_snapshot(store, url, fetched) for url, fetched in pages]
        manifest["frozen"] = len(kept)
        manifest["sources"] = [{"url": k["url"], "sha256": k["sha256"]} for k in kept]
        envelope = {"sources": [{"snap_ref": k["snap_ref"], "sha256": k["sha256"]}
                                for k in kept],
                    "refused": manifest["refused"], "failed": manifest["failed"]}
        store._write(path, path.stem, {**pending, "freeze": envelope})
    return manifest


def _stores(home):
    from .trace_turn_store import TurnStore
    base = home / "state" / "capture-snapshots" / "v1" / "owners"
    owners = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    return [(TurnStore(home, owner), base / owner) for owner in owners]


def export_records(home) -> list[dict]:
    """Export adapter: every capture snapshot, decrypted, body in base64."""
    import json
    from pathlib import Path
    from .trace_enc_write import ItemCipher
    out = []
    for store, directory in _stores(Path(home)):
        for path in sorted(directory.glob("snap_*.enc")):
            cipher = ItemCipher(store.state, store.owner_ref, STORE, path.stem,
                                keystore=store.keystore)
            out.append(json.loads(cipher.open("record", path.read_bytes())))
    return out


def delete_all(home) -> dict:
    """Delete adapter for a whole-custody deletion: keys first, then files."""
    from pathlib import Path
    from .trace_meta_adapters import remove_tree
    removed = 0
    for store, directory in _stores(Path(home)):
        store.keystore.destroy(STORE, [p.stem for p in directory.glob("snap_*.enc")])
        removed += remove_tree(directory)
    return {"removed": removed}
