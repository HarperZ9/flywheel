"""verify_compat_records.py -- check records written by Flywheel 1.x releases.

docs/VERSIONING.md promises that every 2.x release reads and verifies every
record a 1.x release wrote. The fixture set under
tests/fixtures/compat/records-1.x holds one record set per 1.x minor, each
written by that release's own code from PyPI. This script is the check: it
reads a record set with the installed `harness` package and answers MATCH,
DRIFT or FAIL.

    python scripts/verify_compat_records.py [FIXTURE_ROOT]
    python scripts/verify_compat_records.py [FIXTURE_ROOT] --control

A record set is three files: the gate envelope, the gate report that names the
envelope by its two digests, and a receipt sealed over the same candidate.

- MATCH: every file parses, is in the form its writer produces, re-derives its
  own digests, agrees with the other two files, and the oracle re-run over the
  stored candidate reaches the stored result.
- DRIFT: the files parse and something they state no longer re-derives.
- FAIL: a file is unreadable, is no record of its kind, or carries the scope
  list under both field names.

`--control` runs the false-success controls against the same reader: one byte
flipped at every offset of every file, and each receipt given the list under
both names. Exit 0 means no altered record read MATCH.

Standard library plus `harness`. It runs from a checkout or beside an
installed wheel, and writes only to a temporary folder.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "harness").is_dir():          # a checkout; an installed wheel needs nothing
    sys.path.insert(0, str(ROOT))

from harness.envelope import ProofEnvelope            # noqa: E402
from harness.gate import rewitness_envelope, run_gate  # noqa: E402
from harness.receipt import Receipt, SUPPORTED_SCHEMAS  # noqa: E402
from harness.scope import LEGACY_SCOPE_KEY, has_both   # noqa: E402

MATCH, DRIFT, FAIL = "MATCH", "DRIFT", "FAIL"
ENVELOPE, REPORT, RECEIPT = "gate_envelope.json", "gate_report.json", "receipt.json"
FILES = (ENVELOPE, REPORT, RECEIPT)
SUMS = "SHA256SUMS"
DEFAULT_ROOT = ROOT / "tests" / "fixtures" / "compat" / "records-1.x"
_1X_SCHEMAS = ("flywheel.receipt/v3", "flywheel.receipt/v4")


class _Stop(Exception):
    """One finding ends the check: (verdict, reason)."""


def _stop(verdict: str, reason: str):
    raise _Stop(verdict, reason)


_SEEN: dict = {}


def _once(stage: str, data: bytes, check):
    """Run a gate-file stage once per distinct input. The gate files are the
    same bytes in every release, so the controls would repeat each check."""
    key = (stage, hashlib.sha256(data).digest())
    if key not in _SEEN:
        try:
            _SEEN[key] = (check(), None)
        except _Stop as stop:
            _SEEN[key] = (None, stop)
    value, stop = _SEEN[key]
    if stop is not None:
        raise stop
    return value


def _load(name: str, data: bytes, *, newline: bool) -> dict:
    """Parse one file and hold it to the form its writer produces."""
    try:
        text = data.decode("utf-8")
        obj = json.loads(text)
    except (UnicodeDecodeError, ValueError):
        _stop(FAIL, f"{name}: not UTF-8 JSON")
    if not isinstance(obj, dict):
        _stop(FAIL, f"{name}: not a JSON object")
    written = json.dumps(obj, indent=2, sort_keys=True) + ("\n" if newline else "")
    if text.replace("\r\n", "\n") != written:
        _stop(DRIFT, f"{name}: bytes differ from the form the writer produces")
    return obj


@lru_cache(maxsize=1)
def _regenerated() -> tuple[dict, dict]:
    """The envelope and report this release's own gate seals, made once."""
    with tempfile.TemporaryDirectory() as tmp:
        report = run_gate(tmp)
        envelope = json.loads((Path(tmp) / ENVELOPE).read_text(encoding="utf-8"))
    return envelope, report.to_dict()


