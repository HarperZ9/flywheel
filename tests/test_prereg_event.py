"""The prereg event ceremony: append, sign, prove growth, leak nothing.

The freeze it extends was done by hand once. These tests pin the properties that
made it worth turning into a script: the file named signed-head.json always signs
the whole log, the frozen head is never overwritten, growth carries a consistency
proof, a wrong key is refused before it signs, and a
local path cannot ride into a published artifact.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "prereg_event", ROOT / "scripts" / "prereg_event.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

nacl = pytest.importorskip("nacl.signing", reason="signing needs pynacl")

SEED = bytes(range(32))


# ---- scrubbing: a published artifact carries no local path


def test_drive_paths_are_scrubbed():
    out, hits = E.scrub({"store": r"E:\some-drive\model-store"})
    assert out["store"] == E.REDACTED
    assert hits == [("store", "local path")]


def test_scrub_recurses_into_lists_and_nested_objects():
    payload = {"findings": [{"notes": ["no manifest at C:/somewhere/x/y"]},
                            {"notes": ["clean"]}]}
    out, hits = E.scrub(payload)
    assert E.REDACTED in out["findings"][0]["notes"][0]
    assert out["findings"][1]["notes"] == ["clean"]
    assert [w for w, _ in hits] == ["findings[0].notes[0]"]


def test_scrub_leaves_evidence_alone():
    """Digests, model refs and verdicts must survive untouched, or the scrub
    would be destroying the very thing being recorded."""
    payload = {"verdict": "CONSISTENT_WITH_FREEZE", "frozen_sha256": "a" * 64,
               "model": "qwen2.5-coder:32b-instruct-q4_K_M",
               "layer": "sha256:" + "b" * 64, "bytes": 19_851_336_480}
    out, hits = E.scrub(payload)
    assert hits == []
    assert out == payload


def test_posix_local_paths_are_scrubbed_too():
    out, hits = E.scrub({"note": "see /c/dev/local-model/harness"})
    assert E.REDACTED in out["note"]
    assert hits


# ---- keying


def test_event_key_is_content_addressed_and_stable():
    a = E.event_key("k", {"x": 1, "y": 2})
    b = E.event_key("k", {"y": 2, "x": 1})
    assert a == b, "key order must not change the key"
    assert a != E.event_key("k", {"x": 1, "y": 3})
    assert a != E.event_key("other", {"x": 1, "y": 2})


# ---- the ceremony, on an isolated log


def build_log(tmp_path, monkeypatch, seed=SEED):
    """A freeze-shaped log of size 1, signed by `seed`, in a temp dir."""
    import sys
    sys.path.insert(0, str(ROOT))
    from harness.ledger import Ledger
    from harness.tree_head import log_id_for, sign_head

    sk = nacl.SigningKey(seed)
    public = bytes(sk.verify_key)
    d = tmp_path / "prereg"
    d.mkdir()
    ledger_path = d / "ledger.jsonl"
    log_id = log_id_for(public)
    led = Ledger(ledger_path, log_id=log_id)
    led.append_record("prereg-freeze", "k" * 64, {"sha256": "k" * 64})
    signed = sign_head(led.head(), lambda m: sk.sign(m).signature,
                       public_key=public, timestamp="2026-01-01T00:00:00Z")
    (d / "signed-head.json").write_text(json.dumps(signed), encoding="utf-8")
    (d / "heads").mkdir()
    (d / "heads" / "head-0001.json").write_text(json.dumps(signed),
                                                encoding="utf-8")
    (d / "FREEZE.json").write_text(json.dumps({
        "prereg_id": "test.v1", "log_id": log_id,
        "public_key_hex": public.hex()}), encoding="utf-8")
    keyfile = tmp_path / "k.key"
    keyfile.write_text(seed.hex(), encoding="utf-8")

    monkeypatch.setattr(E, "PREREG_DIR", d)
    monkeypatch.setattr(E, "FREEZE", d / "FREEZE.json")
    monkeypatch.setattr(E, "LEDGER", ledger_path)
    monkeypatch.setattr(E, "SIGNED_HEAD", d / "signed-head.json")
    monkeypatch.setattr(E, "FROZEN_HEAD", d / "heads" / "head-0001.json")
    monkeypatch.setattr(E, "HEADS", d / "heads")
    monkeypatch.setattr(E, "REPO", tmp_path)
    return d, keyfile, signed


def test_event_appends_signs_and_proves_growth(tmp_path, monkeypatch):
    from harness.ledger import Ledger
    from harness.tree_head import check_signed_head
    d, keyfile, frozen = build_log(tmp_path, monkeypatch)

    out = E.record("ladder-possession", {"verdict": "OK"},
                   "2026-07-26T23:30:00Z", keyfile)
    assert out["head"]["size"] == 2
    assert out["extends"]["size"] == 1

    public = bytes.fromhex(json.loads(
        (d / "FREEZE.json").read_text(encoding="utf-8"))["public_key_hex"])
    head = json.loads((d / "heads" / "head-0002.json").read_text(encoding="utf-8"))
    ok, why = check_signed_head(head, public)
    assert ok, why
    proof = json.loads(next((d / "heads").glob("consistency-*.json"))
                       .read_text(encoding="utf-8"))
    ok, why = Ledger.check_consistency(proof)
    assert ok, why
    assert proof["old_root"] == frozen["root"], (
        "the proof must anchor to the head that was actually published")


def _public(d):
    return bytes.fromhex(json.loads(
        (d / "FREEZE.json").read_text(encoding="utf-8"))["public_key_hex"])


def _log_id(d):
    return json.loads((d / "FREEZE.json").read_text(encoding="utf-8"))["log_id"]


def test_the_frozen_head_is_never_overwritten(tmp_path, monkeypatch):
    """FREEZE.json and the freeze tag name the size-1 head. Rewriting it would
    invalidate every distributed copy of the freeze attestation."""
    d, keyfile, frozen = build_log(tmp_path, monkeypatch)
    before = (d / "heads" / "head-0001.json").read_bytes()
    E.record("a", {"verdict": "OK"}, "2026-07-26T23:30:00Z", keyfile)
    E.record("b", {"verdict": "OK"}, "2026-07-26T23:31:00Z", keyfile)
    assert (d / "heads" / "head-0001.json").read_bytes() == before
    assert json.loads(before)["size"] == 1


def test_appending_moves_the_signed_head_to_the_full_tree(tmp_path, monkeypatch):
    """The defect this pins: signed-head.json stayed at size 1 while the log
    grew to 8, so the file named "signed head" signed a stale tree. After every
    append it must sign every entry."""
    from harness import prereg_heads
    from harness.ledger import Ledger
    from harness.tree_head import check_signed_head
    d, keyfile, _ = build_log(tmp_path, monkeypatch)
    for i in range(3):
        E.record(f"k{i}", {"v": i}, f"2026-07-26T23:3{i}:00Z", keyfile)
        head = json.loads((d / "signed-head.json").read_text(encoding="utf-8"))
        led = Ledger(d / "ledger.jsonl", log_id=_log_id(d))
        assert head["size"] == led.size() == i + 2
        assert head["root"] == led.root()
        assert check_signed_head(head, _public(d)) == (True, "ok")
        assert prereg_heads.check_current(d, _public(d), _log_id(d)) == (True, "ok")


def test_growth_is_proven_from_the_previous_head_and_from_the_freeze(
        tmp_path, monkeypatch):
    from harness.ledger import Ledger
    d, keyfile, _ = build_log(tmp_path, monkeypatch)
    E.record("a", {"v": 1}, "2026-07-26T23:30:00Z", keyfile)
    out = E.record("b", {"v": 2}, "2026-07-26T23:31:00Z", keyfile)
    assert out["extends"]["size"] == 2
    names = sorted(Path(p).name for p in out["consistency"])
    assert names == ["consistency-0001-to-0003.json",
                     "consistency-0002-to-0003.json"]
    for name in names:
        proof = json.loads((d / "heads" / name).read_text(encoding="utf-8"))
        assert Ledger.check_consistency(proof) == (True, "ok")


def test_a_stale_signed_head_is_refused_before_appending(tmp_path, monkeypatch):
    """The ceremony must not extend a log whose published head is already
    stale; it would only make the gap wider."""
    from harness import prereg_heads
    d, keyfile, _ = build_log(tmp_path, monkeypatch)
    stale = (d / "signed-head.json").read_bytes()
    E.record("a", {"v": 1}, "2026-07-26T23:30:00Z", keyfile)
    (d / "signed-head.json").write_bytes(stale)       # the old main behaviour
    ok, why = prereg_heads.check_current(d, _public(d), _log_id(d))
    assert not ok and why.startswith("stale_signed_head")
    with pytest.raises(E.CeremonyError, match="stale"):
        E.record("b", {"v": 2}, "2026-07-26T23:31:00Z", keyfile)


def test_check_current_refuses_a_head_under_another_key(tmp_path, monkeypatch):
    from harness import prereg_heads
    d, _, _ = build_log(tmp_path, monkeypatch)
    other = bytes(nacl.SigningKey(bytes(range(32, 64))).verify_key)
    ok, why = prereg_heads.check_current(d, other, _log_id(d))
    assert not ok and why.startswith("signed_head_invalid")


def test_a_historical_head_with_other_bytes_is_not_overwritten(tmp_path):
    from harness import prereg_heads
    p = tmp_path / "head-0002.json"
    p.write_text("original\n", encoding="utf-8")
    prereg_heads.write_once(p, "original\n")          # same bytes: no-op
    with pytest.raises(FileExistsError):
        prereg_heads.write_once(p, "rewritten\n")
    assert p.read_text(encoding="utf-8") == "original\n"


def test_replaying_the_same_observation_does_not_grow_the_log(tmp_path, monkeypatch):
    d, keyfile, _ = build_log(tmp_path, monkeypatch)
    payload = {"verdict": "OK"}
    first = E.record("x", payload, "2026-07-26T23:30:00Z", keyfile)
    again = E.record("x", payload, "2026-07-26T23:31:00Z", keyfile)
    assert first["head"]["size"] == 2
    assert again.get("idempotent") is True
    assert again["head"]["size"] == 2
    # The first observation's time is what survives, not the replay's.
    assert again["first_recorded_at"] == "2026-07-26T23:30:00Z"
    rows = (d / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2, "a replay must not add a row"


def test_a_wrong_key_is_refused_before_it_signs(tmp_path, monkeypatch):
    """Signing a head of this log with another key would attest to nothing while
    looking valid on its own."""
    d, _, _ = build_log(tmp_path, monkeypatch)
    other = tmp_path / "other.key"
    other.write_text(bytes(range(32, 64)).hex(), encoding="utf-8")
    with pytest.raises(E.CeremonyError, match="not the log's key"):
        E.record("x", {"v": 1}, "2026-07-26T23:30:00Z", other)
    assert E.record("x", {"v": 1}, "2026-07-26T23:30:00Z", other,
                    dry_run=True)["dry_run"] is True   # dry run needs no key


def test_a_missing_key_is_a_clear_refusal(tmp_path, monkeypatch):
    build_log(tmp_path, monkeypatch)
    with pytest.raises(E.CeremonyError, match="no signing key"):
        E.record("x", {"v": 1}, "2026-07-26T23:30:00Z", tmp_path / "absent.key")


def test_a_tampered_log_is_refused_rather_than_extended(tmp_path, monkeypatch):
    """Appending to a log that fails its own audit would bury the failure one
    entry deeper."""
    d, keyfile, _ = build_log(tmp_path, monkeypatch)
    rows = (d / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(rows[0])
    row["sha256"] = "f" * 64                      # body no longer matches digest
    (d / "ledger.jsonl").write_text(json.dumps(row, sort_keys=True) + "\n",
                                    encoding="utf-8")
    with pytest.raises(E.CeremonyError, match="does not verify"):
        E.record("x", {"v": 1}, "2026-07-26T23:30:00Z", keyfile)


def test_redaction_is_recorded_in_the_entry_not_silent(tmp_path, monkeypatch):
    d, keyfile, _ = build_log(tmp_path, monkeypatch)
    E.record("ladder-possession", {"store": r"E:\some-drive\x"},
             "2026-07-26T23:30:00Z", keyfile)
    rows = [json.loads(l) for l in
            (d / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    entry = rows[-1]
    assert entry["store"] == E.REDACTED
    assert entry["redacted"] == [{"field": "store", "removed": "local path"}]


def test_no_written_artifact_contains_the_private_seed(tmp_path, monkeypatch):
    """The whole point of a public freeze is that the seed never leaves."""
    d, keyfile, _ = build_log(tmp_path, monkeypatch)
    E.record("x", {"v": 1}, "2026-07-26T23:30:00Z", keyfile)
    for f in d.rglob("*"):
        if f.is_file():
            assert SEED.hex() not in f.read_text(encoding="utf-8", errors="replace")
