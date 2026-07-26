#!/usr/bin/env python3
"""prereg_event.py -- append an attested event to the preregistration log.

The freeze that started this log was performed by hand, which means it could not
be repeated and the next event would have been performed by hand too. This is
that ceremony as a script: append a record, sign the new tree head, and emit a
consistency proof from the previously signed head to the new one.

Three properties this is built to hold, each because the obvious shortcut breaks
one of them:

  * **The published freeze stays verifiable.** `signed-head.json` attests the log
    at size 1 and is named by `FREEZE.json` and by a git tag. Overwriting it
    would silently invalidate every copy of that attestation, so new heads are
    written to `heads/head-<size>.json` and the frozen one is never touched.
    Append-only applies to the artifacts, not only to the log.
  * **Growth is proven, not asserted.** Every event emits a consistency proof
    old_size -> new_size. Without it, "we appended" is a claim about a file the
    author controls; with it, anyone holding the old head can check that the log
    they were shown then is a prefix of the log they are shown now.
  * **The signing key is confirmed before use.** The seed is checked to derive
    the public key `FREEZE.json` already published. Signing a head of this log
    with a different key would produce a valid signature attesting to nothing,
    and the log_id check in `check_signed_head` would then reject it downstream.

The private seed is read from disk, used, and never written to any output. It
lives under a gitignored path and no artifact this script emits contains it.

Signing needs pynacl. Verification does not: everything written here is checked
by the vendored stdlib-only verifier before the script exits, so a stranger needs
no dependencies to confirm what was produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from harness.ledger import Ledger                                # noqa: E402
from harness.tree_head import check_signed_head, sign_head       # noqa: E402

PREREG_DIR = REPO / "artifacts" / "prereg"
FREEZE = PREREG_DIR / "FREEZE.json"
LEDGER = PREREG_DIR / "ledger.jsonl"
FROZEN_HEAD = PREREG_DIR / "signed-head.json"
HEADS = PREREG_DIR / "heads"
DEFAULT_KEY = REPO / ".keys" / "prereg-ledger.key"


class CeremonyError(RuntimeError):
    """The event cannot be recorded as asked."""


def load_seed(path: Path, want_public_hex: str) -> tuple[object, bytes]:
    """Return (sign callable, public key bytes), having confirmed the key.

    A seed that derives a different public key than the log published is refused
    here rather than at verification time, so the log never grows a head signed
    by a key nobody was told about.
    """
    if not path.is_file():
        raise CeremonyError(
            f"no signing key at {path}. This ceremony needs the seed that "
            f"published public key {want_public_hex[:16]}...; without it the "
            "event can be appended but not attested.")
    raw = path.read_text(encoding="utf-8").strip()
    try:
        seed = bytes.fromhex(raw)
    except ValueError:
        raise CeremonyError("the key file is not hex")
    if len(seed) != 32:
        raise CeremonyError(f"an Ed25519 seed is 32 bytes, got {len(seed)}")
    try:
        from nacl.signing import SigningKey
    except ImportError:
        raise CeremonyError(
            "signing needs pynacl (pip install pynacl). Verification does not: "
            "the vendored checker is stdlib-only.")
    sk = SigningKey(seed)
    public = bytes(sk.verify_key)
    if public.hex() != want_public_hex:
        raise CeremonyError(
            f"this seed derives public key {public.hex()[:16]}... but the log "
            f"published {want_public_hex[:16]}.... Refusing to sign a head of "
            "this log with a key that is not the log's key.")
    return (lambda msg: sk.sign(msg).signature), public


# A local path is an environment detail, never evidence: the log is published, and
# the same observation is true whichever drive the store sits on. Scrubbing is
# structural rather than a habit of the author, because the author is exactly who
# forgets. Patterns match `check_public_instructions.py`, which guards the
# instruction files; this guards the artifacts.
_LOCAL_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"']*|/(?:c|e)/(?:dev|local-model|Users)[^\s\"']*)")
REDACTED = "<redacted:local-path>"


def scrub(value, trail=""):
    """Return (scrubbed_value, [(path, what_was_removed), ...]).

    Recurses so a path buried in a nested finding is caught too. The redaction
    is recorded rather than silent: an artifact that quietly dropped a field
    would be less honest than one that says a field was removed and why.
    """
    found = []
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            sub, hits = scrub(v, f"{trail}.{k}" if trail else k)
            out[k] = sub
            found.extend(hits)
        return out, found
    if isinstance(value, list):
        out = []
        for i, v in enumerate(value):
            sub, hits = scrub(v, f"{trail}[{i}]")
            out.append(sub)
            found.extend(hits)
        return out, found
    if isinstance(value, str):
        new = _LOCAL_PATH.sub(REDACTED, value)
        if new != value:
            return new, [(trail, "local path")]
        return value, []
    return value, []


def event_key(kind: str, payload: dict) -> str:
    """A content-addressed key, so re-running with identical payload is a no-op.

    `append_record` is idempotent on (kind, key) and refuses the same key with
    different bytes. Keying on the payload digest turns that into exactly the
    behaviour wanted: recording the same observation twice changes nothing, and
    recording a different observation needs its own entry.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(kind.encode() + b"\x00" + blob).hexdigest()


