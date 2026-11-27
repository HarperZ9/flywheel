# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for Slice 34 ZK Pedersen and Slice 35 BuildOS-2.1 bundles."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from harness.zk_pedersen_attest.zk_guards import is_strict_int, normalize_sha256

_ISA_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".x64.elf", "x64-elf"),
    (".rv64.elf", "rv64-elf"),
    (".aarch64.elf", "aarch64-elf"),
    (".wasm", "wasm"),
    (".exe", "x64-pe"),
)

_HEX_KEYS = (
    "nums_H_hex", "c_in_hex", "excess_D_hex", "schnorr_pt_hex", "merkle_root_hex",
    "quic_root_hex", "vm_root_hex", "zk_merkle_root_hex", "bft_ledger_root_hex", "cluster_root_hex",
)
_HEX_RE = {k: re.compile(rf'"{k}"\s*:\s*"([0-9a-fA-F]{{64}})"') for k in _HEX_KEYS}
_INT_KEYS = ("v_in", "v_out1", "v_out2", "verified", "pillars", "curve_eqs")
_INT_RE = {k: re.compile(rf'"{k}"\s*:\s*(\d+)') for k in _INT_KEYS}


@dataclass(frozen=True)
class ZkBinaryRecord:
    """Verified metadata for one Slice 34/35 zero-C binary."""

    isa: str
    rel_path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class ZkAttackRecord:
    """Fail-closed rejection record for one ZK or cross-layer cluster attack."""

    name: str
    rejected: Any
    committed: Any
    error_code: Any
    isas_rejected: Any


@dataclass(frozen=True)
class ZkPedersenBundle:
    """Normalized Slice 34 ZK Pedersen or Slice 35 BuildOS-2.1 cluster bundle."""

    mode: str
    schema: str
    verdict: str
    oracle_exit_code: int
    claim_sha256: str
    v_in: Any
    v_out1: Any
    v_out2: Any
    verified: Any
    pillars: Any
    curve_eqs: Any
    root_hex: str
    aux_hex: dict[str, str]
    pillar_roots: tuple[str, ...]
    binaries: tuple[ZkBinaryRecord, ...]
    attacks: tuple[ZkAttackRecord, ...]
    parse_errors: tuple[str, ...] = ()


def _infer_isa(rel_path: str) -> str:
    low = rel_path.lower()
    for suffix, isa in _ISA_SUFFIXES:
        if low.endswith(suffix):
            return isa
    return ""


