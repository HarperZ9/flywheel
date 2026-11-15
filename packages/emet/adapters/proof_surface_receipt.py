#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
proof_surface_receipt.py - EMET proof-surface receipt adapter.

Optional, out-of-core, stdlib-only adapter. It wraps EMET witness facts as a
small JSON receipt that tools such as repo-proof-index can summarize without
changing EMET's governed stdout or verdict lattice.

Usage:
  python proof_surface_receipt.py verify <path> <anchors.json>
  python proof_surface_receipt.py coherence <source> <view>
  python proof_surface_receipt.py corroborate <path>
  python proof_surface_receipt.py bundle <bundle.json>
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "membrane.py")
SPEC_VERSION = "1.0.0"
BUNDLE_SCHEMA = "proof-surface-bundle/v0"
VERDICT_TOKENS = [
    "MATCH",
    "DRIFT",
    "UNVERIFIABLE",
    "COHERENT",
    "VIEW_DIFFERS_FROM_SOURCE",
    "CORROBORATED",
    "QUARANTINE_READ_PATH_DIVERGENCE",
]
FORBIDDEN_TOKENS = [
    "TRUSTED",
    "APPROVED",
    "SAFE",
    "ALLOWED",
    "PERMITTED",
    "AUTHORIZED",
    "CERTIFIED",
    "COMPLIANT",
]


def sha256(path):
    # Missing/unreadable file -> None (reported as a verdict, never a traceback).
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