def record(kind: str, payload: dict, timestamp: str, key_path: Path,
           *, dry_run: bool = False) -> dict:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    log_id = freeze["log_id"]
    public_hex = freeze["public_key_hex"]

    ledger = Ledger(LEDGER, log_id=log_id)
    old_signed = json.loads(FROZEN_HEAD.read_text(encoding="utf-8"))
    prior = ledger.head()
    if prior["size"] < 1:
        raise CeremonyError("the log is empty; freeze it before adding events")

    # Verify the log we are about to extend before extending it. Appending to a
    # log that already fails its own audit would bury the failure one entry
    # deeper.
    audit = ledger.verify()
    if audit.get("verdict") != "MATCH":
        raise CeremonyError(
            f"the existing log does not verify: {audit.get('verdict')} at entry "
            f"{audit.get('broken_at')}: {audit.get('detail')}")
    ok, why = check_signed_head(old_signed, bytes.fromhex(public_hex))
    if not ok:
        raise CeremonyError(f"the published head does not verify: {why}")

    # Scrub BEFORE keying, so the key addresses the bytes that actually enter the
    # log. Keying the raw payload would make the same observation from two
    # different drives look like two different events.
    payload, redactions = scrub(payload)
    key = event_key(kind, payload)
    body = {"prereg_id": freeze["prereg_id"], "kind_detail": kind,
            "recorded_at": timestamp, **payload}
    if redactions:
        body["redacted"] = [{"field": where, "removed": what}
                            for where, what in redactions]

    if dry_run:
        return {"dry_run": True, "kind": kind, "key": key,
                "would_extend": prior, "payload_keys": sorted(payload),
                "redactions": [w for w, _ in redactions]}

    # Idempotent replay, checked BEFORE appending. The body carries the time of
    # observation, so a second run of the same check would hash differently and
    # the ledger would refuse it as "same key, different bytes". Returning early
    # keeps the FIRST observation's timestamp, which is the honest one, and keeps
    # a re-run from being either an error or a duplicate entry.
    for existing in ledger.records(kind):
        if existing.get("key") == key:
            return {"idempotent": True, "kind": kind, "key": key,
                    "seq": existing["seq"], "head": prior,
                    "first_recorded_at": existing.get("recorded_at")}

    sign, public = load_seed(key_path, public_hex)
    entry = ledger.append_record(kind, key, body)
    new_head = ledger.head()

    signed = sign_head(new_head, sign, public_key=public, timestamp=timestamp)
    proof = ledger.consistency_since({"size": old_signed["size"],
                                      "root": old_signed["root"]})

    # Check both artifacts with the stdlib-only verifiers before writing them.
    ok, why = check_signed_head(signed, public)
    if not ok:
        raise CeremonyError(f"the head this script just signed fails: {why}")
    ok, why = Ledger.check_consistency(proof)
    if not ok:
        raise CeremonyError(f"the consistency proof fails: {why}")

    HEADS.mkdir(parents=True, exist_ok=True)
    head_path = HEADS / f"head-{new_head['size']:04d}.json"
    proof_path = HEADS / (f"consistency-{old_signed['size']:04d}"
                          f"-to-{new_head['size']:04d}.json")
    head_path.write_text(json.dumps(signed, indent=1) + "\n", encoding="utf-8")
    proof_path.write_text(json.dumps(proof, indent=1) + "\n", encoding="utf-8")

    return {"kind": kind, "key": key, "seq": entry["seq"],
            "head": new_head, "signed_head": str(head_path.relative_to(REPO)),
            "consistency": str(proof_path.relative_to(REPO)),
            "extends": {"size": old_signed["size"], "root": old_signed["root"]}}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", required=True,
                    help="event kind, e.g. ladder-possession")
    ap.add_argument("--payload-file", required=True,
                    help="JSON file holding the observation being recorded")
    ap.add_argument("--timestamp", required=True,
                    help="ISO-8601 UTC; supplied by the caller so output pins")
    ap.add_argument("--key", default=str(DEFAULT_KEY))
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be appended, sign nothing")
    args = ap.parse_args()

    payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("the payload must be a JSON object", file=sys.stderr)
        return 1
    try:
        out = record(args.kind, payload, args.timestamp, Path(args.key),
                     dry_run=args.dry_run)
    except (CeremonyError, ValueError) as exc:
        print(f"CEREMONY REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
