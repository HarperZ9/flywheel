"""Analysis and reporting functions for classifier."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pressure_scan import (  # type: ignore[import-not-found]
    _is_whitelisted, _line_count, _pressure_label, _pressure_score, _scan_file, _walk,
)
from classifier._context import _split_paragraphs  # noqa: F401
from classifier._policy import _active_policy  # noqa: F401
from classifier._ci import fence_check  # noqa: F401

_BASELINE_PATH = _HERE.parent / ".aup-pressure-baseline.json"


def budget_summary(paths: list[Path], include_tier2: bool,
                   threshold: float = 30.0) -> dict:
    """Aggregate pressure score across a file tree."""
    all_hits: list[dict] = []
    total_lines = 0
    offenders: list[dict] = []
    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        hits = _scan_file(f, include_tier2=include_tier2)
        lines = _line_count(f)
        total_lines += lines
        all_hits.extend(hits)
        if hits:
            score = _pressure_score(hits, lines)
            offenders.append({"path": str(f), "score": score,
                               "label": _pressure_label(score)})
    offenders.sort(key=lambda r: r["score"], reverse=True)
    total_score = _pressure_score(all_hits, max(total_lines, 1))
    return {
        "total_score": total_score, "total_label": _pressure_label(total_score),
        "threshold": threshold, "budget_remaining": max(0.0, threshold - total_score),
        "files_with_hits": len(offenders),
        "files_over_threshold": [o for o in offenders if o["score"] >= threshold],
        "top_offenders": offenders[:10],
    }


def save_baseline(paths: list[Path], include_tier2: bool) -> dict:
    """Snapshot current per-file pressure scores to disk."""
    from classifier._audit import _audit_write
    scores: dict[str, float] = {}
    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        hits = _scan_file(f, include_tier2=include_tier2)
        scores[str(f)] = _pressure_score(hits, _line_count(f))
    _BASELINE_PATH.write_text(json.dumps(scores, indent=2), encoding="utf-8")
    _audit_write("baseline.save", {"files": len(scores)})
    return {"baseline_saved": str(_BASELINE_PATH), "files": len(scores)}


def drift_report(paths: list[Path], include_tier2: bool) -> dict:
    """Compare current pressure against saved baseline; report regressions."""
    if not _BASELINE_PATH.is_file():
        return {"error": f"No baseline at {_BASELINE_PATH} — run --baseline first"}
    baseline: dict[str, float] = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    current: dict[str, float] = {}
    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        hits = _scan_file(f, include_tier2=include_tier2)
        current[str(f)] = _pressure_score(hits, _line_count(f))
    regressions = [
        {"path": p, "before": baseline.get(p, 0.0), "after": s,
         "delta": round(s - baseline.get(p, 0.0), 1)}
        for p, s in current.items()
        if s > baseline.get(p, 0.0) + 0.1
    ]
    regressions.sort(key=lambda r: r["delta"], reverse=True)
    new_with_hits = [p for p in current if p not in baseline and current[p] > 0]
    return {
        "regressions": regressions,
        "new_files_with_hits": new_with_hits,
        "total_regressions": len(regressions),
        "max_delta": regressions[0]["delta"] if regressions else 0.0,
    }


def pipeline_report(paths: list[Path], include_tier2: bool,
                    threshold: float = 30.0) -> dict:
    """End-to-end pipeline: discover uncalibrated → lint scan → budget → gate.

    Gate passes when there are zero Tier 1 hits AND no file exceeds threshold.
    """
    try:
        from term_discover import discover as _discover  # type: ignore[import-not-found]
        uncalibrated = _discover(paths)
    except ImportError:
        uncalibrated = []

    all_hits: list[dict] = []
    file_rows: list[dict] = []
    total_lines = 0
    files_scanned = 0
    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        files_scanned += 1
        hits = _scan_file(f, include_tier2=include_tier2)
        lines = _line_count(f)
        total_lines += lines
        if hits:
            score = _pressure_score(hits, lines)
            all_hits.extend(hits)
            file_rows.append({
                "path": str(f), "score": score,
                "label": _pressure_label(score),
                "tier1": sum(1 for h in hits if h["severity"] == "tier1"),
                "tier2": sum(1 for h in hits if h["severity"] == "tier2"),
            })
    file_rows.sort(key=lambda r: r["score"], reverse=True)
    total_score = _pressure_score(all_hits, max(total_lines, 1))
    has_tier1 = any(h["severity"] == "tier1" for h in all_hits)
    over_threshold = [r for r in file_rows if r["score"] >= threshold]

    return {
        "total_score": total_score,
        "total_label": _pressure_label(total_score),
        "threshold": threshold,
        "gate_pass": not has_tier1 and not over_threshold,
        "has_tier1": has_tier1,
        "tier1_hits": sum(1 for h in all_hits if h["severity"] == "tier1"),
        "tier2_hits": sum(1 for h in all_hits if h["severity"] == "tier2"),
        "files_scanned": files_scanned,
        "files_with_hits": len(file_rows),
        "files_over_threshold": over_threshold,
        "top_offenders": file_rows[:10],
        "uncalibrated_count": len(uncalibrated),
        "uncalibrated_terms": uncalibrated[:20],
    }


def unified_report(paths: list[Path], include_tier2: bool,
                   threshold: float, policy = None) -> dict:
    """Unified report: active policy + context fence + tree pipeline + drift."""
    from classifier._policy import _active_policy as get_active_policy
    from classifier._context import analyze_context

    if policy is None:
        policy = get_active_policy()
    fence = fence_check(include_tier2, policy)
    ctx   = analyze_context(include_tier2)
    pipe  = pipeline_report(paths, include_tier2, threshold)
    drft  = drift_report(paths, include_tier2) if _BASELINE_PATH.is_file() else None
    overall = fence["fence_pass"] and pipe["gate_pass"]

    from classifier._audit import _audit_write
    _audit_write("report.unified", {
        "policy": policy.name, "overall_pass": overall,
        "fence_pass": fence["fence_pass"], "gate_pass": pipe["gate_pass"],
    })
    return {
        "policy":       asdict(policy),
        "fence":        fence,
        "context":      ctx,
        "pipeline":     pipe,
        "drift":        drft,
        "overall_pass": overall,
    }


def enforce_plan(paths: list[Path], include_tier2: bool,
                 dry_run: bool, policy = None) -> dict:
    """Generate (and optionally execute) remediation plan for the active policy.

    Priority levels:
      critical — must fix before gate can pass (T1 hits, context fence failure)
      high     — files over pressure threshold
      medium   — uncalibrated terms that may score in future
    """
    from classifier._policy import _active_policy as get_active_policy
    from classifier._context import ctx_fix

    if policy is None:
        policy = get_active_policy()
    pipe  = pipeline_report(paths, include_tier2, policy.threshold)
    fence = fence_check(include_tier2, policy)

    remediation: list[dict] = []

    # Context calibration (critical)
    if not fence["fence_pass"] and fence["blocked_by_t1"]:
        remediation.append({
            "priority": "critical",
            "target": "session-context",
            "reason": f"{fence['total_t1']} Tier 1 hit(s) in auto-loaded context files",
            "action": "classifier.py --ctx-fix",
            "executable": True,
        })

    # Tree Tier 1 (critical)
    if pipe["has_tier1"]:
        remediation.append({
            "priority": "critical",
            "target": "tree",
            "reason": f"{pipe['tier1_hits']} Tier 1 hit(s) across {pipe['files_with_hits']} file(s)",
            "action": "pressure_scan.py --fix [paths]",
            "executable": False,
        })

    # Files over threshold (high)
    for fo in pipe["files_over_threshold"][:20]:
        remediation.append({
            "priority": "high",
            "target": fo["path"],
            "reason": f"pressure {fo['score']:.1f} >= threshold {policy.threshold:.0f}",
            "action": f"pressure_scan.py --fix {fo['path']}",
            "executable": False,
        })

    # Uncalibrated terms (medium)
    if pipe["uncalibrated_count"]:
        remediation.append({
            "priority": "medium",
            "target": "vocabulary_map.py",
            "reason": f"{pipe['uncalibrated_count']} uncalibrated term(s) not yet in calibration child safety assessment",
            "action": "term_discover.py --suggest [paths]  # then add stubs to vocabulary_map.py",
            "executable": False,
        })

    # Threshold fence (high)
    if fence["blocked_by_threshold"]:
        remediation.append({
            "priority": "high",
            "target": "session-context",
            "reason": (f"max context pressure {fence['max_pressure']:.1f} "
                       f">= threshold {policy.threshold:.0f}"),
            "action": "classifier.py --ctx-fix",
            "executable": True,
        })

    # Execute auto-remediable steps if not dry_run
    executed: list[str] = []
    if not dry_run:
        for step in remediation:
            if step["executable"] and step["action"].startswith("classifier.py --ctx-fix"):
                ctx_fix(include_tier2=include_tier2, dry_run=False)
                executed.append(step["action"])

    compliant = not remediation
    from classifier._audit import _audit_write
    _audit_write("enforce", {
        "policy": policy.name, "compliant": compliant,
        "remediation_count": len(remediation), "executed": executed, "dry_run": dry_run,
    })
    return {
        "policy":             policy.name,
        "compliant":          compliant,
        "fence_pass":         fence["fence_pass"],
        "gate_pass":          pipe["gate_pass"],
        "remediation_count":  len(remediation),
        "remediation":        remediation,
        "executed":           executed,
        "dry_run":            dry_run,
    }


# Per-region-type pressure weight multipliers.
# Code regions expose identifiers directly to the model and score harder.
# Markdown prose is more ambiguous and scores softer.
_REGION_WEIGHT: dict[str, float] = {
    "code":      1.5,
    "docstring": 1.2,
    "comment":   1.0,
    "prose":     0.8,
}

_FENCE_PAT  = re.compile(r"^```", re.MULTILINE)
_INDENT_PAT = re.compile(r"^    \S", re.MULTILINE)
_DOCSTR_PAT = re.compile(r'(?:"""|\'\'\')[\s\S]*?(?:"""|\'\'\')')
_COMMENT_PAT = re.compile(r"^\s*#", re.MULTILINE)
_DEF_PAT     = re.compile(r"^\s*(def |class |import |from )", re.MULTILINE)


