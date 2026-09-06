"""scan_route.py -- the code-scan surface.

GET  /api/scan/vulnerabilities   the last scan, its chain verdict, and a
                                 fresh re-check of it against the tree
POST /api/scan/vulnerabilities   run a scan and append it to the chain

Two containment rules hold this route down, and both are about what a
caller may choose.

The tree scanned is the repository this gateway already serves. It is not
a field in the request. A scan route that takes a path is a file-read
primitive with a security-sounding name, and it would read anything the
process can reach.

The suppressions are read from a file under the run root, never from the
request body. A suppression is a standing decision about a finding
somebody accepted, so it belongs somewhere an operator edits and reviews.
A body-supplied suppression would let one call quiet a finding and leave
the next reader a clean number with no idea a decision was made.

Findings are capped in the response and never in the counts, so a caller
reading the tail of a long list still sees the true total.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_public import TransportError, error_response
from .vulnerability_scan import (TREES, append_scan, load_scans, scan,
                                 scan_head, scans_intact, scans_path,
                                 verify_scan)

#: The most findings one response carries. The counts are computed over
#: every finding, so the cap shortens a list and never a number.
FINDINGS_SHOWN = 100

#: The fields of a sealed scan a response repeats. `findings` is handled
#: separately because it is the only unbounded one.
CARRIED = ("schema", "scanned_at", "trees", "ruleset_sha256",
           "ruleset_health", "ruleset_proven", "corpus_sha256",
           "files_in_corpus", "files_scanned", "skipped", "counts",
           "suppressed", "suppressed_count", "suppressions_unused",
           "suppressions_sha256", "clean", "prev_sha256", "scan_sha256")


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def _unknown() -> tuple[dict, int]:
    return error_response(
        TransportError("NOT_FOUND", "unknown scan route", 404))


def suppressions_path(run_root) -> Path:
    return Path(run_root) / "scans" / "suppressions.json"


def load_suppressions(path) -> list:
    """Read the standing suppressions. A missing file means none.

    Malformed content is not treated as none. A file somebody wrote and
    broke would otherwise turn into a silently stricter scan, and the
    findings it was meant to excuse would arrive as a surprise regression
    nobody can trace back to a typo.
    """
    path = Path(path)
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("the suppression store is not a list")
    return rows


def _summary(record: dict) -> dict:
    findings = list(record.get("findings", ()))
    out = {key: record[key] for key in CARRIED if key in record}
    out["findings"] = findings[:FINDINGS_SHOWN]
    out["findings_total"] = len(findings)
    out["findings_truncated"] = max(0, len(findings) - FINDINGS_SHOWN)
    return out


def handle_scan_get(path: str, *, root, run_root, clock) -> tuple[dict, int]:
    """The last scan, with both verdicts a reader needs to use it.

    `chain_intact` says the history was not edited. `verify` says the
    newest record still describes the tree and the rules in front of the
    reader. A record can pass either one and fail the other, so they are
    answered separately rather than folded into one word.
    """
    if path != "/api/scan/vulnerabilities":
        return _unknown()
    records = load_scans(scans_path(run_root))
    latest = records[-1] if records else None
    return {"schema": "flywheel.scan-roster/v1",
            "read_at": clock(),
            "scans": len(records),
            "chain_intact": scans_intact(records),
            "head_sha256": scan_head(records),
            "latest": _summary(latest) if latest else None,
            "verify": verify_scan(latest, root) if latest else None}, 200


def _requested_trees(body: dict) -> tuple:
    """Which trees to cover. Only the named ones, never an arbitrary path."""
    asked = body.get("trees")
    if asked is None:
        return TREES
    if not isinstance(asked, list) or not asked:
        raise ValueError("trees is a non-empty list of tree names")
    unknown = [t for t in asked if t not in TREES]
    if unknown:
        raise ValueError(f"not a scannable tree: {unknown[0]!r}")
    return tuple(str(t) for t in asked)


def handle_scan_post(path: str, body: dict, *, root, run_root,
                     clock) -> tuple[dict, int]:
    if path != "/api/scan/vulnerabilities":
        return _unknown()
    records = load_scans(scans_path(run_root))
    if not scans_intact(records):
        # Fail closed, the same way a tick onto a broken fire chain does.
        # Appending a clean scan on top of a history that does not verify
        # would put the reassuring record where the break is easiest to
        # miss.
        return {"schema": "flywheel.scan-ack/v1",
                "scanned": False,
                "refused": "the scan chain is broken"}, 409
    try:
        trees = _requested_trees(body)
        suppressions = load_suppressions(suppressions_path(run_root))
        record = scan(root, scanned_at=clock(), trees=trees,
                      suppressions=suppressions,
                      prev_sha256=scan_head(records))
    except (ValueError, json.JSONDecodeError) as exc:
        return _invalid(str(exc))
    append_scan(record, path=scans_path(run_root))
    return {"schema": "flywheel.scan-ack/v1",
            "scanned": True,
            "scan": _summary(record),
            "verify": verify_scan(record, root)}, 200
