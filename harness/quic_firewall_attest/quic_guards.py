# SPDX-License-Identifier: MIT
"""Fail-closed RFC 9000/9001/9002 anti-replay, CAP_NET_PEER, and 20/20 attack guards."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence

REPLAY_WINDOW_BITS: int = 64

REQUIRED_ISAS: tuple[str, ...] = (
    "x64-pe",
    "x64-elf",
    "rv64-elf",
    "aarch64-elf",
    "wasm",
)

REQUIRED_NET_ATTACKS: tuple[str, ...] = (
    "replay_packet",
    "unapproved_peer_egress",
    "aead_tag_tamper",
    "pn_window_underflow",
)

_WILDCARD_PEERS = frozenset({"*", "0.0.0.0/0", "::/0", "any", "all"})
_HEX_CHARS = frozenset("0123456789abcdef")


def is_strict_int(value: Any) -> bool:
    """Return True only for plain integers, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def normalize_sha256(digest: Any) -> str:
    """Strip optional sha256: prefix and return 64-char lowercase hex if valid."""
    if not isinstance(digest, str):
        return ""
    raw = digest[7:] if digest.startswith("sha256:") else digest
    if len(raw) != 64:
        return ""
    low = raw.lower()
    if any(ch not in _HEX_CHARS for ch in low):
        return ""
    return low


def is_sha256_hex(digest: Any) -> bool:
    """Return True when digest is a valid 64-char hex SHA-256 string."""
    return bool(normalize_sha256(digest))


def sha256_file(path: Path) -> str:
    """Compute streaming SHA-256 hex digest for an artifact file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def check_replay_window_sequence(
    packet_numbers: Sequence[Any],
    window_bits: int = REPLAY_WINDOW_BITS,
) -> tuple[int, int, list[str]]:
    """Simulate a 64-bit sliding anti-replay window; fail closed on replay or underflow."""
    if not isinstance(packet_numbers, Sequence) or isinstance(packet_numbers, (str, bytes)):
        return -1, 0, ["packet_numbers_not_sequence"]
    if not packet_numbers:
        return -1, 0, ["packet_numbers_empty"]
    errs: list[str] = []
    max_pn = -1
    bitmap = 0
    mask = (1 << window_bits) - 1
    for idx, pn in enumerate(packet_numbers):
        if not is_strict_int(pn) or pn < 0:
            errs.append(f"invalid_packet_number_at_{idx}:{pn!r}")
            continue
        if max_pn < 0:
            max_pn = pn
            bitmap = 1
        elif pn > max_pn:
            shift = pn - max_pn
            bitmap = ((bitmap << shift) & mask) | 1 if shift < window_bits else 1
            max_pn = pn
        else:
            diff = max_pn - pn
            if diff >= window_bits:
                errs.append(f"pn_window_underflow_at_{idx}:{pn}")
            elif (bitmap >> diff) & 1:
                errs.append(f"replay_packet_detected_at_{idx}:{pn}")
            else:
                bitmap |= 1 << diff
    return max_pn, bitmap, errs


def check_cap_net_peer_rules(
    default_action: Any,
    rules: Sequence[Any],
) -> list[str]:
    """Verify deny-by-default firewall and explicit CAP_NET_PEER allow rules."""
    errs: list[str] = []
    if default_action != "DENY":
        errs.append(f"firewall_not_deny_by_default:{default_action!r}")
    if not rules:
        errs.append("firewall_rules_empty")
        return errs
    for idx, rule in enumerate(rules):
        cap = getattr(rule, "capability", "")
        peer = str(getattr(rule, "peer_id", "")).strip()
        action = getattr(rule, "action", "")
        if action not in ("ALLOW", "DENY"):
            errs.append(f"firewall_invalid_action_{idx}:{action!r}")
            continue
        if action == "ALLOW":
            if cap != "CAP_NET_PEER":
                errs.append(f"firewall_missing_cap_net_peer_{idx}:{cap!r}")
            if not peer or peer.lower() in _WILDCARD_PEERS:
                errs.append(f"firewall_wildcard_peer_allow_{idx}:{peer!r}")
    return errs


def check_net_attacks(
    attacks: Sequence[Any],
    min_isas: int = 5,
) -> tuple[int, int, list[str]]:
    """Verify all 4 QUIC/firewall attack vectors fail closed across 5 ISAs (20/20)."""
    errs: list[str] = []
    seen: set[str] = set()
    passed = 0
    total_rejs = 0
    for atk in attacks:
        name = getattr(atk, "name", "")
        if not isinstance(name, str) or name not in REQUIRED_NET_ATTACKS:
            errs.append(f"unknown_net_attack:{name!r}")
            continue
        if name in seen:
            errs.append(f"duplicate_net_attack:{name}")
            continue
        seen.add(name)
        if getattr(atk, "rejected", None) is not True:
            errs.append(f"net_attack_not_rejected:{name}")
            continue
        committed = getattr(atk, "committed", None)
        if not is_strict_int(committed) or committed != 0:
            errs.append(f"net_attack_committed_nonzero:{name}:{committed!r}")
            continue
        code = getattr(atk, "error_code", None)
        if not is_strict_int(code) or code >= 0:
            errs.append(f"net_attack_non_negative_code:{name}:{code!r}")
            continue
        isas = getattr(atk, "isas_rejected", None)
        if not is_strict_int(isas) or isas < min_isas:
            errs.append(f"net_attack_isa_count_low:{name}:{isas!r}")
            continue
        passed += 1
        total_rejs += isas
    for req in REQUIRED_NET_ATTACKS:
        if req not in seen:
            errs.append(f"missing_net_attack:{req}")
    return passed, total_rejs, errs
