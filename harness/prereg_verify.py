"""Verify the preregistration ledger in one command.

    python -m harness.prereg_verify
    python -m harness.prereg_verify --dir artifacts/prereg --public-key-hex <64 hex>

Three checks, all standard library:

1. ``Ledger.verify()``: every entry chains to the one before it and the
   recomputed Merkle root is the one the ledger reports.
2. ``prereg_heads.check_current``: ``signed-head.json`` carries a valid
   signature, signs the whole ledger (size and root), and its write-once copy
   in ``heads/`` holds the same head.
3. Every history head in ``heads/`` verifies, and each has a consistency proof
   from the frozen size-1 head.

The key. Pass ``--public-key-hex`` with a key you obtained somewhere other than
this directory. Without it the key is read from ``FREEZE.json`` in the same
directory, and the output says so: a signature under a key that ships beside
the signed file shows the files agree with each other, not who signed them.

Exit codes: 0 MATCH, 1 DRIFT, 2 UNVERIFIABLE (missing files or key).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import prereg_heads
from .ledger import Ledger
from .tree_head import check_signed_head, log_id_for


def _history(prereg: Path, public: bytes) -> list[str]:
    problems: list[str] = []
    heads = sorted((prereg / "heads").glob("head-*.json"))
    if not heads:
        return ["no history heads in heads/"]
    for path in heads:
        head = json.loads(path.read_text(encoding="utf-8"))
        ok, why = check_signed_head(head, public)
        if not ok:
            problems.append(f"{path.name}: {why}")
            continue
        if head["size"] == 1:
            continue
        proof_file = prereg_heads.proof_path(prereg / "heads", 1, head["size"])
        if not proof_file.is_file():
            problems.append(f"{path.name}: no consistency proof from size 1")
            continue
        proof = json.loads(proof_file.read_text(encoding="utf-8"))
        ok, why = Ledger.check_consistency(proof)
        if not ok or proof.get("new_root") != head["root"]:
            problems.append(f"{proof_file.name}: {why if not ok else 'root differs from head'}")
    return problems


def verify(prereg: Path, key_hex: str | None) -> tuple[str, list[str], dict]:
    freeze = json.loads((prereg / "FREEZE.json").read_text(encoding="utf-8"))
    anchor = "argument" if key_hex else "self (FREEZE.json in the same directory)"
    public = bytes.fromhex(key_hex or freeze["public_key_hex"])
    log_id = log_id_for(public)
    ledger = Ledger(prereg / "ledger.jsonl", log_id=log_id)
    report = ledger.verify()
    problems: list[str] = []
    if report.get("verdict") != "MATCH":
        problems.append(f"ledger: {report.get('verdict')}: {report.get('detail')}")
    ok, why = prereg_heads.check_current(prereg, public, log_id)
    if not ok:
        problems.append(f"signed-head.json: {why}")
    problems += _history(prereg, public)
    facts = {"size": ledger.size(), "root": ledger.root(), "log_id": log_id,
             "key_source": anchor}
    return ("MATCH" if not problems else "DRIFT"), problems, facts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m harness.prereg_verify",
                                 description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", type=Path, default=Path("artifacts/prereg"))
    ap.add_argument("--public-key-hex", help="the signing key, from a source you trust")
    a = ap.parse_args(argv)
    try:
        verdict, problems, facts = verify(a.dir, a.public_key_hex)
    except (OSError, KeyError, ValueError) as exc:
        print(f"UNVERIFIABLE: {exc}", file=sys.stderr)
        return 2
    print(f"ledger size {facts['size']}, root {facts['root']}")
    print(f"log id {facts['log_id']}; key source: {facts['key_source']}")
    for p in problems:
        print(f"  problem: {p}")
    print(f"verdict: {verdict}")
    return 0 if verdict == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
