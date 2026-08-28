"""anchor_submit.py -- submit a digest to OpenTimestamps calendars, build a .ots.

This is the producer's network leg. The stranger's verifier (`ots_verify.py`) is
the part that must be ours and standard-library-only; this part talks to public
calendars and is author-side, so it lives apart from the verifier closure even
though it too uses only the standard library.

Two honesties are built in. First, the calendar never sees the artifact digest:
a random 16-byte nonce is appended and re-hashed, so what is submitted is
`sha256(digest + nonce)` and the artifact stays private until the operator chooses
to reveal it. Second, a fresh submission returns a PENDING proof, which names a
calendar that promised to anchor the digest but is not yet a Bitcoin block. The
proof only bounds time after `upgrade` replaces that promise with a block
attestation, typically hours later. `build_ots` is pure and tested; the network
functions are thin and used by the CLI and a live smoke test.
"""
from __future__ import annotations

import hashlib
import secrets
import urllib.error
import urllib.request

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"

# The default Bitcoin calendars. Submitting to more than one means no single
# calendar's disappearance loses the proof.
CALENDARS = (
    "https://alice.btc.calendar.opentimestamps.org",
    "https://bob.btc.calendar.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
)

_ACCEPT = "application/vnd.opentimestamps.v1"
_AGENT = "flywheel-anchor/1"


class SubmitError(RuntimeError):
    """A calendar could not be reached or returned an error."""


def fresh_nonce() -> bytes:
    """16 random bytes, so the calendar commits a value unlinkable to the file."""
    return secrets.token_bytes(16)


def submitted_digest(digest: bytes, nonce: bytes) -> bytes:
    """What the calendar actually sees: sha256(artifact_digest + nonce)."""
    return hashlib.sha256(bytes(digest) + bytes(nonce)).digest()


def _varuint(n: int) -> bytes:
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def build_ots(digest: bytes, nonce: bytes, calendar_reply: bytes) -> bytes:
    """Assemble a detached .ots proof from a calendar's reply.

    The reply is the calendar's serialized timestamp continuing from the SUBMITTED
    digest. We prepend the path that reaches it from the artifact digest: append
    the nonce, then sha256. The result is a standalone proof `ots_verify` accepts.
    """
    digest = bytes(digest)
    if len(digest) != 32:
        raise SubmitError("artifact digest must be 32 bytes (sha256)")
    path = b"\xf0" + _varuint(len(nonce)) + bytes(nonce) + b"\x08"
    return MAGIC + b"\x01" + b"\x08" + digest + path + bytes(calendar_reply)


def _post(url: str, body: bytes, timeout: float) -> bytes:
    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Accept", _ACCEPT)
    req.add_header("User-Agent", _AGENT)
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError) as e:
        raise SubmitError(f"{url}: {e}")


def submit(digest: bytes, *, nonce: bytes = None, calendars=CALENDARS,
           timeout: float = 15.0) -> dict:
    """Submit `digest` to the calendars; return the first pending proof built.

    Returns {"ots", "submitted_hex", "nonce_hex", "calendar", "errors"}. Raises
    SubmitError only if every calendar failed. The proof is PENDING; call
    `upgrade` later to obtain the Bitcoin attestation.
    """
    nonce = fresh_nonce() if nonce is None else bytes(nonce)
    submitted = submitted_digest(digest, nonce)
    errors = []
    for url in calendars:
        try:
            reply = _post(url + "/digest", submitted, timeout)
        except SubmitError as e:
            errors.append(str(e))
            continue
        return {"ots": build_ots(digest, nonce, reply),
                "submitted_hex": submitted.hex(), "nonce_hex": nonce.hex(),
                "calendar": url, "errors": errors}
    raise SubmitError("no calendar accepted the digest: " + "; ".join(errors))


def upgrade(submitted_hex: str, *, calendar: str, timeout: float = 15.0):
    """Fetch the upgraded timestamp for a submitted digest, or None if not ready.

    A calendar answers `/timestamp/<hex>` with the Bitcoin-attested continuation
    once the digest is in a block, and 404 while it is still pending.
    """
    url = f"{calendar}/timestamp/{submitted_hex}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", _ACCEPT)
    req.add_header("User-Agent", _AGENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise SubmitError(f"{url}: {e}")
    except (urllib.error.URLError, OSError) as e:
        raise SubmitError(f"{url}: {e}")
