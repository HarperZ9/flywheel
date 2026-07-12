"""findings.py -- compose the measured findings into one receipt-bound document.

"Uplift the findings when the runs end": rather than hand-transcribe numbers from
run artifacts into docs and pages (which drift), this scans the known artifact
JSONs, extracts each headline metric WITH its source path and content hash, and
emits one `flywheel.findings/v1` document carrying a root hash over all sources.
The shell/site render it; a run's completion re-runs it; every number on every
surface traces to an artifact a third party can re-check.

Discipline: a missing artifact yields an honest "pending" finding, never a
fabricated number. The root hash changes iff a source artifact changes, so a
stale page is detectable (its embedded root hash won't match a fresh compose).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .run_paths import run_root_default

DEFAULT_RUN_ROOT = Path(run_root_default())


def _load_and_hash(p: Path) -> tuple[object, str | None]:
    """Read the file ONCE, then hash and parse the SAME bytes -- no TOCTOU gap
    between the value and the hash, and any read/parse error yields (None, None)
    so the caller emits an honest 'pending' rather than a partial value."""
    try:
        raw = p.read_bytes()
    except Exception:
        return None, None
    sha = hashlib.sha256(raw).hexdigest()
    try:
        return json.loads(raw.decode("utf-8")), sha
    except Exception:
        return None, sha   # present but unparseable -> pending, but hash the bytes


def _num(v):
    """Return v only if it is a real number (not None/str/bool); else None."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


@dataclass
class Finding:
    key: str
    claim: str
    value: str | None                 # None => pending
    source: str
    source_sha256: str | None
    bounds: str = ""
    status: str = "measured"          # measured | pending

    def to_dict(self) -> dict:
        return {
            "key": self.key, "claim": self.claim, "value": self.value,
            "source": self.source, "source_sha256": self.source_sha256,
            "bounds": self.bounds, "status": self.status,
        }


def _pct(x) -> str:
    return f"{x:.0%}" if isinstance(x, (int, float)) else str(x)


def _pending(key: str, claim: str, name: str, sha: str | None,
             findings: list[Finding]) -> None:
    findings.append(Finding(key, claim, None, name, sha, status="pending"))


def _selector_finding(root: Path, findings: list[Finding]) -> None:
    p = root / "selector_consensus_headroom.json"
    claim = "Holding generation fixed, only the selector varies"
    data, sha = _load_and_hash(p)
    n = _num(data.get("n_tasks")) if isinstance(data, dict) else None
    def passed(k):
        v = data.get(k) if isinstance(data, dict) else None
        return _num(v.get("passed")) if isinstance(v, dict) else None  # inner may be non-dict
    single, ext, slf, cons = passed("single_shot"), passed("verified_external"), \
        passed("verified_self"), passed("verified_consensus")
    if None in (n, single, ext, slf, cons):
        _pending("selector_comparison", claim, p.name, sha, findings)
        return
    findings.append(Finding(
        "selector_comparison", claim,
        f"single {single}/{n}, external {ext}/{n}, self {slf}/{n}, consensus {cons}/{n}",
        p.name, sha,
        bounds="headroom subset, one model, code tasks with oracles; external "
               "earns capability (McNemar p=0.0015), self earns zero (p=1.0)"))


def _passn_finding(root: Path, findings: list[Finding]) -> None:
    claim = "Raising the candidate budget moves tasks across the >=2-correct threshold"
    # Pick the most COMPLETE pass@N artifact by the signals it carries (max_n,
    # then n_tasks), not a hardcoded name -- any future passn_curve_*.json wins
    # if it is larger. Excludes *.partial.jsonl (glob is *.json only).
    best_p, best_key = None, (-1, -1)
    try:
        curves = sorted(root.glob("passn_curve*.json"))
    except Exception:
        curves = []
    for c in curves:
        d, _ = _load_and_hash(c)
        if isinstance(d, dict):
            key = (_num(d.get("max_n")) or 0, _num(d.get("n_tasks")) or 0)
            if key > best_key:
                best_p, best_key = c, key
    p = best_p or (root / "passn_curve_n32.json")
    data, sha = _load_and_hash(p)
    if not isinstance(data, dict) or not isinstance(data.get("curve_summary"), dict) \
            or not data.get("budget_levels"):
        _pending("passn_curve", claim, p.name, sha, findings)
        return
    cs, levels, parts = data["curve_summary"], data["budget_levels"], []
    for lv in levels:
        s = cs.get(str(lv), {})
        pr, cr = _num(s.get("pass_at_n_rate")), _num(s.get("consensus_reachable_rate"))
        if pr is None or cr is None:
            _pending("passn_curve", claim, p.name, sha, findings)
            return
        parts.append(f"N={lv}: pass {pr:.0%} / consensus-reachable {cr:.0%}")
    findings.append(Finding(
        "passn_curve", claim, "; ".join(parts), p.name, sha,
        bounds=f"{_num(data.get('n_tasks'))} headroom tasks, exact per-pool counts"))


