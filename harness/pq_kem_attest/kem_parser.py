# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for PQ Hybrid KEM manifests and engine-receipt/1 bundles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.pq_kem_attest.pq_guards import (
    MLKEM_K,
    MLKEM_N,
    MLKEM_Q,
    is_strict_int,
    normalize_sha256,
)

_ARTIFACT_ISA_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".x64.elf", "x64-elf"),
    (".rv64.elf", "rv64-elf"),
    (".aarch64.elf", "aarch64-elf"),
    (".wasm", "wasm"),
    (".exe", "x64-pe"),
)


@dataclass(frozen=True)
class IsaBinaryRecord:
    """Verified metadata for one target architecture binary."""

    isa: str
    rel_path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class FoControlRecord:
    """Result record for one planted post-quantum or hybrid attack control."""

    name: str
    rejected: bool
    hybrid_committed: int
    error_code: int
    isas_rejected: int


@dataclass(frozen=True)
class PqKemBundle:
    """Normalized FIPS 203 ML-KEM-512 + X25519 hybrid KEM attestation bundle."""

    schema: str
    verdict: str
    oracle_exit_code: int
    claim_sha256: str
    q: Any
    n: Any
    k: Any
    hybrid_committed: Any
    binaries: tuple[IsaBinaryRecord, ...]
    coefficients: tuple[Any, ...] | None
    fo_controls: tuple[FoControlRecord, ...]
    parse_errors: tuple[str, ...] = ()


def _infer_isa(rel_path: str) -> str:
    low = rel_path.lower()
    for suffix, isa in _ARTIFACT_ISA_SUFFIXES:
        if low.endswith(suffix):
            return isa
    return ""


def _parse_controls(raw_controls: Any, errs: list[str]) -> tuple[FoControlRecord, ...]:
    if raw_controls is None:
        return ()
    if not isinstance(raw_controls, list):
        errs.append("fo_controls_not_list")
        return ()
    out: list[FoControlRecord] = []
    for idx, item in enumerate(raw_controls):
        if not isinstance(item, dict):
            errs.append(f"fo_control_not_dict_{idx}")
            continue
        out.append(
            FoControlRecord(
                name=str(item.get("name", "")),
                rejected=item.get("rejected"),
                hybrid_committed=item.get("hybrid_committed"),
                error_code=item.get("error_code"),
                isas_rejected=item.get("isas_rejected"),
            )
        )
    return tuple(out)


def _parse_binary_list(raw_bins: Any, errs: list[str]) -> tuple[IsaBinaryRecord, ...]:
    if not isinstance(raw_bins, list):
        errs.append("binaries_not_list")
        return ()
    out: list[IsaBinaryRecord] = []
    for idx, item in enumerate(raw_bins):
        if not isinstance(item, dict):
            errs.append(f"binary_not_dict_{idx}")
            continue
        size = item.get("bytes", item.get("byte_size", -1))
        out.append(
            IsaBinaryRecord(
                isa=str(item.get("isa", "")),
                rel_path=str(item.get("rel_path", "")),
                byte_size=size if is_strict_int(size) else -1,
                sha256=normalize_sha256(item.get("sha256", "")),
            )
        )
    return tuple(out)


def parse_pq_kem_payload(data: dict[str, Any]) -> PqKemBundle:
    """Parse a structured PQ Hybrid KEM JSON bundle."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return PqKemBundle(
            "", "REJECT", 1, "", None, None, None, None, (), None, (), ("payload_not_dict",)
        )
    params = data.get("params") if isinstance(data.get("params"), dict) else data
    coeffs = data.get("coefficients")
    coeffs_tuple = tuple(coeffs) if isinstance(coeffs, list) else coeffs
    binaries = _parse_binary_list(data.get("binaries", []), errs)
    controls = _parse_controls(data.get("fo_controls"), errs)
    exit_code = data.get("oracle_exit_code", 0)
    return PqKemBundle(
        schema=str(data.get("schema", "")),
        verdict=str(data.get("verdict", "")),
        oracle_exit_code=exit_code if is_strict_int(exit_code) else -1,
        claim_sha256=normalize_sha256(data.get("claim_sha256", "")),
        q=params.get("q"),
        n=params.get("n"),
        k=params.get("k"),
        hybrid_committed=data.get("hybrid_committed", 1),
        binaries=binaries,
        coefficients=coeffs_tuple,
        fo_controls=controls,
        parse_errors=tuple(errs),
    )


def _extract_receipt_binaries(artifacts: Any) -> tuple[IsaBinaryRecord, ...]:
    if not isinstance(artifacts, list):
        return ()
    bins: list[IsaBinaryRecord] = []
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        rel = str(art.get("rel_path", ""))
        isa = _infer_isa(rel)
        if isa:
            size = art.get("bytes", -1)
            bins.append(
                IsaBinaryRecord(
                    isa=isa,
                    rel_path=rel,
                    byte_size=size if is_strict_int(size) else -1,
                    sha256=normalize_sha256(art.get("sha256", "")),
                )
            )
    return tuple(bins)


def parse_pq_kem_receipt(
    receipt: dict[str, Any],
    supplement: dict[str, Any] | None = None,
) -> PqKemBundle:
    """Parse a canonical engine-receipt/1 JSON envelope for Slice 29 PQ Hybrid KEM."""
    errs: list[str] = []
    if not isinstance(receipt, dict):
        return PqKemBundle(
            "", "REJECT", 1, "", None, None, None, None, (), None, (), ("receipt_not_dict",)
        )
    oracle = receipt.get("oracle") if isinstance(receipt.get("oracle"), dict) else {}
    digests = receipt.get("digests") if isinstance(receipt.get("digests"), dict) else {}
    subject = receipt.get("subject") if isinstance(receipt.get("subject"), dict) else {}
    bins = _extract_receipt_binaries(subject.get("artifacts"))
    excerpt = str(oracle.get("stdout_excerpt", ""))
    q_val = MLKEM_Q if '"q": 3329' in excerpt else None
    n_val = MLKEM_N if '"n": 256' in excerpt else None
    k_val = MLKEM_K if '"k": 2' in excerpt else None
    committed = 1 if '"hybrid_committed": 1' in excerpt else 0
    coeffs: Any = None
    controls: tuple[FoControlRecord, ...] = ()
    if isinstance(supplement, dict):
        q_val = supplement.get("q", q_val)
        n_val = supplement.get("n", n_val)
        k_val = supplement.get("k", k_val)
        committed = supplement.get("hybrid_committed", committed)
        if "coefficients" in supplement:
            raw_c = supplement["coefficients"]
            coeffs = tuple(raw_c) if isinstance(raw_c, list) else raw_c
        controls = _parse_controls(supplement.get("fo_controls"), errs)
    exit_code = oracle.get("exit_code", -1)
    return PqKemBundle(
        schema=str(receipt.get("schema", "")),
        verdict=str(receipt.get("verdict", "")),
        oracle_exit_code=exit_code if is_strict_int(exit_code) else -1,
        claim_sha256=normalize_sha256(digests.get("claim_sha256", "")),
        q=q_val,
        n=n_val,
        k=k_val,
        hybrid_committed=committed,
        binaries=bins,
        coefficients=coeffs,
        fo_controls=controls,
        parse_errors=tuple(errs),
    )