def _subset(old, new) -> bool:
    """True when every value the old record states is what the new one states.
    A later release may add a field; it may not change one."""
    if isinstance(old, dict):
        return isinstance(new, dict) and all(
            key in new and _subset(value, new[key]) for key, value in old.items())
    if isinstance(old, list):
        return (isinstance(new, list) and len(old) <= len(new)
                and all(_subset(a, b) for a, b in zip(old, new)))
    return type(old) is type(new) and old == new


def _envelope(data: bytes) -> tuple[ProofEnvelope, dict]:
    stored = _load(ENVELOPE, data, newline=False)
    try:
        envelope = ProofEnvelope(**stored)
    except TypeError:
        _stop(FAIL, f"{ENVELOPE}: not a proof envelope")
    if not _subset(stored, asdict(envelope)):
        _stop(FAIL, f"{ENVELOPE}: a field does not survive the reader")
    if not _subset(stored, _regenerated()[0]):
        _stop(DRIFT, f"{ENVELOPE}: differs from the envelope the gate seals")
    return envelope, stored


@lru_cache(maxsize=1)
def _scratch() -> Path:
    """One temporary folder for the run, removed at exit."""
    tmp = tempfile.TemporaryDirectory()
    atexit.register(tmp.cleanup)
    return Path(tmp.name)


def _rewitness(data: bytes) -> None:
    """The product's own re-witness, over the stored bytes."""
    path = _scratch() / ENVELOPE
    path.write_bytes(data)
    result = rewitness_envelope(path)
    if result != MATCH:
        _stop(DRIFT, f"{ENVELOPE}: re-witness read {result}")


def _report(data: bytes, envelope: ProofEnvelope) -> None:
    stored = _load(REPORT, data, newline=False)
    named = (stored.get("envelope_hash") == envelope.content_hash()
             and stored.get("claim_hash") == envelope.claim_hash()
             and stored.get("verdict") == envelope.verdict)
    if not named:
        _stop(DRIFT, f"{REPORT}: does not name this envelope")
    if stored.get("rewitness") != MATCH:
        _stop(DRIFT, f"{REPORT}: the writer did not record a re-witness MATCH")
    if not _subset(stored, _regenerated()[1]):
        _stop(DRIFT, f"{REPORT}: differs from the report the gate writes")


def _receipt(data: bytes, envelope: dict, release: str) -> None:
    body = _load(RECEIPT, data, newline=True)
    if has_both(body):
        _stop(FAIL, f"{RECEIPT}: carries the scope list under both field names")
    if body.get("schema") not in _1X_SCHEMAS or body["schema"] not in SUPPORTED_SCHEMAS:
        _stop(FAIL, f"{RECEIPT}: not a 1.x receipt schema")
    if LEGACY_SCOPE_KEY not in body:
        _stop(FAIL, f"{RECEIPT}: a 1.x receipt names its list {LEGACY_SCOPE_KEY}")
    try:
        receipt = Receipt.from_dict(body)
        digests = (receipt.claim_sha256(), receipt.subject_sha256())
        again = receipt.to_dict()
    except Exception as exc:               # the reader refused it: that is the finding
        _stop(FAIL, f"{RECEIPT}: the reader refused it ({type(exc).__name__})")
    if digests != (body.get("claim_sha256"), body.get("subject_sha256")):
        _stop(DRIFT, f"{RECEIPT}: a stored digest does not re-derive")
    if again != body:
        _stop(DRIFT, f"{RECEIPT}: a field does not survive the reader")
    # harness_version sits outside both receipt digests, so the receipt alone
    # cannot show it was altered. The fixture set states which release wrote it.
    if release and body["harness_version"] != release:
        _stop(DRIFT, f"{RECEIPT}: harness_version is not the release that wrote it")
    candidate = "sha256:" + hashlib.sha256(envelope["candidate"].encode()).hexdigest()
    bound = (body["candidate_sha256"] == candidate
             and body["oracle_qa_card_hash"] == envelope["oracle_output_hash"]
             and body["verdict"] == envelope["verdict"])
    if not bound:
        _stop(DRIFT, f"{RECEIPT}: not sealed over the envelope beside it")