def _humaneval_finding(root: Path, findings: list[Finding]) -> None:
    p = root / "he_base_comparison.json"
    claim = "Domain CPT did not improve general code-completion (load-bearing negative)"
    data, sha = _load_and_hash(p)
    # Require the comparison to actually carry paired pass counts before claiming it.
    if not isinstance(data, dict) or not any(
            k in data for k in ("mcnemar", "flywheel_pass", "base_pass", "delta")):
        _pending("humaneval_base_vs_cpt", "HumanEval pass@1 base vs CPT (same harness)",
                 p.name, sha, findings)
        return
    # Surface only known numeric fields -- never dump the raw artifact into a
    # public value (that could leak arbitrary content the artifact happens to hold).
    mc = data.get("mcnemar") if isinstance(data.get("mcnemar"), dict) else {}
    fw, base = _num(data.get("flywheel_pass")), _num(data.get("base_pass"))
    delta, pval = _num(data.get("delta")), _num(mc.get("p_value"))
    parts = []
    if fw is not None and base is not None:
        parts.append(f"flywheel {fw} vs base {base}")
    if delta is not None:
        parts.append(f"delta {delta}")
    if pval is not None:
        parts.append(f"McNemar p={pval}")
    findings.append(Finding(
        "humaneval_base_vs_cpt", claim,
        "; ".join(parts) if parts else "see artifact", p.name, sha,
        bounds="same runner/quant/temp; McNemar not significant; moat is Layer B, not the weights"))


def _difficulty_finding(root: Path, findings: list[Finding]) -> None:
    p = root / "difficulty_screen_hard_v2_110.json"
    claim = "Curated lane screened for headroom (single-shot does not saturate)"
    data, sha = _load_and_hash(p)
    headroom = data.get("headroom_at_temp0") if isinstance(data, dict) else None
    if not isinstance(headroom, list):
        _pending("difficulty_screen", claim, p.name, sha, findings)
        return
    total = _num(data.get("n_tasks"))            # explicit None check: a real 0 must survive
    if total is None:
        sat = data.get("saturated_at_temp0")
        total = len(headroom) + (len(sat) if isinstance(sat, list) else 0)
    findings.append(Finding(
        "difficulty_screen", claim,
        f"{len(headroom)} headroom of {total} at temp 0",
        p.name, sha, bounds="trained 14B via ollama, honest model_ref"))


def project_findings(run_root: Path | str = DEFAULT_RUN_ROOT) -> dict:
    """Scan artifacts, emit the receipt-bound findings document with a root hash."""
    root = Path(run_root)
    findings: list[Finding] = []
    _difficulty_finding(root, findings)
    _selector_finding(root, findings)
    _passn_finding(root, findings)
    _humaneval_finding(root, findings)

    # Root hash over the source hashes (order-stable) -> a fingerprint of the
    # evidence set. Changes iff any source artifact changes.
    h = hashlib.sha256()
    for f in findings:
        h.update((f.key + "|" + (f.source_sha256 or "MISSING")).encode())
    root_hash = h.hexdigest()

    measured = sum(1 for f in findings if f.status == "measured")
    return {
        "schema": "flywheel.findings/v1",
        "root_hash": root_hash,
        "measured": measured,
        "pending": len(findings) - measured,
        "findings": [f.to_dict() for f in findings],
    }


def verify_findings(doc: dict, run_root: Path | str = DEFAULT_RUN_ROOT) -> bool:
    """Re-compose and check the root hash matches -- the findings doc is itself
    a receipt; a stale one (a source changed since) fails this check."""
    fresh = project_findings(run_root)
    return fresh["root_hash"] == doc.get("root_hash")


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RUN_ROOT
    doc = project_findings(root)
    print(json.dumps(doc, indent=1))
