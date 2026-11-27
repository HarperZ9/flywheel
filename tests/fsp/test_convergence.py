"""Red team against the convergence rule (SPEC.md section 11, threat row 14.10)."""

from __future__ import annotations

from harness.fsp.crypto import Ed25519Signer
from harness.fsp.signals import SourceRegistry, find_convergence, make_signal

HOUR = 3_600_000


def _entry(src, kind, t_ms, counted=True, cluster="c1"):
    sig = make_signal(src, kind, cluster, t_ms, {"k": kind})
    return {"logged_ms": t_ms, "body": sig["body"], "counted": counted,
            "ref": {"kind": kind, "t": t_ms}}


def test_two_signals_of_one_family_never_converge():
    s = Ed25519Signer()
    entries = [_entry(s, "network_egress", 0), _entry(s, "facility_power", HOUR)]
    assert find_convergence(entries, "c1", 86400) is None


def test_two_families_inside_the_window_converge():
    s = Ed25519Signer()
    entries = [_entry(s, "network_egress", 0), _entry(s, "program_tripwire", 23 * HOUR)]
    conv = find_convergence(entries, "c1", 86400)
    assert conv is not None and len(conv["families"]) == 2


def test_two_families_outside_the_window_do_not():
    s = Ed25519Signer()
    entries = [_entry(s, "network_egress", 0), _entry(s, "program_tripwire", 25 * HOUR)]
    assert find_convergence(entries, "c1", 86400) is None


def test_human_reports_escalate_but_never_stop_alone():
    s = Ed25519Signer()
    humans = [_entry(s, "whistleblower", 0), _entry(s, "researcher_finding", HOUR),
              _entry(s, "evaluation_finding", 2 * HOUR)]
    assert find_convergence(humans, "c1", 86400) is None
    assert find_convergence(humans + [_entry(s, "usage_anomaly", 3 * HOUR)], "c1", 86400)


def test_uncounted_signals_do_not_enter_the_set():
    s = Ed25519Signer()
    entries = [_entry(s, "network_egress", 0), _entry(s, "program_tripwire", HOUR, False)]
    assert find_convergence(entries, "c1", 86400) is None


def test_hard_signals_and_other_clusters_do_not_count():
    """Hard signals never count toward convergence (SPEC.md Finding S17)."""
    s = Ed25519Signer()
    two_hard = [_entry(s, "tamper", 0), _entry(s, "attestation_failure", HOUR)]
    assert find_convergence(two_hard, "c1", 86400) is None
    mixed = [_entry(s, "tamper", 0), _entry(s, "program_tripwire", HOUR, cluster="c2")]
    assert find_convergence(mixed, "c1", 86400) is None


def test_proof_signals_do_not_count_finding_p5():
    s = Ed25519Signer()
    entries = [_entry(s, "clone_proof", 0), _entry(s, "program_tripwire", HOUR)]
    assert find_convergence(entries, "c1", 86400) is None


def test_registry_rejects_unregistered_sources_kinds_and_forged_families():
    reg = SourceRegistry(60)
    good, rogue = Ed25519Signer(), Ed25519Signer()
    reg.register(good.public_hex(), {"network_egress"})
    assert reg.admit(make_signal(good, "network_egress", "c1", 0, {}), 0).counted
    assert not reg.admit(make_signal(rogue, "network_egress", "c1", 0, {}), 0).ok
    assert not reg.admit(make_signal(good, "program_tripwire", "c1", 0, {}), 0).ok
    forged = make_signal(good, "network_egress", "c1", 0, {})
    forged["body"]["family"] = "program_behavior"
    assert not reg.admit(forged, 0).ok


def test_flooding_source_is_logged_but_not_counted_past_the_rate():
    reg = SourceRegistry(60)
    src = Ed25519Signer()
    reg.register(src.public_hex(), {"usage_anomaly"})
    results = [reg.admit(make_signal(src, "usage_anomaly", "c1", i, {"i": i}), i * 1000)
               for i in range(100)]
    assert sum(r.counted for r in results) == 60
    assert all(r.ok for r in results)
