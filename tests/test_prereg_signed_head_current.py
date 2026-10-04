"""CI gate: the published prereg signed head signs the whole ledger.

`artifacts/prereg/signed-head.json` once signed a size-1 tree while the ledger
held 8 entries, and no check noticed. This file fails whenever the file named
"signed head" disagrees with the ledger it claims to sign. Stdlib only, so it
runs in the dependency-free phase 0 slice on every OS.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import prereg_heads                       # noqa: E402
from harness.ledger import Ledger                      # noqa: E402
from harness.tree_head import check_signed_head        # noqa: E402

PREREG = ROOT / "artifacts" / "prereg"
FREEZE = json.loads((PREREG / "FREEZE.json").read_text(encoding="utf-8"))
PUBLIC = bytes.fromhex(FREEZE["public_key_hex"])


def test_published_signed_head_signs_every_ledger_entry():
    ok, why = prereg_heads.check_current(PREREG, PUBLIC, FREEZE["log_id"])
    assert ok, why


def test_freeze_names_a_head_that_still_attests_the_freeze():
    """The freeze attestation moved files, not bytes: the head FREEZE.json
    names must still be the size-1 head over the frozen ledger root."""
    head = json.loads((ROOT / FREEZE["signed_head"]).read_text(encoding="utf-8"))
    assert check_signed_head(head, PUBLIC) == (True, "ok")
    assert head["size"] == FREEZE["ledger_size"] == 1
    assert head["root"] == FREEZE["ledger_root"]


def test_every_history_head_verifies_and_has_a_proof_from_the_freeze():
    heads = sorted((PREREG / "heads").glob("head-*.json"))
    assert heads, "no history heads"
    for path in heads:
        head = json.loads(path.read_text(encoding="utf-8"))
        assert check_signed_head(head, PUBLIC) == (True, "ok"), path.name
        assert path.name == f"head-{head['size']:04d}.json"
        if head["size"] == 1:
            continue
        proof_file = prereg_heads.proof_path(PREREG / "heads", 1, head["size"])
        proof = json.loads(proof_file.read_text(encoding="utf-8"))
        assert proof["new_root"] == head["root"]
        assert Ledger.check_consistency(proof) == (True, "ok"), proof_file.name
