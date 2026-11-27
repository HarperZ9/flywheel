"""Log delay, alert clocks and the recheck (SPEC.md sections 9.2, 13)."""

from __future__ import annotations

from harness.fsp.alerts import AlertPipeline, clock_verdict
from harness.fsp.crypto import Ed25519Signer
from harness.fsp.log import TransparencyLog, promise_breached
from harness.fsp.merkle import MerkleTree, verify_consistency, verify_inclusion
from harness.fsp.recheck import daily_recheck, recheck_convergence
from harness.fsp.shim import tick
from harness.fsp.signals import make_signal
from harness.fsp.world import SimClock


def test_merkle_proofs_verify_for_every_size_and_reject_tampering():
    tree = MerkleTree()
    for i in range(33):
        tree.append(bytes([i]))
    for n in range(1, 34):
        for m in range(n):
            proof = tree.inclusion_proof(m, n)
            assert verify_inclusion(tree.leaves[m], m, n, proof, tree.root(n))
            if proof:
                bad = [bytes(32)] + proof[1:]
                assert not verify_inclusion(tree.leaves[m], m, n, bad, tree.root(n))
        for old in range(1, n):
            assert verify_consistency(old, n, tree.root(old), tree.root(n),
                                      tree.consistency_proof(old, n))


def test_log_that_delays_an_entry_breaks_its_signed_promise():
    clock = SimClock()
    log = TransparencyLog("log-x", "JX", clock, t_record_s=60)
    log.merge_delay_ms = 5 * 60_000
    promise = log.submit({"type": "signal", "body": {"k": 1}, "sigs": []})
    clock.advance(61)
    assert promise_breached(promise, log, int(clock() * 1000))
    clock.advance(300)
    log.integrate()
    assert not promise_breached(promise, log, int(clock() * 1000))


def test_clock_verdict_reads_met_missed_and_unverifiable():
    assert clock_verdict(0, 30_000, 60, 10) == "MET"
    assert clock_verdict(0, 90_000, 60, 10) == "MISSED"
    assert clock_verdict(0, 55_000, 60, 10) == "UNVERIFIABLE"
    assert clock_verdict(0, None, 60, 10) == "UNVERIFIABLE"


def test_alert_pipeline_records_triages_notifies_and_escalates(sim):
    w = sim.world
    pipe = AlertPipeline(w)
    prog, net = Ed25519Signer(), Ed25519Signer()
    w.sources.register(prog.public_hex(), {"program_tripwire"})
    w.sources.register(net.public_hex(), {"network_egress"})
    for src, kind in ((prog, "program_tripwire"), (net, "network_egress")):
        rec = pipe.record(make_signal(src, kind, "c1", w.now_ms(), {}), w.now_ms())
        w.clock.advance(20 * 60)
        pipe.triage(rec)
        w.clock.advance(60 * 60)
        pipe.notify(rec)
        verdicts = [r["verdict"] for r in pipe.clock_rows(rec)]
        assert verdicts == ["MET", "MET", "MET"]
    conv = pipe.convergence("c1")
    assert conv is not None
    assert recheck_convergence(w, conv, "c1", pipe.admitted)["verdict"] == "MATCH"
    assert pipe.record(make_signal(Ed25519Signer(), "tamper", "c1", 0, {}), 0) is None


def test_late_fail_closed_log_entry_reads_drift(sim):
    w = sim.world
    sim.backends[0].trip_tamper()
    tick(sim.dev)
    w.clock.advance(5 * 60)  # the carrier holds the event for five minutes
    w.deliver(sim.dev)
    rows = daily_recheck(w)
    assert [r["verdict"] for r in rows if r["subject"].startswith("fail-closed")] == ["DRIFT"]


def test_prompt_fail_closed_log_entry_reads_match(sim):
    sim.backends[0].trip_tamper()
    tick(sim.dev)
    sim.world.deliver(sim.dev)
    rows = daily_recheck(sim.world)
    assert [r["verdict"] for r in rows] == ["MATCH"]
