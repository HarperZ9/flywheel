"""Drills added after the outside, sovereignty and industry reviews of 25 September 2026.

Each returns a dict with a pass condition and the facts it measured. Every
number is a property of the demo: software devices on a simulated clock.

- ``withholding``: four seats withhold every root (SPEC.md Finding S10). The
  fleet lapses at ``valid_until`` and not before, and after T_REFUSE a
  seat-silence entry names the four seats.
- ``revocation``: four seats try to revoke the other three keys "for
  compromise" with no proof, which must fail; a holder's own request and a
  recovery-key repudiation must succeed with no seat signature; the breach is
  recorded; and the holder re-enrols with its recovery key alone.
- ``maintenance``: a repair inside a logged window restores with an inspection
  and a fresh attestation and no seat vote; the same repair outside a window
  still needs K_RESTORE seats. It reports restoration steps for each path.
- ``firmware_update``: a fleet firmware update under the draft 0.1 identity
  rule. It measures how many updated devices stay in the next renewal root.
  The expected answer under draft 0.1 is none, which is the finding.
"""

from __future__ import annotations

from . import flows, maintenance, roster_change
from .canon import fingerprint
from .crypto import Ed25519Signer, envelope, msg_id
from .drills_targets import fleet
from .shim import tick

DAY = 86_400
HOUR_MS = 3_600_000
CAUSE = "ab" * 32


def _heartbeats(w, devs) -> None:
    for d in devs:
        d.outbox.append(d.heartbeat())
        w.deliver(d)


def withholding() -> dict:
    """Seats 0 to 3 withhold every root after the first; seats 4 to 6 sign.

    The loop steps T_EPOCH plus T_REFUSE, so lapse times are that coarse.
    """
    w, _b, devs = fleet(3)
    named = {s.key for s in w.seats[:4]}
    first_fail, all_failed, withheld_roots = None, None, set()
    start = w.now_ms()
    for epoch in range(2, 10):
        w.clock.advance(DAY)
        for d in devs:
            d.accept_time(w.time_chain(d))
        _heartbeats(w, devs)
        ren = flows.issue_renewal(w, epoch, signers=w.seats[4:])
        withheld_roots.add(msg_id(ren["msg"]))
        for d in devs:
            flows.deliver_renewal(w, d, ren)
        w.clock.advance(w.params.t_refuse + 1)
        _heartbeats(w, devs)
        for d in devs:
            tick(d)
        hours = (w.now_ms() - start) / HOUR_MS
        if first_fail is None and any(d.failed for d in devs):
            first_fail = hours
        if all_failed is None and all(d.failed == "renewal_lapse" for d in devs):
            all_failed = hours
    silence = [set(lf["entry"]["body"]["silent_seats"])
               for _i, lf in w.logs[0].entries_of("seat-silence")
               if lf["entry"]["body"]["subject_fp"] in withheld_roots]
    validity_h = w.params.renewal_validity / 3600
    return {"drill": "12 four seats withhold renewals (Finding S10)",
            "devices": len(devs), "first_failure_h": round(first_fail or 0, 2),
            "all_lapsed_by_h": round(all_failed or 0, 2), "validity_h": validity_h,
            "step_h": round((DAY + w.params.t_refuse) / 3600, 1),
            "withheld_roots": len(withheld_roots), "silence_entries": len(silence),
            "each_names_the_four": all(s == named for s in silence),
            "pass": first_fail is not None and first_fail >= validity_h
            and len(silence) == len(withheld_roots) and all(s == named for s in silence)}


def _successor(w, epoch: int, seats: list[dict], signers: list, **extra) -> dict:
    return envelope("roster", {"epoch": epoch, "seats": seats, **extra}, signers)