def run_core(args, cwd=None):
    return subprocess.run(
        [sys.executable, CORE] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def tool_version():
    result = run_core(["selftest"])
    for line in result.stdout.splitlines():
        if line.startswith("emet_self_sha256="):          # canonical token (SPEC s.14)
            return line.split("=", 1)[1].strip()
    for line in result.stdout.splitlines():                # legacy alias (removed at 2.0);
        if line.startswith("membrane_self_sha256="):        # its line carries a trailing note,
            return line.split("=", 1)[1].split()[0]         # so take only the hex token
    return "unknown"


def verdict_line(stdout):
    for line in stdout.splitlines():
        for token in FORBIDDEN_TOKENS:
            if _token_present(token, line):
                return "UNVERIFIABLE", "authority token refused by receipt adapter"
        for token in VERDICT_TOKENS:
            if _token_present(token, line):
                return token, line
    return "UNVERIFIABLE", ""


def _token_present(token, line):
    return re.search(r"(?<![A-Z0-9_])" + re.escape(token) + r"(?![A-Z0-9_])", line) is not None


def subject(path):
    h = sha256(path)
    digest = {"sha256": h} if h is not None else {"unavailable": "E_NOT_FOUND"}
    return {
        "name": os.path.basename(path),
        "digest": digest,
    }


def receipt_id(check, verdict, subjects):
    payload = json.dumps(
        {"check": check, "verdict": verdict, "subject": subjects},
        sort_keys=True,
    )
    return "emet-" + check + "-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def receipt(check, subjects, result):
    verdict, line = verdict_line(result.stdout)
    return {
        "receipt_id": receipt_id(check, verdict, subjects),
        "verdict": verdict,
        "witness": {
            "implementation": "emet-python-reference",
            "spec_version": SPEC_VERSION,
            "self_sha256": tool_version(),
            "check": check,
        },
        "subject": subjects,
        "evidence": {
            "exit_code": result.returncode,
            "stdout_verdict_line": line,
        },
        "notes": (
            "EMET emits witness facts only. The receipt preserves the closed "
            "verdict lattice and carries no authority, permission, or release "
            "decision."
        ),
    }


def _load_bundle(bundle_path):
    # Returns (manifest, error). A malformed or unreadable manifest, a wrong
    # schema, or a missing files[] list is not re-derivable -> UNVERIFIABLE.
    try:
        with open(bundle_path, "rb") as handle:
            manifest = json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None, "bundle.json missing or malformed"
    if not isinstance(manifest, dict):
        return None, "bundle.json is not an object"
    if manifest.get("schema") != BUNDLE_SCHEMA:
        return None, "unexpected bundle schema"
    if not isinstance(manifest.get("files"), list):
        return None, "bundle.json has no files list"
    return manifest, None


def _rederive_files(bundle_dir, files):
    # Re-derive every manifest entry against its sibling file on disk.
    # DRIFT dominates UNVERIFIABLE: a difference outranks an inability to check.
    rederived = 0
    drift = None
    unverifiable = None
    for entry in files:
        name = entry.get("name") if isinstance(entry, dict) else None
        recorded = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not isinstance(recorded, str):
            unverifiable = unverifiable or "malformed manifest entry"
            continue
        actual = sha256(os.path.join(bundle_dir, name))
        if actual is None:
            unverifiable = unverifiable or ("UNVERIFIABLE missing " + name)
        elif actual != recorded:
            drift = drift or ("DRIFT " + name)
        else:
            rederived += 1
    if drift is not None:
        return "DRIFT", drift, rederived
    if unverifiable is not None:
        return "UNVERIFIABLE", unverifiable, rederived
    return "MATCH", "MATCH bundle re-derived", rederived


def bundle_receipt(bundle_path):
    # Witness a proof-surface bundle.json by re-deriving each manifest file.
    # The synthesized verdict line is passed through verdict_line() so an
    # injected authority token is refused and the lattice stays closed.
    bundle_dir = os.path.dirname(os.path.abspath(bundle_path))
    subjects = [subject(bundle_path)]
    manifest, error = _load_bundle(bundle_path)
    if manifest is None:
        result = _BundleResult(2, "UNVERIFIABLE " + error)
        data = receipt("bundle", subjects, result)
        data["evidence"]["files_total"] = 0
        data["evidence"]["files_rederived"] = 0
        return data
    files = manifest["files"]
    if _has_authority_token(manifest):
        # An authority token anywhere in the manifest (including a file name)
        # is refused before any verdict is formed; the lattice stays closed.
        data = receipt("bundle", subjects, _BundleResult(2, "authority=TRUSTED"))
        data["evidence"]["files_total"] = len(files)
        data["evidence"]["files_rederived"] = 0
        return data
    verdict, line, rederived = _rederive_files(bundle_dir, files)
    exit_code = 0 if verdict == "MATCH" else (1 if verdict == "DRIFT" else 2)
    data = receipt("bundle", subjects, _BundleResult(exit_code, line))
    data["evidence"]["files_total"] = len(files)
    data["evidence"]["files_rederived"] = rederived
    return data


def _has_authority_token(manifest):
    text = json.dumps(manifest)
    return any(_token_present(token, text) for token in FORBIDDEN_TOKENS)


class _BundleResult:
    # Minimal stand-in for a subprocess result: the bundle witness re-derives
    # in-process, so there is no core stdout to parse -- we synthesize one line.
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout


def emit(data):
    print(json.dumps(data, indent=2, sort_keys=True))


def main():
    args = sys.argv
    if len(args) >= 4 and args[1] == "verify":
        path, anchors = args[2], args[3]
        cwd = os.path.dirname(os.path.abspath(anchors)) or "."
        result = run_core(["verify", os.path.abspath(path)], cwd=cwd)
        emit(receipt("verify", [subject(path)], result))
        sys.exit(0)
    if len(args) >= 4 and args[1] == "coherence":
        source, view = args[2], args[3]
        result = run_core(["coherence", os.path.abspath(source), os.path.abspath(view)])
        emit(receipt("coherence", [subject(source), subject(view)], result))
        sys.exit(0)
    if len(args) >= 3 and args[1] == "corroborate":
        path = args[2]
        result = run_core(["corroborate", os.path.abspath(path)])
        emit(receipt("corroborate", [subject(path)], result))
        sys.exit(0)
    if len(args) >= 3 and args[1] == "bundle":
        emit(bundle_receipt(args[2]))
        sys.exit(0)
    print(__doc__)
    sys.exit(64)


if __name__ == "__main__":
    main()
