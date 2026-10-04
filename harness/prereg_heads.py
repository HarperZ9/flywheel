"""prereg_heads.py -- where the preregistration log keeps its signed heads.

Two files carry two different promises, and the names say which:

  * ``signed-head.json`` is the CURRENT head. It signs the whole tree, every
    entry in ``ledger.jsonl``, and it is replaced on every append. A reader who
    opens the file named "signed head" gets the head of the log as it stands.
  * ``heads/head-NNNN.json`` is the head at size NNNN, written once and never
    touched again. ``heads/head-0001.json`` is the freeze attestation that
    ``FREEZE.json`` and the freeze git tag name; its bytes are the bytes that
    were published at the freeze.

Until 2026-10-04 the roles were reversed: ``signed-head.json`` held the frozen
size-1 head forever and new heads went only to ``heads/``. A reader who checked
the file named "signed head" checked a head seven entries stale, and nothing
failed. ``check_current`` is the gate that makes that state a test failure.

Stdlib only, like the verifiers it calls, so a stranger needs no dependencies to
run the check.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .ledger import Ledger
from .tree_head import check_signed_head

SIGNED_HEAD_NAME = "signed-head.json"
HEADS_DIR_NAME = "heads"


def head_path(heads_dir: Path, size: int) -> Path:
    """The write-once file for the head at ``size``."""
    return Path(heads_dir) / f"head-{size:04d}.json"


def proof_path(heads_dir: Path, old_size: int, new_size: int) -> Path:
    return Path(heads_dir) / f"consistency-{old_size:04d}-to-{new_size:04d}.json"


def _dump(obj: dict) -> str:
    # The format every head and proof in artifacts/prereg already uses.
    return json.dumps(obj, indent=1) + "\n"


def write_atomic(path: Path, text: str) -> None:
    """Replace ``path`` in one step, so a crash never leaves half a head."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_once(path: Path, text: str) -> None:
    """Write a historical head or proof. An existing file with other bytes is
    refused: a size-N head that changed after publication is a rewrite."""
    path = Path(path)
    if path.exists():
        if path.read_text(encoding="utf-8") == text:
            return
        raise FileExistsError(
            f"{path.name} already exists with different bytes; historical heads "
            "and proofs are write-once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def publish(prereg_dir: Path, signed: dict, proofs: list[dict]) -> dict:
    """Write the new head everywhere it belongs, current head LAST.

    The write-once copy and the proofs land first. ``signed-head.json`` moves
    only after them, so a reader never sees a current head whose history file
    or growth proof is missing.
    """
    prereg_dir = Path(prereg_dir)
    heads = prereg_dir / HEADS_DIR_NAME
    hp = head_path(heads, signed["size"])
    write_once(hp, _dump(signed))
    written = []
    for proof in proofs:
        pp = proof_path(heads, proof["old_size"], proof["new_size"])
        write_once(pp, _dump(proof))
        written.append(pp)
    write_atomic(prereg_dir / SIGNED_HEAD_NAME, _dump(signed))
    return {"head_file": hp, "proofs": written}


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_current(prereg_dir: Path, public_key: bytes, log_id: str) -> tuple[bool, str]:
    """(ok, reason). Does ``signed-head.json`` sign the whole ledger.

    Checks, in order: the signature verifies under the key the caller trusts;
    the signed size equals the number of ledger entries; the signed root equals
    the root recomputed from the ledger; the write-once copy at that size holds
    the same head. The key is an argument, never read from the head.
    """
    prereg_dir = Path(prereg_dir)
    sh_path = prereg_dir / SIGNED_HEAD_NAME
    if not sh_path.is_file():
        return False, "no_signed_head"
    signed = _load(sh_path)
    ok, why = check_signed_head(signed, public_key)
    if not ok:
        return False, f"signed_head_invalid: {why}"
    ledger = Ledger(prereg_dir / "ledger.jsonl", log_id=log_id)
    if signed.get("size") != ledger.size():
        return False, (f"stale_signed_head: signs size {signed.get('size')}, "
                       f"ledger holds {ledger.size()} entries")
    if signed.get("root") != ledger.root():
        return False, "signed_root_differs_from_ledger_root"
    copy = head_path(prereg_dir / HEADS_DIR_NAME, signed["size"])
    if not copy.is_file() or _load(copy) != signed:
        return False, f"missing_or_different_history_copy: {copy.name}"
    return True, "ok"