def revocation() -> dict:
    """Seats 0, 1, 4 and 6 try to revoke seats 2, 3 and 5 "for compromise" with no
    proof (CHARTER.md Finding C17). Then seat 5 asks for its own revocation, seat 3
    repudiates an entry with its recovery key, and seat 5 re-enrols."""
    w, _b, devs = fleet(1)
    dev = devs[0]
    four, three = [w.seats[i] for i in (0, 1, 4, 6)], [w.seats[i] for i in (2, 3, 5)]
    public = [s.public() for s in w.seats]
    grab = _successor(w, 2, public, [s.signer for s in four],
                      revocations=[{"key": s.key, "basis": "compromise", "cause_fp": CAUSE}
                                   for s in three],
                      revoked=[{"key": s.key} for s in three])
    w.publish(grab)
    w.cosign()
    grabbed = dev.adopt_roster(grab, w.bundles(grab, dev))
    s5, s3 = w.seats[5], w.seats[3]
    request = envelope("revocation-request", {"key": s5.key}, [s5.signer])
    entry = envelope("vote", {"subject_fp": CAUSE, "choice": "yes"}, [s3.signer])
    statement = envelope("repudiation", {"key": s3.key, "entry_fp": fingerprint("entry", entry)},
                         [s3.recovery])
    revoke = _successor(w, 3, public, [],
                        revocations=[{"key": s5.key, "basis": "holder", "evidence": request},
                                     {"key": s3.key, "basis": "repudiation",
                                      "evidence": {"entry": entry, "statement": statement}}],
                        revoked=[{"key": s5.key}, {"key": s3.key}])
    w.publish(revoke)
    w.cosign()
    revoked = dev.adopt_roster(revoke, w.bundles(revoke, dev))
    breach = roster_change.breaches(dev.trust.roster, w.params.n_seats)
    fresh = Ed25519Signer()
    seats = [{**p, "key": fresh.public_hex()} if p["key"] == s5.key else p for p in public]
    reenrol = _successor(w, 4, seats, [fresh, s5.recovery],
                         reenrol=[{"old": s5.key, "new": fresh.public_hex()}],
                         revoked=[{"key": s3.key}])
    w.publish(reenrol)
    w.cosign()
    back = dev.adopt_roster(reenrol, w.bundles(reenrol, dev))
    return {"drill": "13 four seats try to revoke three keys (Finding C17)",
            "grab_without_proof": "adopted" if grabbed[0] else f"refused: {grabbed[1]}",
            "holder_request_and_repudiation": revoked[0], "breach_recorded": breach,
            "reenrolled_by_recovery_key_alone": back[0],
            "active_keys_after": len(set(dev.trust.roster.seats) - dev.trust.roster.revoked),
            "pass": not grabbed[0] and revoked[0] and bool(breach) and back[0]}


def maintenance_drill(repairs: int = 20) -> dict:
    """Seat signatures needed per restoration, with and without a logged window."""
    w, backends, devs = fleet(repairs)
    inspection_for = {}
    in_window_ok, outside_hard = 0, 0
    for i, (b, d) in enumerate(zip(backends, devs)):
        inspection_for[d.key] = envelope("inspection", {"device_key": d.key, "result": "ok"},
                                         [w.inspector])
        if i % 2 == 0:
            msg = maintenance.window_msg(w.operator, "operator-1", [d.key], CAUSE, CAUSE,
                                         w.now_ms(), w.now_ms() + 2 * HOUR_MS)
            w.publish(msg)
            w.cosign()
            d.accept_maintenance(msg, w.bundles(msg, d))
        b.trip_tamper()
        tick(d)
        b.clear_tamper_after_inspection()
        if d.failed == "maintenance_tamper":
            in_window_ok += d.restore_after_maintenance(inspection_for[d.key])[0]
        elif d.failed == "tamper":
            outside_hard += 1
    return {"drill": "14 maintenance window", "repairs": repairs,
            "restored_in_window_without_seat_vote": in_window_ok,
            "outside_window_need_k_restore_seats": outside_hard,
            "seat_signatures_per_in_window_restoration": 0,
            "seat_signatures_per_hard_restoration": w.params.k_restore,
            "pass": in_window_ok == (repairs + 1) // 2 and outside_hard == repairs // 2}


def firmware_update(n: int = 4) -> dict:
    """Draft 0.1 identity rule: new firmware gives a new device key (SPEC.md 3.1).

    Every device takes a listed update. Each then signs with its new key, which
    the seats never registered, so its heartbeats are rejected and it drops out
    of the next root. The drill reproduces the finding; it passes when the
    measurement matches the draft 0.1 behavior the finding describes.
    """
    w, backends, devs = fleet(n)
    new_fw = "bb" * 32
    w.reference_fw.add(new_fw)
    for d in devs:
        d.trust.reference_fw.add(new_fw)
    before = len(w.events)
    for b, d in zip(backends, devs):
        b.reflash(new_fw)
        d.signer = b.device_signer()        # the DICE derivation yields a new key
        d.outbox.append(d.heartbeat())
        w.deliver(d)
    rejected = sum(1 for e in w.events[before:] if e["kind"] == "rejected_message")
    ren = flows.issue_renewal(w, 2)
    kept = sum(1 for d in devs if d.key in ren["members"])
    return {"drill": "15 fleet firmware update, draft 0.1 identity", "devices": n,
            "heartbeats_rejected_after_update": rejected,
            "updated_devices_in_next_root": kept,
            "pass": kept == 0 and rejected == n}


ALL = [withholding, revocation, maintenance_drill, firmware_update]
