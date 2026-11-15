#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""report.py - EMET output rendering: the human grammar (default) and the
machine-readable --json envelope (SPEC section 13, the v1 target).

Part of the named core (SPEC section 10); stdlib-only, no third-party
dependency. It changes only HOW a verdict is rendered, never WHAT: the verdict
token still comes through verdict.governed() at the call site, so the closed
lattice (SPEC section 2) is enforced before a byte reaches stdout in either mode.

The envelope is canonical JSON - sorted keys, ", "/": " separators, UTF-8,
ensure_ascii - the SAME byte form SPEC section 7 pins for the audit chain. That
makes the governed fields of an envelope re-derivable and byte-identical across
conforming implementations; impl-defined detail (verify want/got, corroborate
per-channel hashes - SPEC sections 4 and 15) may differ or be absent.
"""
import sys, os, json, hashlib

EMET_VERSION = "1.3.1"
SPEC_VERSION = "1.0.0"

# Set True by the CLI front-end when --json is present. Module-level so the
# command handlers can stay small: human prints route through say(), the verdict
# routes through emit(), and neither handler needs to thread a mode flag.
JSON = False

def enable_json():
    global JSON
    JSON = True

def say(line):
    """Emit a human-grammar line, unless --json mode is active."""
    if not JSON:
        print(line)

def self_hash(core_dir, filenames):
    """Artifact-of-record hash (SPEC s.14): SHA-256 over the sorted-by-name
    concatenation of the core source files' raw bytes, so the identity reflects
    the WHOLE implementation, not just one file."""
    h = hashlib.sha256()
    for name in sorted(filenames):
        with open(os.path.join(core_dir, name), "rb") as f:
            h.update(f.read())
    return h.hexdigest()

def canonical(obj):
    """The canonical JSON byte form (SPEC s.7): sorted keys, ', '/': ' separators,
    ensure_ascii. Identical to json.dumps(obj, sort_keys=True)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True)

def emit(command, verdict, exit_code, **fields):
    """In --json mode, print one canonical envelope to stdout; then exit.

    `verdict` is a governed, closed-lattice token (or None for selftest, which
    reports an identity, not a judgement). `fields` carries command-specific data;
    None-valued fields are dropped so the envelope shape is stable per command.
    Always calls sys.exit(exit_code) so the exit code stays the contract (SPEC s.5)
    in both modes.
    """
    if JSON:
        env = {"command": command, "emet_version": EMET_VERSION,
               "spec_version": SPEC_VERSION, "exit_code": exit_code}
        if verdict is not None:
            env["verdict"] = verdict
        env.update({k: v for k, v in fields.items() if v is not None})
        print(canonical(env))
    sys.exit(exit_code)
