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
proof only bounds time after `upgrade_proof` polls the calendar on the pending
message and splices the block attestation in place of that promise, typically
hours later. `build_ots` and the splice are pure and tested; the network
functions are thin and used by the CLI and a live smoke test.
"""
from __future__ import annotations

import hashlib
import secrets
import urllib.error
import urllib.request

from harness import ots_verify

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"

# The pending-attestation tag, used to locate the promise this leg replaces with
# a block. The producer depends on the verifier for the parse (`pending_target`);
# the verifier never depends on the producer, so the stranger's closure stays
# standard-library-only.
PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")

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


def _read_varuint(data: bytes, i: int):
    """Read a base-128 varuint at offset `i`; return (value, offset_after)."""
    result = shift = 0
    while True:
        b = data[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7
        if shift > 63:  # a 64-bit length never needs more; refuse the overlong form
            raise SubmitError("malformed varuint: overlong encoding")


def pending_target(ots_bytes: bytes, expected_digest: bytes):
    """The (message, calendar_uri) a pending proof's Bitcoin upgrade is keyed on.

    A calendar folds the submitted digest into an aggregation tree and puts the
    pending attestation on the tree message, not on the submitted digest. That
    message is what the calendar's `/timestamp/<hex>` endpoint answers to once the
    block lands; polling anything else, the submitted digest included, 404s
    forever. Returns None when the proof carries no pending attestation for this
    digest, so a confirmed or digest-mismatched proof has nothing to upgrade. The
    parse is the verifier's, so there is one reader of these bytes, not two.
    """
    result = ots_verify.verify(bytes(ots_bytes), bytes(expected_digest))
    pending = result.get("pending") or []
    if not pending:
        return None
    first = pending[0]
    return bytes.fromhex(first["reached"]), first["uri"]


def splice_upgrade(pending_ots: bytes, continuation: bytes) -> bytes:
    """Replace the terminal pending attestation with a calendar's continuation.

    The continuation runs from the same message the pending attestation sat on
    (the message `pending_target` returns), so it grafts on exactly where the
    promise was and keeps every operation that reached that message. Rebuilding
    the proof from the artifact digest instead would drop those operations and
    break it. Refuses a proof that does not end in one pending attestation reaching
    the end of the bytes, rather than corrupt it.
    """
    pending_ots = bytes(pending_ots)
    marker = b"\x00" + PENDING_TAG
    idx = pending_ots.rfind(marker)
    if idx < 0:
        raise SubmitError("no terminal pending attestation to splice onto")
    i = idx + len(marker)
    try:
        length, i = _read_varuint(pending_ots, i)
    except IndexError:
        raise SubmitError("malformed pending attestation length")
    if i + length != len(pending_ots):
        raise SubmitError("pending attestation is not the terminal edge")
    return pending_ots[:idx] + bytes(continuation)


def _http_get_text(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", _AGENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("ascii", "strict").strip()
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as e:
        raise SubmitError(f"{url}: {e}")


def _get_timestamp(uri: str, r_hex: str, *, timeout: float = 15.0):
    """GET a calendar's Bitcoin continuation for message `r_hex`, or None if 404.

    The calendar answers `/timestamp/<message>` with the serialized operations
    from that message down to the Bitcoin attestation once the block lands, and
    404 while the message is still pending. `r_hex` is the pending message from
    `pending_target`, not the submitted digest.
    """
    url = f"{uri}/timestamp/{r_hex}"
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


def upgrade_proof(pending_ots: bytes, expected_digest: bytes, *,
                  get=None, timeout: float = 15.0):
    """A pending proof upgraded to carry the Bitcoin block, or None if not ready.

    Polls the calendar on the pending message and, on a hit, splices the
    continuation in place of the promise (`splice_upgrade`). `get` is the poll,
    `get(uri, message_hex) -> bytes | None`, injected in tests; the CLI lets it
    default to the live HTTP fetch. Returns None when the proof has nothing to
    upgrade or the calendar has not upgraded the message yet.

    Two refusals guard the splice, because it writes over the sole pending proof.
    A proof carrying more than one pending attestation is refused: `pending_target`
    reads the first pending but `splice_upgrade` replaces the last, so on a
    multi-calendar proof the two name different branches and the graft would be
    unverifiable. And the spliced proof is re-verified before it is returned; a
    continuation that does not reach a Bitcoin attestation binding this digest (an
    error page, a calendar bug) is refused rather than returned as a proof that
    verifies to nothing. Both raise SubmitError, leaving the good pending proof for
    the caller to keep.
    """
    pending_ots = bytes(pending_ots)
    expected_digest = bytes(expected_digest)
    before = ots_verify.verify(pending_ots, expected_digest)
    pending = before.get("pending") or []
    if not pending:
        return None
    if len(pending) > 1:
        raise SubmitError(
            "proof carries more than one pending attestation; the single-branch "
            "splice would graft onto the wrong calendar, so it refuses rather than "
            "write an unverifiable proof")
    message = bytes.fromhex(pending[0]["reached"])
    uri = pending[0]["uri"]
    if get is None:
        get = lambda u, r_hex: _get_timestamp(u, r_hex, timeout=timeout)
    continuation = get(uri, message.hex())
    if continuation is None:
        return None
    spliced = splice_upgrade(pending_ots, continuation)
    after = ots_verify.verify(spliced, expected_digest)
    if after.get("file_digest") != expected_digest.hex() or not after.get("bitcoin"):
        raise SubmitError(
            "the calendar's continuation did not splice into a proof reaching a "
            "Bitcoin attestation over this digest; refusing to overwrite the good "
            "pending proof")
    return spliced


def _fetch_block_header(height: int, *, timeout: float = 15.0) -> bytes:
    """Fetch a block header by height from a public explorer (blockstream.info).

    Two GETs: the block hash for the height, then that block's raw 80-byte header.
    The header is not trusted for chain linkage (see `anchor.does_not_prove`); it
    is the input the offline proof-of-work recheck needs, and a wrong header simply
    fails that recheck rather than passing a forgery.
    """
    base = "https://blockstream.info/api"
    block_hash = _http_get_text(f"{base}/block-height/{height}", timeout)
    header_hex = _http_get_text(f"{base}/block/{block_hash}/header", timeout)
    try:
        return bytes.fromhex(header_hex)
    except ValueError as e:
        raise SubmitError(f"block {height}: explorer returned a non-hex header: {e}")


def block_header(height: int, *, fetch=None, timeout: float = 15.0) -> bytes:
    """The 80-byte header for a block height, stored so the proof verifies offline.

    A confirmed proof commits a block's merkle root; a stranger's verifier needs
    that block's header to recheck the proof of work and the merkle root with no
    network. `fetch` is injected as `fetch(height) -> bytes` in tests; the CLI
    defaults to a public explorer. Refuses a reply that is not exactly 80 bytes
    rather than store a header that cannot verify.
    """
    if fetch is None:
        fetch = lambda h: _fetch_block_header(h, timeout=timeout)
    header = fetch(height)
    if header is None or len(header) != 80:
        got = 0 if header is None else len(header)
        raise SubmitError(f"block {height}: expected an 80-byte header, got {got} bytes")
    return bytes(header)
