"""Stage 4 execution-oracle validation, planted-fault sanitizer, and SFTS synthesis."""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness.verifier_sanitizer import audit_verifier_planted_wrong

BUILTIN_SFTS_RECORDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "K-001", "numerical", "log_sum_exp",
        "m + log(sum(exp(x_i - m)))",
        "Max-shifted log-sum-exp preventing float64 overflow across wide dynamic ranges",
        "ulp_err<=1e-15",
    ),
    (
        "K-002", "optimization", "birkhoff_sinkhorn",
        "P_{k+1} = diag(1 / (P_k 1)) P_k diag(1 / (P_k^T 1))",
        "Alternating row and column scaling onto the doubly stochastic Birkhoff polytope",
        "marginal_err<=1e-12",
    ),
    (
        "K-003", "statistics", "welford_online_variance",
        "M2_n = M2_{n-1} + (x_n - mean_{n-1})(x_n - mean_n)",
        "Single-pass numerically stable streaming mean and variance accumulator",
        "catastrophic_cancel=0",
    ),
    (
        "K-004", "numerical", "kahan_compensated_sum",
        "y = x_i - c; t = s + y; c = (t - s) - y; s = t",
        "Compensated floating-point summation tracking low-order rounding error",
        "rel_err<=2e-16",
    ),
    (
        "K-005", "ml_kernels", "online_safe_softmax",
        "d_i = d_{i-1} * exp(m_{i-1} - m_i) + exp(x_i - m_i)",
        "Streaming normalizer update enabling tiled single-pass attention softmax",
        "sum_prob=1.0",
    ),
    (
        "K-006", "cryptography", "rfc6962_merkle_hash",
        "MTH(d) = SHA256(0x00 || d); Node(l,r) = SHA256(0x01 || l || r)",
        "Domain-separated Merkle leaf and interior hashing preventing second-preimage forgery",
        "rfc6962_exact",
    ),
)


def _run_buildc_check(bld_code: str) -> bool:
    """Invoke buildc check on a temporary BuildLang source file if installed."""
    buildc_bin = shutil.which("buildc")
    if not buildc_bin:
        return False
    with tempfile.NamedTemporaryFile(mode="w", suffix=".bld", delete=False, encoding="utf-8") as tmp:
        tmp.write(bld_code)
        tmp_path = Path(tmp.name)
    try:
        proc = subprocess.run([buildc_bin, "check", str(tmp_path)], capture_output=True, text=True, check=False)
        return proc.returncode == 0
    except OSError:
        return False
    finally:
        tmp_path.unlink(missing_ok=True)


def validate_oracle_candidate(
    cand: dict[str, Any],
    *,
    buildc_runner: Callable[[str], bool] | None = None,
) -> tuple[bool, str]:
    """Verify candidate passes deterministic external oracle and rejects planted-wrong mutations."""
    kind = cand.get("oracle_kind", "")
    if kind == "f64_exact":
        expected = float(cand["expected_f64"])
        tol = float(cand.get("tol", 1e-12))

        def grade(ans: str) -> bool:
            match = re.search(r"FINAL_F64=([-+0-9.eE]+)", ans)
            if not match:
                return False
            try:
                return abs(float(match.group(1)) - expected) <= tol
            except ValueError:
                return False

        audit = audit_verifier_planted_wrong(f"f64:{cand['id']}", grade)
        if audit["status"] != "PASS":
            return False, "GRADER_SANITIZER_LEAKY"
        if not grade(str(cand.get("target", ""))):
            return False, "ORACLE_GOLDEN_FAILED"
        if grade(f"FINAL_F64={expected + 1.0:.12f}"):
            return False, "ORACLE_MUTATION_NOT_CAUGHT"
        return True, "OK"

    if kind == "buildlang_check":
        code = str(cand.get("reference_code", ""))
        runner = buildc_runner
        if runner is None:
            if not shutil.which("buildc"):
                return False, "BUILDC_NOT_INSTALLED"
            runner = _run_buildc_check
        if not runner(code):
            return False, "BUILDC_ORACLE_FAILED"
        broken = code.replace("-> f64", "-> bool", 1)
        if broken == code or runner(broken):
            return False, "BUILDC_MUTATION_NOT_CAUGHT"
        return True, "OK"

    if kind == "search_trace_grounded":
        req_id = str(cand["expected_source_id"])
        req_sha = str(cand["expected_evidence_sha12"])
        req_token = str(cand["expected_grounded_token"])

        def sfts_grade(ans: str) -> bool:
            return (
                "<search>" in ans
                and "<evidence" in ans
                and req_id in ans
                and req_sha in ans
                and req_token in ans
            )

        audit = audit_verifier_planted_wrong(f"sfts:{cand['id']}", sfts_grade)
        if audit["status"] != "PASS":
            return False, "GRADER_SANITIZER_LEAKY"
        if not sfts_grade(str(cand.get("target", ""))):
            return False, "SFTS_ORACLE_GOLDEN_FAILED"
        if sfts_grade(f"<search>query</search><evidence id=FAKE-999>ungrounded</evidence> {req_token}"):
            return False, "SFTS_COUNTERFACTUAL_NOT_CAUGHT"
        return True, "OK"

    if kind == "leaky_regex_trap":
        def leaky_grade(ans: str) -> bool:
            return "PASS" in ans or len(ans) >= 0

        audit = audit_verifier_planted_wrong(f"trap:{cand['id']}", leaky_grade)
        if audit["status"] != "PASS":
            return False, "GRADER_SANITIZER_LEAKY"
        return True, "OK"

    return False, f"UNKNOWN_ORACLE_KIND:{kind}"


