"""anchor_cli.py -- `flywheel anchor`: witness a head with parties the author does not control.

  flywheel anchor head <head.json> --key <key file> [--expect-public-key HEX]
                       [--anchor-dir DIR] [--ots | --no-ots] [--dry-run]
  flywheel anchor verify <head.json> --public-key HEX [--anchor-dir DIR | --record PATH]
                       [--ots-anchor PATH] [--head-key HEX] [--online]

`head` logs the artifact's SHA-512 and an Ed25519ph signature in Sigstore's Rekor
and, with `--ots`, submits its SHA-256 to OpenTimestamps calendars. Two anchors
with different controllers: the Sigstore project runs Rekor, and OpenTimestamps
commits into Bitcoin. Only hashes and the signature leave the machine.
`--dry-run` prints the exact entry that would be sent and sends nothing.

`verify` rechecks the Rekor record offline against the PINNED Rekor key, and the
OpenTimestamps anchor when given. `--online` also refetches the entry and proves
the stored checkpoint is a prefix of today's log. The public key is always an
argument, never read from the record.

A JSON artifact is anchored in its canonical form (sorted keys, tight
separators), so a checkout that rewrites line endings still hashes the same.
Exit codes: 0 every anchor checked holds, 1 something failed, 2 usage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import anchor, rekor_online, rekor_submit, rekor_verify
from .receipt_fields import canonical


def artifact_bytes(path: Path) -> tuple[bytes, str]:
    """(bytes to anchor, form). JSON is canonicalized; anything else is raw."""
    raw = Path(path).read_bytes()
    if Path(path).suffix.lower() == ".json":
        return canonical(json.loads(raw.decode("utf-8-sig"))).encode(), "canonical-json"
    return raw, "raw"


def record_path(path: Path, anchor_dir: Path | None = None, suffix: str = "-rekor.json") -> Path:
    """Where an anchor record for `path` lives: `<stem>-rekor.json` (or
    `<stem>-anchor.json` for OpenTimestamps) in `anchor_dir`, default the
    artifact's own directory. Prereg heads use `artifacts/anchor/`, beside the
    existing OpenTimestamps anchor, so no record lands in `heads/`."""
    base = Path(anchor_dir) if anchor_dir else Path(path).parent
    return base / (Path(path).stem + suffix)


def rekor_suffix(public_key: bytes) -> str:
    """One Rekor record per (artifact, key): the key's first 8 hex in the name."""
    return f"-rekor-{bytes(public_key).hex()[:8]}.json"


def _rel(path: Path) -> str:
    """A repo-relative, forward-slash path for the record; never a local root."""
    p = Path(path).resolve()
    for parent in p.parents:
        if (parent / ".git").exists():
            return p.relative_to(parent).as_posix()
    return p.name


def _write_json(path: Path, obj: dict) -> None:
    Path(path).write_text(json.dumps(obj, indent=2) + "\n",
                          encoding="utf-8", newline="\n")


def cmd_head(args) -> int:
    data, form = artifact_bytes(args.artifact)
    sign_ph, public = rekor_submit.load_ph_signer(Path(args.key), args.expect_public_key)
    entry = rekor_submit.proposed_entry(data, sign_ph, public)
    if args.dry_run:
        print(json.dumps({"would_send_to": rekor_verify.REKOR_URL + rekor_submit.ENTRIES_PATH,
                          "artifact_form": form, "entry": entry}, indent=2))
        return 0
    uuid, logged = rekor_submit.submit(entry, rekor_submit.urllib_request)
    rec = rekor_submit.build_record(_rel(args.artifact), data, public, uuid, logged)
    rec["artifact"]["form"] = form
    check = rekor_verify.verify_record(rec, data, public)
    if not check["ok"]:
        print(f"Rekor returned an entry that does not verify: {check['reasons']}",
              file=sys.stderr)
        return 1
    out = record_path(args.artifact, args.anchor_dir, rekor_suffix(public))
    _write_json(out, rec)
    print(f"rekor: log index {rec['log_index']}, integrated {rec['integrated_time']}")
    print(f"  record : {out}")
    print(f"  search : {rec['search_url']}")
    if args.ots:
        return _stamp_ots(record_path(args.artifact, args.anchor_dir, "-anchor.json"), data)
    return 0


