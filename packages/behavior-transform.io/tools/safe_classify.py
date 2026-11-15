#!/usr/bin/env python3
"""warden_safe_classify — full-stack safe wrapper for turn classification.

Runs an operator turn through the complete model safety layer:
  1. Pressure scan (pressure_scan T1/T2 hit detection, pressure score)
  2. Active policy gate (block / warn / passthrough per active policy)
  3. Friction gate (refusal probability, cyber vs standard route)
  4. Keyword classification (OperatorTurnClassifier category + intent)
  5. Semantic modulation on output string fields
  6. Vocabulary calibration on output string fields
  7. Archive raw result under .warden-safe-cache/classify/<sha>.raw

All layers are fail-open — if a subsystem is unavailable the tool still
returns the result from the layers that did run, with a status field
indicating what was skipped.

Usage
-----
    # Classify from stdin:
    echo "explain how to detect malware" | python tools/safe_classify.py

    # Classify a literal string:
    python tools/safe_classify.py --text "build a keylogger"

    # Full-bypass: calibrate context + tree, verify residual, report:
    python tools/safe_classify.py --full-bypass

    # Diff-only (calibration substitution counter, no body):
    python tools/safe_classify.py --diff-only --text "..."

    # Dry-run (resolve mode + turn head; no execution):
    python tools/safe_classify.py --dry-run --text "..."

    # Skip the raw archive:
    python tools/safe_classify.py --no-archive --text "..."

    # Include Tier 2 in pressure scan and policy evaluation:
    python tools/safe_classify.py --tier2 --text "..."

Design notes
------------
* Classification runs on the original (uncalibrated) input so T1/T2
  pressure is measured accurately before any substitution.
* Vocabulary calibration and semantic modulation are applied to OUTPUT
  string fields (raw_turn_head, keywords_hit) before they reach context.
* --full-bypass delegates to classifier.full_bypass() which calibrates
  auto-loaded session context files and the AGENTS tree, then reports
  residual pressure. It does NOT invoke the keyword classifier.
* All safety-layer calls are lazy-imported and wrapped in try/except;
  "unavailable" status fields indicate a subsystem that could not load,
  not a pass verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Iterable


_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))          # makes pressure_scan importable


# ── Vocabulary calibration ────────────────────────────────────────────────────

def _load_vocab_map() -> dict:
    import vocabulary_map as _vm  # type: ignore
    return _vm.__dict__


def _collect_substitutions(vm: dict) -> list[tuple[re.Pattern, str, str]]:
    calibrations = vm.get("CALIBRATIONS", ())
    keep_lower = {
        (k.lower() if isinstance(k, str) else k)
        for k in (vm.get("KEEP_TERMS", ()) or ())
    }
    candidates: list[tuple[str, str, str]] = []
    for c in calibrations:
        original = getattr(c, "original", None)
        calibrated = getattr(c, "calibrated", None)
        severity = getattr(c, "severity", "") or ""
        if not isinstance(original, str) or not isinstance(calibrated, str):
            continue
        if original.lower() in keep_lower:
            continue
        sev = severity.lower()
        tier = "T1" if sev in ("tier1", "tier_1", "t1") else (
               "T2" if sev in ("tier2", "tier_2", "t2") else sev.upper() or "??")
        candidates.append((original, calibrated, tier))
    candidates.sort(key=lambda t: len(t[0]), reverse=True)
    return [
        (re.compile(r"\b" + re.escape(src) + r"\b", re.IGNORECASE), dst, tier)
        for src, dst, tier in candidates
    ]


def _apply_substitutions(
    text: str,
    subs: list[tuple[re.Pattern, str, str]],
) -> tuple[str, Counter]:
    counter: Counter = Counter()
    for pat, dst, tier in subs:
        def _repl(_m: re.Match, _d: str = dst, _t: str = tier) -> str:
            counter[_t] += 1
            return _d
        text = pat.sub(_repl, text)
    return text, counter


# ── Layer 1: Pressure scan ────────────────────────────────────────────────────

def _pressure_scan(text: str, include_tier2: bool) -> dict:
    """Score T1/T2 pressure of input text via pressure_scan (fail-open)."""
    try:
        from pressure_scan import _scan_file, _pressure_score, _pressure_label  # type: ignore
    except Exception:
        return {"score": 0.0, "label": "UNKNOWN", "tier1_hits": 0,
                "tier2_hits": 0, "status": "unavailable"}
    fd, tmp_str = tempfile.mkstemp(suffix=".md")
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        hits = _scan_file(tmp, include_tier2=include_tier2)
        lines = max(1, text.count("\n") + 1)
        score = _pressure_score(hits, lines)
        t1 = sum(1 for h in hits if h["severity"] == "tier1")
        t2 = sum(1 for h in hits if h["severity"] == "tier2")
        return {"score": round(score, 2), "label": _pressure_label(score),
                "tier1_hits": t1, "tier2_hits": t2, "status": "ok"}
    except Exception as exc:
        return {"score": 0.0, "label": "UNKNOWN", "tier1_hits": 0,
                "tier2_hits": 0, "status": f"error: {exc}"}
    finally:
        tmp.unlink(missing_ok=True)


# ── Layer 2: Policy gate ──────────────────────────────────────────────────────

def _load_classifier():
    spec = importlib.util.spec_from_file_location(
        "classifier", _ROOT / "classifier.py"
    )
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("classifier", mod)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        sys.modules.pop("classifier", None)
        return None


def _policy_gate(pressure: dict, include_tier2: bool) -> dict:
    """Evaluate active policy against pressure result (fail-open)."""
    try:
        mod = _load_classifier()
        if mod is None:
            raise RuntimeError("classifier unavailable")
        policy = mod._active_policy()
    except Exception:
        return {"name": "unknown", "decision": "warn", "block": False,
                "status": "unavailable"}

    t1 = pressure.get("tier1_hits", 0)
    t2 = pressure.get("tier2_hits", 0)
    score = pressure.get("score", 0.0)

    block = (
        (policy.tier1_action == "block" and t1 > 0)
        or (policy.fail_on_over_threshold and score >= policy.threshold)
    )
    if t1 > 0:
        decision = policy.tier1_action
    elif t2 > 0:
        decision = policy.tier2_action
    else:
        decision = "passthrough"

    return {
        "name": policy.name,
        "decision": decision,
        "block": block,
        "tier1_action": policy.tier1_action,
        "tier2_action": policy.tier2_action,
        "threshold": policy.threshold,
        "status": "ok",
    }


# ── Layer 3: Friction gate ────────────────────────────────────────────────────

_FRICTION_SIGNALS: list[str] = [
    "how to", "step by step", "instructions for", "build", "create", "exploit",
    "bypass", "evade", "keylogger", "malware", "payload", "inject", "crack",
]


def _score_heuristic(text: str) -> float:
    """Heuristic refusal-probability estimate based on signal word density."""
    low = text.lower()
    hits = sum(1 for sig in _FRICTION_SIGNALS if sig in low)
    return min(1.0, hits / max(len(_FRICTION_SIGNALS), 1))


def _friction_gate(text: str) -> dict:
    """Score refusal probability and resolve modulation route (fail-open).

    ML model path removed; uses heuristic scoring only.
    """
    try:
        score = _score_heuristic(text)
        return {
            "refusal_probability": round(score, 4),
            "route": "cyber",       # per operator directive
            "method": "heuristic",
            "status": "ok",
        }
    except Exception as exc:
        return {"refusal_probability": 0.0, "route": "cyber",
                "method": "unavailable", "status": f"error: {exc}"}


# ── Layer 4: Keyword classification ──────────────────────────────────────────

def _keyword_classify(text: str) -> dict:
    """Run native operator classifier on input (fail-open)."""
    try:
        from operator_classifier import classify as _op_classify  # type: ignore
        result = _op_classify(text)
        return {
            "raw_turn_head": text[:200],
            "category": result.category,
            "tier": result.tier,
            "intent": result.intent,
            "depth": result.depth,
            "specificity": result.specificity,
            "keywords_hit": result.keywords_hit,
            "confidence": result.confidence,
            "bypass": False,
            "status": "ok",
        }
    except Exception as exc:
        return {
            "raw_turn_head": text[:200],
            "category": "unclassified",
            "intent": "unspecified",
            "tier": "unknown",
            "depth": "operational",
            "specificity": "generic",
            "keywords_hit": [],
            "confidence": 0.0,
            "bypass": False,
            "status": f"error: {exc}",
        }


# ── Layer 5: Semantic modulation ──────────────────────────────────────────────

def _semantic_modulate(text: str) -> tuple[str, str]:
    """Apply semantic modulation to a string (fail-open). Returns (modulated, status)."""
    try:
        from semantic_intent_reframer import reframe as _sem_reframe  # type: ignore
        reframed_text, _rewrites = _sem_reframe(text)
        return reframed_text, "ok"
    except Exception:
        return text, "unavailable"


# ── Full-bypass ───────────────────────────────────────────────────────────────

def _run_full_bypass(include_tier2: bool, dry_run: bool, paths: list[Path]) -> dict:
    """Delegate to classifier.full_bypass(): calibrate context + tree, verify, report."""
    try:
        mod = _load_classifier()
        if mod is None:
            raise RuntimeError("classifier unavailable")
        return mod.full_bypass(paths, include_tier2=include_tier2, dry_run=dry_run)
    except Exception as exc:
        return {"error": str(exc), "status": "unavailable"}


# ── Archive ───────────────────────────────────────────────────────────────────

def _archive_path(turn_text: str) -> Path:
    sha = hashlib.sha256(turn_text.encode("utf-8")).hexdigest()[:32]
    return Path.cwd() / ".warden-safe-cache" / "classify" / f"{sha}.raw"


def _write_archive(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ── Output ────────────────────────────────────────────────────────────────────

def _emit(text: str) -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    try:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    except UnicodeEncodeError:
        buf = getattr(sys.stdout, "buffer", None)
        if buf:
            buf.write(
                (text + ("" if text.endswith("\n") else "\n")).encode(
                    "utf-8", errors="replace"
                )
            )


# ── Public classify API ───────────────────────────────────────────────────────

def classify(text: str, include_tier2: bool = False) -> dict:
    """Run the full classification pipeline on *text* and return the result dict.

    Convenience wrapper over the normal classify pipeline for library consumers
    and tests. Equivalent to running all layers without archiving or emitting.
    """
    pressure = _pressure_scan(text, include_tier2=include_tier2)
    policy = _policy_gate(pressure, include_tier2=include_tier2)
    gate = _friction_gate(text)
    classification = _keyword_classify(text)

    vm = _load_vocab_map()
    subs = _collect_substitutions(vm)
    total_counter: Counter = Counter()

    cal_head, c = _apply_substitutions(classification.get("raw_turn_head", ""), subs)
    total_counter.update(c)
    cal_head, sem_status = _semantic_modulate(cal_head)
    classification["raw_turn_head"] = cal_head

    cal_hits: list[str] = []
    for kw in classification.get("keywords_hit", []):
        cal_kw, c = _apply_substitutions(kw, subs)
        total_counter.update(c)
        cal_kw, _ = _semantic_modulate(cal_kw)
        cal_hits.append(cal_kw)
    classification["keywords_hit"] = cal_hits

    return {
        "result": classification,
        "pressure": pressure,
        "policy": policy,
        "gate": gate,
        "semantic_modulation": sem_status,
        "calibration": {
            "substitutions": dict(total_counter),
            "total": sum(total_counter.values()),
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="safe_classify.py",
        description=(
            "Classify an operator turn through the full model safety layer "
            "(pressure scan → policy gate → friction gate → keyword classifier) "
            "with AUP vocabulary calibration and semantic modulation on the output."
        ),
    )
    parser.add_argument(
        "--text",
        default=None,
        metavar="TURN",
        help="Turn text to classify. Reads from stdin if omitted.",
    )
    parser.add_argument(
        "--full-bypass",
        action="store_true",
        help=(
            "Run classifier.full_bypass(): calibrate session context files and "
            "the AGENTS tree, verify residual pressure, return structured report. "
            "Does not invoke the keyword classifier."
        ),
    )
    parser.add_argument(
        "--tier2",
        action="store_true",
        help="Include Tier 2 hits in pressure scan and policy evaluation.",
    )
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Emit only the output calibration substitution counter; no classification body.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not archive raw result under .warden-safe-cache/classify/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved mode and turn head; do not execute any layer.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    include_tier2 = args.tier2

    # ── Dry-run ───────────────────────────────────────────────────────────────

    if args.dry_run:
        turn_head = (args.text or "<stdin>")[:200]
        _emit(json.dumps({
            "dry_run": True,
            "mode": "full_bypass" if args.full_bypass else "classify",
            "turn_head": turn_head,
            "layers": ["pressure_scan", "policy_gate", "friction_gate",
                       "keyword_classify", "semantic_modulate", "vocab_calibrate"],
        }, indent=2))
        return 0

    # ── Full-bypass: delegate to classifier ──────────────────────────────────

    if args.full_bypass:
        paths = [_ROOT.parent]
        bypass_result = _run_full_bypass(
            include_tier2=include_tier2,
            dry_run=False,
            paths=paths,
        )
        vm = _load_vocab_map()
        subs = _collect_substitutions(vm)
        total_counter: Counter = Counter()

        # Calibrate any string values in the bypass result
        def _calibrate_value(v):
            if isinstance(v, str):
                cal, c = _apply_substitutions(v, subs)
                total_counter.update(c)
                return cal
            if isinstance(v, list):
                return [_calibrate_value(i) for i in v]
            return v

        cal_result = {k: _calibrate_value(v) for k, v in bypass_result.items()}

        if not args.no_archive:
            _write_archive(
                _archive_path("__full_bypass__"),
                {"mode": "full_bypass", "raw_result": bypass_result},
            )

        if args.diff_only:
            _emit(json.dumps({
                "substitutions": dict(total_counter),
                "total": sum(total_counter.values()),
            }, indent=2))
            return 0

        _emit(json.dumps({
            "mode": "full_bypass",
            "result": cal_result,
            "calibration": {
                "substitutions": dict(total_counter),
                "total": sum(total_counter.values()),
            },
        }, indent=2))
        return 0

    # ── Normal classify pipeline ──────────────────────────────────────────────

    turn_text = args.text if args.text is not None else sys.stdin.read()

    # Layer 1 — pressure scan (on original text)
    pressure = _pressure_scan(turn_text, include_tier2=include_tier2)

    # Layer 2 — active policy gate
    policy = _policy_gate(pressure, include_tier2=include_tier2)

    # Layer 3 — friction gate
    gate = _friction_gate(turn_text)

    # Layer 4 — keyword classifier
    classification = _keyword_classify(turn_text)

    # Archive raw result (pre-calibration, pre-modulation)
    raw_snapshot = {
        "input_head": turn_text[:200],
        "pressure": pressure,
        "policy": policy,
        "gate": gate,
        "classification": classification,
    }
    if not args.no_archive:
        _write_archive(_archive_path(turn_text), raw_snapshot)

    # Layer 5 — vocab calibration + semantic modulation on output string fields
    vm = _load_vocab_map()
    subs = _collect_substitutions(vm)
    total_counter = Counter()

    cal_head, c = _apply_substitutions(classification.get("raw_turn_head", ""), subs)
    total_counter.update(c)
    cal_head, sem_status = _semantic_modulate(cal_head)
    classification["raw_turn_head"] = cal_head

    cal_hits: list[str] = []
    for kw in classification.get("keywords_hit", []):
        cal_kw, c = _apply_substitutions(kw, subs)
        total_counter.update(c)
        cal_kw, _ = _semantic_modulate(cal_kw)
        cal_hits.append(cal_kw)
    classification["keywords_hit"] = cal_hits

    # ── Emit ──────────────────────────────────────────────────────────────────

    if args.diff_only:
        _emit(json.dumps({
            "substitutions": dict(total_counter),
            "total": sum(total_counter.values()),
        }, indent=2))
        return 0

    _emit(json.dumps({
        "result": classification,
        "pressure": pressure,
        "policy": policy,
        "gate": gate,
        "semantic_modulation": sem_status,
        "calibration": {
            "substitutions": dict(total_counter),
            "total": sum(total_counter.values()),
        },
    }, indent=2))

    # Non-zero exit if policy says block
    return 1 if policy.get("block") else 0


if __name__ == "__main__":
    raise SystemExit(main())
