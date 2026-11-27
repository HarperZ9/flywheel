# SPDX-License-Identifier: MIT
"""Fail-closed 3f+1 BFT quorum, equivocation, Ed25519, and RFC 6962 guards."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence

BFT_LEDGER_ROOT_HEX: str = (
    "5a5ab5b24408b84df9c2e941d34e23bcb3eb3291aa09f80dec3a91bc27552b60"
)
BFT_NODES: int = 4
BFT_MIN_QUORUM: int = 3

REQUIRED_ISAS: tuple[str, ...] = (
    "x64-pe",
    "x64-elf",
    "rv64-elf",
    "aarch64-elf",
    "wasm",
)

REQUIRED_BFT_ATTACKS: tuple[str, ...] = (
    "equivocation_double_vote",
    "sub_quorum_2of4",
    "forged_ed25519_sig",
    "tampered_parent_hash",
)

_HEX_CHARS = frozenset("0123456789abcdef")


def is_strict_int(value: Any) -> bool:
    """Return True only for plain integers, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def normalize_sha256(digest: Any) -> str:
    """Strip optional sha256: prefix and validate 64 lowercase hex characters."""
    if not isinstance(digest, str):
        return ""
    raw = digest[7:] if digest.startswith("sha256:") else digest
    if len(raw) != 64:
        return ""
    low = raw.lower()
    return low if all(ch in _HEX_CHARS for ch in low) else ""


def is_sha256_hex(digest: Any) -> bool:
    """Return True when digest is a valid 64-char hex SHA-256 string."""
    return bool(normalize_sha256(digest))


def is_ed25519_sig_hex(sig: Any) -> bool:
    """Return True when sig is a valid 128-char hex Ed25519 signature."""
    if not isinstance(sig, str) or len(sig) != 128:
        return False
    return all(ch in _HEX_CHARS for ch in sig.lower())


def sha256_file(path: Path) -> str:
    """Compute streaming SHA-256 hex digest for an artifact file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def rfc6962_mth(leaves: Sequence[bytes]) -> bytes:
    """Compute RFC 6962 Merkle Tree Hash MTH(D[0:n]) over ordered leaf byte strings."""
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return hashlib.sha256(b"\x00" + leaves[0]).digest()
    k = 1 << ((n - 1).bit_length() - 1)
    return hashlib.sha256(b"\x01" + rfc6962_mth(leaves[:k]) + rfc6962_mth(leaves[k:])).digest()


def check_bft_quorum_votes(
    votes: Sequence[Any],
    target_block_hex: str,
    num_nodes: int = BFT_NODES,
    min_quorum: int = BFT_MIN_QUORUM,
) -> tuple[int, list[str]]:
    """Verify >=3/4 distinct Ed25519 votes and trap any equivocating double-vote."""
    errs: list[str] = []
    seen_vote: dict[tuple[int, int], str] = {}
    valid_signers: set[int] = set()
    norm_target = normalize_sha256(target_block_hex)
    for idx, vote in enumerate(votes):
        vid = getattr(vote, "validator_id", None)
        height = getattr(vote, "height", None)
        bhash = normalize_sha256(getattr(vote, "block_hash", ""))
        sig_hex = getattr(vote, "sig_hex", "")
        sig_ok = getattr(vote, "ed25519_valid", None)
        if not is_strict_int(vid) or not (0 <= vid < num_nodes):
            errs.append(f"invalid_validator_id_{idx}:{vid!r}")
            continue
        if not is_strict_int(height) or height < 0:
            errs.append(f"invalid_vote_height_{idx}:{height!r}")
            continue
        if not bhash:
            errs.append(f"invalid_vote_block_hash_{idx}")
            continue
        key = (vid, height)
        if key in seen_vote:
            if seen_vote[key] != bhash:
                errs.append(f"equivocation_double_vote:V{vid}:h{height}")
            else:
                errs.append(f"duplicate_vote:V{vid}:h{height}")
            continue
        seen_vote[key] = bhash
        if not is_ed25519_sig_hex(sig_hex) or sig_ok is not True:
            errs.append(f"invalid_ed25519_sig:V{vid}")
            continue
        if bhash == norm_target:
            valid_signers.add(vid)
    if len(valid_signers) < min_quorum:
        errs.append(f"sub_quorum_votes:{len(valid_signers)}<{min_quorum}")
    return len(valid_signers), errs


def check_bft_attacks(
    attacks: Sequence[Any],
    min_isas: int = 5,
) -> tuple[int, int, list[str]]:
    """Verify all 4 Byzantine attack vectors fail closed across 5 ISAs (20/20)."""
    errs: list[str] = []
    seen: set[str] = set()
    passed, total_rejs = 0, 0
    for atk in attacks:
        name = getattr(atk, "name", "")
        if not isinstance(name, str) or name not in REQUIRED_BFT_ATTACKS:
            errs.append(f"unknown_bft_attack:{name!r}")
            continue
        if name in seen:
            errs.append(f"duplicate_bft_attack:{name}")
            continue
        seen.add(name)
        if getattr(atk, "rejected", None) is not True:
            errs.append(f"bft_attack_not_rejected:{name}")
            continue
        committed = getattr(atk, "committed", None)
        if not is_strict_int(committed) or committed != 0:
            errs.append(f"bft_attack_committed_nonzero:{name}:{committed!r}")
            continue
        code = getattr(atk, "error_code", None)
        if not is_strict_int(code) or code >= 0:
            errs.append(f"bft_attack_non_negative_code:{name}:{code!r}")
            continue
        isas = getattr(atk, "isas_rejected", None)
        if not is_strict_int(isas) or isas < min_isas:
            errs.append(f"bft_attack_isa_count_low:{name}:{isas!r}")
            continue
        passed += 1
        total_rejs += isas
    for req in REQUIRED_BFT_ATTACKS:
        if req not in seen:
            errs.append(f"missing_bft_attack:{req}")
    return passed, total_rejs, errs
