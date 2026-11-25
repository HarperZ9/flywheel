"""Three-Plate Verification Oracle + AB520 Bundler Secret Guard.

Applies Whitworth three-plate flatness metrology to verification (pure stdlib):
  - Plate A: proposer self-report status, empty output, and overt crash/TODO markers.
  - Plate B: stub/bypass patterns, live assumption-mutation check, AB520 frontend bundler
    secret-prefix + credential guard, zero em-dash and anti-slop rules, SHA-256 provenance.
  - Plate C: IEEE-754 known-answer formula re-execution, protected-number preservation,
    self-vs-hidden echo-chamber guard, direct arithmetic checks, missing-witness classification.

Verdicts: MATCH | DRIFT | UNVERIFIABLE.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

EM_DASH = "\u2014"
AIRY_J1_OVER_PI = 1.2196698912665045
K_BOLTZ = 1.380649e-23
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?(?![A-Za-z0-9_])")
FormulaFn = Callable[[dict[str, Any]], float]

STUB_BYPASS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anygeometry_witness_bypass", re.compile(r"(?i)\banygeometry\s*=\s*true\b")),
    ("lean_sorry_or_admit", re.compile(r"(?m)(?:^|\s)(?:sorry|admit)(?:\s|$|--|;)")),
    ("tautological_assert", re.compile(r"(?i)\bassert\s+(?:True|1\s*==\s*1|0\s*==\s*0)\b")),
    ("skipped_test_escape", re.compile(r"(?i)(?:@pytest\.mark\.skip|@unittest\.skip|\bxit\s*\(|\btest\.skip\s*\()")),
    ("stub_return_true", re.compile(r"(?i)\bdef\s+(?:verify|check|prove|validate)[a-z0-9_]*\([^)]*\)\s*(?:->[^:]+)?:\s*return\s+True\b")),
    ("silent_fallback_magic", re.compile(r"(?i)except\s*(?:Exception)?\s*:\s*return\s+(?:True|15|10|5|0\.0)\b")),
    ("unchecked_axiom_stub", re.compile(r"(?i)\b(?:assume_valid|skip_oracle|bypass_verify|trust_proposer)\s*=\s*True\b")),
)

BUNDLER_SECRET_PREFIX_RE = re.compile(
    r"(?i)\b(?:VITE|NEXT_PUBLIC|PUBLIC|REACT_APP|NUXT_PUBLIC|EXPO_PUBLIC)_[A-Z0-9_]*"
    r"(?:SECRET|PRIVATE|API_KEY|SERVICE_ROLE|OPENAI|STRIPE|ANTHROPIC|RESEND|SUPABASE_SERVICE|"
    r"TOKEN|PASSWORD|ACCESS_KEY|AUTH_KEY)[A-Z0-9_]*\b"
)
BUNDLER_ENV_INLINE_RE = re.compile(
    r"(?i)(?:import\.meta\.env\.|process\.env\.)(?:VITE|NEXT_PUBLIC|PUBLIC|REACT_APP|NUXT_PUBLIC|EXPO_PUBLIC)_"
    r"[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASS|AUTH|STRIPE|OPENAI|ANTHROPIC|RESEND|SERVICE_ROLE|PRIVATE)[A-Z0-9_]*"
)

CREDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----")),
    ("aws_access_key_id", re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Za-z0-9])")),
    ("github_token", re.compile(r"(?<![A-Za-z0-9_\-])(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{22,255})")),
    ("sk_api_key", re.compile(r"(?<![A-Za-z0-9_\-])sk-(?:(?:live|proj|ant|test)-?[A-Za-z0-9_\-]{10,255}|[A-Za-z0-9_\-]{20,255})")),
    ("stripe_key", re.compile(r"(?<![A-Za-z0-9_])(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{10,255}")),
    ("slack_token", re.compile(r"(?<![A-Za-z0-9])xox[abeprs]-[A-Za-z0-9\-]{10,255}")),
    ("google_api_key", re.compile(r"(?<![A-Za-z0-9_\-])AIza[0-9A-Za-z_\-]{35}(?![0-9A-Za-z_\-])")),
    ("jwt", re.compile(r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{12,}")),
    ("resend_key", re.compile(r"(?<![A-Za-z0-9_])re_[A-Za-z0-9_]{20,}")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{20,}")),
    ("credential_assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|"
        r"auth[_-]?token|password|passwd)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=.]{12,}['\"]?"
    )),
)

SLOP_PHRASE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("slop_delve", re.compile(r"(?i)\bdelve(?:s|d|ing)?\s+into\b")),
    ("slop_tapestry", re.compile(r"(?i)\b(?:rich\s+)?tapestry\s+of\b")),
    ("slop_fast_paced", re.compile(r"(?i)\bin\s+today['\u2019]s\s+fast[- ]paced\b")),
    ("slop_worth_noting", re.compile(r"(?i)\bit\s+is\s+worth\s+noting\s+that\b")),
    ("slop_testament", re.compile(r"(?i)\bstands\s+as\s+a\s+testament\s+to\b")),
    ("slop_game_changer", re.compile(r"(?i)\bgame[- ]chang(?:er|ing)\b")),
    ("slop_seamlessly", re.compile(r"(?i)\bseamlessly\s+integrat(?:es|ing|ed)\b")),
)


@dataclass
class PlateReport:
    plate: str
    passed: bool
    defects: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ThreePlateVerdict:
    case_id: str
    verdict: str
    single_plate_verdict: str
    two_plate_verdict: str
    plate_a: PlateReport
    plate_b: PlateReport
    plate_c: PlateReport
    all_defects: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id, "verdict": self.verdict,
            "single_plate_verdict": self.single_plate_verdict,
            "two_plate_verdict": self.two_plate_verdict,
            "all_defects": list(self.all_defects),
            "plate_a_pass": self.plate_a.passed,
            "plate_b_pass": self.plate_b.passed,
            "plate_c_pass": self.plate_c.passed,
        }


def run_plate_a(case: dict[str, Any]) -> PlateReport:
    """Proposer surface check: self-reported status and overt failure markers."""
    defects: list[str] = []
    if case.get("proposer_self_test_passed") is False:
        defects.append("plate_a:proposer_reported_fail")
    content = str(case.get("claim_or_code", ""))
    if not content.strip():
        defects.append("plate_a:empty_submission")
    if "Traceback (most recent call last):" in content or "SYNTAX_ERROR" in content:
        defects.append("plate_a:overt_crash_marker")
    if "TODO_UNFINISHED" in content:
        defects.append("plate_a:unfinished_todo")
    return PlateReport("A", passed=(len(defects) == 0), defects=defects)


def scan_bundler_secrets(text: str) -> list[str]:
    """AB520 frontend bundler secret-prefix and embedded credential scanner."""
    hits: list[str] = []
    if BUNDLER_SECRET_PREFIX_RE.search(text):
        hits.append("plate_b:ab520_bundler_secret_prefix")
    if BUNDLER_ENV_INLINE_RE.search(text):
        hits.append("plate_b:ab520_bundler_env_inline")
    for name, rx in CREDENTIAL_PATTERNS:
        if name == "credential_assignment":
            if any(all(t not in m.group(0).lower() for t in ("placeholder", "example", "redacted")) for m in rx.finditer(text)):
                hits.append(f"plate_b:ab520_credential_{name}")
        elif rx.search(text):
            hits.append(f"plate_b:ab520_credential_{name}")
    return sorted(set(hits))


def _check_provenance(case: dict[str, Any]) -> list[str]:
    expected_sha, claimed_sha, source_body = (
        case.get("expected_source_sha256"), case.get("claimed_source_sha256"), case.get("source_body")
    )
    if source_body is not None and claimed_sha is not None:
        actual = hashlib.sha256(str(source_body).encode("utf-8")).hexdigest()
        return ["plate_b:source_sha256_drift"] if actual != str(claimed_sha) else []
    if expected_sha is not None and claimed_sha is not None and str(expected_sha) != str(claimed_sha):
        return ["plate_b:source_sha256_mismatch"]
    return []


def run_plate_b(case: dict[str, Any]) -> PlateReport:
    """Independent static policy, assumption-mutation, AB520 secret, and provenance checker."""
    defects: list[str] = []
    notes: list[str] = []
    text, kind = str(case.get("claim_or_code", "")), str(case.get("artifact_kind", "generic"))
    defects.extend(f"plate_b:{lbl}" for lbl, rx in STUB_BYPASS_PATTERNS if rx.search(text))
    am = case.get("assumption_check")
    if isinstance(am, dict):
        if not bool(am.get("passes_under_true_assumption", True)):
            defects.append("plate_b:fails_under_true_assumption")
        if bool(am.get("passes_under_mutated_assumption", False)):
            defects.append("plate_b:assumption_mutation_bypass")
            notes.append("Witness passed after negating core hypothesis")
    defects.extend(scan_bundler_secrets(text))
    if EM_DASH in text:
        defects.append("plate_b:em_dash_violation")
    if kind in ("prose", "report", "readme", "claim"):
        defects.extend(f"plate_b:{lbl}" for lbl, rx in SLOP_PHRASE_PATTERNS if rx.search(text))
    defects.extend(_check_provenance(case))
    return PlateReport("B", passed=(len(defects) == 0), defects=sorted(set(defects)), notes=notes)


def _fresnel_dielectric(p: dict[str, Any]) -> float:
    n1, n2, ci = float(p["n1"]), float(p["n2"]), float(p["cos_i"])
    st2 = (n1 / n2) ** 2 * max(0.0, 1.0 - ci * ci)
    if st2 >= 1.0:
        return 1.0
    ct = math.sqrt(1.0 - st2)
    rs = ((n1 * ci - n2 * ct) / (n1 * ci + n2 * ct)) ** 2
    rp = ((n1 * ct - n2 * ci) / (n1 * ct + n2 * ci)) ** 2
    return 0.5 * (rs + rp)


def _friis(p: dict[str, Any]) -> float:
    gains, temps = [float(x) for x in p["gains"]], [float(x) for x in p["temps"]]
    total, prod = temps[0], 1.0
    for g, t in zip(gains, temps[1:]):
        prod *= g
        total += t / prod
    return total


def _auroc(p: dict[str, Any]) -> float:
    pos, neg = [float(x) for x in p["pos"]], [float(x) for x in p["neg"]]
    return sum(1.0 if a > b else (0.5 if a == b else 0.0) for a in pos for b in neg) / (len(pos) * len(neg))


def _haversine_km(p: dict[str, Any]) -> float:
    lat1, lon1 = math.radians(p["lat1"]), math.radians(p["lon1"])
    lat2, lon2 = math.radians(p["lat2"]), math.radians(p["lon2"])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2.0 * 6371.0088 * math.asin(min(1.0, math.sqrt(a)))


FORMULA_REGISTRY: dict[str, FormulaFn] = {
    "OPT-002": _fresnel_dielectric,
    "OPT-004": lambda p: p["f0"] + (1.0 - p["f0"]) * ((1.0 - p["cos_theta"]) ** 5),
    "OPT-007": lambda p: abs(p["f"]) / p["D"],
    "OPT-008": lambda p: (AIRY_J1_OVER_PI if p.get("exact_j1", True) else 1.22) * p["lam"] * p["N"],
    "OPT-009": lambda p: 1.0 / (p["lam_mm"] * p["N"]),
    "OPT-033": lambda p: math.exp(-p["alpha"] * p["d"]),
    "COL-001": lambda p: p["v"] / 12.92 if p["v"] <= 0.04045 else ((p["v"] + 0.055) / 1.055) ** 2.4,
    "COL-019": lambda p: 0.2126 * p["r"] + 0.7152 * p["g"] + 0.0722 * p["b"],
    "COL-030": lambda p: (max(p["l1"], p["l2"]) + 0.05) / (min(p["l1"], p["l2"]) + 0.05),
    "SIG-011": lambda p: 20.0 * math.log10(2.0 ** p["bits"]) + 10.0 * math.log10(1.5),
    "SIG-013": lambda p: -math.fsum(x * math.log2(x) for x in p["probs"] if x > 0.0),
    "SIG-021": _friis,
    "SIG-029": lambda p: 440.0 * (2.0 ** ((p["note"] - 69.0) / 12.0)),
    "SIG-030": lambda p: 20.0 * math.log10(p["a"]),
    "STA-007": _auroc,
    "PHY-007": lambda p: p["v"] * p["L"] / p.get("nu", 1e-6),
    "PHY-039": lambda p: K_BOLTZ * p["T"] * math.log(2.0) * p.get("bits", 1.0),
    "PHY-054": lambda p: 2.0 * p["gamma"] / p["r"],
    "GEO-014": lambda p: 0.0 if p["t"] <= 0.0 else (1.0 if p["t"] >= 1.0 else p["t"] ** 2 * (3.0 - 2.0 * p["t"])),
    "GEO-020": _haversine_km,
}


def _check_formula(spec: dict[str, Any], registry: dict[str, FormulaFn], defects: list[str], notes: list[str]) -> None:
    fid, claimed = str(spec["formula_id"]), float(spec["claimed_value"])
    rel_tol, abs_tol_cfg = float(spec.get("rel_tol", 1e-4)), spec.get("abs_tol")
    try:
        ref = registry[fid](spec["params"])
        abs_tol = float(abs_tol_cfg) if abs_tol_cfg is not None else (1e-12 if ref == 0.0 else 0.0)
        if not math.isclose(claimed, ref, rel_tol=rel_tol, abs_tol=abs_tol):
            defects.append(f"plate_c:numeric_drift:{fid}")
            notes.append(f"claimed={claimed} vs oracle={ref}")
    except Exception as exc:
        defects.append(f"plate_c:oracle_exec_error:{type(exc).__name__}")


def _check_arithmetic(arith: dict[str, Any], defects: list[str], notes: list[str]) -> None:
    op, vals, claimed = arith["op"], [float(x) for x in arith["values"]], float(arith["claimed"])
    ops = {"sum": math.fsum, "mean": lambda v: math.fsum(v) / len(v), "ratio": lambda v: v[0] / v[1], "pct": lambda v: 100.0 * v[0] / v[1]}
    ref = ops[op](vals) if op in ops else math.nan
    if not math.isclose(claimed, ref, rel_tol=1e-4, abs_tol=1e-4):
        defects.append(f"plate_c:arithmetic_mismatch:{op}")
        notes.append(f"claimed={claimed} vs exact={ref}")


def run_plate_c(case: dict[str, Any], formula_registry: dict[str, FormulaFn] | None = None) -> tuple[PlateReport, bool]:
    """Independent execution and ground-truth oracle. Returns (PlateReport, unverifiable)."""
    defects: list[str] = []
    notes: list[str] = []
    unverifiable = bool(case.get("witness_missing") is True)
    if unverifiable:
        notes.append("Missing required execution witness or raw artifact")
    reg = FORMULA_REGISTRY if formula_registry is None else {**FORMULA_REGISTRY, **formula_registry}
    if isinstance(case.get("formula_oracle"), dict):
        _check_formula(case["formula_oracle"], reg, defects, notes)
    if case.get("protected_source_text") is not None:
        src_nums = sorted(set(NUMBER_RE.findall(str(case["protected_source_text"]))))
        draft_nums = set(NUMBER_RE.findall(str(case.get("claim_or_code", ""))))
        missing = [n for n in src_nums if n not in draft_nums]
        if missing:
            defects.append("plate_c:protected_number_mutated")
            notes.append(f"missing protected numbers: {missing}")
    if "self_test_score" in case and "hidden_test_score" in case:
        gap = float(case["self_test_score"]) - float(case["hidden_test_score"])
        if gap > float(case.get("max_allowed_echo_gap", 0.15)):
            defects.append("plate_c:swarm_echo_chamber_divergence")
            notes.append(f"self={case['self_test_score']} hidden={case['hidden_test_score']} gap={gap:.3f}")
    if isinstance(case.get("arithmetic_check"), dict):
        _check_arithmetic(case["arithmetic_check"], defects, notes)
    return PlateReport("C", passed=(not defects and not unverifiable), defects=defects, notes=notes), unverifiable


def verify_case(
    case: dict[str, Any], *, enable_a: bool = True, enable_b: bool = True,
    enable_c: bool = True, formula_registry: dict[str, FormulaFn] | None = None,
) -> ThreePlateVerdict:
    """Adjudicate a case across Plates A, B, and C with optional plate ablation."""
    pa = run_plate_a(case) if enable_a else PlateReport("A", passed=True, notes=["disabled"])
    pb = run_plate_b(case) if enable_b else PlateReport("B", passed=True, notes=["disabled"])
    pc, unverifiable = (
        run_plate_c(case, formula_registry=formula_registry) if enable_c
        else (PlateReport("C", passed=True, notes=["disabled"]), False)
    )
    all_defects = pa.defects + pb.defects + pc.defects
    verdict = "DRIFT" if all_defects else ("UNVERIFIABLE" if unverifiable else "MATCH")
    return ThreePlateVerdict(
        case_id=str(case.get("case_id", "unknown")), verdict=verdict,
        single_plate_verdict="MATCH" if pa.passed else "DRIFT",
        two_plate_verdict="MATCH" if (pa.passed and pb.passed) else "DRIFT",
        plate_a=pa, plate_b=pb, plate_c=pc, all_defects=all_defects,
    )
