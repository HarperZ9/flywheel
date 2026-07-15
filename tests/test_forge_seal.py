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


def test_empty_arm_cannot_be_drift_checked(tmp_path):
    # sealed=sha256('') vs current='' is moved:false for an arm that never
    # existed; an empty arm is refused, not passed.
    prp_id = _seal(tmp_path)
    out = forge_recheck(tmp_path, prp_id, {"intent_source": "   "})
    assert "error" in out and "empty" in out["error"]


def test_identical_arms_are_named_degenerate(tmp_path):
    # the Y-chain collapsed to one string hashed twice is a test that cannot
    # fail; the receipt must say so instead of reporting two independent arms.
    same = "one text for both arms"
    prp_id = persist_forge_seal(
        tmp_path, GOAL,
        intent_sha256=hashlib.sha256(same.encode()).hexdigest(),
        architecture_sha256=hashlib.sha256(same.encode()).hexdigest())
    out = forge_recheck(tmp_path, prp_id, {"intent_source": same,
                                           "architecture_source": same})
    assert out["degenerate"] is True
    assert "any_moved" not in out


def test_recheck_receipt_points_at_the_stored_seal(tmp_path):
    # a stranger holding the receipt can find and re-read the seal record
    prp_id = _seal(tmp_path)
    out = forge_recheck(tmp_path, prp_id, {"intent_source": INTENT})
    assert out["prp_id"] == prp_id
    assert out["seal_path"].endswith(f"{prp_id}.json")
