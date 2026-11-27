"""Stage 1 provenance firewall and pluggable domain adapters (HIPAA Safe Harbor, SI Physics)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Any

from .common import (
    ALLOWED_LICENSES,
    DENIED_LICENSES,
    DISALLOWED_COLLECTION_MODES,
    SECRET_PATTERNS,
)

# Official HHS 45 CFR 164.514(b)(2) 17 restricted 3-digit ZIP prefixes (population <= 20,000)
HIPAA_RESTRICTED_ZIP3 = frozenset({
    "036", "059", "063", "102", "203", "556", "692", "790", "821",
    "823", "830", "831", "878", "879", "884", "890", "893",
})

_HIPAA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("patient_name", re.compile(r"\b(?:Patient\s+Name|Full\s+Name)\s*:\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+")),
    ("mrn", re.compile(r"\bMRN[:#\s-]*\d{4,}\b", re.IGNORECASE)),
    ("dob_or_exact_iso_date", re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")),
    ("exact_us_date", re.compile(r"\b(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/(?:19|20)?\d{2}\b")),
    ("phone_pii", re.compile(r"(?<!\d)(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")),
    ("account_or_license_id", re.compile(r"\b(?:Account|Acct|License|Certificate)\s*#?\s*:\s*[A-Z0-9-]{6,}\b", re.IGNORECASE)),
    ("ipv4_address", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
)
_ZIP5_RE = re.compile(r"\bZIP[:\s#]*(\d{5})(?:-\d{4})?\b", re.IGNORECASE)
_ICD10_RE = re.compile(r"^[A-TV-Z][0-9]{2}(?:\.[0-9A-Za-z]{1,4})?$")
_LOINC_RE = re.compile(r"^\d{1,5}-\d$")

_PHYSIO_BOUNDS: dict[str, tuple[float, float]] = {
    "heart_rate_bpm": (20.0, 260.0),
    "spo2_pct": (50.0, 100.0),
    "temp_c": (25.0, 44.0),
    "systolic_mmhg": (40.0, 280.0),
    "diastolic_mmhg": (20.0, 180.0),
}

# SI base dimensional exponent vectors: (Mass kg, Length m, Time s, Current A, Temp K)
SI_UNIT_DIMS: dict[str, tuple[int, int, int, int, int]] = {
    "1": (0, 0, 0, 0, 0),
    "kg": (1, 0, 0, 0, 0),
    "m": (0, 1, 0, 0, 0),
    "s": (0, 0, 1, 0, 0),
    "A": (0, 0, 0, 1, 0),
    "K": (0, 0, 0, 0, 1),
    "m/s": (0, 1, -1, 0, 0),
    "m/s^2": (0, 1, -2, 0, 0),
    "N": (1, 1, -2, 0, 0),
    "J": (1, 2, -2, 0, 0),
    "W": (1, 2, -3, 0, 0),
    "Pa": (1, -1, -2, 0, 0),
    "kg*m/s": (1, 1, -1, 0, 0),
}


def assign_patient_level_split(patient_id: str, eval_ratio: float = 0.2) -> str:
    """Deterministic zero-leak patient-grouped train/eval assignment."""
    if not patient_id.strip():
        raise ValueError("patient_id must be non-empty")
    digest = hashlib.sha256(f"patient-split:{patient_id.strip()}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(1 << 64)
    return "eval" if bucket < eval_ratio else "train"


def verify_zero_patient_bleed(
    train_patient_ids: Sequence[str],
    eval_patient_ids: Sequence[str],
) -> tuple[bool, list[str]]:
    """Fail-closed check asserting zero overlap of patient IDs across train and eval splits."""
    overlap = sorted(set(train_patient_ids) & set(eval_patient_ids))
    return len(overlap) == 0, overlap


class DomainAdapter:
    """First-class pluggable adapter contract for non-code and multi-modal domains."""

    adapter_name: str = "base"

    def validate(self, row: dict[str, Any], text: str) -> tuple[bool, str, dict[str, Any]]:
        return True, "OK", {"adapter": self.adapter_name}


class MedicalHipaaSafeHarborAdapter(DomainAdapter):
    """HIPAA Safe Harbor de-ID, physiological/ICD/LOINC sanity oracle, and patient-level split tagger."""

    adapter_name = "medical_hipaa_safe_harbor"

    def validate(self, row: dict[str, Any], text: str) -> tuple[bool, str, dict[str, Any]]:
        for label, pat in _HIPAA_PATTERNS:
            if pat.search(text):
                return False, f"HIPAA_SAFE_HARBOR_VIOLATION:{label}", {}
        for match in _ZIP5_RE.finditer(text):
            zip3 = match.group(1)[:3]
            if zip3 in HIPAA_RESTRICTED_ZIP3:
                return False, f"HIPAA_SAFE_HARBOR_VIOLATION:restricted_zip3_{zip3}", {}
        for field, (lo, hi) in _PHYSIO_BOUNDS.items():
            if field in row and row[field] is not None:
                val = float(row[field])
                if not (lo <= val <= hi):
                    return False, f"MEDICAL_RANGE_VIOLATION:{field}={val}", {}
        if row.get("icd10_code") and not _ICD10_RE.match(str(row["icd10_code"])):
            return False, f"MEDICAL_SCHEMA_VIOLATION:icd10={row['icd10_code']}", {}
        if row.get("loinc_code") and not _LOINC_RE.match(str(row["loinc_code"])):
            return False, f"MEDICAL_SCHEMA_VIOLATION:loinc={row['loinc_code']}", {}
        meta: dict[str, Any] = {"adapter": self.adapter_name, "hipaa_safe_harbor_checked": True}
        if row.get("patient_group_token"):
            meta["patient_split"] = assign_patient_level_split(str(row["patient_group_token"]))
        return True, "OK", meta


class ScientificPhysicsSensorAdapter(DomainAdapter):
    """SI-unit dimensional analysis oracle plus conservation-law residual check."""

    adapter_name = "scientific_physics_sensor"

    def validate(self, row: dict[str, Any], text: str) -> tuple[bool, str, dict[str, Any]]:
        lhs_units = row.get("si_lhs_units")
        rhs_units = row.get("si_rhs_units")
        if lhs_units and rhs_units:
            try:
                lhs_dim = tuple(sum(SI_UNIT_DIMS[u][i] for u in lhs_units) for i in range(5))
                rhs_dim = tuple(sum(SI_UNIT_DIMS[u][i] for u in rhs_units) for i in range(5))
            except KeyError as exc:
                return False, f"SI_UNKNOWN_UNIT:{exc.args[0]}", {}
            if lhs_dim != rhs_dim:
                return False, f"SI_DIMENSIONAL_MISMATCH:{lhs_dim}!={rhs_dim}", {}
        if "conservation_in" in row and "conservation_out" in row:
            c_in = float(row["conservation_in"])
            c_out = float(row["conservation_out"])
            tol = float(row.get("conservation_tol", 1e-6))
            rel_res = abs(c_in - c_out) / max(abs(c_in), 1e-12)
            if rel_res > tol:
                return False, f"CONSERVATION_RESIDUAL_VIOLATION:{rel_res:.3e}>{tol:.3e}", {}
        return True, "OK", {"adapter": self.adapter_name, "si_physics_checked": True}


DOMAIN_ADAPTERS: dict[str, DomainAdapter] = {
    "medical_clinical": MedicalHipaaSafeHarborAdapter(),
    "scientific_physics": ScientificPhysicsSensorAdapter(),
}


def run_domain_adapter(row: dict[str, Any], text: str) -> tuple[bool, str, dict[str, Any]]:
    """Run the registered adapter for a row's domain if one exists."""
    domain = str(row.get("domain") or "").strip().lower()
    adapter = DOMAIN_ADAPTERS.get(domain)
    if adapter is None:
        return True, "OK", {}
    return adapter.validate(row, text)


def stage1_provenance_firewall(row: dict[str, Any], text: str) -> tuple[bool, str, dict[str, Any]]:
    """Fail-closed check for secrets, PII, non-consensual tracking, and closed licenses."""
    if not text or len(text) < 12:
        return False, "EMPTY_OR_TOO_SHORT", {}
    mode = str(row.get("collection_mode", "public_or_consented")).strip().upper()
    if mode in DISALLOWED_COLLECTION_MODES:
        return False, f"PRIVACY_ACT_GUARDRAIL_REJECTED:{mode}", {}
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return False, f"SECRET_OR_PII_DETECTED:{label}", {}

    raw_lic = str(row.get("license") or row.get("spdx_license") or "curated-open").strip()
    if raw_lic.upper() in DENIED_LICENSES or raw_lic not in ALLOWED_LICENSES:
        return False, f"LICENSE_REJECTED:{raw_lic}", {}

    provenance = {
        "spdx_license": raw_lic,
        "source_corpus": str(row.get("_source_corpus", row.get("source", "unknown"))),
        "consent_basis": str(row.get("consent_basis", "public_consented_or_synthetic")),
        "firewall_checked": True,
    }
    return True, "OK", provenance
