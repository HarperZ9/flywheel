# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for Slice 33 BFT Consensus bundles and engine-receipt/1 files."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from harness.bft_consensus_attest.bft_guards import is_strict_int, normalize_sha256

_ISA_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".x64.elf", "x64-elf"),
    (".rv64.elf", "rv64-elf"),
    (".aarch64.elf", "aarch64-elf"),
    (".wasm", "wasm"),
    (".exe", "x64-pe"),
)

_HEX_RE = {
    "genesis_hex": re.compile(r'"genesis_hex"\s*:\s*"([0-9a-fA-F]{64})"'),
    "blk3_hex": re.compile(r'"blk3_hex"\s*:\s*"([0-9a-fA-F]{64})"'),
    "ledger_root_hex": re.compile(r'"ledger_root_hex"\s*:\s*"([0-9a-fA-F]{64})"'),
}
_INT_RE = {
    "nodes": re.compile(r'"nodes"\s*:\s*(\d+)'),
    "quorum": re.compile(r'"quorum"\s*:\s*(\d+)'),
    "height": re.compile(r'"height"\s*:\s*(\d+)'),
}


@dataclass(frozen=True)
class BftBinaryRecord:
    """Verified metadata for one Slice 33 zero-C binary."""

    isa: str
    rel_path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class BftVoteRecord:
    """Single validator vote over a block height."""

    validator_id: Any
    height: Any
    block_hash: str
    sig_hex: str
    ed25519_valid: Any


@dataclass(frozen=True)
class BftAttackRecord:
    """Fail-closed rejection record for one Byzantine attack control."""

    name: str
    rejected: Any
    committed: Any
    error_code: Any
    isas_rejected: Any


@dataclass(frozen=True)
class BftConsensusBundle:
    """Normalized Slice 33 BFT Consensus attestation bundle."""

    schema: str
    verdict: str
    oracle_exit_code: int
    claim_sha256: str
    nodes: Any
    quorum: Any
    height: Any
    blk3_hex: str
    ledger_root_hex: str
    log_leaves_hex: tuple[str, ...] | None
    votes: tuple[BftVoteRecord, ...]
    binaries: tuple[BftBinaryRecord, ...]
    attacks: tuple[BftAttackRecord, ...]
    parse_errors: tuple[str, ...] = ()


def _infer_isa(rel_path: str) -> str:
    low = rel_path.lower()
    for suffix, isa in _ISA_SUFFIXES:
        if low.endswith(suffix):
            return isa
    return ""


def _parse_votes(raw: Any, errs: list[str]) -> tuple[BftVoteRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("votes_not_list")
        return ()
    out: list[BftVoteRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"vote_not_dict_{idx}")
            continue
        out.append(BftVoteRecord(item.get("validator_id"), item.get("height"), str(item.get("block_hash", "")), str(item.get("sig_hex", "")), item.get("ed25519_valid")))
    return tuple(out)


def _parse_attacks(raw: Any, errs: list[str]) -> tuple[BftAttackRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("attacks_not_list")
        return ()
    out: list[BftAttackRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"attack_not_dict_{idx}")
            continue
        out.append(BftAttackRecord(str(item.get("name", "")), item.get("rejected"), item.get("committed"), item.get("error_code"), item.get("isas_rejected")))
    return tuple(out)


def _parse_bins(raw: Any, errs: list[str]) -> tuple[BftBinaryRecord, ...]:
    if not isinstance(raw, list):
        errs.append("binaries_not_list")
        return ()
    out: list[BftBinaryRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"binary_not_dict_{idx}")
            continue
        sz = item.get("bytes", item.get("byte_size", -1))
        out.append(BftBinaryRecord(str(item.get("isa", "")), str(item.get("rel_path", "")), sz if is_strict_int(sz) else -1, normalize_sha256(item.get("sha256", ""))))
    return tuple(out)


def _extract_receipt_bins(artifacts: Any) -> tuple[BftBinaryRecord, ...]:
    if not isinstance(artifacts, list):
        return ()
    out: list[BftBinaryRecord] = []
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        rel = str(art.get("rel_path", ""))
        isa = _infer_isa(rel)
        if isa:
            sz = art.get("bytes", -1)
            out.append(BftBinaryRecord(isa, rel, sz if is_strict_int(sz) else -1, normalize_sha256(art.get("sha256", ""))))
    return tuple(out)


def parse_bft_payload(data: dict[str, Any]) -> BftConsensusBundle:
    """Parse a structured Slice 33 BFT Consensus JSON bundle."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return BftConsensusBundle("", "REJECT", 1, "", None, None, None, "", "", None, (), (), (), ("payload_not_dict",))
    leaves = data.get("log_leaves_hex")
    ec = data.get("oracle_exit_code", 0)
    return BftConsensusBundle(
        schema=str(data.get("schema", "")),
        verdict=str(data.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(data.get("claim_sha256", "")),
        nodes=data.get("nodes"),
        quorum=data.get("quorum"),
        height=data.get("height"),
        blk3_hex=normalize_sha256(data.get("blk3_hex", "")),
        ledger_root_hex=normalize_sha256(data.get("ledger_root_hex", "")),
        log_leaves_hex=tuple(leaves) if isinstance(leaves, list) else None,
        votes=_parse_votes(data.get("votes"), errs),
        binaries=_parse_bins(data.get("binaries", []), errs),
        attacks=_parse_attacks(data.get("attacks"), errs),
        parse_errors=tuple(errs),
    )


def parse_bft_receipt(
    receipt: dict[str, Any],
    supplement: dict[str, Any] | None = None,
) -> BftConsensusBundle:
    """Parse a canonical engine-receipt/1 JSON envelope for Slice 33 BFT Consensus."""
    errs: list[str] = []
    if not isinstance(receipt, dict):
        return BftConsensusBundle("", "REJECT", 1, "", None, None, None, "", "", None, (), (), (), ("receipt_not_dict",))
    oracle = receipt.get("oracle") if isinstance(receipt.get("oracle"), dict) else {}
    digests = receipt.get("digests") if isinstance(receipt.get("digests"), dict) else {}
    subject = receipt.get("subject") if isinstance(receipt.get("subject"), dict) else {}
    excerpt = str(oracle.get("stdout_excerpt", ""))
    hx = {k: (m.group(1).lower() if (m := pat.search(excerpt)) else "") for k, pat in _HEX_RE.items()}
    iv = {k: (int(m.group(1)) if (m := pat.search(excerpt)) else None) for k, pat in _INT_RE.items()}
    supp = supplement if isinstance(supplement, dict) else {}
    leaves = supp.get("log_leaves_hex")
    ec = oracle.get("exit_code", -1)
    return BftConsensusBundle(
        schema=str(receipt.get("schema", "")),
        verdict=str(receipt.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(digests.get("claim_sha256", "")),
        nodes=supp.get("nodes", iv["nodes"]),
        quorum=supp.get("quorum", iv["quorum"]),
        height=supp.get("height", iv["height"]),
        blk3_hex=normalize_sha256(supp.get("blk3_hex", hx["blk3_hex"])),
        ledger_root_hex=normalize_sha256(supp.get("ledger_root_hex", hx["ledger_root_hex"])),
        log_leaves_hex=tuple(leaves) if isinstance(leaves, list) else None,
        votes=_parse_votes(supp.get("votes"), errs),
        binaries=_extract_receipt_bins(subject.get("artifacts")),
        attacks=_parse_attacks(supp.get("attacks"), errs),
        parse_errors=tuple(errs),
    )
