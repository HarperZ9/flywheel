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
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA = "flywheel.web-snapshot/v1"
_TIMEOUT = 60
_MAX_BYTES = 25_000_000


def _ip_blocked(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True   # unresolvable is refused, not guessed
    return (ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _guard_url(url: str) -> "str | None":
    """Refuse SSRF before any connection: only http(s), and every address
    the host resolves to must be a global (public) address. Returns a
    named reason to block, or None to allow. The scaffold freezes URLs
    from any prompt, so the gateway must never be steered at loopback,
    private, or cloud-metadata endpoints."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as e:
        return f"blocked: unparseable url ({e})"
    if parts.scheme not in ("http", "https"):
        return f"blocked: scheme {parts.scheme!r} is not http(s)"
    host = parts.hostname
    if not host:
        return "blocked: no host"
    try:
        infos = socket.getaddrinfo(host, parts.port or (
            443 if parts.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        return f"blocked: host does not resolve ({e})"
    for info in infos:
        if _ip_blocked(info[4][0]):
            return (f"blocked: {host} resolves to {info[4][0]}, which is "
                    "not a global address")
    return None


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        reason = _guard_url(newurl)
        if reason:
            raise urllib.error.HTTPError(newurl, code, reason, headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str) -> tuple:
    reason = _guard_url(url)
    if reason:
        raise ValueError(reason)
    opener = urllib.request.build_opener(_GuardedRedirect())
    req = urllib.request.Request(url, headers={
        "User-Agent": "flywheel-gather/1.0 (+receipted research intake)"})
    with opener.open(req, timeout=_TIMEOUT) as r:
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
    # accumulate observed origins: two URLs serving identical bytes share
    # the hash, and the sidecar must keep BOTH origins, not clobber the first
    sidecar = dest / f"{sha}.json"
    observed = []
    if sidecar.exists():
        try:
            prior = json.loads(sidecar.read_text(encoding="utf-8"))
            observed = list(prior.get("observed_urls", []))
        except Exception:
            observed = []
    if url not in observed:
        observed.append(url)
    doc = {"schema": SCHEMA, "url": url, "final_url": final_url,
           "sha256": sha, "bytes": len(body),
           "content_type": str(headers.get("Content-Type", "")).split(";")[0],
           "path": str(blob), "observed_urls": observed,
           "note": "the hash IS the receipt: any quotation from this "
                   "source is re-checkable against these bytes offline"}
    sidecar.write_text(
        json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    return doc
