#!/usr/bin/env python3
"""anchor_confirmatory.py -- the run_end ceremony, scripted before it is needed.

THE ORDER AT run_end, so nothing is improvised at the moment it matters:

  1. python scripts/compute_endpoint.py          (refuses before run_end)
  2. python scripts/compute_arms.py              (same gate)
  3. python scripts/render_report.py             (renders, computes nothing)
  4. python scripts/anchor_confirmatory.py --stage run
  5. python scripts/anchor_confirmatory.py --stage analysis
  6. verify the ledger returns MATCH

Two stages because they witness two different facts:

  * --stage run anchors the WALK: the journal's own bytes and its mechanical
    counts. Nothing in the journal is an outcome (the walker cannot write one),
    so this stage can run the moment run_end lands, before any analysis.
  * --stage analysis anchors the ANALYSIS: the sha256 of the three artifacts
    plus the primary endpoint facts. It refuses until all three exist, so the
    anchor can never point at a report that was still being produced.

Both stages refuse without run_end. Neither has an override flag.

This script builds the payload and prints the exact ceremony command; it signs
nothing itself. Pass --key to run the ceremony in-process instead. The key
stays wherever the operator keeps it, and no payload here ever contains it.

Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_CE = None


def _load_compute_endpoint():
    """Cached, for the reason compute_arms caches it: two importlib loads make
    two EndpointGate classes, and an except naming one misses the other."""
    global _CE
    if _CE is None:
        spec = importlib.util.spec_from_file_location(
            "compute_endpoint", REPO / "scripts" / "compute_endpoint.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CE = mod
    return _CE


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _journal_rows(journal: Path) -> list:
    rows = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def run_payload(journal: Path) -> dict:
    """The walk, as mechanical facts. The journal carries no verdict and no
    candidate, so nothing here can leak an outcome into the ledger."""
    ce = _load_compute_endpoint()
    ce.require_run_end(journal)
    rows = _journal_rows(journal)
    events = Counter(r.get("event") for r in rows)
    done = [r for r in rows if r.get("event") == "pair_done"]
    ends = [r for r in rows if r.get("event") == "run_end"]
    per_family = Counter(r["family"] for r in done)
    return {
        "prereg_id": "prereg.size-invariant-verification.v1",
        "cites_parent_sha256": ("31055c924d48fe67ebdf29ab8f067840"
                                "f83ccc6ff1d1f469bc0abb2be0dffa08"),
        "journal_sha256": _sha(journal),
        "events": dict(sorted(events.items())),
        "pairs_done": len(done),
        "pairs_failed_nonzero_exit": sum(1 for r in done if r["exit_code"]),
        "pairs_failed_reported_at_run_end": ends[-1].get("pairs_failed"),
        "per_family_pairs": dict(sorted(per_family.items())),
        "total_wall_seconds": round(sum(r["wall_seconds"] for r in done), 1),
        "note": ("mechanical facts only: the journal is written by a walker "
                 "that cannot read a verdict, so neither can this payload"),
    }


def analysis_payload(journal: Path, reports: Path) -> dict:
    """The analysis artifacts, by hash, plus the primary endpoint facts. Runs
    only after every artifact exists: an anchor must never point at a report
    that was still being produced."""
    ce = _load_compute_endpoint()
    ce.require_run_end(journal)
    names = ("endpoint-report.json", "arms-report.json",
             "confirmatory-report.md")
    missing = [n for n in names if not (reports / n).is_file()]
    if missing:
        raise ce.EndpointGate(
            "analysis artifacts missing: " + ", ".join(missing) + ". Run the "
            "drivers and the renderer first; anchoring an absent artifact "
            "would witness nothing.")
    endpoint_doc = json.loads(
        (reports / "endpoint-report.json").read_text(encoding="utf-8"))
    families = {}
    for fam, block in endpoint_doc.get("families", {}).items():
        p = block["primary"]
        families[fam] = {"n_bodies": p["n_bodies"],
                         "n_disagreements": p["n_disagreements"],
                         "met": p["met"]}
    return {
        "prereg_id": "prereg.size-invariant-verification.v1",
        "cites_parent_sha256": ("31055c924d48fe67ebdf29ab8f067840"
                                "f83ccc6ff1d1f469bc0abb2be0dffa08"),
        "journal_sha256": _sha(journal),
        "artifact_sha256": {n: _sha(reports / n) for n in names},
        "primary_endpoint": families,
        "note": ("anchored AFTER run_end and after the artifacts existed; the "
                 "drivers that produced them refuse to run any earlier"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", required=True, choices=("run", "analysis"))
    ap.add_argument("--journal", default=str(
        REPO / "artifacts" / "pool" / "confirmatory-journal.jsonl"))
    ap.add_argument("--reports", default=str(REPO / "artifacts" / "endpoint"))
    ap.add_argument("--key", default=None,
                    help="signing seed path; omit to only write the payload "
                         "and print the ceremony command")
    ap.add_argument("--timestamp", default=None,
                    help="UTC timestamp for the ceremony (required with --key)")
    args = ap.parse_args(argv)

    journal = Path(args.journal)
    ce = _load_compute_endpoint()
    try:
        if args.stage == "run":
            payload = run_payload(journal)
            kind = "confirmatory-run"
        else:
            payload = analysis_payload(journal, Path(args.reports))
            kind = "confirmatory-analysis"
    except ce.EndpointGate as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3

    out = Path(args.reports)
    out.mkdir(parents=True, exist_ok=True)
    payload_path = out / f"anchor-{args.stage}-payload.json"
    payload_path.write_text(json.dumps(payload, indent=1, sort_keys=True),
                            encoding="utf-8")
    print(f"payload -> {payload_path}")

    cmd = [sys.executable, str(REPO / "scripts" / "prereg_event.py"),
           "--kind", kind, "--payload-file", str(payload_path)]
    if args.key:
        if not args.timestamp:
            print("REFUSED: --key without --timestamp; the ceremony records "
                  "when, and guessing is not recording", file=sys.stderr)
            return 3
        cmd += ["--timestamp", args.timestamp, "--key", args.key]
        proc = subprocess.run(cmd)
        return proc.returncode
    print("ceremony command (append your --timestamp and --key):")
    print("  " + " ".join(cmd) + " --timestamp <UTC> --key <seed-path>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
