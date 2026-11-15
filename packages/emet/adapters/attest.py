#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
attest.py -- EMET in-toto attestation adapter (OPTIONAL, out-of-core, stdlib-only).

Wraps an EMET verdict as an in-toto v1 Statement with an EMET predicate, so the
verdict is consumable by cosign, slsa-verifier, and Sigstore policy-controller
with zero EMET-specific code on their side.

Emits UNSIGNED JSON: EMET holds no key (SPEC boundaries 5 and 6). The OPERATOR
signs (for example cosign attest) and, if desired, uploads to a transparency log.
EMET attests; the operator actuates. This adapter lives outside the core (SPEC
section 10): the minimal-TCB guarantee covers membrane, organs, and monitor, not
this file.

The predicateType URL uses a placeholder domain (emet.dev). The project that
adopts EMET SHOULD host the predicate definition at a URL it controls.

Usage:
  python attest.py verify <path> <anchors.json>
  python attest.py coherence <source> <view>
  python attest.py corroborate <path>
"""
import os, sys, json, hashlib, subprocess, re

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "membrane.py")
SPEC_VERSION = "1.0.0"
PREDICATE_TYPE = "https://emet.dev/attestation/coherence/v1"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
VERDICT_TOKENS = ["MATCH", "DRIFT", "UNVERIFIABLE", "COHERENT",
                  "VIEW_DIFFERS_FROM_SOURCE", "CORROBORATED",
                  "QUARANTINE_READ_PATH_DIVERGENCE"]
# Authority words that must never be surfaced as a verdict; same defensive
# posture as proof_surface_receipt.py.
FORBIDDEN_TOKENS = ["TRUSTED", "APPROVED", "SAFE", "ALLOWED",
                    "PERMITTED", "AUTHORIZED", "CERTIFIED", "COMPLIANT"]

def sha256(path):
    # Missing/unreadable file is reported as a verdict, not a traceback.
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None

def subject(path):
    h = sha256(path)
    digest = {"sha256": h} if h is not None else {"unavailable": "E_NOT_FOUND"}
    return {"name": os.path.basename(path), "digest": digest}

def tool_version():
    p = subprocess.run([sys.executable, CORE, "selftest"], capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith("emet_self_sha256="):          # canonical token (SPEC s.14)
            return line.split("=", 1)[1].strip()
    for line in p.stdout.splitlines():                     # legacy alias (removed at 2.0);
        if line.startswith("membrane_self_sha256="):        # its line carries a trailing note,
            return line.split("=", 1)[1].split()[0]         # so take only the hex token
    # Distinguish "selftest ran but emits no self-hash" from "selftest failed".
    if p.returncode != 0:
        return "selftest_failed:rc=" + str(p.returncode)
    return "unknown"

def run_core(args, cwd=None):
    return subprocess.run([sys.executable, CORE] + args, cwd=cwd, capture_output=True, text=True)

def _token_present(token, line):
    return re.search(r"(?<![A-Z0-9_])" + re.escape(token) + r"(?![A-Z0-9_])", line) is not None

def first_verdict(stdout):
    for line in stdout.splitlines():
        for tok in FORBIDDEN_TOKENS:
            if _token_present(tok, line):
                return "UNVERIFIABLE"
        for tok in VERDICT_TOKENS:
            if _token_present(tok, line):
                return tok
    return "UNVERIFIABLE"

def statement(subjects, check, verdict, evidence):
    return {
        "_type": STATEMENT_TYPE,
        "subject": subjects,
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "emet_spec_version": SPEC_VERSION,
            "emet_tool_version": tool_version(),
            "check": check,
            "verdict": verdict,
            "evidence": evidence,
            "signed": False,
            "note": "Unsigned EMET attestation. The operator signs and actuates; EMET holds no key and performs no action.",
        },
    }

def emit(st):
    print(json.dumps(st, indent=2, sort_keys=True))

def main():
    a = sys.argv
    if len(a) >= 4 and a[1] == "verify":
        path, anchors = a[2], a[3]
        cwd = os.path.dirname(os.path.abspath(anchors)) or "."
        p = run_core(["verify", os.path.abspath(path)], cwd=cwd)
        emit(statement([subject(path)], "verify", first_verdict(p.stdout), {"exit_code": p.returncode}))
        sys.exit(0)
    if len(a) >= 4 and a[1] == "coherence":
        src, view = a[2], a[3]
        p = run_core(["coherence", os.path.abspath(src), os.path.abspath(view)])
        emit(statement([subject(src), subject(view)], "coherence", first_verdict(p.stdout), {"exit_code": p.returncode}))
        sys.exit(0)
    if len(a) >= 3 and a[1] == "corroborate":
        path = a[2]
        p = run_core(["corroborate", os.path.abspath(path)])
        emit(statement([subject(path)], "corroborate", first_verdict(p.stdout), {"exit_code": p.returncode}))
        sys.exit(0)
    print(__doc__)
    sys.exit(64)

if __name__ == "__main__":
    main()