def _build_sfts_row(
    fid: str,
    field: str,
    name: str,
    equation: str,
    what: str,
    check_note: str,
    source_label: str,
) -> dict[str, Any]:
    snippet = f"{fid} ({field}) {name}: {equation} | check={check_note}"
    ev_sha12 = hashlib.sha256(snippet.encode("utf-8")).hexdigest()[:12]
    prompt = (
        f"Search-native verification task: retrieve the canonical formula record for {name} "
        f"in domain '{field}', cite its verified ID and evidence hash, and state its defining relation."
    )
    trace = (
        f"<search>{source_label} query=\"{fid} {name}\"</search>\n"
        f"<evidence source_id=\"{fid}\" sha12=\"{ev_sha12}\">{snippet}</evidence>\n"
        f"<synthesis>Grounded in {fid} (sha12={ev_sha12}): {what}. Relation: {equation}.</synthesis>"
    )
    return {
        "id": f"forge-sfts-{fid.lower()}",
        "domain": "search_from_the_start_trace",
        "license": "clean-room-synthetic",
        "oracle_kind": "search_trace_grounded",
        "expected_source_id": fid,
        "expected_evidence_sha12": ev_sha12,
        "expected_grounded_token": fid,
        "prompt": prompt,
        "target": trace,
        "_source_corpus": "data_forge_sfts_2611_26809",
    }


def synthesize_search_from_the_start_rows(
    formulas_tsv_path: Path | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    """Search-From-The-Start (arXiv:2611.26809) retrieval-native reasoning synthesizer."""
    if formulas_tsv_path is None:
        return [
            _build_sfts_row(fid, field, name, eq, what, note, "BUILTIN_CATALOG")
            for fid, field, name, eq, what, note in BUILTIN_SFTS_RECORDS[:limit]
        ]

    if not formulas_tsv_path.is_file():
        return []
    lines = formulas_tsv_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 2:
        return []
    verified_rows: list[list[str]] = []
    for ln in lines[1:]:
        cols = ln.split("\t")
        if len(cols) >= 15 and cols[14].strip() in ("VERIFIED", "READ") and len(cols[3].strip()) >= 12:
            verified_rows.append(cols)
    verified_rows.reverse()
    return [
        _build_sfts_row(
            cols[0].strip(), cols[1].strip(), cols[2].strip(),
            cols[3].strip(), cols[4].strip(), cols[11].strip(),
            formulas_tsv_path.name,
        )
        for cols in verified_rows[:limit]
    ]


def synthesize_oracle_verified_rows(
    count_f64: int = 12,
    include_buildlang: bool | None = None,
) -> list[dict[str, Any]]:
    """Synthesize clean-room oracle-verified rows (exact f64 formulas + optional BuildLang)."""
    rows: list[dict[str, Any]] = []
    for k in range(count_f64):
        a = 1.25 + 0.37 * k
        b = 0.75 + 0.19 * k
        val = math.log(math.exp(a) + math.exp(b))
        rows.append({
            "id": f"forge-synth-f64-{k:03d}",
            "domain": "f64_oracle_synthesis",
            "license": "clean-room-synthetic",
            "oracle_kind": "f64_exact",
            "expected_f64": val,
            "tol": 1e-12,
            "prompt": f"Compute exact f64 log-sum-exp log(exp({a:.2f}) + exp({b:.2f})) to 1e-12 precision.",
            "target": f"FINAL_F64={val:.15f}",
            "_source_corpus": "data_forge_oracle_synth",
        })
    emit_bld = (shutil.which("buildc") is not None) if include_buildlang is None else include_buildlang
    if emit_bld:
        bld_snippet = (
            "fn stable_sigmoid(x: f64) -> f64 {\n"
            "    if x >= 0.0 {\n"
            "        return 1.0 / (1.0 + exp(-x));\n"
            "    }\n"
            "    let ex: f64 = exp(x);\n"
            "    ex / (1.0 + ex)\n"
            "}\n"
            "fn main() ~ Console {\n"
            "    println!(\"{:.12}\", stable_sigmoid(0.5));\n"
            "}\n"
        )
        rows.append({
            "id": "forge-synth-bld-000",
            "domain": "buildlang_oracle_synthesis",
            "license": "clean-room-synthetic",
            "oracle_kind": "buildlang_check",
            "prompt": "Write a numerically stable sigmoid kernel in BuildLang returning f64.",
            "reference_code": bld_snippet,
            "target": bld_snippet,
            "_source_corpus": "data_forge_buildc_synth",
        })
    return rows
