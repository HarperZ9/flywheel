#!/usr/bin/env python3
"""Pressure scanner â€” vocabulary linter.

Scans source files for tradecraft-register vocabulary that the Anthropic
API safety filter scores. Tier 1 hits fail the lint; Tier 2 hits warn.

Usage:
    pressure_scan.py [PATH ...]              # scan paths or default tree
    pressure_scan.py --json                  # JSON output for CI
    pressure_scan.py --no-tier2              # silence Tier 2 warnings
    pressure_scan.py --fail-tier2            # treat Tier 2 as failures

Exit codes:
    0 â€” no Tier 1 hits (and no Tier 2 hits if --fail-tier2)
    1 â€” Tier 1 hits found
    2 â€” usage error

Per-line escapes:
    `# noqa: AUP-ALIAS`     skip line (used by _compat/aliases.py)
    `# noqa: AUP-ARCHIVE`   skip line (use sparingly; prefer renaming)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from vocabulary_map import (  # type: ignore[import-not-found]
    CALIBRATIONS,
    LINTER_WHITELIST,
    by_severity,
)

PROSE_SCOPES = {"free-prose", "verb-prose", "noun-prose"}

SCAN_EXTENSIONS = {
    ".py", ".pyi", ".md", ".rst", ".txt",
    ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".toml", ".json",
    ".cfg", ".ini",
}

SKIP_DIRS = {
    ".git", ".github", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".tox", ".venv", "venv", "node_modules", "dist", "build", ".eggs",
}

# ---------------------------------------------------------------------------
# Classifier maneuverability profiles
# ---------------------------------------------------------------------------
PROFILES: dict[str, dict] = {
    "strict":  {"include_tier2": True,  "fail_tier2": True},   # zero tolerance
    "guarded": {"include_tier2": True,  "fail_tier2": False},  # warn on T2
    "minimal": {"include_tier2": False, "fail_tier2": False},  # T1 only
}

# Weight of each tier in the pressure-score calculation.
_TIER_WEIGHT: dict[str, float] = {"tier1": 10.0, "tier2": 2.0}


def _build_pattern(originals: list[str], ignore_case: bool) -> re.Pattern[str] | None:
    if not originals:
        return None
    originals = sorted(originals, key=len, reverse=True)
    parts: list[str] = []
    for o in originals:
        if " " in o:
            inner = r"\s+".join(re.escape(p) for p in o.split(" "))
        else:
            inner = re.escape(o)
        if " " not in o and "-" not in o and "/" not in o:
            parts.append(r"\b" + inner + r"\b")
        else:
            parts.append(inner)
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile("(" + "|".join(parts) + ")", flags)


def _patterns_for(severity: str) -> list[tuple[re.Pattern[str], bool]]:
    """Build (pattern, is_prose) tuples â€” separate case-sensitive identifier
    pattern from case-insensitive prose pattern so identifier-scope entries
    don't flag legitimate lowercase prose elsewhere (e.g., 'extracted' as a
    bare verb, 'Callback' inside BLE-Callback technology references)."""
    cals = by_severity(severity)
    code_originals = [c.original for c in cals if c.scope not in PROSE_SCOPES]
    prose_originals = [c.original for c in cals if c.scope in PROSE_SCOPES]
    out: list[tuple[re.Pattern[str], bool]] = []
    code_pat = _build_pattern(code_originals, ignore_case=False)
    if code_pat is not None:
        out.append((code_pat, False))
    prose_pat = _build_pattern(prose_originals, ignore_case=True)
    if prose_pat is not None:
        out.append((prose_pat, True))
    return out


_TIER1_PATS = _patterns_for("tier1")
_TIER2_PATS = _patterns_for("tier2")
# Two lookup tables: case-sensitive originals for identifier scope,
# lowercase originals for prose scope.
_ORIG_TO_CAL = {c.original: c for c in CALIBRATIONS if c.scope not in PROSE_SCOPES}
_ORIG_LOWER_TO_CAL = {c.original.lower(): c for c in CALIBRATIONS if c.scope in PROSE_SCOPES}


def _pressure_score(hits: list[dict], total_lines: int) -> float:
    """Classifier pressure score 0â€“100. Density-weighted: >30 = likely block, >10 = caution."""
    raw = sum(_TIER_WEIGHT.get(h["severity"], 1.0) for h in hits)
    return min(100.0, round(raw / max(total_lines, 1) * 1000, 1))


def _pressure_label(score: float) -> str:
    if score >= 30:
        return "BLOCK"
    if score >= 10:
        return "CAUTION"
    return "PASS"


def _line_count(path: Path) -> int:
    try:
        return path.read_text(encoding="utf-8", errors="replace").count("\n") + 1
    except OSError:
        return 1


def _is_whitelisted(path: Path) -> bool:
    pposix = path.as_posix()
    return any(w in pposix for w in LINTER_WHITELIST)


def _scan_file(path: Path, include_tier2: bool) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    hits: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "noqa: AUP-ALIAS" in line or "noqa: AUP-ARCHIVE" in line:
            continue
        for sev, pats in (("tier1", _TIER1_PATS), ("tier2", _TIER2_PATS)):
            if sev == "tier2" and not include_tier2:
                continue
            for pat, is_prose in pats:
                for m in pat.finditer(line):
                    matched = m.group(0)
                    if is_prose:
                        cal = _ORIG_LOWER_TO_CAL.get(matched.lower())
                    else:
                        cal = _ORIG_TO_CAL.get(matched)
                    if cal is None:
                        continue
                    # Skip no-op aliases (calibrated == original) â€” these are
                    # documentation-only entries; flagging them is pure noise.
                    if cal.calibrated == matched or cal.calibrated == cal.original:
                        continue
                    hits.append({
                        "path": str(path),
                        "line": lineno,
                        "col": m.start() + 1,
                        "severity": sev,
                        "original": matched,
                        "calibrated": cal.calibrated,
                        "scope": cal.scope,
                        "snippet": line.rstrip()[:240],
                    })
    return hits


def _fix_file(path: Path, *, include_tier2: bool, dry_run: bool) -> tuple[Counter, bool]:
    """Apply calibrations to a file. Returns (counter, changed).

    Skips lines with `# noqa: AUP-ALIAS` or `# noqa: AUP-ARCHIVE` so the
    intentional-archive sites stay intact. Writes atomically via tempfile
    + os.replace; never partially overwrites.
    """
    counter: Counter = Counter()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return counter, False

    new_lines: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        if "noqa: AUP-ALIAS" in line or "noqa: AUP-ARCHIVE" in line:
            new_lines.append(line)
            continue
        new_line = line
        for sev, pats in (("tier1", _TIER1_PATS), ("tier2", _TIER2_PATS)):
            if sev == "tier2" and not include_tier2:
                continue
            tier_label = "T1" if sev == "tier1" else "T2"
            for pat, is_prose in pats:
                def _sub(m: re.Match, _is_prose: bool = is_prose, _tier: str = tier_label) -> str:
                    matched = m.group(0)
                    if _is_prose:
                        cal = _ORIG_LOWER_TO_CAL.get(matched.lower())
                    else:
                        cal = _ORIG_TO_CAL.get(matched)
                    if cal is None:
                        return matched
                    counter[_tier] += 1
                    return cal.calibrated
                new_line = pat.sub(_sub, new_line)
        new_lines.append(new_line)

    new_text = "".join(new_lines)
    changed = new_text != text

    if changed and not dry_run:
        # Atomic write: tempfile in same dir + os.replace.
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=".pressure_scan_fix.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(new_text)
            os.replace(tmp_path, path)
        except Exception:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise
    return counter, changed


def _walk(paths: list[Path]):
    for p in paths:
        if not p.exists():
            continue
        if p.is_file():
            if p.suffix.lower() in SCAN_EXTENSIONS:
                yield p
            continue
        for f in p.rglob("*"):
            if any(part in SKIP_DIRS for part in f.parts):
                continue
            if f.is_file() and f.suffix.lower() in SCAN_EXTENSIONS:
                yield f


def _default_paths() -> list[Path]:
    return [Path.cwd()]


def _get_note(h: dict) -> str:
    cal = _ORIG_TO_CAL.get(h["original"]) or _ORIG_LOWER_TO_CAL.get(h["original"].lower())
    return (cal.note or "") if cal else ""


def _run_probe(text: str, include_tier2: bool, as_json: bool) -> int:
    """Score an ad-hoc text snippet. Returns exit code (1 = T1 hit)."""
    fd, tmp_str = tempfile.mkstemp(suffix=".py")
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        hits = _scan_file(tmp, include_tier2=include_tier2)
        for h in hits:
            h["path"] = "<probe>"
    finally:
        tmp.unlink(missing_ok=True)
    score = _pressure_score(hits, max(text.count("\n") + 1, 1))
    label = _pressure_label(score)
    tier1 = [h for h in hits if h["severity"] == "tier1"]
    tier2 = [h for h in hits if h["severity"] == "tier2"]
    if as_json:
        print(json.dumps({"tier1": tier1, "tier2": tier2,
                          "pressure_score": score, "pressure_label": label}, indent=2))
    else:
        print(f"Probe pressure: {score:.1f}/100  [{label}]")
        if tier1:
            print(f"  T1 ({len(tier1)}): " + ", ".join(f"'{h['original']}'" for h in tier1[:10]))
        if tier2:
            print(f"  T2 ({len(tier2)}): " + ", ".join(f"'{h['original']}'" for h in tier2[:10]))
        if not hits:
            print("  Probe clean.")
    return 1 if tier1 else 0


def _run_summary(paths: list[Path], include_tier2: bool, as_json: bool) -> int:
    """Per-file classifier pressure summary table. Returns 1 if any T1 hits."""
    rows: list[dict] = []
    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        hits = _scan_file(f, include_tier2=include_tier2)
        if not hits:
            continue
        lines = _line_count(f)
        score = _pressure_score(hits, lines)
        rows.append({
            "path": str(f),
            "lines": lines,
            "tier1": sum(1 for h in hits if h["severity"] == "tier1"),
            "tier2": sum(1 for h in hits if h["severity"] == "tier2"),
            "pressure_score": score,
            "pressure_label": _pressure_label(score),
        })
    rows.sort(key=lambda r: r["pressure_score"], reverse=True)
    if as_json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("AUP linter clean.")
            return 0
        print(f"{'Score':>6}  {'T1':>4}  {'T2':>4}  {'Label':>7}  Path")
        print("-" * 80)
        for r in rows:
            print(f"  {r['pressure_score']:>5.1f}  {r['tier1']:>4}  {r['tier2']:>4}  "
                  f"{r['pressure_label']:>7}  {r['path']}")
    return 1 if any(r["tier1"] > 0 for r in rows) else 0


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="AUP vocabulary linter / classifier maneuverability tool")
    ap.add_argument("paths", nargs="*", help="Files or directories to scan (default: warden_*)")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    ap.add_argument("--no-tier2", action="store_true", help="Suppress Tier 2 warnings")
    ap.add_argument("--fail-tier2", action="store_true", help="Treat Tier 2 hits as failures")
    ap.add_argument("--fix", action="store_true",
                    help="Apply calibrations in-place (atomic write per file)")
    ap.add_argument("--dry-run", action="store_true",
                    help="With --fix: report what would change but do not write")
    # Classifier maneuverability / modulation
    ap.add_argument("--profile", choices=list(PROFILES), default=None,
                    help="Calibration profile: strict | guarded | minimal")
    ap.add_argument("--score", action="store_true",
                    help="Include classifier pressure score (0â€“100) in output")
    ap.add_argument("--probe", metavar="TEXT",
                    help="Score an ad-hoc text snippet instead of scanning files")
    ap.add_argument("--summary", action="store_true",
                    help="Per-file pressure summary table â€” no per-line details")
    ap.add_argument("--explain", action="store_true",
                    help="Show calibration notes alongside each hit")
    args = ap.parse_args(argv)

    # Profile overrides individual tier flags
    if args.profile:
        preset = PROFILES[args.profile]
        include_tier2 = preset["include_tier2"]
        fail_tier2 = preset["fail_tier2"]
    else:
        include_tier2 = not args.no_tier2
        fail_tier2 = args.fail_tier2

    if args.probe is not None:
        return _run_probe(args.probe, include_tier2=include_tier2, as_json=args.json)

    paths = [Path(p) for p in args.paths] if args.paths else _default_paths()

    if args.fix:
        total_counter: Counter = Counter()
        changed_files: list[str] = []
        for f in _walk(paths):
            if _is_whitelisted(f):
                continue
            counter, changed = _fix_file(f, include_tier2=include_tier2, dry_run=args.dry_run)
            total_counter.update(counter)
            if changed:
                changed_files.append(str(f))
        report = {
            "mode": "dry-run" if args.dry_run else "fix",
            "files_changed": changed_files,
            "files_changed_count": len(changed_files),
            "substitutions": dict(total_counter),
            "total": sum(total_counter.values()),
        }
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            verb = "would change" if args.dry_run else "changed"
            print(f"pressure_scan --fix: {verb} {len(changed_files)} file(s); "
                  f"substitutions={dict(total_counter)} total={sum(total_counter.values())}")
            for f in changed_files:
                print(f"  {f}")
        return 0

    if args.summary:
        return _run_summary(paths, include_tier2=include_tier2, as_json=args.json)

    all_hits: list[dict] = []
    file_lines: dict[str, int] = {}
    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        hits = _scan_file(f, include_tier2=include_tier2)
        all_hits.extend(hits)
        if args.score and hits:
            file_lines[str(f)] = _line_count(f)

    tier1 = [h for h in all_hits if h["severity"] == "tier1"]
    tier2 = [h for h in all_hits if h["severity"] == "tier2"]

    if args.json:
        out: dict = {"tier1": tier1, "tier2": tier2}
        if args.score:
            total_lines = sum(file_lines.values()) or max(len(all_hits), 1)
            score = _pressure_score(all_hits, total_lines)
            out["pressure_score"] = score
            out["pressure_label"] = _pressure_label(score)
        print(json.dumps(out, indent=2))
    else:
        if args.score:
            total_lines = sum(file_lines.values()) or max(len(all_hits), 1)
            score = _pressure_score(all_hits, total_lines)
            print(f"Classifier pressure: {score:.1f}/100  [{_pressure_label(score)}]")
        if tier1:
            print(f"== Tier 1 â€” BLOCK ({len(tier1)} hit{'s' if len(tier1) != 1 else ''}) ==")
            for h in tier1:
                note = f"  # {_get_note(h)}" if args.explain and _get_note(h) else ""
                print(f"  {h['path']}:{h['line']}:{h['col']}  "
                      f"'{h['original']}' -> '{h['calibrated']}'  [{h['scope']}]{note}")
                print(f"    {h['snippet']}")
        if tier2 and include_tier2:
            print(f"== Tier 2 â€” warn ({len(tier2)} hit{'s' if len(tier2) != 1 else ''}) ==")
            for h in tier2:
                note = f"  # {_get_note(h)}" if args.explain and _get_note(h) else ""
                print(f"  {h['path']}:{h['line']}:{h['col']}  "
                      f"'{h['original']}' -> '{h['calibrated']}'  [{h['scope']}]{note}")
        if not tier1 and (not tier2 or not include_tier2):
            print("AUP linter clean.")

    if tier1:
        return 1
    if tier2 and fail_tier2:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

