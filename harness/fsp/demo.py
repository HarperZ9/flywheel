"""The live demo. Run: python -m harness.fsp.demo

It starts two dummy workloads the demo owns, then shows that a valid,
logged, quorum-signed halt stops exactly the named workload while the other
keeps running; that five bad orders are refused with a logged reason; and
that a lapsed renewal fails the demo device closed. It governs only its own
child processes and writes a transcript to reports/.
"""

from __future__ import annotations

import datetime as dt
import json
import time

from . import flows
from .alerts import AlertPipeline
from .crypto import Ed25519Signer
from .demo_setup import ROOT, Transcript, build, show_heartbeats
from .recheck import daily_recheck
from .shim import receive_order, tick
from .signals import make_signal


def converge(world, tag_alpha: str, out: Transcript) -> dict:
    pipe = AlertPipeline(world)
    prog, net = Ed25519Signer(), Ed25519Signer()
    world.sources.register(prog.public_hex(), {"program_tripwire"})
    world.sources.register(net.public_hex(), {"network_egress"})
    for src, kind in ((prog, "program_tripwire"), (net, "network_egress")):
        sig = make_signal(src, kind, "cluster-1", world.now_ms(), {"demo": kind}, tag=tag_alpha)
        rec = pipe.record(sig, world.now_ms())
        pipe.triage(rec)
        pipe.notify(rec)
        verdicts = {r["step"]: r["verdict"] for r in pipe.clock_rows(rec)}
        out.say(f"  signal {kind:17s} family {rec['family']:17s} log index "
                f"{rec['log_index']:3d} clocks {verdicts}")
    conv = pipe.convergence("cluster-1")
    esc = pipe.escalate(conv)
    out.say(f"  convergence: families {conv['families']}; evaluator hand-off and "
            f"governance referral logged at {esc}")
    return conv


def halt_named(world, dev, mgr, conv, out: Transcript) -> tuple[dict, tuple]:
    tag = mgr.tags["alpha"]
    lead = world.params.t_halt_notice * 1000
    eff = world.now_ms() + lead + 500
    notice = flows.post_notice(world, "cluster-1", [tag], eff, eff + 3_600_000)
    eff = max(eff, notice[1] + lead)
    order = flows.build_order(world, "halt", "cluster-1", tags=[tag], notice=notice,
                              effective_ms=eff, expires_ms=eff + 3_600_000,
                              convergence={k: conv[k] for k in ("families", "window_start_ms",
                                                                "window_end_ms")},
                              evidence=conv["evidence"])
    out.say(f"  dependent notice logged {notice[1]} ms; order effective {eff} ms "
            f"(notice lead {world.params.t_halt_notice} s, demo value)")
    res = receive_order(dev, flows.package(world, order, dev, notice))
    out.say(f"  device: {res['status']} (checks 1 to 6 and 8 to 11 passed, waiting for "
            f"effective time)")
    applied_at = None
    while applied_at is None:
        time.sleep(world.params.t_poll / 4)
        for r in tick(dev):
            if r["status"] == "applied":
                applied_at = world.now_ms()
    world.deliver(dev)
    time.sleep(0.3)
    before = {n: mgr.progress(n) for n in ("alpha", "beta")}
    time.sleep(2.0)
    after = {n: mgr.progress(n) for n in ("alpha", "beta")}
    out.say(f"  applied {applied_at - eff} ms after effective time; alpha running "
            f"{mgr.running('alpha')}, beta running {mgr.running('beta')}")
    out.say(f"  progress over the 2 s after the halt: alpha {before['alpha']}->{after['alpha']}, "
            f"beta {before['beta']}->{after['beta']}")
    try:
        mgr.start("alpha")
    except PermissionError as exc:
        out.say(f"  restart of alpha refused: {exc}")
    retag = mgr.start("alpha-renamed")
    out.say(f"  the same job started under a new name gets tag {retag[:12]} and runs "
            f"{mgr.running('alpha-renamed')}: the device cannot see a re-tag (Finding P14, "
            f"SPEC Finding S5)")
    mgr.stop("alpha-renamed")
    out.step("halt", order_to_effect_ms=applied_at - eff, alpha_running=mgr.running("alpha"),
             beta_running=mgr.running("beta"), progress_before=before, progress_after=after)
    return order, notice


