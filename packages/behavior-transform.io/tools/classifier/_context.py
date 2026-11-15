"""Context analysis and management for classifier."""
from __future__ import annotations

import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pressure_scan import (  # type: ignore[import-not-found]
    _fix_file, _line_count, _pressure_label, _pressure_score, _scan_file,
)
from classifier._audit import _audit_write  # noqa: F401


# ---------------------------------------------------------------------------
# Session context file discovery
# ---------------------------------------------------------------------------

def _context_files() -> list[tuple[str, Path]]:
    home = Path.home()
    cwd = Path.cwd()
    candidates: list[tuple[str, Path]] = [
        ("global CLAUDE.md", home / ".claude" / "CLAUDE.md"),
        ("project CLAUDE.md", cwd / "CLAUDE.md"),
        ("local CLAUDE.md",   cwd / "CLAUDE.local.md"),
    ]
    base = home / ".claude" / "projects"
    if base.is_dir():
        for proj in sorted(base.iterdir()):
            mem = proj / "memory" / "MEMORY.md"
            if mem.is_file():
                candidates.append((f"memory/{proj.name}/MEMORY.md", mem))
    return [(lbl, p) for lbl, p in candidates if p.is_file()]


# ---------------------------------------------------------------------------
# Paragraph-level segment splitter
# ---------------------------------------------------------------------------

def _split_paragraphs(text: str) -> list[tuple[int, str]]:
    segs: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 1
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        if line.strip():
            if not buf:
                start = lineno
            buf.append(line)
        elif buf:
            segs.append((start, "".join(buf)))
            buf = []
    if buf:
        segs.append((start, "".join(buf)))
    return segs


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------

def analyze_context(include_tier2: bool) -> list[dict]:
    """Scan every auto-loaded context file and return pressure per file."""
    results = []
    for label, path in _context_files():
        hits = _scan_file(path, include_tier2=include_tier2)
        lines = _line_count(path)
        score = _pressure_score(hits, lines)
        results.append({
            "label": label, "path": str(path), "lines": lines,
            "tier1": sum(1 for h in hits if h["severity"] == "tier1"),
            "tier2": sum(1 for h in hits if h["severity"] == "tier2"),
            "pressure_score": score,
            "pressure_label": _pressure_label(score),
        })
    return sorted(results, key=lambda r: r["pressure_score"], reverse=True)


def annotate_file(path: Path, include_tier2: bool) -> list[dict]:
    """Return per-paragraph pressure rows for a single file, sorted by score."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows: list[dict] = []
    suffix = path.suffix or ".txt"
    for start, seg in _split_paragraphs(text):
        seg_lines = seg.count("\n") + 1
        fd, tmp_str = tempfile.mkstemp(suffix=suffix)
        tmp = Path(tmp_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(seg)
            hits = _scan_file(tmp, include_tier2=include_tier2)
        finally:
            tmp.unlink(missing_ok=True)
        if not hits:
            continue
        score = _pressure_score(hits, seg_lines)
        rows.append({
            "start_line": start, "end_line": start + seg_lines - 1,
            "tier1": sum(1 for h in hits if h["severity"] == "tier1"),
            "tier2": sum(1 for h in hits if h["severity"] == "tier2"),
            "pressure_score": score,
            "pressure_label": _pressure_label(score),
            "preview": seg[:100].rstrip(),
            "terms": [{"original": h["original"], "calibrated": h["calibrated"],
                       "severity": h["severity"]} for h in hits],
        })
    return sorted(rows, key=lambda r: r["pressure_score"], reverse=True)


def validate_file(path: Path, include_tier2: bool) -> dict:
    """Apply calibrations to a temp copy and return before/after pressure."""
    before_hits = _scan_file(path, include_tier2=include_tier2)
    before_lines = _line_count(path)
    before_score = _pressure_score(before_hits, before_lines)
    fd, tmp_str = tempfile.mkstemp(suffix=path.suffix or ".txt")
    tmp = Path(tmp_str)
    try:
        os.close(fd)
        tmp.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        _fix_file(tmp, include_tier2=include_tier2, dry_run=False)
        after_hits = _scan_file(tmp, include_tier2=include_tier2)
    finally:
        tmp.unlink(missing_ok=True)
    after_score = _pressure_score(after_hits, before_lines)
    before_term_cal = {h["original"]: h["calibrated"] for h in before_hits}
    before_counts = Counter(h["original"] for h in before_hits)
    after_counts  = Counter(h["original"] for h in after_hits)
    substitutions = {
        term: {"count": before_counts[term] - after_counts.get(term, 0),
               "calibrated": before_term_cal[term]}
        for term in before_counts
        if before_counts[term] > after_counts.get(term, 0)
    }
    return {
        "path": str(path),
        "before_score": before_score, "before_label": _pressure_label(before_score),
        "after_score":  after_score,  "after_label":  _pressure_label(after_score),
        "delta": round(after_score - before_score, 1),
        "hits_before": len(before_hits), "hits_after": len(after_hits),
        "hits_removed": len(before_hits) - len(after_hits),
        "substitutions": substitutions,
    }


def ctx_fix(include_tier2: bool, dry_run: bool) -> list[dict]:
    """Apply calibrations in-place to auto-loaded context files."""
    results = []
    for label, path in _context_files():
        counter, changed = _fix_file(path, include_tier2=include_tier2, dry_run=dry_run)
        results.append({
            "label": label,
            "path": str(path),
            "changed": changed,
            "substitutions": dict(counter),
            "total": sum(counter.values()),
        })
    if not dry_run:
        total_subs = sum(r["total"] for r in results)
        _audit_write("ctx.fix", {"files_changed": sum(1 for r in results if r["changed"]),
                                  "total_substitutions": total_subs})
    return results
