#!/usr/bin/env python3
"""flywheel_anchor.py -- the key and the external anchor, usable end to end.

Four subcommands cover the whole life of an anchored tree head:

  keygen   mint the Ed25519 signing key (public material printed, secret never)
  stamp    sign a tree head and submit its digest to OpenTimestamps calendars
  upgrade  replace a pending proof with the Bitcoin attestation once it lands
  verify   recheck a stamped anchor the way a stranger does, offline

The signing key is minted by `receipt_signer` (ssh-keygen, secret written to a
file the operator owns and never shown). The digest, the signed head, and the
proof are produced by `anchor`/`anchor_submit`, and rechecked by the stdlib
verifier `ots_verify`. This script is only the seam that wires them for a person
at a terminal; every piece it calls is separately tested, and the testable core
it drives (keygen_report, build_stamp, verify_stamp, apply_upgrade, the Zenodo
leg) lives in `anchor_core` and is exercised offline in
tests/test_flywheel_anchor*.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import anchor_submit, ots_verify, receipt_signer  # noqa: E402
from harness import zenodo_deposit  # noqa: E402
# The testable core the CLI drives. Re-exported through this module so callers
# and tests reach the whole surface as `flywheel_anchor.<name>`.
from scripts.anchor_core import (  # noqa: E402,F401
    _COMMENT, _header_provider, _now_iso, _read_token, apply_upgrade,
    build_stamp, keygen_report, verify_stamp, zenodo_dry_run, zenodo_live,
    zenodo_live_report_lines, zenodo_report_lines)


# --- CLI wiring -------------------------------------------------------------

def _ots_sibling(anchor_path: str) -> Path:
    """The proof sits beside its anchor: anchor.json -> anchor.json.ots."""
    return Path(str(anchor_path) + ".ots")


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes to a temp sibling, then os.replace onto `path`. os.replace is
    atomic on one filesystem, so a reader (or a crashing writer) never leaves a
    half-written file: the target is either the whole old content or the whole
    new content, never a truncation."""
    tmp = Path(str(path) + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    """The utf-8 text sibling of _atomic_write_bytes, for the JSON record."""
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _load_pub(spec: str | None, rec: dict) -> tuple[bytes, bool]:
    """(public key, out_of_band). A `.pub` path or hex is the trust anchor; with
    neither, fall back to the record's own key and flag it consistency-only."""
    if spec:
        p = Path(spec)
        if p.exists():
            return receipt_signer._raw_public_key_from_openssh(p), True
        return bytes.fromhex(spec), True
    return bytes.fromhex(rec["signed_head"]["public_key"]), False


def cmd_keygen(args) -> int:
    info = receipt_signer.generate_signing_key(
        args.key, comment=_COMMENT, overwrite=args.overwrite)
    for line in keygen_report(info):
        print(line)
    return 0


def cmd_stamp(args) -> int:
    head = json.loads(Path(args.head).read_text(encoding="utf-8"))
    key = receipt_signer.load_signing_key(args.key)
    ts = args.timestamp or _now_iso()
    submit = None if args.offline else (lambda raw: anchor_submit.submit(raw))
    rec, ots = build_stamp(head, key, ts, submit=submit)
    Path(args.out).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(f"anchor written: {args.out}")
    print(f"  digest    : {rec['anchor_digest']}")
    if ots is None:
        print("  timestamp : absent (offline); run stamp without --offline to submit")
        return 0
    _ots_sibling(args.out).write_bytes(ots)
    print(f"  proof     : {_ots_sibling(args.out)}  ({len(ots)} bytes)")
    print(f"  calendar  : {rec['ots']['calendar']}")
    print("  state     : pending -- run `upgrade` in a few hours for the block")
    return 0


def _print_confirmed_block(full_ots: bytes, digest: bytes, rec: dict) -> None:
    """Re-verify a confirmed proof offline from the record's own stored header and
    print the block it lands in, so a poll re-run and a later `verify` agree."""
    final = ots_verify.verify(full_ots, digest, _header_provider(rec))
    leaf = (final.get("bitcoin") or [{}])[0]
    print(f"  block     : height {leaf.get('height')}  "
          f"(verified offline: {final['ok']})")


def cmd_upgrade(args) -> int:
    rec = json.loads(Path(args.anchor).read_text(encoding="utf-8"))
    block = rec.get("ots") or {}
    if block.get("state") == "absent" or "submitted_hex" not in block:
        print("this anchor has no submitted timestamp to upgrade")
        return 1
    ots_path = _ots_sibling(args.anchor)
    if not ots_path.exists():
        print(f"no pending proof beside the anchor: {ots_path}")
        return 1
    digest = bytes.fromhex(rec["digest_hex"])
    # Already confirmed: a re-run has nothing to poll -- a confirmed proof carries
    # no pending message. Re-verify offline from the stored header and report, so a
    # poller re-run agrees with `verify` instead of misreading it as still pending.
    if block.get("state") == "confirmed":
        print(f"already confirmed: {ots_path}")
        _print_confirmed_block(ots_path.read_bytes(), digest, rec)
        return 0
    pending_ots = ots_path.read_bytes()
    # Poll the calendar and splice the block in place of the promise, then fetch the
    # block header so the confirmed record verifies offline. A transient calendar or
    # explorer failure, or a continuation that does not improve the proof, leaves
    # through SubmitError with the good pending .ots on disk untouched.
    try:
        full_ots = anchor_submit.upgrade_proof(pending_ots, digest)
        if full_ots is None:
            print("the calendar has not upgraded yet -- still pending, try again later")
            return 0
        checked = ots_verify.verify(full_ots, digest)
        leaves = checked.get("bitcoin") or []
        header = anchor_submit.block_header(leaves[0]["height"]) if leaves else None
    except anchor_submit.SubmitError as e:
        print(f"upgrade did not complete: {e}", file=sys.stderr)
        print(f"  the pending proof is left untouched: {ots_path}", file=sys.stderr)
        return 3
    rec, full_ots = apply_upgrade(rec, full_ots, header=header)
    # Persist the proof before the record, each atomically. The two artifacts are
    # written in sequence and a process can die between them; proof-first means any
    # interruption lands on the safe side -- the intact old pending pair, or a
    # confirmed pair -- never a `confirmed` record over a stale/truncated .ots that
    # the confirmed short-circuit above would then refuse to re-poll (Finding 7).
    _atomic_write_bytes(ots_path, full_ots)
    _atomic_write_text(Path(args.anchor), json.dumps(rec, indent=2))
    state = rec["ots"]["state"]
    print(f"proof upgraded: {ots_path}  ({len(full_ots)} bytes)")
    print(f"  state     : {state}")
    if state == "confirmed":
        _print_confirmed_block(full_ots, digest, rec)
    return 0


def cmd_verify(args) -> int:
    rec = json.loads(Path(args.anchor).read_text(encoding="utf-8"))
    pub, out_of_band = _load_pub(args.pub, rec)
    ots_path = Path(args.ots) if args.ots else _ots_sibling(args.anchor)
    ots_bytes = ots_path.read_bytes() if ots_path.exists() else None
    # A confirmed record carries the block header; supply it so the Bitcoin leg
    # verifies offline instead of reporting present-but-unproven.
    r = verify_stamp(rec, ots_bytes, pub, header_provider=_header_provider(rec))
    print(f"head_ok   : {r['head_ok']}  ({r['head_reason']})")
    print(f"digest    : {r['anchor_digest']}")
    ts = r["timestamp"]
    if isinstance(ts, dict):
        print(f"timestamp : ok={ts['ok']}  ({ts['reason']})")
    else:
        print(f"timestamp : {ts}")
    print(f"ANCHORED  : {r['ok']}")
    if not out_of_band:
        print("  note: no --pub given; checked against the record's own key "
              "(consistency only, not identity)")
    return 0 if r["ok"] else 1


def cmd_zenodo(args) -> int:
    # --publish only means something with --live; a dry run mints nothing. Refuse
    # the nonsensical combination rather than ignore it silently.
    if args.publish and not args.live:
        print("REFUSED: --publish requires --live (a dry run mints nothing)",
              file=sys.stderr)
        return 3
    try:
        rec = json.loads(Path(args.anchor).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"REFUSED: could not read anchor record {args.anchor}: {e}",
              file=sys.stderr)
        return 3
    creators = [{"name": args.creator}] if args.creator else None
    if not args.live:
        try:
            report = zenodo_dry_run(rec, title=args.title, creators=creators)
        except zenodo_deposit.DepositError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 3
        for line in zenodo_report_lines(report):
            print(line)
        return 0
    # Live path: the token comes from a file, and publish is the one irreversible
    # switch. The corrupt-record guard in deposit_anchor still runs before the net.
    try:
        token = _read_token(args.token_file)
        result = zenodo_live(rec, zenodo_deposit.urllib_transport, token=token,
                             title=args.title, creators=creators,
                             sandbox=args.sandbox, publish=args.publish)
    except zenodo_deposit.DepositError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        # If create() had already succeeded, a draft exists on Zenodo; surface it
        # so the operator can find and discard it instead of re-running blind.
        if getattr(e, "deposition_id", None) or getattr(e, "self_url", None):
            print(f"  a draft may already exist on Zenodo: deposition "
                  f"{e.deposition_id} at {e.self_url} -- find and discard it "
                  f"before re-running", file=sys.stderr)
        return 3
    for line in zenodo_live_report_lines(result, sandbox=args.sandbox):
        print(line)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="mint the key and anchor a signed tree head")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("keygen", help="mint the Ed25519 signing key")
    g.add_argument("--key", default=str(receipt_signer.DEFAULT_KEY_PATH),
                   help="private key path (default: ~/.flywheel/keys/...)")
    g.add_argument("--overwrite", action="store_true",
                   help="retire an existing key at that path (careful)")
    g.set_defaults(func=cmd_keygen)

    s = sub.add_parser("stamp", help="sign a tree head and timestamp its digest")
    s.add_argument("--head", required=True, help="JSON tree head (from Ledger.head())")
    s.add_argument("--out", required=True, help="anchor record to write")
    s.add_argument("--key", default=str(receipt_signer.DEFAULT_KEY_PATH))
    s.add_argument("--timestamp", default=None, help="head attestation time (default: now)")
    s.add_argument("--offline", action="store_true", help="sign only, do not submit")
    s.set_defaults(func=cmd_stamp)

    u = sub.add_parser("upgrade", help="finish a pending proof into a Bitcoin block")
    u.add_argument("--anchor", required=True, help="anchor record from `stamp`")
    u.set_defaults(func=cmd_upgrade)

    v = sub.add_parser("verify", help="recheck a stamped anchor offline")
    v.add_argument("--anchor", required=True)
    v.add_argument("--ots", default=None, help="proof file (default: <anchor>.ots)")
    v.add_argument("--pub", default=None,
                   help="signer public key as .pub path or hex (out-of-band trust)")
    v.set_defaults(func=cmd_verify)

    z = sub.add_parser(
        "zenodo",
        help="the durability DOI leg: dry-run by default (show the exact bytes and "
             "metadata a deposit would carry, no network); --live to deposit")
    z.add_argument("--anchor", required=True, help="anchor record from `stamp`")
    z.add_argument("--title", default=None, help="override the deposit title")
    z.add_argument("--creator", default=None,
                   help="override the sole creator, as 'Family, Given'")
    z.add_argument("--live", action="store_true",
                   help="deposit for real (default is a dry run that touches nothing)")
    z.add_argument("--token-file", default=None,
                   help="path to the Zenodo token (read from a file, never argv); "
                        "required with --live")
    z.add_argument("--sandbox", action="store_true",
                   help="deposit to sandbox.zenodo.org (a throwaway DOI) instead of "
                        "production")
    z.add_argument("--publish", action="store_true",
                   help="mint the permanent DOI (IRREVERSIBLE); without it a draft "
                        "is created and left unpublished")
    z.set_defaults(func=cmd_zenodo)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
