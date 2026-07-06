#!/usr/bin/env python3
"""
corpus_manifest.py  —  build the training-corpus manifest from an allowlist.

Walks C:/dev under the allowlist's include roots, applies excludes, and writes:
  - manifest.jsonl     one line per included file: {path, bytes, ext, tokens_est}
  - manifest_summary.json
  - safety_report.txt  every path dropped by the SAFETY GATE, with the reason


Usage:
  python corpus_manifest.py [--allowlist allowlist.scoped.yaml] [--base C:/dev]
"""
from __future__ import annotations
import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

# --- SAFETY GATE ------------------------------------------------------------
# Any path whose parts contain one of these segments is dropped, always.
# Backstop that fails CLOSED. NEVER narrow this set; only ever add to it.
# Dual-use / opsec / private-line trees never enter the training corpus.
SAFETY_DENY_SEGMENTS = {
    "opsec", "seed", "sofer", "kun", "aleph", "warden", "gate",
}

# Filename / path substring markers for dual-use content that must never train,
# even if it lives outside the denied segments. Matched case-insensitively.
SAFETY_DENY_MARKERS = (
    "intercept",
)

# Text/code extensions we ingest. Everything else (binaries, images, archives,
# model weights, lockfiles) is skipped.
TEXT_EXTS = {
    ".py", ".md", ".txt", ".rst", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".json", ".jsonl", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".c", ".h", ".hpp", ".hh", ".cpp", ".cc", ".cxx", ".rs", ".go", ".java",
    ".rb", ".sh", ".bash", ".ps1", ".psm1", ".sql", ".html", ".htm", ".css",
    ".scss", ".lua", ".zig", ".ml", ".mli", ".lean", ".v", ".thy", ".agda",
    ".hs", ".ex", ".exs", ".kt", ".swift", ".scala", ".clj", ".proto",
    ".r", ".jl", ".nim", ".tex", ".bib", ".xml", ".gradle", ".cmake",
}
MAX_FILE_BYTES = 2 * 1024 * 1024  # skip files > 2 MB (generated/vendored junk)


def load_allowlist(path: Path) -> tuple[list[str], list[str]]:
    """Minimal parser for the include:/exclude: list-of-globs format.

    Avoids a hard PyYAML dependency; the allowlist format is a flat two-list
    document, so a line-oriented reader is sufficient and dependency-free.
    """
    include: list[str] = []
    exclude: list[str] = []
    section: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in ("include:", "exclude:"):
            section = stripped[:-1]
            continue
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            # strip inline comment (no '#' appears inside our glob values)
            if "#" in item:
                item = item.split("#", 1)[0].strip()
            item = item.strip().strip('"').strip("'").strip()
            if not item:
                continue
            (include if section == "include" else exclude).append(item)
    return include, exclude


def safety_reason(rel_posix: str) -> str | None:
    """Return a non-empty reason string if the path must be gated out."""
    parts = set(rel_posix.lower().split("/"))
    hit = parts & SAFETY_DENY_SEGMENTS
    if hit:
        return f"denied-segment:{sorted(hit)[0]}"
    low = rel_posix.lower()
    for marker in SAFETY_DENY_MARKERS:
        if marker in low:
            return f"denied-marker:{marker}"
    return None


def matches_any(rel_posix: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_posix, p) for p in patterns)


def include_roots(patterns: list[str]) -> list[str]:
    """First path segment of each include glob, so os.walk only descends into
    the roots we actually need instead of all of C:/dev."""
    roots: set[str] = set()
    for p in patterns:
        seg = p.split("/", 1)[0].replace("*", "").strip()
        if seg:
            roots.add(seg)
        else:
            roots.add("")  # root-level glob like "*.md"
    return sorted(roots)


def walk_corpus(base: Path, include: list[str], exclude: list[str]):
    included: list[dict] = []
    gated: list[tuple[str, str]] = []
    skipped_binary = 0
    skipped_excluded = 0
    skipped_toobig = 0

    roots = include_roots(include)
    walk_targets = []
    for r in roots:
        walk_targets.append(base if r == "" else base / r)

    seen: set[str] = set()
    for target in walk_targets:
        if not target.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(target):
            dp = Path(dirpath)
            # prune excluded / gated directories early for speed + safety
            keep_dirs = []
            for d in dirnames:
                rel_d = (dp / d).relative_to(base).as_posix()
                if safety_reason(rel_d):
                    gated.append((rel_d + "/", safety_reason(rel_d)))
                    continue
                if matches_any(rel_d, exclude) or matches_any(rel_d + "/", exclude):
                    continue
                keep_dirs.append(d)
            dirnames[:] = keep_dirs

            for fn in filenames:
                fp = dp / fn
                rel = fp.relative_to(base).as_posix()
                if rel in seen:
                    continue
                seen.add(rel)

                reason = safety_reason(rel)
                if reason:
                    gated.append((rel, reason))
                    continue
                if not matches_any(rel, include):
                    continue
                if matches_any(rel, exclude):
                    skipped_excluded += 1
                    continue
                ext = fp.suffix.lower()
                if ext not in TEXT_EXTS:
                    skipped_binary += 1
                    continue
                try:
                    size = fp.stat().st_size
                except OSError:
                    continue
                if size > MAX_FILE_BYTES:
                    skipped_toobig += 1
                    continue
                included.append(
                    {"path": rel, "bytes": size, "ext": ext,
                     "tokens_est": size // 4}
                )

    return included, gated, {
        "skipped_binary": skipped_binary,
        "skipped_excluded": skipped_excluded,
        "skipped_toobig": skipped_toobig,
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--allowlist", default=str(here / "allowlist.scoped.yaml"))
    ap.add_argument("--base", default="C:/dev")
    ap.add_argument("--out", default=str(here))
    args = ap.parse_args()

    base = Path(args.base)
    include, exclude = load_allowlist(Path(args.allowlist))
    included, gated, skips = walk_corpus(base, include, exclude)

    out = Path(args.out)
    with (out / "manifest.jsonl").open("w", encoding="utf-8") as fh:
        for rec in included:
            fh.write(json.dumps(rec) + "\n")

    total_bytes = sum(r["bytes"] for r in included)
    total_tokens = sum(r["tokens_est"] for r in included)
    by_ext: dict[str, int] = {}
    for r in included:
        by_ext[r["ext"]] = by_ext.get(r["ext"], 0) + 1

    summary = {
        "allowlist": args.allowlist,
        "base": args.base,
        "files": len(included),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1e6, 1),
        "tokens_est": total_tokens,
        "tokens_est_millions": round(total_tokens / 1e6, 1),
        "by_ext_top": dict(sorted(by_ext.items(), key=lambda kv: -kv[1])[:15]),
        "gated_by_safety": len(gated),
        **skips,
    }
    (out / "manifest_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    with (out / "safety_report.txt").open("w", encoding="utf-8") as fh:
        fh.write("SAFETY GATE — paths dropped from the training corpus\n")
        fh.write("=" * 60 + "\n")
        fh.write(f"total dropped: {len(gated)}\n\n")
        for rel, reason in sorted(gated):
            fh.write(f"{reason}\t{rel}\n")

    print(json.dumps(summary, indent=2))
    print(f"\nSAFETY GATE dropped {len(gated)} paths "
          f"(see safety_report.txt)")
    print(f"manifest.jsonl: {len(included)} files, "
          f"~{summary['tokens_est_millions']}M tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