def _parse_attacks(raw: Any, errs: list[str]) -> tuple[ZkAttackRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("attacks_not_list")
        return ()
    out: list[ZkAttackRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"attack_not_dict_{idx}")
            continue
        out.append(ZkAttackRecord(str(item.get("name", "")), item.get("rejected"), item.get("committed"), item.get("error_code"), item.get("isas_rejected")))
    return tuple(out)


def _parse_bins(raw: Any, errs: list[str]) -> tuple[ZkBinaryRecord, ...]:
    if not isinstance(raw, list):
        errs.append("binaries_not_list")
        return ()
    out: list[ZkBinaryRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"binary_not_dict_{idx}")
            continue
        sz = item.get("bytes", item.get("byte_size", -1))
        out.append(ZkBinaryRecord(str(item.get("isa", "")), str(item.get("rel_path", "")), sz if is_strict_int(sz) else -1, normalize_sha256(item.get("sha256", ""))))
    return tuple(out)


def _extract_receipt_bins(artifacts: Any) -> tuple[ZkBinaryRecord, ...]:
    if not isinstance(artifacts, list):
        return ()
    out: list[ZkBinaryRecord] = []
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        rel = str(art.get("rel_path", ""))
        isa = _infer_isa(rel)
        if isa:
            sz = art.get("bytes", -1)
            out.append(ZkBinaryRecord(isa, rel, sz if is_strict_int(sz) else -1, normalize_sha256(art.get("sha256", ""))))
    return tuple(out)


def parse_zk_payload(data: dict[str, Any]) -> ZkPedersenBundle:
    """Parse a structured Slice 34 ZK Pedersen or Slice 35 BuildOS-2.1 JSON bundle."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ZkPedersenBundle("unknown", "", "REJECT", 1, "", None, None, None, None, None, None, "", {}, (), (), (), ("payload_not_dict",))
    mode = str(data.get("mode", "cluster_v21" if "cluster_root_hex" in data else "zk_pedersen"))
    root_hex = normalize_sha256(data.get("cluster_root_hex" if mode == "cluster_v21" else "merkle_root_hex", ""))
    aux = {k: normalize_sha256(data.get(k, "")) for k in ("nums_H_hex", "c_in_hex", "excess_D_hex", "schnorr_pt_hex")}
    p_roots = tuple(normalize_sha256(data.get(k, "")) for k in ("quic_root_hex", "vm_root_hex", "zk_merkle_root_hex", "bft_ledger_root_hex")) if mode == "cluster_v21" else ()
    ec = data.get("oracle_exit_code", 0)
    return ZkPedersenBundle(
        mode=mode,
        schema=str(data.get("schema", "")),
        verdict=str(data.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(data.get("claim_sha256", "")),
        v_in=data.get("v_in"),
        v_out1=data.get("v_out1"),
        v_out2=data.get("v_out2"),
        verified=data.get("verified"),
        pillars=data.get("pillars"),
        curve_eqs=data.get("curve_eqs"),
        root_hex=root_hex,
        aux_hex=aux,
        pillar_roots=p_roots,
        binaries=_parse_bins(data.get("binaries", []), errs),
        attacks=_parse_attacks(data.get("attacks"), errs),
        parse_errors=tuple(errs),
    )


def parse_zk_receipt(
    receipt: dict[str, Any],
    supplement: dict[str, Any] | None = None,
) -> ZkPedersenBundle:
    """Parse canonical engine-receipt/1 for Slice 34 (68923) or Slice 35 (68932)."""
    errs: list[str] = []
    if not isinstance(receipt, dict):
        return ZkPedersenBundle("unknown", "", "REJECT", 1, "", None, None, None, None, None, None, "", {}, (), (), (), ("receipt_not_dict",))
    oracle = receipt.get("oracle") if isinstance(receipt.get("oracle"), dict) else {}
    digests = receipt.get("digests") if isinstance(receipt.get("digests"), dict) else {}
    subject = receipt.get("subject") if isinstance(receipt.get("subject"), dict) else {}
    excerpt = str(oracle.get("stdout_excerpt", ""))
    hx = {k: (m.group(1).lower() if (m := pat.search(excerpt)) else "") for k, pat in _HEX_RE.items()}
    iv = {k: (int(m.group(1)) if (m := pat.search(excerpt)) else None) for k, pat in _INT_RE.items()}
    supp = supplement if isinstance(supplement, dict) else {}
    mode = "cluster_v21" if (hx["cluster_root_hex"] or "cluster_root_hex" in supp) else "zk_pedersen"
    root_hex = normalize_sha256(supp.get("cluster_root_hex", hx["cluster_root_hex"]) if mode == "cluster_v21" else supp.get("merkle_root_hex", hx["merkle_root_hex"]))
    aux = {k: normalize_sha256(supp.get(k, hx[k])) for k in ("nums_H_hex", "c_in_hex", "excess_D_hex", "schnorr_pt_hex")}
    p_roots = tuple(normalize_sha256(supp.get(k, hx[k])) for k in ("quic_root_hex", "vm_root_hex", "zk_merkle_root_hex", "bft_ledger_root_hex")) if mode == "cluster_v21" else ()
    ec = oracle.get("exit_code", -1)
    return ZkPedersenBundle(
        mode=mode,
        schema=str(receipt.get("schema", "")),
        verdict=str(receipt.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(digests.get("claim_sha256", "")),
        v_in=supp.get("v_in", iv["v_in"]),
        v_out1=supp.get("v_out1", iv["v_out1"]),
        v_out2=supp.get("v_out2", iv["v_out2"]),
        verified=supp.get("verified", iv["verified"]),
        pillars=supp.get("pillars", iv["pillars"]),
        curve_eqs=supp.get("curve_eqs", iv["curve_eqs"]),
        root_hex=root_hex,
        aux_hex=aux,
        pillar_roots=p_roots,
        binaries=_extract_receipt_bins(subject.get("artifacts")),
        attacks=_parse_attacks(supp.get("attacks"), errs),
        parse_errors=tuple(errs),
    )
