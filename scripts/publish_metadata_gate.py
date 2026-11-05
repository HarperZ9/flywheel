#!/usr/bin/env python3
"""publish_metadata_gate.py -- block a publish that adds personal metadata.

check_publish_metadata.py finds personal metadata in a tree. The public tree
already carried 1,370 findings when this gate was frozen (2026-11-04), most of
them workspace paths in test fixtures and scripts. A gate that failed on all of
them would block every publish, so the existing findings are frozen in a
baseline of counts, and from then on:

  - a file whose count for a category grows fails the gate,
  - a file not in the baseline with any finding fails the gate,
  - a finding from a private pattern (the machine name, the git global email,
    an entry in the untracked deny list) always fails the gate, since the
    baseline is written from the generic patterns only.

The baseline holds paths, categories and counts, never a matched value, and it
can only shrink: `--write-baseline` refuses a count larger than the frozen one
unless `--allow-growth` is passed. scripts/publish_public.py runs this gate on
its staging tree before any push; CI runs it on the checkout.

Usage:
  publish_metadata_gate.py ROOT [--baseline FILE] [--deny-list FILE]
                           [--all-files] [--write-baseline [--allow-growth]]
Exit 0 when clean, 1 when blocked. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_publish_metadata as C  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "project-docs" / "records" / "2026-11-04-publish-metadata-baseline.json"
SCHEMA = "flywheel.publish-metadata-baseline/1"


def collect(root: Path, patterns, all_files: bool = False) -> dict[str, Counter]:
    """{relative path: Counter(category)} for every file with a finding."""
    files, base = C.select_files(root.resolve(), all_files, None)
    out: dict[str, Counter] = {}
    for p in files:
        found, _fixed = C.scan_file(p, patterns, fix=False)
        if found:
            out[p.relative_to(base).as_posix()] = Counter(cat for _l, cat, _d in found)
    return out


def load_baseline(path: Path) -> dict[str, dict[str, int]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise SystemExit(f"publish_metadata_gate: unknown baseline schema in {path.name}")
    return data["files"]


def excess(current: dict[str, Counter], baseline: dict[str, dict[str, int]]):
    """(path, category, count now, count allowed) for every count over its baseline."""
    rows = []
    for rel in sorted(current):
        allowed = baseline.get(rel, {})
        for cat, n in sorted(current[rel].items()):
            if n > allowed.get(cat, 0):
                rows.append((rel, cat, n, allowed.get(cat, 0)))
    return rows


def write_baseline(root: Path, path: Path, allow_growth: bool, stream=sys.stdout) -> int:
    current = collect(root, C.T.GENERIC)
    old = load_baseline(path)
    grown = excess(current, old) if old else []
    if grown and not allow_growth:
        for rel, cat, n, was in grown:
            print(f"{rel}: {cat}: {n} > frozen {was}", file=stream)
        print("refused: the baseline only shrinks; pass --allow-growth to override",
              file=stream)
        return 1
    files = {rel: dict(sorted(c.items())) for rel, c in sorted(current.items())}
    body = {"schema": SCHEMA, "patterns": "generic only (check_publish_metadata GENERIC)",
            "total": sum(sum(c.values()) for c in files.values()), "files": files}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(body, indent=1) + "\n").encode("utf-8"))
    print(f"baseline written: {len(files)} files, {body['total']} findings", file=stream)
    return 0


def gate(root: Path, baseline_path: Path = BASELINE, deny_list=None, all_files=False,
         stream=sys.stdout) -> int:
    """Return 0 when no file adds a finding over the baseline, else 1."""
    patterns = C.T.GENERIC + C.T.local_patterns(deny_list)
    current = collect(root, patterns, all_files)
    rows = excess(current, load_baseline(baseline_path))
    for rel, cat, n, was in rows:
        print(f"{rel}: {cat}: {n} finding(s), baseline allows {was}", file=stream)
    total = sum(sum(c.values()) for c in current.values())
    print(f"publish metadata gate: {len(current)} files with findings, {total} findings, "
          f"{len(rows)} over the baseline", file=stream)
    if rows:
        print("BLOCKED: remove the new metadata, or run check_publish_metadata.py "
              "--mode fix for image, PDF and Office files", file=stream)
    return 1 if rows else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", nargs="?", default=str(REPO))
    ap.add_argument("--baseline", default=str(BASELINE))
    ap.add_argument("--deny-list", help="untracked file of private regexes, one per line")
    ap.add_argument("--all-files", action="store_true", help="read untracked files too")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--allow-growth", action="store_true")
    a = ap.parse_args(argv)
    if a.write_baseline:
        return write_baseline(Path(a.root), Path(a.baseline), a.allow_growth)
    return gate(Path(a.root), Path(a.baseline), a.deny_list, a.all_files)


if __name__ == "__main__":
    sys.exit(main())
