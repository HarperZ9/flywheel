"""keys.py -- the signer's Ed25519 key, held in the signer's own home.

The seed is generated on the signer's side, written once with owner-only
permissions, and never sent anywhere. The public key sits beside it in a file
anyone may read, so the operator can pin it.

Signing uses ``cryptography`` when installed and ``pynacl`` otherwise (the
``signing`` extra). Both are constant-time Ed25519 implementations; a pure
Python signer would leak timing to a caller that can ask for many signatures.
"""
from __future__ import annotations

import os
import secrets
import stat
import sys
from pathlib import Path

SEED_NAME = "signer-ed25519.seed"
PUBLIC_NAME = "signer-ed25519.pub"


class KeyError_(RuntimeError):
    """The key could not be created, loaded or used."""


def _backend(seed: bytes):
    """Return (sign(bytes) -> 64 bytes, public key bytes)."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        sk = Ed25519PrivateKey.from_private_bytes(seed)
        pub = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return sk.sign, pub
    except ImportError:
        pass
    try:
        from nacl.signing import SigningKey
    except ImportError as exc:
        raise KeyError_("signing needs the 'signing' extra (cryptography or pynacl)") from exc
    nk = SigningKey(seed)
    return (lambda msg: nk.sign(msg).signature), bytes(nk.verify_key)


def _check_private_mode(path: Path) -> None:
    """On POSIX, refuse a seed that group or others can read."""
    if sys.platform == "win32":
        return  # the Windows setup script sets the ACL; see SEPARATE-SIGNER.md
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise KeyError_(f"{path.name} is readable by group or others "
                        f"(mode {oct(mode)}); it must be 0600")


def create(home: Path) -> bytes:
    """Create the key if absent. Returns the public key. Never overwrites."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        os.chmod(home, 0o700)
    seed_path = home / SEED_NAME
    if not seed_path.exists():
        fd = os.open(seed_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(secrets.token_bytes(32).hex())
    _, public = load(home)
    (home / PUBLIC_NAME).write_text(public.hex() + "\n", encoding="ascii")
    return public


def load(home: Path):
    """Return (sign callable, public key bytes) for the key in ``home``."""
    seed_path = Path(home) / SEED_NAME
    if not seed_path.is_file():
        raise KeyError_(f"no key at {seed_path}; run the signer's init first")
    _check_private_mode(seed_path)
    try:
        seed = bytes.fromhex(seed_path.read_text(encoding="ascii").strip())
    except ValueError as exc:
        raise KeyError_("the seed file is not hex") from exc
    if len(seed) != 32:
        raise KeyError_(f"an Ed25519 seed is 32 bytes, got {len(seed)}")
    return _backend(seed)
