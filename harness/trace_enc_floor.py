"""Floor and prefix rules: encryption never silently goes backwards (7.3, SP-08).

Once a store holds one encrypted item, a marker
`state/keys/v1/owners/<owner>/<store>.floor` exists and a plaintext write to
that store fails with ENC_REQUIRED, for example after a reinstall without the
key store. Same-user code can delete the marker; it guards against accident,
not against the owner's own processes (design 3.5).

Within one item, a plaintext prefix followed by encrypted files is valid, so a
trace begun before the upgrade keeps reading and its new records are
encrypted. An encrypted file followed by a plaintext one is refused as a
downgrade (ENC_DOWNGRADE).
"""
from __future__ import annotations

from pathlib import Path

from .trace_enc import EncError, is_encrypted


def floor_path(state_root, owner_ref: str, store: str) -> Path:
    return Path(state_root) / "keys" / "v1" / "owners" / owner_ref / f"{store}.floor"


def has_floor(state_root, owner_ref: str, store: str) -> bool:
    return floor_path(state_root, owner_ref, store).exists()


def set_floor(state_root, owner_ref: str, store: str) -> None:
    path = floor_path(state_root, owner_ref, store)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"flywheel.encryption-floor/v1\n")


def floors(state_root) -> dict[str, bool]:
    """Every store with a floor, for any owner under this state root."""
    base = Path(state_root) / "keys" / "v1" / "owners"
    found = sorted(base.glob("*/*.floor")) if base.is_dir() else []
    return {path.stem: True for path in found}


class PrefixCheck:
    """Feed each file of one item in order; refuses encrypted-then-plaintext."""

    def __init__(self) -> None:
        self.seen_encrypted = False

    def reset(self) -> None:
        self.seen_encrypted = False

    def feed(self, blob: bytes) -> bool:
        encrypted = is_encrypted(blob)
        if self.seen_encrypted and not encrypted:
            raise EncError("ENC_DOWNGRADE")
        self.seen_encrypted = self.seen_encrypted or encrypted
        return encrypted
