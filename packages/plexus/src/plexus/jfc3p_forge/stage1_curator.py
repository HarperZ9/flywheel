"""Stage-1 Tier-A license firewall, 13-gram DS-01..DS-07 decontamination, and 14-lane readiness gate."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

TIER_A_LICENSES: frozenset[str] = frozenset({
    "CC0",
    "CC0-1.0",
    "PUBLIC-DOMAIN",
    "UNLICENSE",
    "CC-BY",
    "CC-BY-3.0",
    "CC-BY-4.0",
    "MIT",
    "APACHE-2.0",
    "BSD-2-CLAUSE",
    "BSD-3-CLAUSE",
    "ISC",
    "ODC-BY",
    "ODC-BY-1.0",
    "FIRST-PARTY-OPEN",
})

BLOCKED_LICENSE_MARKERS: tuple[str, ...] = (
    "-NC",
    "_NC",
    "NON-COMMERCIAL",
    "NONCOMMERCIAL",
    "-ND",
    "_ND",
    "NO-DERIV",
    "NODERIV",
    "PROPRIETARY",
    "ALL-RIGHTS-RESERVED",
    "RESEARCH-ONLY",
    "ACADEMIC-ONLY",
    "EVAL-ONLY",
    "GPL",
    "AGPL",
    "LGPL",
    "UNKNOWN",
    "UNLICENSED",
)

TOKEN_RE = re.compile(r"[a-z0-9_]+")

FROZEN_DS_HOLDOUTS: dict[str, tuple[str, ...]] = {
    "DS-01": (
        "tool repair trajectory inspect failing build command capture stderr patch source verify exit code zero",
        "flywheel three plate repair loop detect malformed json argument recover with schema validated tool call",
    ),
    "DS-02": (
        "buildlang compiler deterministic effect row check compile kcore fast kernel verify sha256 bit exact output",
    ),
    "DS-03": (
        "formulas tsv known answer ieee754 float64 stefan boltzmann irradiance planck spectral radiance zero ulp check",
    ),
    "DS-04": (
        "raw dx12 moving camera flip temporal motion vector flicker threshold half percent sagnac shader oracle",
    ),
    "DS-05": (
        "cmmns metadata graph node provenance edge citation index zero raw media public shard verification",
    ),
    "DS-06": (
        "three plate oracle planted defect trap reject secret leak stubbed test false accept rate zero",
    ),
    "DS-07": (
        "federated recall stratified workstation library query hit at five latency two millisecond provenance check",
    ),
}


@dataclass(frozen=True)
class LicenseDecision:
    license_raw: str
    normalized: str
    allowed: bool
    tier: str
    reason: str


@dataclass(frozen=True)
class ContaminationMatch:
    contaminated: bool
    matched_datasets: tuple[str, ...]
    matched_ngram_count: int


@dataclass(frozen=True)
class LaneSpec:
    lane_id: str
    domain: str
    min_verified_tokens: int
    min_oracle_coverage: float


@dataclass(frozen=True)
class LaneStats:
    lane_id: str
    verified_tokens: int
    oracle_verified_records: int
    total_records: int
    contamination_hits: int = 0
    license_violations: int = 0

    @property
    def oracle_coverage(self) -> float:
        if self.total_records <= 0:
            return 0.0
        return self.oracle_verified_records / float(self.total_records)


@dataclass(frozen=True)
class CurationSummary:
    total_seen: int
    accepted: int
    license_rejected: int
    contamination_rejected: int
    lane_stats: dict[str, LaneStats]


@dataclass(frozen=True)
class ReadinessReport:
    verdict: str
    ok: bool
    passing_lanes: int
    total_lanes: int
    blocking_lanes: tuple[str, ...]
    reasons: tuple[str, ...]


LANE_14_SPECS: tuple[LaneSpec, ...] = (
    LaneSpec("lane_01_realtime_3d_vision", "vision_3d", 5_000_000_000, 0.90),
    LaneSpec("lane_02_code_compilers_formal", "code_compilers", 25_000_000_000, 0.95),
    LaneSpec("lane_03_agentic_tool_repair", "agentic_rl", 2_000_000_000, 0.95),
    LaneSpec("lane_04_verification_anti_hallucination", "verification", 1_000_000_000, 0.99),
    LaneSpec("lane_05_formal_math_proofing", "formal_math", 10_000_000_000, 0.95),
    LaneSpec("lane_06_optics_color_imaging", "optics_color", 500_000_000, 0.95),
    LaneSpec("lane_07_audio_music_dsp", "audio_dsp", 1_000_000_000, 0.90),
    LaneSpec("lane_08_multiphysics_cosmo_video", "multiphysics", 2_000_000_000, 0.95),
    LaneSpec("lane_09_humanities_law_ocr", "humanities_ocr", 10_000_000_000, 0.85),
    LaneSpec("lane_10_systems_kernels_db", "systems_kernels", 5_000_000_000, 0.95),
    LaneSpec("lane_11_cad_materials_3d_sdf", "cad_materials", 1_000_000_000, 0.95),
    LaneSpec("lane_12_nuclear_aerospace_sim", "nuclear_aero", 500_000_000, 0.95),
    LaneSpec("lane_13_embodied_robotics_control", "embodied_robotics", 2_000_000_000, 0.95),
    LaneSpec("lane_14_bio_neuro_chem_med", "bio_neuro_chem", 5_000_000_000, 0.90),
)


def _normalize_license(raw: str) -> str:
    cleaned = re.sub(r"[\s_]+", "-", (raw or "").strip().upper())
    return re.sub(r"-+", "-", cleaned).strip("-")


def check_license_firewall(license_id: str) -> LicenseDecision:
    """Enforce Tier-A open license allowlist and fail-closed Tier-B/NC/ND refusal."""
    norm = _normalize_license(license_id)
    if not norm:
        return LicenseDecision(license_id, norm, False, "REJECTED", "missing or empty license identifier")
    for marker in BLOCKED_LICENSE_MARKERS:
        if marker in norm or norm == marker.lstrip("-"):
            return LicenseDecision(license_id, norm, False, "TIER_B_BLOCKED", f"blocked license marker: {marker}")
    if norm in TIER_A_LICENSES:
        return LicenseDecision(license_id, norm, True, "TIER_A", "approved Tier-A permissive license")
    return LicenseDecision(license_id, norm, False, "REJECTED", f"license not in Tier-A allowlist: {norm}")


def normalize_tokens(text: str) -> tuple[str, ...]:
    """Normalize text to lowercase alphanumeric tokens for deterministic n-gram matching."""
    return tuple(TOKEN_RE.findall((text or "").lower()))


def extract_13grams(text: str, n: int = 13) -> tuple[str, ...]:
    """Return deterministic SHA-256 prefix digests for all contiguous word-level n-grams."""
    tokens = normalize_tokens(text)
    if len(tokens) < n or n <= 0:
        return ()
    out: list[str] = []
    for idx in range(len(tokens) - n + 1):
        gram = " ".join(tokens[idx : idx + n]).encode("utf-8")
        out.append(hashlib.sha256(gram).hexdigest()[:16])
    return tuple(out)


class ContaminationIndex:
    """Word-level 13-gram contamination detector against frozen DS-01..DS-07 holdouts."""

    def __init__(self, n: int = 13, include_builtin: bool = True) -> None:
        self.n = n
        self._index: dict[str, set[str]] = {}
        if include_builtin:
            for ds_id, texts in FROZEN_DS_HOLDOUTS.items():
                for text in texts:
                    self.add_holdout_text(ds_id, text)

    def add_holdout_text(self, dataset_id: str, text: str) -> int:
        grams = extract_13grams(text, n=self.n)
        for digest in grams:
            self._index.setdefault(digest, set()).add(dataset_id)
        return len(grams)

    def load_holdout_jsonl(self, dataset_id: str, path: Path, text_fields: tuple[str, ...] = ("text", "prompt", "query")) -> int:
        added = 0
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                parts = [str(row[f]) for f in text_fields if f in row and row[f]]
                if parts:
                    added += self.add_holdout_text(dataset_id, " ".join(parts))
        return added

    def check_text(self, text: str) -> ContaminationMatch:
        matched_ds: set[str] = set()
        hits = 0
        for digest in extract_13grams(text, n=self.n):
            owners = self._index.get(digest)
            if owners:
                hits += 1
                matched_ds.update(owners)
        return ContaminationMatch(hits > 0, tuple(sorted(matched_ds)), hits)


def curate_records(records: Iterable[dict[str, Any]], holdout_index: ContaminationIndex | None = None) -> CurationSummary:
    """Filter raw candidate records through the Tier-A license firewall and 13-gram detector."""
    index = holdout_index if holdout_index is not None else ContaminationIndex()
    buckets: dict[str, list[int]] = {}
    total_seen = accepted = lic_rej = contam_rej = 0
    for rec in records:
        total_seen += 1
        lane_id = str(rec.get("lane_id", "unknown"))
        row = buckets.setdefault(lane_id, [0, 0, 0, 0, 0])
        lic = check_license_firewall(str(rec.get("license", "")))
        if not lic.allowed:
            lic_rej += 1
            row[4] += 1
            continue
        contam = index.check_text(str(rec.get("text", "")))
        if contam.contaminated:
            contam_rej += 1
            row[3] += 1
            continue
        accepted += 1
        row[0] += max(0, int(rec.get("tokens", len(normalize_tokens(str(rec.get("text", "")))))))
        row[1] += 1 if bool(rec.get("oracle_verified", False)) else 0
        row[2] += 1
    stats = {
        lid: LaneStats(lid, v[0], v[1], v[2], contamination_hits=v[3], license_violations=v[4])
        for lid, v in buckets.items()
    }
    return CurationSummary(total_seen, accepted, lic_rej, contam_rej, stats)


def evaluate_readiness(
    lane_stats: dict[str, LaneStats],
    *,
    specs: tuple[LaneSpec, ...] = LANE_14_SPECS,
    require_all_lanes: bool = True,
) -> ReadinessReport:
    """Compute strict GO vs NO_GO_DATA_GATE verdict across all 14 frontier lanes."""
    blocking: list[str] = []
    reasons: list[str] = []
    passing = 0
    for spec in specs:
        st = lane_stats.get(spec.lane_id)
        if st is None:
            if require_all_lanes:
                blocking.append(spec.lane_id)
                reasons.append(f"{spec.lane_id}: missing lane statistics")
            continue
        lane_errs: list[str] = []
        if st.license_violations > 0:
            lane_errs.append(f"license_violations={st.license_violations}")
        if st.contamination_hits > 0:
            lane_errs.append(f"contamination_hits={st.contamination_hits}")
        if st.verified_tokens < spec.min_verified_tokens:
            lane_errs.append(f"tokens={st.verified_tokens} < floor={spec.min_verified_tokens}")
        if st.oracle_coverage < spec.min_oracle_coverage:
            lane_errs.append(f"oracle_coverage={st.oracle_coverage:.4f} < floor={spec.min_oracle_coverage:.2f}")
        if lane_errs:
            blocking.append(spec.lane_id)
            reasons.append(f"{spec.lane_id}: " + "; ".join(lane_errs))
        else:
            passing += 1
    ok = len(blocking) == 0 and (passing == len(specs) if require_all_lanes else passing > 0)
    verdict = "GO" if ok else "NO_GO_DATA_GATE"
    return ReadinessReport(verdict, ok, passing, len(specs), tuple(blocking), tuple(reasons))
