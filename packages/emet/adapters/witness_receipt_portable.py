#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
witness_receipt_portable.py - offline re-verifier for the portable witness
receipt (SPEC section 17).

Optional, out-of-core, stdlib-only convenience wrapper. It provides
`emet check <receipt.json>` in one place for a party who received a receipt and
wants to re-derive it on a completely isolated machine: no anchor store, no
membrane_log.jsonl, no network, no shared key required. It does NOT change the
receipt structure or the closed verdict lattice - it calls the same named-core
re-derivation (emet.witness_receipt.check_receipt) the CLI `emet check` uses.

Usage:
  python witness_receipt_portable.py <receipt.json> [--recompute-from-paths]
  python witness_receipt_portable.py <receipt.json> --recompute-from-paths <dir>

Verdict + exit code (mirrors the core lattice precedence):
  RECEIPT_VALID        exit 0   content address re-derives; subjects (if asked)
                                still hash to the recorded digests.
  RECEIPT_TAMPERED     exit 1   a doctored field or a changed subject.
  RECEIPT_UNVERIFIABLE exit 2   malformed receipt or an unreadable subject.
"""
import os
import sys

# Allow running both as `python adapters/witness_receipt_portable.py` and as an
# imported module from the test suite: ensure the repo root is importable.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from emet import witness_receipt  # noqa: E402

_EXIT = {"RECEIPT_VALID": 0, "RECEIPT_TAMPERED": 1, "RECEIPT_UNVERIFIABLE": 2}


def check(receipt_path, base_dir=None, recompute=False, signing_key=None):
    """Re-verify a receipt file offline. Returns (verdict, exit_code, detail).

    `base_dir` roots relative subject paths for the optional recompute; it
    defaults to the receipt file's own directory so a portable receipt+subject
    pair checks in place. `signing_key` (bytes) is optional; absent falls back to
    the EMET_RECEIPT_SIGNING_KEY env var inside check_receipt, else
    content-addressing alone.
    """
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(receipt_path)) or "."
    try:
        receipt = witness_receipt.load_receipt(receipt_path)
    except ValueError as e:
        return "RECEIPT_UNVERIFIABLE", _EXIT["RECEIPT_UNVERIFIABLE"], str(e)
    verdict, detail = witness_receipt.check_receipt(
        receipt, base_dir=base_dir, recompute=recompute, signing_key=signing_key)
    return verdict, _EXIT[verdict], detail


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    positional = [a for a in argv if not a.startswith("-")]
    recompute = "--recompute-from-paths" in argv
    if not positional:
        sys.stderr.write(__doc__)
        return 64
    receipt_path = positional[0]
    # An explicit directory may follow --recompute-from-paths; otherwise re-derive
    # relative to the receipt file's directory.
    base_dir = positional[1] if recompute and len(positional) > 1 else None
    verdict, exit_code, detail = check(receipt_path, base_dir=base_dir, recompute=recompute)
    print("result=" + verdict + " reason=" + detail)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