def _stamp_ots(out: Path, data: bytes) -> int:
    from . import anchor_submit
    head = json.loads(data)
    if head.get("schema") != "flywheel.signed-tree-head/v1":
        print("ots: skipped, only signed tree heads take the OpenTimestamps leg")
        return 0
    if out.exists():
        print(f"ots: skipped, {out} already exists (upgrade it, never overwrite)")
        return 0
    rec = anchor.build_anchor(head)
    res = anchor_submit.submit(bytes.fromhex(rec["digest_hex"]))
    rec["ots"] = {"state": "pending", "submitted_hex": res["submitted_hex"],
                  "nonce_hex": res["nonce_hex"], "calendar": res["calendar"]}
    _write_json(out, rec)
    Path(str(out) + ".ots").write_bytes(res["ots"])
    print(f"ots: pending at {res['calendar']}; record {out}")
    print("  upgrade once Bitcoin confirms: python scripts/flywheel_anchor.py upgrade " + str(out))
    return 0


def _verify_ots(path: str, data: bytes, head_key: bytes) -> dict:
    rec = json.loads(Path(path).read_text(encoding="utf-8"))
    if canonical(rec.get("signed_head")).encode() != data:
        return {"ok": False, "reasons": ["OTS_ANCHOR_IS_FOR_OTHER_BYTES"]}
    ots_file = Path(str(path) + ".ots")
    ots_bytes = ots_file.read_bytes() if ots_file.exists() else None
    res = anchor.verify_anchor(rec, head_key, ots_bytes=ots_bytes,
                               header_provider=anchor.stored_header_provider(rec))
    ts = res["timestamp"]
    reasons = [] if res["ok"] else [res["head_reason"] or "OTS_TIMESTAMP_NOT_CONFIRMED"]
    height = None
    if isinstance(ts, dict):
        height = next((b["height"] for b in ts.get("bitcoin") or [] if b.get("verified")), None)
    return {"ok": res["ok"], "reasons": reasons, "bitcoin_block": height}


def cmd_verify(args) -> int:
    data, _ = artifact_bytes(args.artifact)
    public = bytes.fromhex(args.public_key)
    rec_path = (Path(args.record) if args.record
                else record_path(args.artifact, args.anchor_dir, rekor_suffix(public)))
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    results = {"rekor_offline": rekor_verify.verify_record(rec, data, public)}
    if args.online:
        results["rekor_online"] = rekor_online.verify_online(
            rec, data, public, rekor_submit.urllib_request)
    if args.ots_anchor:
        head_key = bytes.fromhex(args.head_key or args.public_key)
        results["opentimestamps"] = _verify_ots(args.ots_anchor, data, head_key)
    ok = all(r["ok"] for r in results.values())
    print(json.dumps({"ok": ok, "artifact": str(args.artifact), **results,
                      "does_not_prove": rekor_verify.does_not_prove()}, indent=2))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="flywheel anchor", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("head", help="log a head in Rekor (and optionally OpenTimestamps)")
    h.add_argument("artifact", type=Path)
    h.add_argument("--key", required=True, help="OpenSSH Ed25519 private key or hex seed file")
    h.add_argument("--expect-public-key", help="refuse a key that derives any other public key")
    h.add_argument("--ots", action=argparse.BooleanOptionalAction, default=True,
                   help="also submit to OpenTimestamps calendars (default on)")
    h.add_argument("--dry-run", action="store_true", help="print the entry; send nothing")
    h.add_argument("--anchor-dir", type=Path, help="where records go (default: beside the artifact)")
    v = sub.add_parser("verify", help="recheck the anchors of a head")
    v.add_argument("artifact", type=Path)
    v.add_argument("--public-key", required=True, help="the Rekor entry's key, pinned out of band")
    v.add_argument("--record", help="the Rekor record (default: <stem>-rekor-<key8>.json in --anchor-dir)")
    v.add_argument("--anchor-dir", type=Path, help="where the records are (default: beside the artifact)")
    v.add_argument("--ots-anchor", help="an OpenTimestamps anchor record to check as well")
    v.add_argument("--head-key", help="the head's own signing key, if not --public-key")
    v.add_argument("--online", action="store_true", help="refetch from Rekor and prove consistency")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return cmd_head(args) if args.cmd == "head" else cmd_verify(args)
    except (RuntimeError, OSError, ValueError) as e:  # RekorError, SubmitError, OtsError
        print(f"flywheel anchor: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
