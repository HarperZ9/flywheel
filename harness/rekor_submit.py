"""rekor_submit.py -- put one artifact's hash and signature into Sigstore's Rekor.

What goes over the wire is the `hashedrekord` entry and nothing else: the SHA-512
of the artifact, an Ed25519ph signature over it, and the PEM of the public key.
The artifact's bytes never leave the machine. `proposed_entry` builds that entry
and `assert_hash_only` refuses anything that carries more, so a later edit cannot
start uploading content by accident.

Why Ed25519ph and not the plain Ed25519 the rest of Flywheel uses: Rekor only
sees the digest, so for an Ed25519 key it checks the prehashed variant (RFC 8032
section 5.1, empty context). Same key, different signature over the same bytes.
Signing goes through libsodium (PyNaCl's `crypto_sign_ed25519ph_*`), a
constant-time implementation; the stdlib side only verifies.

No account, no OIDC login and no Fulcio certificate: the key is the identity, and
where the key is published is what binds it to a person.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from . import ed25519ph_verify, rekor_verify

ENTRIES_PATH = "/api/v1/log/entries"


class RekorError(RuntimeError):
    """The entry could not be built, submitted or fetched as asked."""


# --- the signing key ---------------------------------------------------------

def ph_signer_from_seed(seed: bytes):
    """(sign_ph(bytes) -> 64 bytes, raw public key) for a 32-byte Ed25519 seed."""
    try:
        from nacl import bindings
    except ImportError as e:
        raise RekorError("Ed25519ph signing needs pynacl (pip install pynacl); "
                         "verification does not") from e
    if len(seed) != 32:
        raise RekorError(f"an Ed25519 seed is 32 bytes, got {len(seed)}")
    public, secret = bindings.crypto_sign_seed_keypair(bytes(seed))

    def sign_ph(message: bytes) -> bytes:
        state = bindings.crypto_sign_ed25519ph_state()
        bindings.crypto_sign_ed25519ph_update(state, bytes(message))
        return bindings.crypto_sign_ed25519ph_final_create(state, secret)

    return sign_ph, bytes(public)


def load_ph_signer(path: Path, want_public_hex: str | None = None):
    """Load a key file: an OpenSSH Ed25519 private key or a hex seed.

    With `want_public_hex`, a key that derives any other public key is refused
    here, before anything is signed or sent.
    """
    data = Path(path).read_bytes()
    if b"OPENSSH PRIVATE KEY" in data:
        try:
            from cryptography.hazmat.primitives.serialization import load_ssh_private_key
            seed = load_ssh_private_key(data, password=None).private_bytes_raw()
        except Exception as e:  # noqa: BLE001 -- surfaced as a named error
            raise RekorError(f"could not load an Ed25519 key from {path}: {e}") from e
    else:
        try:
            seed = bytes.fromhex(data.decode("utf-8").strip())
        except (UnicodeDecodeError, ValueError) as e:
            raise RekorError(f"{path} is neither an OpenSSH key nor a hex seed") from e
    sign_ph, public = ph_signer_from_seed(seed)
    if want_public_hex and public.hex() != want_public_hex.lower():
        raise RekorError(f"this key derives public key {public.hex()[:16]}..., "
                         f"not the pinned {want_public_hex[:16]}...; refusing")
    return sign_ph, public


# --- the entry ---------------------------------------------------------------

def proposed_entry(artifact: bytes, sign_ph, public_key: bytes) -> dict:
    """Sign and build the hashedrekord. Checks its own signature before returning."""
    signature = sign_ph(bytes(artifact))
    if not ed25519ph_verify.verify_ph(public_key, bytes(artifact), signature):
        raise RekorError("the Ed25519ph signature does not verify under the public key")
    entry = rekor_verify.hashedrekord_entry(artifact, signature, public_key)
    assert_hash_only(entry, artifact)
    return entry


def assert_hash_only(entry: dict, artifact: bytes) -> None:
    """Refuse an entry that carries anything but a hash, a signature and a key."""
    spec = entry.get("spec") or {}
    if set(entry) != {"apiVersion", "kind", "spec"} or set(spec) != {"data", "signature"}:
        raise RekorError("the entry carries fields beyond hash, signature and key")
    if set(spec["data"]) != {"hash"} or set(spec["signature"]) != {"content", "publicKey"}:
        raise RekorError("the entry carries fields beyond hash, signature and key")
    wire = json.dumps(entry).encode()
    if len(artifact) >= 16 and (bytes(artifact) in wire
                                or base64.b64encode(bytes(artifact)) in wire):
        raise RekorError("the artifact's bytes appear in the entry; refusing")


# --- the network leg ---------------------------------------------------------

def _first(reply: bytes) -> tuple[str, dict]:
    data = json.loads(reply)
    if not isinstance(data, dict) or len(data) != 1:
        raise RekorError("Rekor returned an unexpected entry shape")
    return next(iter(data.items()))


def submit(entry: dict, request, *, base_url: str = rekor_verify.REKOR_URL) -> tuple[str, dict]:
    """POST the entry; on a duplicate, fetch the existing one. Returns (uuid, entry).

    `request(method, url, body=None) -> (status, bytes, headers)` is injected: a fake
    in tests, `urllib_request` at the terminal.
    """
    status, reply, headers = request("POST", base_url + ENTRIES_PATH,
                                     body=json.dumps(entry).encode())
    if status == 201:
        return _first(reply)
    if status == 409:
        location = (headers or {}).get("Location") or (headers or {}).get("location")
        if not location:
            raise RekorError("Rekor reports a duplicate entry but gave no location")
        return fetch(location.rsplit("/", 1)[-1], request, base_url=base_url)
    raise RekorError(f"Rekor refused the entry ({status}): {reply[:300]!r}")


def fetch(uuid: str, request, *, base_url: str = rekor_verify.REKOR_URL) -> tuple[str, dict]:
    status, reply, _ = request("GET", f"{base_url}{ENTRIES_PATH}/{uuid}")
    if status != 200:
        raise RekorError(f"Rekor could not return entry {uuid} ({status})")
    return _first(reply)


def build_record(artifact_path: str, artifact: bytes, public_key: bytes,
                 uuid: str, entry: dict) -> dict:
    """The record stored beside the artifact. Pins are named, not trusted."""
    index = entry.get("logIndex")
    return {
        "schema": rekor_verify.SCHEMA,
        "artifact": {"path": artifact_path,
                     "sha512": hashlib.sha512(artifact).hexdigest(),
                     "sha256": hashlib.sha256(artifact).hexdigest()},
        "public_key": public_key.hex(),
        "signature_scheme": "ed25519ph",
        "rekor": {"url": rekor_verify.REKOR_URL, "log_id": rekor_verify.REKOR_LOG_ID},
        "uuid": uuid,
        "log_index": index,
        "integrated_time": entry.get("integratedTime"),
        "search_url": f"https://search.sigstore.dev/?logIndex={index}",
        "entry": {k: entry[k] for k in ("body", "integratedTime", "logID",
                                        "logIndex", "verification") if k in entry},
        "does_not_prove": rekor_verify.does_not_prove(),
    }


def urllib_request(method: str, url: str, body: bytes | None = None,
                   timeout: float = 30.0):
    """The real transport: stdlib urllib. Returns (status, body, headers)."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "flywheel-anchor"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})
    except (urllib.error.URLError, OSError) as e:
        raise RekorError(f"could not reach {url}: {e}") from e
