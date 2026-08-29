"""receipt_signer.py -- the author-side signer the verifiers deliberately omit.

`receipt_sign.py` and `tree_head.py` both take a signature "produced elsewhere"
and a public key; neither generates keys, on the stated principle that a verifier
is a stranger who must need nothing while a signer is the author who already has
tooling. This module is that tooling, and nothing in the stdlib verifier closure
imports it.

It leans on two things a signer legitimately has: `ssh-keygen` to mint the key
(an audited RNG, and the exact OpenSSH format GitHub and `ssh-keygen -Y` already
speak, so one key serves receipt signing, the tree head, and later an SSHSIG
cross-check) and `cryptography` to load that key and produce a raw Ed25519
signature. The primitive both verifier modules want is small: `bytes -> 64
signature bytes`, plus the raw 32-byte public key. That is all this exposes.

The private key lives in a file the caller owns, defaulting under the user's home
and never the repo. This module reads it into memory for the run and signs with
it. It never prints it, never returns it, and never writes it anywhere but the
path `ssh-keygen` was told to use.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .receipt import Receipt
from .receipt_sign import SignedReceipt, ed25519_attach

# A signer keeps its key outside every repo, under the user's own home.
DEFAULT_KEY_PATH = Path.home() / ".flywheel" / "keys" / "receipt-signing-ed25519"

_OPENSSH_PRIVATE_MARKER = b"-----BEGIN OPENSSH PRIVATE KEY-----"


class SigningKeyError(RuntimeError):
    """A key could not be minted, loaded, or used as an Ed25519 signer."""


@dataclass(frozen=True)
class SigningKeyInfo:
    """What a caller may see after key generation: public material only."""
    private_key_path: Path
    public_key_path: Path
    public_key_bytes: bytes
    key_id: str
    fingerprint: str  # the SHA256:... GitHub displays for the same key


def _ssh_wire_public_key(public_key_bytes: bytes) -> bytes:
    """The OpenSSH wire encoding of an ed25519 public key: two length-prefixed
    strings. This is what a fingerprint and a `.pub` line are computed over."""
    def s(b: bytes) -> bytes:
        return len(b).to_bytes(4, "big") + b
    return s(b"ssh-ed25519") + s(bytes(public_key_bytes))


def fingerprint_for(public_key_bytes: bytes) -> str:
    """The `SHA256:<base64>` fingerprint OpenSSH and GitHub show, so the operator
    can eyeball that the key here is the key uploaded there."""
    digest = hashlib.sha256(_ssh_wire_public_key(public_key_bytes)).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def key_id_for(public_key_bytes: bytes) -> str:
    """A stable, rotatable identifier bound to the key, not to a filename."""
    return "ed25519:" + hashlib.sha256(bytes(public_key_bytes)).hexdigest()[:32]


def openssh_public_line(public_key_bytes: bytes, comment: str) -> str:
    """The one-line `ssh-ed25519 AAAA... comment` a caller uploads to GitHub."""
    blob = base64.b64encode(_ssh_wire_public_key(public_key_bytes)).decode()
    tail = f" {comment}" if comment else ""
    return f"ssh-ed25519 {blob}{tail}"


def _raw_public_key_from_openssh(pub_path: Path) -> bytes:
    """Read the 32 raw public-key bytes out of an OpenSSH `.pub` line."""
    try:
        parts = pub_path.read_text(encoding="utf-8").split()
    except UnicodeDecodeError as e:
        # This read is the first step on the stranger's verify seam (_load_pub).
        # A `.pub` whose bytes are not valid utf-8 must be a named refusal, not a
        # UnicodeDecodeError that escapes -- the same never-raises contract the
        # corrupt-blob branch below already honours one step later.
        raise SigningKeyError(
            f"{pub_path} is not a utf-8 ssh-ed25519 public key: {e}") from e
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise SigningKeyError(f"{pub_path} is not an ssh-ed25519 public key")
    try:
        blob = base64.b64decode(parts[1])
    except (binascii.Error, ValueError) as e:
        # A corrupt blob raises binascii.Error (a ValueError subclass). This
        # function is a caller-supplied trust anchor on the verify path, so a bad
        # `.pub` must be a named refusal, not an uncaught crash.
        raise SigningKeyError(
            f"{pub_path} has a corrupt ssh-ed25519 key blob: {e}") from e
    # wire = s("ssh-ed25519") s(pubkey); the pubkey is the last length-prefixed
    # string and is 32 bytes for ed25519.
    name_len = int.from_bytes(blob[:4], "big")
    off = 4 + name_len
    key_len = int.from_bytes(blob[off:off + 4], "big")
    raw = blob[off + 4:off + 4 + key_len]
    if len(raw) != 32:
        raise SigningKeyError("an ed25519 public key is 32 bytes")
    return raw


def _lock_down(path: Path) -> None:
    """Best-effort restriction of the private key to the current user.

    POSIX honours chmod directly. On Windows chmod only toggles the read-only
    bit, so we also reset the ACL with icacls when it is available; a missing
    icacls is not fatal, it just leaves inherited ACLs in place.
    """
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if sys.platform.startswith("win"):
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        if user:
            try:
                subprocess.run(
                    ["icacls", str(path), "/inheritance:r",
                     "/grant:r", f"{user}:F"],
                    capture_output=True, text=True, check=False)
            except OSError:
                pass


def generate_signing_key(dest, *, comment: str,
                         overwrite: bool = False) -> SigningKeyInfo:
    """Mint a dedicated Ed25519 signing key with `ssh-keygen` at `dest`.

    ssh-keygen writes the private key to `dest` and the public key to
    `dest.pub`; with `-q` it prints neither. This function returns public
    material only. It refuses to clobber an existing key unless `overwrite`.
    """
    priv = Path(dest)
    pub = Path(str(priv) + ".pub")
    if priv.exists() and not overwrite:
        raise SigningKeyError(
            f"refusing to overwrite an existing key at {priv}; pass "
            f"overwrite=True only if you mean to retire it")
    priv.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for p in (priv, pub):
            p.unlink(missing_ok=True)
    proc = subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(priv), "-N", "",
         "-C", comment, "-q"],
        capture_output=True, text=True)
    if proc.returncode != 0 or not priv.exists() or not pub.exists():
        raise SigningKeyError(
            f"ssh-keygen failed ({proc.returncode}): {proc.stderr.strip()}")
    _lock_down(priv)
    raw_pub = _raw_public_key_from_openssh(pub)
    return SigningKeyInfo(
        private_key_path=priv, public_key_path=pub, public_key_bytes=raw_pub,
        key_id=key_id_for(raw_pub), fingerprint=fingerprint_for(raw_pub))


class SigningKey:
    """A loaded private key. Holds the secret in memory for the run and exposes
    the one primitive the verifier modules consume: sign(bytes) -> 64 bytes."""

    def __init__(self, private_key) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise SigningKeyError("not an Ed25519 private key")
        self._key = private_key
        self.public_key_bytes: bytes = private_key.public_key().public_bytes_raw()
        self.key_id: str = key_id_for(self.public_key_bytes)
        self.fingerprint: str = fingerprint_for(self.public_key_bytes)

    def sign(self, data: bytes) -> bytes:
        """Raw Ed25519 over `data`. 64 bytes, exactly what both verifiers want."""
        if not isinstance(data, (bytes, bytearray)):
            raise SigningKeyError("sign takes bytes")
        return self._key.sign(bytes(data))


def load_signing_key(path=DEFAULT_KEY_PATH) -> SigningKey:
    """Load an OpenSSH Ed25519 private key from `path` into a `SigningKey`."""
    from cryptography.hazmat.primitives.serialization import (
        load_ssh_private_key)
    data = Path(path).read_bytes()
    if _OPENSSH_PRIVATE_MARKER not in data:
        raise SigningKeyError(
            f"{path} is not an OpenSSH private key (expected one from "
            f"ssh-keygen -t ed25519)")
    try:
        key = load_ssh_private_key(data, password=None)
    except Exception as e:  # noqa: BLE001 -- surfaced as a named signer error
        raise SigningKeyError(
            f"could not load an Ed25519 private key from {path}: {e}") from e
    return SigningKey(key)


def sign_receipt(receipt: Receipt, key: SigningKey) -> SignedReceipt:
    """Sign `receipt` over its recomputed `claim_sha256`, exactly what
    `receipt_sign.verify_signed` recomputes and checks."""
    signature = key.sign(receipt.claim_sha256().encode())
    return ed25519_attach(receipt, signature, key.public_key_bytes,
                          key_id=key.key_id)
