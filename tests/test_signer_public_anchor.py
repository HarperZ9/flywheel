"""The signer's heads go to public logs, and a host-level rewrite fails against them.

The attacker here owns the host: it reads the signer's seed, rewrites a record,
recomputes every seal and re-signs every attestation with the real key. Under the
pinned key alone that forgery reads MATCH, which is the gap. Held to a head the
anchor job logged before the rewrite, it must read DRIFT.

Rekor and the OpenTimestamps calendars are fakes; no test touches the network.
A fake Rekor cannot sign as Rekor, so ``body_only`` keeps every check of the entry
body (hash and Ed25519ph signature under the pinned key) and drops only the log's
own signatures. One test runs the real check unpatched and shows that a receipt
with an unsigned log entry does not count as an anchor.
"""
from __future__ import annotations

import base64
import json

import pytest

pytest.importorskip("nacl.bindings")

from harness import rekor_verify  # noqa: E402
from harness.preaction import cli, records  # noqa: E402
from harness.preaction.records import HoldStore  # noqa: E402
from harness.preaction.verify import verify_store  # noqa: E402
from harness.signer import anchor_job, keys, statement  # noqa: E402
from tests.signer_fixtures import RunningSigner  # noqa: E402
from tests.test_signer_forgery import _decision, _rechain, _rows, _write  # noqa: E402
from tests._anchor_fixtures import _fake_submit  # noqa: E402

LOG_ONLY = ("SET_INVALID", "INCLUSION_PROOF", "CHECKPOINT")
REAL_CHECK = rekor_verify.verify_record


def body_only(rec, data, key):
    res = REAL_CHECK(rec, data, key)
    reasons = [r for r in res["reasons"] if not r.startswith(LOG_ONLY)]
    return {**res, "ok": not reasons, "reasons": reasons}


class FakeRekor:
    """Answers entry POSTs and index lookups the way Rekor does."""

    def __init__(self):
        self.entries, self.sent = {}, []

    def __call__(self, method, url, body=None):
        self.sent.append(body)
        if url.endswith("/index/retrieve"):
            return 200, json.dumps(sorted(self.entries)).encode(), {}
        entry = json.loads(body)
        uuid = f"{len(self.entries):064x}"
        self.entries[uuid] = {"body": base64.b64encode(json.dumps(entry).encode()).decode(),
                              "integratedTime": 1_760_000_000 + len(self.entries),
                              "logID": rekor_verify.REKOR_LOG_ID,
                              "logIndex": 100 + len(self.entries), "verification": {}}
        return 201, json.dumps({uuid: self.entries[uuid]}).encode(), {}


@pytest.fixture
def signer(tmp_path):
    s = RunningSigner(tmp_path / "signer-home")
    yield s
    s.stop()


@pytest.fixture
def anchored(tmp_path, signer, monkeypatch):
    """Three signed records, then one anchor run. Returns (home, anchors, rekor)."""
    monkeypatch.setattr(rekor_verify, "verify_record", body_only)
    home, anchors, rekor = tmp_path / "home", tmp_path / "anchors", FakeRekor()
    store = HoldStore(home, signer=signer.client())
    for i in range(3):
        store.append(_decision(i))
    out = anchor_job.run_once(signer.home, anchors, request=rekor, ots_submit=_fake_submit())
    assert out["ok"] and out["results"][0]["anchored"], out
    return home, anchors, rekor


def _verify(home, signer, anchors, **kw):
    return verify_store(home, trust_root=signer.public_hex, anchors=anchors, **kw)


def _causes(report):
    return {f["cause"] for f in report["findings"]}


def _host_rewrite(home, signer_home):
    """Root on the host: edit seq 2, rechain, re-sign everything with the real key."""
    sign, public = keys.load(signer_home)
    store = HoldStore(home, signer=None)
    rows = _rows(store)
    rows[1]["decision"] = "APPROVED_ONCE"
    for r in _rechain(rows):
        body = statement.attestation_body(
            store=records.store_id(home), seq=r["store_seq"], prev=r["prev_record_sha256"],
            seal=r["seal"]["hex"], signed_at="2026-10-04T00:00:00Z",
            isolation={"mode": "separate-identity"}, key_id=statement.key_id_for(public))
        body["signature"] = sign(statement.preimage(body)).hex()
        r["attestation"] = body
    _write(store, rows)


def test_only_hashes_and_a_signature_reach_rekor(anchored):
    home, anchors, rekor = anchored
    receipt = next(anchors.glob("*/head-*.json"))
    head = json.loads(receipt.read_text())["signed_head"]
    wire = b"".join(rekor.sent)
    assert head["store"].encode() not in wire and head["seal"].encode() not in wire
    assert receipt.with_suffix(".ots").exists()


def test_an_anchored_store_is_anchored_through_its_last_record(anchored, signer):
    home, anchors, _ = anchored
    report = _verify(home, signer, anchors)
    assert report["verdict"] == "MATCH", report
    pub = report["public_anchor"]
    assert pub["status"] == "ANCHORED" and pub["anchored_through_seq"] == 3
    assert pub["unanchored_records"] == 0 and pub["anchors"][0]["ots"] == "pending"


