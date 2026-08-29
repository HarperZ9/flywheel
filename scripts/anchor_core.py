#!/usr/bin/env python3
"""anchor_core.py -- the testable core the anchor CLI is built from.

The pieces here take no argv and open no argparse: they sign a tree head, verify
a stamped anchor, record a Bitcoin upgrade, and compute the Zenodo durability
leg. `flywheel_anchor.py` is the thin seam that wires them for a person at a
terminal; keeping the core apart lets the CLI stay small and lets these run
offline in tests/test_flywheel_anchor*.py. Every harness piece called here
(`anchor`, `ots_verify`, `receipt_signer`, `anchor_zenodo`, `zenodo_deposit`) is
separately tested.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import anchor, ots_verify, receipt_signer  # noqa: E402
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


def apply_upgrade(anchor_rec: dict, full_ots: bytes, *,
                  header: bytes | None = None) -> tuple[dict, bytes]:
    """Record the state of an already-spliced full proof, storing a verified header.

    `full_ots` is the proof `upgrade_proof` produced, standalone from the artifact
    digest. The state becomes `confirmed` when it carries a Bitcoin attestation,
    `pending` while it does not. When a block landed, the height is recorded, and
    the supplied header is stored only when it actually verifies that block (right
    proof of work, right merkle root); a header that does not verify is left out
    rather than persist a value that lies. With the header stored, a stranger
    rechecks the block offline from the record alone.
    """
    digest = bytes.fromhex(anchor_rec["digest_hex"])
    provider = (lambda h: header) if header is not None else None
    checked = ots_verify.verify(bytes(full_ots), digest, provider)
    block = dict(anchor_rec.get("ots") or {})
    leaves = checked.get("bitcoin") or []
    if leaves:
        leaf = leaves[0]
        block["state"] = "confirmed"
        block["block_height"] = leaf["height"]
        if header is not None and leaf["verified"]:
            block["block_header"] = bytes(header).hex()
        else:
            block.pop("block_header", None)
    else:
        block["state"] = "pending"
        block.pop("block_height", None)
        block.pop("block_header", None)
    rec = dict(anchor_rec)
    rec["ots"] = block
    return rec, bytes(full_ots)


def _header_provider(anchor_rec: dict):
    """A `header_provider(height)` from the record's stored block header, or None.

    A confirmed record carries the block header the proof commits, so `verify` can
    recheck the proof of work and merkle root with no network. The provider hands
    that header back only for its own height, so a proof asking for any other
    height gets nothing. Returns None when no header is stored, which is the honest
    state for a pending or absent anchor.
    """
    block = anchor_rec.get("ots") or {}
    header_hex = block.get("block_header")
    if not header_hex:
        return None
    header = bytes.fromhex(header_hex)
    height = block.get("block_height")
    return lambda h: header if (height is None or h == height) else None


# --- the Zenodo durability leg ----------------------------------------------

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
