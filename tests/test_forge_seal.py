"""The Y-chain drift check must not trust the checked party for both sides.
The seal is persisted server-side at forge time under a prp_id; a recheck
reads the sealed hashes from disk and compares only the caller's CURRENT
sources. A caller-supplied sealed hash is refused: computing
sealed = sha256(current) yourself is not a check, it is theatre."""
import hashlib

from harness.gateway import forge_recheck, persist_forge_seal

GOAL = "add a receipted export lane"
INTENT = "the user wants exports that carry their own verification"
ARCH = "exporter writes rows; a verifier re-derives each row hash"


def _seal(tmp_path):
    return persist_forge_seal(
        tmp_path, GOAL,
        intent_sha256=hashlib.sha256(INTENT.encode()).hexdigest(),
        architecture_sha256=hashlib.sha256(ARCH.encode()).hexdigest())


def test_seal_is_persisted_and_id_returned(tmp_path):
    prp_id = _seal(tmp_path)
    assert prp_id and len(prp_id) == 16
    assert (tmp_path / "forge" / f"{prp_id}.json").is_file()


def test_recheck_reads_the_seal_from_disk(tmp_path):
    prp_id = _seal(tmp_path)
    out = forge_recheck(tmp_path, prp_id, {"intent_source": INTENT,
                                           "architecture_source": ARCH + " changed"})
    assert out["arms"]["intent"]["moved"] is False
    assert out["arms"]["architecture"]["moved"] is True
    assert out["any_moved"] is True


def test_recheck_of_unknown_prp_is_a_named_error(tmp_path):
    out = forge_recheck(tmp_path, "0123456789abcdef", {"intent_source": INTENT})
    assert "error" in out and "seal" in out["error"].lower()


def test_recheck_refuses_a_traversal_shaped_id(tmp_path):
    out = forge_recheck(tmp_path, "../evil", {"intent_source": INTENT})
    assert "error" in out


def test_recheck_with_no_comparable_arm_is_an_error(tmp_path):
    prp_id = _seal(tmp_path)
    out = forge_recheck(tmp_path, prp_id, {})
    assert "error" in out