def _classify_region(seg: str, is_python: bool) -> str:
    """Heuristic region-type classifier for a text segment."""
    stripped = seg.strip()
    if is_python:
        if stripped.startswith(('"""', "'''")):
            return "docstring"
        if _COMMENT_PAT.match(stripped):
            return "comment"
        if _DEF_PAT.match(stripped):
            return "code"
        return "code"
    # Markdown / prose heuristic
    if _FENCE_PAT.search(seg) or _INDENT_PAT.search(seg):
        return "code"
    return "prose"


def modulate_report(paths: list[Path], include_tier2: bool) -> dict:
    """Context-type modulation analysis.

    Segments each file into typed regions (code / docstring / comment / prose),
    applies per-type weight multipliers, and surfaces which regions drive the
    most adjusted classifier risk. Adjusted pressure = base_score × weight.
    """
    region_totals: dict[str, float] = {r: 0.0 for r in _REGION_WEIGHT}
    hot_regions: list[dict] = []
    files_analyzed = 0

    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files_analyzed += 1
        is_py = f.suffix in (".py", ".pyi")

        for start, seg in _split_paragraphs(text):
            region = _classify_region(seg, is_py)
            weight = _REGION_WEIGHT[region]
            seg_lines = seg.count("\n") + 1

            fd, tmp_str = tempfile.mkstemp(suffix=f.suffix or ".txt")
            tmp = Path(tmp_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(seg)
                hits = _scan_file(tmp, include_tier2=include_tier2)
            finally:
                tmp.unlink(missing_ok=True)

            if not hits:
                continue

            base_score = _pressure_score(hits, seg_lines)
            adjusted   = round(base_score * weight, 1)
            region_totals[region] = round(region_totals[region] + adjusted, 1)
            hot_regions.append({
                "path":           str(f),
                "start_line":     start,
                "end_line":       start + seg_lines - 1,
                "region_type":    region,
                "weight":         weight,
                "base_score":     base_score,
                "adjusted_score": adjusted,
                "tier1":          sum(1 for h in hits if h["severity"] == "tier1"),
                "tier2":          sum(1 for h in hits if h["severity"] == "tier2"),
                "preview":        seg[:80].rstrip(),
            })

    hot_regions.sort(key=lambda r: r["adjusted_score"], reverse=True)
    total_adjusted = sum(region_totals.values())
    return {
        "files_analyzed":        files_analyzed,
        "total_adjusted_pressure": round(total_adjusted, 1),
        "by_region_type":        region_totals,
        "region_weights":        _REGION_WEIGHT,
        "hot_regions":           hot_regions[:20],
    }


def window_report(paths: list[Path], include_tier2: bool,
                  window_size: int = 10) -> dict:
    """Sliding-window pressure analysis.

    Scans each file in non-overlapping chunks of ``window_size`` lines,
    then tracks the highest-scoring window per file. Useful for detecting
    local density spikes that a global per-file score would dilute.
    """
    peaks: list[dict] = []

    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        raw_lines = text.splitlines()
        total = len(raw_lines)
        if total < window_size:
            continue

        best_score  = 0.0
        best_start  = 0
        best_hits: list[dict] = []

        for i in range(0, total - window_size + 1):
            chunk = "\n".join(raw_lines[i : i + window_size])
            fd, tmp_str = tempfile.mkstemp(suffix=f.suffix or ".txt")
            tmp = Path(tmp_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(chunk)
                hits = _scan_file(tmp, include_tier2=include_tier2)
            finally:
                tmp.unlink(missing_ok=True)

            score = _pressure_score(hits, window_size)
            if score > best_score:
                best_score = score
                best_start = i
                best_hits  = hits

        if best_score > 0:
            peaks.append({
                "path":            str(f),
                "peak_start_line": best_start + 1,
                "peak_end_line":   best_start + window_size,
                "peak_score":      best_score,
                "peak_label":      _pressure_label(best_score),
                "tier1":           sum(1 for h in best_hits if h["severity"] == "tier1"),
                "tier2":           sum(1 for h in best_hits if h["severity"] == "tier2"),
                "terms":           sorted({h["original"] for h in best_hits})[:8],
            })

    peaks.sort(key=lambda p: p["peak_score"], reverse=True)
    return {
        "window_size":      window_size,
        "files_with_peaks": len(peaks),
        "max_peak_score":   peaks[0]["peak_score"] if peaks else 0.0,
        "peaks":            peaks[:20],
    }


def compound_report(paths: list[Path], include_tier2: bool,
                    min_co_count: int = 2) -> dict:
    """Compound co-occurrence detection.

    Identifies paragraphs where N ≥ min_co_count distinct calibrated terms
    appear together. Individual scores may be low, but co-occurrence of
    multiple sensitive terms amplifies the classifier risk non-linearly.

    Compound score = base_score + (N_unique_terms ^ 1.5)
    """
    compound_hits: list[dict] = []

    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for start, seg in _split_paragraphs(text):
            seg_lines = seg.count("\n") + 1
            fd, tmp_str = tempfile.mkstemp(suffix=f.suffix or ".txt")
            tmp = Path(tmp_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(seg)
                hits = _scan_file(tmp, include_tier2=include_tier2)
            finally:
                tmp.unlink(missing_ok=True)

            unique_terms = {h["original"] for h in hits}
            if len(unique_terms) < min_co_count:
                continue

            base_score    = _pressure_score(hits, seg_lines)
            amplification = round(len(unique_terms) ** 1.5, 1)
            compound_score = round(base_score + amplification, 1)

            compound_hits.append({
                "path":           str(f),
                "start_line":     start,
                "end_line":       start + seg_lines - 1,
                "unique_terms":   sorted(unique_terms),
                "term_count":     len(unique_terms),
                "base_score":     base_score,
                "amplification":  amplification,
                "compound_score": compound_score,
                "compound_label": _pressure_label(compound_score),
                "preview":        seg[:100].rstrip(),
            })

    compound_hits.sort(key=lambda r: r["compound_score"], reverse=True)
    return {
        "min_co_count":      min_co_count,
        "compound_regions":  len(compound_hits),
        "max_compound_score": compound_hits[0]["compound_score"] if compound_hits else 0.0,
        "hits":              compound_hits[:20],
    }