def refusals(world, dev, halt: dict, notice: tuple, out: Transcript) -> list[dict]:
    now, tag = world.now_ms(), halt["body"]["scope"]["workload_tags"]
    cases = [
        ("unlogged order", flows.build_order(world, "throttle", "cluster-1", level=50,
                                             publish=False), None),
        ("3 of 7 signatures", flows.build_order(world, "throttle", "cluster-1", level=50,
                                                signers=(2, 3, 4)), None),
        ("expired order", flows.build_order(world, "throttle", "cluster-1", level=50,
                                            effective_ms=now - 7_200_000,
                                            expires_ms=now - 3_600_000), None),
        ("replayed halt", halt, notice),
        ("no non-frontier seat", flows.build_order(
            world, "halt", "cluster-1", tags=tag, notice=notice, signers=flows.NO_NONFRONTIER,
            effective_ms=now + 5000, expires_ms=now + 3_600_000), notice),
    ]
    rows = []
    for name, order, ntc in cases:
        res = receive_order(dev, flows.package(world, order, dev, ntc))
        logged = world.deliver(dev)
        idx = logged[-1][1]["log-0"] if logged else None
        out.say(f"  {name:22s} -> {res['status']} at check {res.get('check')}: "
                f"{res.get('reason')} (refusal logged at log-0 index {idx})")
        rows.append({"case": name, **{k: res.get(k) for k in ("status", "check", "reason")},
                     "refusal_log_index": idx})
    out.step("refusals", cases=rows)
    return rows


def lapse(world, dev, mgr, out: Transcript) -> None:
    ren = flows.issue_renewal(world, 2, validity_s=6)
    ok, why = flows.deliver_renewal(world, dev, ren)
    out.say(f"  renewal epoch 2 accepted {ok} ({why}); demo validity 6 s; no later renewal")
    start = time.time()
    while dev.failed is None:
        time.sleep(0.25)
        tick(dev)
    logged = world.deliver(dev)
    fc = [m for m, _ in logged if m["type"] == "failclosed"][0]
    leaf = world.logs[0].leaves[logged[-1][1]["log-0"]]
    delay = leaf["logged_ms"] - fc["body"]["at_ms"]
    out.say(f"  device failed closed after {time.time() - start:.1f} s, reason "
            f"{dev.failed}; event logged {delay} ms after it happened; beta running "
            f"{mgr.running('beta')}")
    out.step("lapse", reason=dev.failed, logged_after_ms=delay, beta_running=mgr.running("beta"))


def main() -> None:
    out = Transcript()
    out.say(f"Fail-safe protocol prototype, live demo, {dt.datetime.now().isoformat(timespec='seconds')}")
    world, backend, dev, mgr = build(out)
    try:
        show_heartbeats(world, dev, out)
        mgr.start("alpha"), mgr.start("beta")
        time.sleep(1.5)
        out.say(f"Workloads started: alpha {mgr.progress('alpha')}, beta {mgr.progress('beta')}")
        out.say("Step 1, converging signals:")
        conv = converge(world, mgr.tags["alpha"], out)
        out.say("Step 2, logged 4-of-7 halt of workload alpha:")
        halt, notice = halt_named(world, dev, mgr, conv, out)
        out.say("Step 3, orders the device must refuse:")
        refusals(world, dev, halt, notice, out)
        out.say("Step 4, lapsed renewal:")
        lapse(world, dev, mgr, out)
        rows = daily_recheck(world)
        counts = {v: sum(r["verdict"] == v for r in rows) for v in ("MATCH", "DRIFT", "UNVERIFIABLE")}
        out.say(f"Daily recheck of device actions against the log: {counts}")
        out.step("recheck", rows=rows)
    finally:
        mgr.stop_all()
        backend.close()
    stamp = dt.date.today().isoformat()
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / f"demo-{stamp}.txt").write_text("\n".join(out.lines) + "\n", "utf-8")
    (ROOT / "reports" / f"demo-{stamp}.json").write_text(json.dumps(out.data, indent=1), "utf-8")


if __name__ == "__main__":
    main()
