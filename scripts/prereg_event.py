#!/usr/bin/env python3
"""prereg_event.py -- append an attested event to the preregistration log.

The freeze that started this log was performed by hand, which means it could not
be repeated and the next event would have been performed by hand too. This is
that ceremony as a script: append a record, sign the new tree head, and emit a
consistency proof from the previously signed head to the new one.

Three properties this is built to hold, each because the obvious shortcut breaks
one of them:

  * **The file named "signed head" signs the whole log.** `signed-head.json`
    is replaced on every append with a head over every entry, so a reader who
    checks it checks the log as it stands. Each head is also written once to
    `heads/head-<size>.json` and never touched again; `heads/head-0001.json`
    holds the freeze attestation byte for byte, and `FREEZE.json` names it.
    An earlier version left `signed-head.json` at size 1 forever, and the file
    went seven entries stale with no failure anywhere. The ceremony now refuses
    to extend a log whose current head is stale, and
    `harness.prereg_heads.check_current` fails CI on the same condition.
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

from harness import prereg_heads                                 # noqa: E402
from harness.ledger import Ledger                                # noqa: E402
from harness.tree_head import check_signed_head, sign_head       # noqa: E402

PREREG_DIR = REPO / "artifacts" / "prereg"
FREEZE = PREREG_DIR / "FREEZE.json"
LEDGER = PREREG_DIR / "ledger.jsonl"
SIGNED_HEAD = PREREG_DIR / prereg_heads.SIGNED_HEAD_NAME
HEADS = PREREG_DIR / prereg_heads.HEADS_DIR_NAME
FROZEN_HEAD = prereg_heads.head_path(HEADS, 1)
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


def _verified_head(path: Path, public: bytes, label: str) -> dict:
    if not path.is_file():
        raise CeremonyError(f"the {label} head is missing at {path.name}")
    signed = json.loads(path.read_text(encoding="utf-8"))
    ok, why = check_signed_head(signed, public)
    if not ok:
        raise CeremonyError(f"the {label} head does not verify: {why}")
    return signed


def _check_before_append(ledger: Ledger, public: bytes) -> tuple[dict, dict]:
    """Return (current signed head, frozen head), or refuse.

    Verify the log we are about to extend before extending it: appending to a
    log that fails its own audit, or whose published head is stale, would bury
    the failure one entry deeper.
    """
    if ledger.size() < 1:
        raise CeremonyError("the log is empty; freeze it before adding events")
    audit = ledger.verify()
    if audit.get("verdict") != "MATCH":
        raise CeremonyError(
            f"the existing log does not verify: {audit.get('verdict')} at entry "
            f"{audit.get('broken_at')}: {audit.get('detail')}")
    current = _verified_head(SIGNED_HEAD, public, "published")
    frozen = _verified_head(FROZEN_HEAD, public, "frozen")
    if current["size"] != ledger.size() or current["root"] != ledger.root():
        raise CeremonyError(
            f"the published head is stale: it signs size {current['size']} and "
            f"the log holds {ledger.size()} entries. Re-publish the head over "
            "the full tree before appending.")
    return current, frozen


def _event_body(freeze: dict, kind: str, payload: dict, timestamp: str):
    """Scrub, key and wrap the payload. Returns (key, body, redactions).

    Scrub BEFORE keying, so the key addresses the bytes that actually enter the
    log. Keying the raw payload would make the same observation from two
    different drives look like two different events.
    """
    payload, redactions = scrub(payload)
    key = event_key(kind, payload)
    body = {"prereg_id": freeze["prereg_id"], "kind_detail": kind,
            "recorded_at": timestamp, **payload}
    if redactions:
        body["redacted"] = [{"field": where, "removed": what}
                            for where, what in redactions]
    return key, body, redactions


def _growth_proofs(ledger: Ledger, current: dict, frozen: dict) -> list[dict]:
    """Proofs from the previous head and from the freeze to the new head.

    The previous head is what a reader who checked last time holds; the frozen
    head is what every copy of the freeze attestation holds. When they are the
    same head, one proof serves both.
    """
    olds = [current] if current["size"] == frozen["size"] else [frozen, current]
    proofs = [ledger.consistency_since({"size": o["size"], "root": o["root"]})
              for o in olds]
    for proof in proofs:
        ok, why = Ledger.check_consistency(proof)
        if not ok:
            raise CeremonyError(f"the consistency proof fails: {why}")
    return proofs


def record(kind: str, payload: dict, timestamp: str, key_path: Path,
           *, dry_run: bool = False) -> dict:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    public_hex = freeze["public_key_hex"]
    ledger = Ledger(LEDGER, log_id=freeze["log_id"])
    prior = ledger.head()
    current, frozen = _check_before_append(ledger, bytes.fromhex(public_hex))
    key, body, redactions = _event_body(freeze, kind, payload, timestamp)

    if dry_run:
        return {"dry_run": True, "kind": kind, "key": key,
                "would_extend": prior, "payload_keys": sorted(payload),
                "redactions": [w for w, _ in redactions]}

    # Idempotent replay, checked BEFORE appending. The body carries the time of
    # observation, so a second run of the same check would hash differently and
    # the ledger would refuse it. Returning early keeps the FIRST observation's
    # timestamp, which is the honest one.
    for existing in ledger.records(kind):
        if existing.get("key") == key:
            return {"idempotent": True, "kind": kind, "key": key,
                    "seq": existing["seq"], "head": prior,
                    "first_recorded_at": existing.get("recorded_at")}

    sign, public = load_seed(key_path, public_hex)
    entry = ledger.append_record(kind, key, body)
    signed = sign_head(ledger.head(), sign, public_key=public, timestamp=timestamp)
    ok, why = check_signed_head(signed, public)
    if not ok:
        raise CeremonyError(f"the head this script just signed fails: {why}")
    written = prereg_heads.publish(PREREG_DIR, signed,
                                   _growth_proofs(ledger, current, frozen))
    return {"kind": kind, "key": key, "seq": entry["seq"],
            "head": ledger.head(),
            "signed_head": str(SIGNED_HEAD.relative_to(REPO)),
            "head_file": str(written["head_file"].relative_to(REPO)),
            "consistency": [str(p.relative_to(REPO)) for p in written["proofs"]],
            "extends": {"size": current["size"], "root": current["root"]}}


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
