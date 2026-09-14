#!/usr/bin/env python3
"""governance_cli.py -- the `flywheel gov` subcommand for the governance instruments.

Runs the Environment Incentive Manifest, the Coercive-Environment Detector, and
the Non-Coercive-Environment Certificate from the shipped command, so a manifest
can be witnessed, re-checked, scanned, certified, and verified without importing
the package. JSON in, JSON out. Exit codes follow the verdict: 0 for MATCH or a
non-coercive scan, 1 for DRIFT or a coercive scan, 3 for UNVERIFIABLE, 2 for a
usage or input error. Standard library only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import coercive_environment as ce
from . import incentive_manifest as im
from . import internal_consistency as ic
from . import internalization_gap as ig
from . import reward_gap as rg
from . import served_model_provenance as smp
from .transitive_witness import DRIFT, MATCH, UNVERIFIABLE

_EXIT = {MATCH: 0, DRIFT: 1, UNVERIFIABLE: 3}
_USAGE = (
    "usage: flywheel gov <command>\n"
    "  eim-witness  ROOT PATH [PATH ...]      build witness entries for a manifest\n"
    "  eim-recheck  MANIFEST.json ROOT        recompute the witness (MATCH/DRIFT/UNVERIFIABLE)\n"
    "  ced          MANIFEST.json             scan for coercive primitives\n"
    "  ncec-issue   MANIFEST.json [PROP ...]  issue a non-coercive certificate\n"
    "  ncec-verify  CERT.json MANIFEST.json   re-derive a certificate\n"
    "  erg          MANIFEST.json LOG.json    reward gap: high reward without declared intent\n"
    "  igap         MANIFEST.json LOG.json    internalization gap: complies when watched, not when unwatched\n"
    "  smp          CLAIM.json OBSERVED.json   served-model provenance: did you get the model you were promised\n"
    "  icp          MANIFEST.json LOG.json    internal consistency: does the internal honesty signal track behavior\n")


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(obj):
    print(json.dumps(obj, indent=1, sort_keys=True))


def _usage() -> int:
    print(_USAGE, file=sys.stderr)
    return 2


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _usage()
    command, rest = argv[0], argv[1:]
    try:
        if command == "eim-witness":
            if len(rest) < 2:
                return _usage()
            _emit(im.witness_entries(rest[1:], Path(rest[0])))
            return 0
        if command == "eim-recheck":
            if len(rest) != 2:
                return _usage()
            result = im.recheck(_load(rest[0]), Path(rest[1]))
            _emit(result)
            return _EXIT[result["verdict"]]
        if command == "ced":
            if len(rest) != 1:
                return _usage()
            result = ce.detect(_load(rest[0]))
            _emit(result)
            return 0 if result["verdict"] == ce.NON_COERCIVE else 1
        if command == "ncec-issue":
            if not rest:
                return _usage()
            _emit(ce.issue_certificate(_load(rest[0]), rest[1:]))
            return 0
        if command == "ncec-verify":
            if len(rest) != 2:
                return _usage()
            result = ce.verify_certificate(_load(rest[0]), _load(rest[1]))
            _emit(result)
            return _EXIT[result["verdict"]]
        if command == "erg":
            if len(rest) != 2:
                return _usage()
            result = rg.analyze(_load(rest[0]), _load(rest[1]))
            _emit(result)
            return 0 if result["verdict"] == rg.NO_GAP else 1
        if command == "igap":
            if len(rest) != 2:
                return _usage()
            result = ig.analyze(_load(rest[0]), _load(rest[1]))
            _emit(result)
            return 0 if result["verdict"] == ig.NO_GAP else 1
        if command == "smp":
            if len(rest) != 2:
                return _usage()
            result = smp.analyze(_load(rest[0]), _load(rest[1]))
            _emit(result)
            return _EXIT[result["verdict"]]
        if command == "icp":
            if len(rest) != 2:
                return _usage()
            result = ic.analyze(_load(rest[0]), _load(rest[1]))
            _emit(result)
            return _EXIT[result["verdict"]]
    except (im.ManifestError, ce.CertificateError, rg.RewardGapError,
            ig.InternalizationGapError, smp.ProvenanceError,
            ic.InternalConsistencyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"unknown command: {command}", file=sys.stderr)
    return _usage()


if __name__ == "__main__":
    raise SystemExit(main())
