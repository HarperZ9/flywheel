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
here (keygen_report, build_stamp, verify_stamp, apply_upgrade) is exercised
offline in tests/test_flywheel_anchor.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import anchor, anchor_submit, ots_verify, receipt_signer  # noqa: E402
from harness import anchor_zenodo, zenodo_deposit  # noqa: E402

_COMMENT = "flywheel-receipt-signing"

# The durability leg's default deposit metadata. A skeleton the operator reviews
# and overrides on the command line; the creator is the account that holds the
# signing key and the Zenodo token.
_ZENODO_TITLE = "Flywheel confirmatory anchor: signed tree head"
_ZENODO_DESC = ("The canonical signed tree head whose sha256 is the anchor "
                "digest. Deposited so the durability DOI and the Bitcoin "
                "timestamp witness one digest, not two unrelated facts.")
_ZENODO_CREATORS = [{"name": "Harper, Zain Dana"}]


def _now_iso() -> str:
    """UTC, whole seconds, the Z-suffixed form the tree head records."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- the testable core ------------------------------------------------------

def keygen_report(info: receipt_signer.SigningKeyInfo) -> list[str]:
    """The lines `keygen` prints: public material and the one next command.

    The private key is named by its path so the operator knows where it lives,
    and is otherwise absent. Nothing here is the secret itself.
    """
    add = (f"gh ssh-key add {info.public_key_path} "
           f"--type authentication --title {_COMMENT}")
    return [
        "flywheel signing key minted (public material only shown here):",
        f"  private key : {info.private_key_path}   (held offline; never printed)",
        f"  public key  : {info.public_key_path}",
        f"  key_id      : {info.key_id}",
        f"  fingerprint : {info.fingerprint}",
        "  public line (this is what you upload):",
        "    " + receipt_signer.openssh_public_line(info.public_key_bytes, _COMMENT),
        "",
        "  register it on GitHub as an AUTHENTICATION key with:",
        "    " + add,
    ]


def build_stamp(head: dict, key, timestamp: str, *, submit=None) -> tuple[dict, bytes | None]:
    """Sign `head`, then (if `submit` is given) timestamp its digest.

    `submit` is a callable `raw_digest -> {ots, submitted_hex, nonce_hex,
    calendar, ...}`, injected so the pure part is testable; the CLI passes
    `anchor_submit.submit`. Returns (anchor record, .ots bytes or None). The
    record carries an `ots` block recording the submission so `upgrade` can
    finish it later; offline, that block is honestly `{"state": "absent"}`.
    """
    rec = anchor.sign_and_anchor(head, key.sign, public_key=key.public_key_bytes,
                                 timestamp=timestamp)
    if submit is None:
        rec["ots"] = {"state": "absent"}
        return rec, None
    res = submit(bytes.fromhex(rec["digest_hex"]))
    rec["ots"] = {"state": "pending", "submitted_hex": res["submitted_hex"],
                  "nonce_hex": res["nonce_hex"], "calendar": res["calendar"]}
    return rec, res["ots"]


def verify_stamp(anchor_rec: dict, ots_bytes, public_key: bytes, *,
                 header_provider=None) -> dict:
    """Recheck a stamped anchor: the signed head, and the timestamp if present.

    A thin pass-through to `anchor.verify_anchor`, which raises nothing and takes
    the key as an argument rather than from the record.
    """
    return anchor.verify_anchor(anchor_rec, public_key, ots_bytes=ots_bytes,
                                header_provider=header_provider)


def apply_upgrade(anchor_rec: dict, digest: bytes, nonce: bytes,
                  upgraded_reply: bytes) -> tuple[dict, bytes]:
    """Rebuild the full proof from a calendar's upgraded reply.

    The reply continues from the SUBMITTED digest; `build_ots` prepends the path
    (nonce, sha256) back to the artifact digest, so the result is a standalone
    proof. The state becomes `confirmed` only when the rebuilt proof actually
    carries a Bitcoin attestation, `pending` while it does not.
    """
    new_ots = anchor_submit.build_ots(digest, nonce, upgraded_reply)
    checked = ots_verify.verify(new_ots, digest)
    block = dict(anchor_rec.get("ots") or {})
    block["state"] = "confirmed" if checked["bitcoin"] else "pending"
    rec = dict(anchor_rec)
    rec["ots"] = block
    return rec, new_ots


def _zenodo_metadata(*, title: str = None, description: str = None,
                     creators: list = None) -> dict:
    """The deposit metadata, from overrides or the reviewed defaults. Shared by
    the dry run and the live deposit so both carry identical metadata."""
    return zenodo_deposit.build_metadata(
        title=title or _ZENODO_TITLE,
        description=description or _ZENODO_DESC,
        creators=creators or [dict(c) for c in _ZENODO_CREATORS])


def zenodo_dry_run(anchor_rec: dict, *, title: str = None,
                   description: str = None, creators: list = None) -> dict:
    """What a Zenodo deposit of this anchor WOULD carry, computed offline.

    The DOI is irreversible once published, so this is the step before it: it
    resolves the exact bytes a deposit would upload (the canonical signed head,
    whose sha256 IS the anchor digest, so the DOI witnesses the same digest the
    Bitcoin leg timestamps) and a metadata skeleton to review. It calls nothing;
    it takes no transport. `deposit_bytes` refuses a record whose stored digest
    disagrees with its own head, so a corrupt record raises here, at the
    terminal, not at the network.
    """
    name, data = anchor_zenodo.deposit_bytes(anchor_rec)
    metadata = _zenodo_metadata(title=title, description=description,
                                creators=creators)
    return {
        "filename": name,
        "size_bytes": len(data),
        "bound_digest": anchor_rec.get("anchor_digest"),
        "digest_hex": anchor_rec.get("digest_hex"),
        "metadata": metadata,
        "does_not_prove": anchor_zenodo.does_not_prove(),
    }


def zenodo_live(anchor_rec: dict, request, *, token: str, title: str = None,
                description: str = None, creators: list = None,
                sandbox: bool = False, publish: bool = False) -> dict:
    """Deposit this anchor's bound bytes for real, through the injected transport.

    The uploaded file is the canonical signed head (`deposit_bytes`), so the DOI
    witnesses exactly the digest the Bitcoin leg timestamps. A corrupt record is
    refused inside `deposit_anchor` before any network call. Draft by default; a
    created-but-unpublished deposition is a private draft the operator can inspect
    or discard. `publish=True` is the one switch that mints the permanent public
    DOI, and it is the caller's explicit choice. The transport is injected: a fake
    in tests, `zenodo_deposit.urllib_transport` at the terminal.
    """
    metadata = _zenodo_metadata(title=title, description=description,
                                creators=creators)
    return anchor_zenodo.deposit_anchor(
        request, anchor_rec, token=token, metadata=metadata,
        sandbox=sandbox, publish=publish)


def zenodo_report_lines(report: dict) -> list[str]:
    """The lines `zenodo` prints: the bound artifact, the metadata to review, and
    a plain statement that this run deposited nothing."""
    md = report["metadata"]["metadata"]
    lines = [
        "Zenodo durability leg -- DRY RUN (no deposition created, no DOI minted):",
        f"  file       : {report['filename']}  ({report['size_bytes']} bytes)",
        f"  bound to   : {report['bound_digest']}",
        "    (the deposited file's sha256 is this digest; the Bitcoin leg "
        "timestamps the same digest, so the two anchors witness one fact)",
        "  metadata skeleton (review and override with --title/--creator before a live deposit):",
        f"    title       : {md['title']}",
        f"    creators    : {', '.join(c['name'] for c in md['creators'])}",
        f"    upload_type : {md['upload_type']}",
        f"    access      : {md['access_right']} ({md.get('license', 'n/a')})",
        "  does not prove:",
    ]
    lines += [f"    - {r}" for r in report["does_not_prove"]]
    lines.append(
        "  a live deposit is a separate, gated step: it needs the Zenodo token "
        "and an explicit go, and publish is irreversible.")
    return lines


def zenodo_live_report_lines(result: dict, *, sandbox: bool) -> list[str]:
    """The lines a live deposit prints: where it landed, the draft or the DOI, and
    the standing caveats. The token is never among them."""
    where = ("SANDBOX (throwaway DOI, not citable)" if sandbox
             else "PRODUCTION (permanent public DOI)")
    lines = [
        f"Zenodo durability leg -- LIVE deposit to {where}:",
        f"  deposition : {result.get('deposition_id')}",
        f"  api record : {result.get('self_url')}  (REST endpoint, not a browsable page)",
        f"  files      : {', '.join(str(f) for f in (result.get('files') or []))}",
        f"  bound to   : {result.get('anchor_digest')}",
        f"  published  : {result.get('published')}",
    ]
    if result.get("published"):
        lines.append(f"  DOI        : {result.get('doi')}")
        lines.append(f"  DOI url    : {result.get('doi_url')}")
    else:
        lines.append("  a draft was created; no DOI minted. Re-run with --publish "
                     "to mint the permanent DOI (irreversible).")
    lines.append("  does not prove:")
    lines += [f"    - {r}" for r in result.get("does_not_prove", [])]
    return lines


def _read_token(path: str | None) -> str:
    """The deposit token, read from a file, stripped. Never argv, never a URL.

    A live deposit takes its credential from a file so it never rides the command
    line or process table. A missing or empty file is a `DepositError`, refused
    before any network call.
    """
    if not path:
        raise zenodo_deposit.DepositError(
            "a live deposit needs --token-file (the token is never passed on argv)")
    p = Path(path)
    if not p.exists():
        raise zenodo_deposit.DepositError(f"token file not found: {path}")
    # utf-8-sig transparently strips a UTF-8 BOM (PowerShell's default Out-File
    # writes one); a BOM is not whitespace, so .strip() would leave it on the token
    # and corrupt the Bearer header. Any read error (a directory, wrong ACL,
    # non-UTF-8 bytes) leaves through DepositError, not a raw traceback.
    try:
        token = p.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeDecodeError) as e:
        raise zenodo_deposit.DepositError(
            f"token file could not be read: {path} ({e})") from e
    if not token:
        raise zenodo_deposit.DepositError(f"token file is empty: {path}")
    return token


# --- CLI wiring -------------------------------------------------------------

def _ots_sibling(anchor_path: str) -> Path:
    """The proof sits beside its anchor: anchor.json -> anchor.json.ots."""
    return Path(str(anchor_path) + ".ots")


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


def cmd_upgrade(args) -> int:
    rec = json.loads(Path(args.anchor).read_text(encoding="utf-8"))
    block = rec.get("ots") or {}
    if block.get("state") == "absent" or "submitted_hex" not in block:
        print("this anchor has no submitted timestamp to upgrade")
        return 1
    reply = anchor_submit.upgrade(block["submitted_hex"], calendar=block["calendar"])
    if reply is None:
        print("the calendar has not upgraded yet -- still pending, try again later")
        return 0
    digest = bytes.fromhex(rec["digest_hex"])
    nonce = bytes.fromhex(block["nonce_hex"])
    rec, new_ots = apply_upgrade(rec, digest, nonce, reply)
    Path(args.anchor).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    _ots_sibling(args.anchor).write_bytes(new_ots)
    print(f"proof rebuilt: {_ots_sibling(args.anchor)}  ({len(new_ots)} bytes)")
    print(f"  state     : {rec['ots']['state']}")
    return 0


def cmd_verify(args) -> int:
    rec = json.loads(Path(args.anchor).read_text(encoding="utf-8"))
    pub, out_of_band = _load_pub(args.pub, rec)
    ots_path = Path(args.ots) if args.ots else _ots_sibling(args.anchor)
    ots_bytes = ots_path.read_bytes() if ots_path.exists() else None
    r = verify_stamp(rec, ots_bytes, pub)
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