def test_records_after_the_last_anchor_are_unanchored_never_passed(anchored, signer, capsys):
    home, anchors, _ = anchored
    store = HoldStore(home, signer=signer.client())
    store.append(_decision(7))
    store.append(_decision(8))
    report = _verify(home, signer, anchors)
    assert report["public_anchor"]["status"] == "PARTIAL"
    assert report["public_anchor"]["unanchored_records"] == 2
    assert any("not publicly anchored" in n for n in report["public_anchor"]["notes"])
    args = ["verify", str(home), "--trust-root", signer.public_hex, "--anchors", str(anchors)]
    assert cli.main(args) == 0
    assert cli.main(args + ["--require-public-anchor"]) == 3
    capsys.readouterr()


def test_a_host_rewrite_passes_the_key_but_fails_the_anchored_head(anchored, signer):
    """The false-success control. The same forgery, two verifiers."""
    home, anchors, _ = anchored
    _host_rewrite(home, signer.home)
    key_only = verify_store(home, trust_root=signer.public_hex)
    assert key_only["verdict"] == "MATCH"                 # the gap anchoring closes
    held = _verify(home, signer, anchors)
    assert held["verdict"] == "DRIFT"
    assert "ANCHORED_HEAD_DISAGREES" in _causes(held)


def test_a_truncated_store_fails_the_anchored_head(anchored, signer):
    home, anchors, _ = anchored
    path = HoldStore(home, signer=None).path
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(lines[:2]), encoding="utf-8")
    held = _verify(home, signer, anchors)
    assert "STORE_SHORTER_THAN_ANCHORED_HEAD" in _causes(held)


def test_a_receipt_whose_log_entry_rekor_never_signed_does_not_count(anchored, signer,
                                                                      monkeypatch):
    home, anchors, _ = anchored
    monkeypatch.undo()                                   # the real Rekor check
    held = _verify(home, signer, anchors)
    assert held["public_anchor"]["status"] == "NONE"
    assert "ANCHOR_RECEIPT_INVALID" in _causes(held) and held["verdict"] == "DRIFT"


def test_a_receipt_for_a_forged_head_is_refused(anchored, signer, tmp_path):
    home, anchors, _ = anchored
    receipt = next(anchors.glob("*/head-*.json"))
    rec = json.loads(receipt.read_text())
    rec["signed_head"]["seq"] = 2                        # not what the key signed
    receipt.write_text(json.dumps(rec))
    held = _verify(home, signer, anchors)
    assert "ANCHOR_RECEIPT_INVALID" in _causes(held)
    assert held["public_anchor"]["status"] == "NONE"


def test_a_deleted_receipt_is_caught_online(anchored, signer):
    home, anchors, rekor = anchored
    for p in anchors.glob("*/head-*"):
        p.unlink()
    offline = _verify(home, signer, anchors)
    assert offline["public_anchor"]["status"] == "NONE"   # not a pass, but not a finding
    online = _verify(home, signer, anchors, anchors_online=rekor)
    assert "ANCHORED_HEAD_WITHOUT_RECEIPT" in _causes(online)
    assert online["verdict"] == "DRIFT"


def test_an_unreachable_rekor_is_reported_not_passed(anchored, signer):
    home, anchors, _ = anchored

    def down(*a, **k):
        raise OSError("no route")
    report = _verify(home, signer, anchors, anchors_online=down)
    assert report["public_anchor"]["online"]["checked"] is False
    assert any("did not complete" in n for n in report["public_anchor"]["notes"])


def test_the_job_waits_for_min_new_and_skips_an_unmoved_head(anchored, signer):
    home, anchors, rekor = anchored
    again = anchor_job.run_once(signer.home, anchors, request=rekor)
    assert again["results"][0]["anchored"] is False
    HoldStore(home, signer=signer.client()).append(_decision(5))
    waits = anchor_job.run_once(signer.home, anchors, request=rekor, min_new=2)
    assert waits["results"][0]["anchored"] is False
    goes = anchor_job.run_once(signer.home, anchors, request=rekor, min_new=1)
    assert goes["results"][0]["anchored"] is True and goes["results"][0]["seq"] == 4


def test_a_calendar_failure_keeps_the_rekor_anchor(tmp_path, signer, monkeypatch):
    monkeypatch.setattr(rekor_verify, "verify_record", body_only)
    home = tmp_path / "home"
    HoldStore(home, signer=signer.client()).append(_decision(0))

    def calendars_down(digest):
        raise RuntimeError("every calendar refused")
    out = anchor_job.run_once(signer.home, tmp_path / "a", request=FakeRekor(),
                              ots_submit=calendars_down)
    assert out["ok"] and out["results"][0]["ots"] == "failed"


def test_a_rekor_refusal_writes_no_receipt_and_fails_the_run(tmp_path, signer):
    HoldStore(tmp_path / "home", signer=signer.client()).append(_decision(0))
    out = anchor_job.run_once(signer.home, tmp_path / "a",
                              request=lambda *a, **k: (500, b"down", {}))
    assert not out["ok"] and not list((tmp_path / "a").glob("*/head-*.json"))


def test_without_an_anchors_dir_the_report_says_not_checked(tmp_path, signer):
    home = tmp_path / "home"
    HoldStore(home, signer=signer.client()).append(_decision(0))
    report = verify_store(home, trust_root=signer.public_hex)
    assert report["public_anchor"]["status"] == "NOT_CHECKED"
    notes = report["public_anchor"]["notes"]
    assert any("not held to any publicly anchored head" in n for n in notes)
