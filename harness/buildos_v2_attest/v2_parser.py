# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for BuildOS-2.0 sovereign bundles and engine-receipt/1 files."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from harness.buildos_v2_attest.v2_guards import is_strict_int, normalize_sha256

_ISA_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".x64.elf", "x64-elf"),
    (".rv64.elf", "rv64-elf"),
    (".aarch64.elf", "aarch64-elf"),
    (".wasm", "wasm"),
    (".exe", "x64-pe"),
)

_ROOT_RE = re.compile(r'"sovereign_root_hex"\s*:\s*"([0-9a-fA-F]+)')


@dataclass(frozen=True)
class V2BinaryRecord:
    """Verified metadata for one BuildOS-2.0 zero-C target binary."""

    isa: str
    rel_path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class SubsystemLeafRecord:
    """One ordered BuildOS-2.0 subsystem leaf digest."""

    name: str
    digest_hex: str


@dataclass(frozen=True)
class V2AttackRecord:
    """Fail-closed rejection record for one cross-subsystem attack vector."""

    name: str
    rejected: Any
    sovereign_committed: Any
    error_code: Any
    isas_rejected: Any


@dataclass(frozen=True)
class BuildOSV2Bundle:
    """Normalized BuildOS-2.0 12-subsystem sovereign attestation bundle."""

    schema: str
    verdict: str
    oracle_exit_code: int
    claim_sha256: str
    merkle_root: str
    binaries: tuple[V2BinaryRecord, ...]
    subsystems: tuple[SubsystemLeafRecord, ...]
    attacks: tuple[V2AttackRecord, ...]
    parse_errors: tuple[str, ...] = ()


def _infer_isa(rel_path: str) -> str:
    low = rel_path.lower()
    for suffix, isa in _ISA_SUFFIXES:
        if low.endswith(suffix):
            return isa
    return ""


def _parse_binaries(raw: Any, errs: list[str]) -> tuple[V2BinaryRecord, ...]:
    if not isinstance(raw, list):
        errs.append("binaries_not_list")
        return ()
    out: list[V2BinaryRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"binary_not_dict_{idx}")
            continue
        size = item.get("bytes", item.get("byte_size", -1))
        out.append(
            V2BinaryRecord(
                isa=str(item.get("isa", "")),
                rel_path=str(item.get("rel_path", "")),
                byte_size=size if is_strict_int(size) else -1,
                sha256=normalize_sha256(item.get("sha256", "")),
            )
        )
    return tuple(out)


def _parse_subsystems(raw: Any, errs: list[str]) -> tuple[SubsystemLeafRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("subsystems_not_list")
        return ()
    out: list[SubsystemLeafRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"subsystem_not_dict_{idx}")
            continue
        out.append(
            SubsystemLeafRecord(
                name=str(item.get("name", "")),
                digest_hex=str(item.get("digest_hex", item.get("sha256", ""))),
            )
        )
    return tuple(out)


def _parse_attacks(raw: Any, errs: list[str]) -> tuple[V2AttackRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("attacks_not_list")
        return ()
    out: list[V2AttackRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"attack_not_dict_{idx}")
            continue
        out.append(
            V2AttackRecord(
                name=str(item.get("name", "")),
                rejected=item.get("rejected"),
                sovereign_committed=item.get("sovereign_committed"),
                error_code=item.get("error_code"),
                isas_rejected=item.get("isas_rejected"),
            )
        )
    return tuple(out)


def _extract_receipt_bins(artifacts: Any) -> tuple[V2BinaryRecord, ...]:
    if not isinstance(artifacts, list):
        return ()
    out: list[V2BinaryRecord] = []
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        rel = str(art.get("rel_path", ""))
        isa = _infer_isa(rel)
        if isa:
            size = art.get("bytes", -1)
            out.append(
                V2BinaryRecord(
                    isa=isa,
                    rel_path=rel,
                    byte_size=size if is_strict_int(size) else -1,
                    sha256=normalize_sha256(art.get("sha256", "")),
                )
            )
    return tuple(out)


def parse_buildos_v2_payload(data: dict[str, Any]) -> BuildOSV2Bundle:
    """Parse a structured BuildOS-2.0 JSON bundle."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return BuildOSV2Bundle("", "REJECT", 1, "", "", (), (), (), ("payload_not_dict",))
    ec = data.get("oracle_exit_code", 0)
    return BuildOSV2Bundle(
        schema=str(data.get("schema", "")),
        verdict=str(data.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(data.get("claim_sha256", "")),
        merkle_root=str(data.get("merkle_root", data.get("sovereign_root_hex", ""))),
        binaries=_parse_binaries(data.get("binaries", []), errs),
        subsystems=_parse_subsystems(data.get("subsystems"), errs),
        attacks=_parse_attacks(data.get("attacks"), errs),
        parse_errors=tuple(errs),
    )


def parse_buildos_v2_receipt(
    receipt: dict[str, Any],
    supplement: dict[str, Any] | None = None,
) -> BuildOSV2Bundle:
    """Parse an engine-receipt/1 JSON envelope for BuildOS-2.0 Slice 30."""
    errs: list[str] = []
    if not isinstance(receipt, dict):
        return BuildOSV2Bundle("", "REJECT", 1, "", "", (), (), (), ("receipt_not_dict",))
    oracle = receipt.get("oracle") if isinstance(receipt.get("oracle"), dict) else {}
    digests = receipt.get("digests") if isinstance(receipt.get("digests"), dict) else {}
    subject = receipt.get("subject") if isinstance(receipt.get("subject"), dict) else {}
    bins = _extract_receipt_bins(subject.get("artifacts"))
    excerpt = str(oracle.get("stdout_excerpt", ""))
    match = _ROOT_RE.search(excerpt)
    root = match.group(1).lower() if match else ""
    subs: tuple[SubsystemLeafRecord, ...] = ()
    attacks: tuple[V2AttackRecord, ...] = ()
    if isinstance(supplement, dict):
        root = str(supplement.get("merkle_root", supplement.get("sovereign_root_hex", root)))
        subs = _parse_subsystems(supplement.get("subsystems"), errs)
        attacks = _parse_attacks(supplement.get("attacks"), errs)
    ec = oracle.get("exit_code", -1)
    return BuildOSV2Bundle(
        schema=str(receipt.get("schema", "")),
        verdict=str(receipt.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(digests.get("claim_sha256", "")),
        merkle_root=root,
        binaries=bins,
        subsystems=subs,
        attacks=attacks,
        parse_errors=tuple(errs),
    )