def verify_record(files: dict, release: str = "") -> tuple[str, str]:
    """(verdict, reason) for one record set given as {file name: bytes}.
    `release` is the version that wrote it, when the caller knows."""
    try:
        missing = [name for name in FILES if name not in files]
        if missing:
            _stop(FAIL, "missing " + ", ".join(missing))
        raw = files[ENVELOPE]
        envelope, stored = _once("envelope", raw, lambda: _envelope(raw))
        _once("report", raw + files[REPORT], lambda: _report(files[REPORT], envelope))
        _receipt(files[RECEIPT], stored, release)
        _once("rewitness", raw, lambda: _rewitness(raw))
    except _Stop as stop:
        return stop.args[0], stop.args[1]
    return MATCH, ""


def read_record(folder) -> dict:
    return {name: (Path(folder) / name).read_bytes()
            for name in FILES if (Path(folder) / name).is_file()}


def record_folders(root=DEFAULT_ROOT) -> list[Path]:
    def key(path):
        return tuple(int(part) for part in path.name.split("."))
    return sorted((p for p in Path(root).iterdir()
                   if p.is_dir() and p.name[0].isdigit()), key=key)


def sums_problems(root=DEFAULT_ROOT) -> list[str]:
    """Files whose LF bytes differ from the committed SHA256SUMS."""
    problems = []
    for line in (Path(root) / SUMS).read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        path = Path(root) / name
        data = path.read_bytes().replace(b"\r\n", b"\n") if path.is_file() else None
        if data is None or hashlib.sha256(data).hexdigest() != digest:
            problems.append(name)
    return problems


def flip(data: bytes, offset: int) -> bytes:
    """`data` with the low bit of one byte inverted."""
    return data[:offset] + bytes([data[offset] ^ 1]) + data[offset + 1:]


def flipped_byte_control(verify, root=DEFAULT_ROOT) -> tuple[int, list[str]]:
    """Flip one byte at every offset of every file. Returns (flips tried, the
    flips `verify` read as MATCH). A sound reader returns an empty list."""
    tried, passed = 0, []
    for folder in record_folders(root):
        files = read_record(folder)
        for name in FILES:
            for offset in range(len(files[name])):
                altered = {**files, name: flip(files[name], offset)}
                tried += 1
                if verify(altered, folder.name)[0] == MATCH:
                    passed.append(f"{folder.name}/{name}@{offset}")
    return tried, passed


def both_names_control(verify, root=DEFAULT_ROOT) -> list[str]:
    """Give each receipt the list under both names. Returns the releases whose
    altered record `verify` read as MATCH."""
    passed = []
    for folder in record_folders(root):
        files = read_record(folder)
        body = json.loads(files[RECEIPT])
        body["scope"] = list(body[LEGACY_SCOPE_KEY])
        altered = (json.dumps(body, indent=2, sort_keys=True) + "\n").encode()
        if verify({**files, RECEIPT: altered}, folder.name)[0] == MATCH:
            passed.append(folder.name)
    return passed


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    control = "--control" in args
    paths = [a for a in args if not a.startswith("-")]
    root = Path(paths[0]) if paths else DEFAULT_ROOT
    bad = 0
    for name in sums_problems(root):
        print(f"DRIFT  {name}: bytes differ from {SUMS}")
        bad += 1
    for folder in record_folders(root):
        verdict, reason = verify_record(read_record(folder), folder.name)
        print(f"{verdict:<6} {folder.name}" + (f": {reason}" if reason else ""))
        bad += verdict != MATCH
    if control:
        tried, passed = flipped_byte_control(verify_record, root)
        both = both_names_control(verify_record, root)
        print(f"control: {tried} single-byte flips, {len(passed)} read MATCH; "
              f"{len(both)} both-name receipts read MATCH")
        bad += len(passed) + len(both)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
