"""Correlated-lapse drill and false-halt accounting (SPEC.md 7.4, drill 4; ASSESSMENT H2).

Every renewal path is cut at once while devices stay online to the seats.
The drill reports when the seats warn, when each device fails closed, how
many one event reaches, and how service comes back. A second run carries the
same renewals by file, as removable media would, and no device lapses.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import flows
from .backends.software import SoftwareSecureElement
from .shim import tick
from .world import World

HOUR = 3600


def _site_fleet(n_sites: int, per_site: int) -> tuple[World, list]:
    w = World()
    devs = []
    for s in range(n_sites):
        site = [w.add_device(SoftwareSecureElement(w.fw, w.clock), f"site-{s}")
                for _ in range(per_site)]
        w.provision_cluster(f"site-{s}", site)
        devs += site
    flows.bootstrap(w, devs)
    return w, devs


def _via_file(ren: dict, run_dir: Path) -> dict:
    """Carry a renewal through a file: only signed data survives the trip."""
    path = run_dir / f"renewal-epoch-{ren['msg']['body']['epoch']}.json"
    payload = {"msg": ren["msg"], "members": ren["members"], "order": ren["order"]}
    path.write_text(json.dumps(payload), "utf-8")
    loaded = json.loads(path.read_text("utf-8"))
    return {**ren, "msg": loaded["msg"], "members": loaded["members"], "order": loaded["order"]}


def _hour(w: World, devs: list, epoch_state: dict, deliver, cut: bool) -> None:
    w.clock.advance(HOUR)
    for dev in devs:
        dev.accept_time(w.time_chain(dev))
        dev.outbox.append(dev.heartbeat())
        w.deliver(dev)
    if w.now_ms() >= epoch_state["next"]:
        ren = flows.issue_renewal(w, epoch_state["epoch"])
        epoch_state["epoch"] += 1
        epoch_state["next"] += w.params.t_epoch * 1000
        epoch_state["stale"] = w.desk.stale_renewals(ren["msg"]["body"]["epoch"])
        if not cut:
            for dev in devs:
                flows.deliver_renewal(w, dev, deliver(ren))
    for dev in devs:
        tick(dev)


def run(n_sites: int = 3, per_site: int = 8, cut_days: int = 9,
        file_channel: bool = False, run_dir: Path | None = None) -> dict:
    w, devs = _site_fleet(n_sites, per_site)
    run_dir = run_dir or Path.cwd() / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    deliver = (lambda r: _via_file(r, run_dir)) if file_channel else (lambda r: None)
    state = {"epoch": 2, "next": w.now_ms() + w.params.t_epoch * 1000, "stale": []}
    t0, warn_at, lapses = w.now_ms(), None, {}
    for _ in range(cut_days * 24):
        _hour(w, devs, state, deliver, cut=not file_channel)
        if state["stale"] and warn_at is None:
            warn_at = w.now_ms()
        for dev in devs:
            if dev.failed and dev.key not in lapses:
                lapses[dev.key] = w.now_ms()
    restore_h, back = None, w.now_ms()
    if lapses:
        for _ in range(48):  # the path comes back; roots keep their daily cadence
            _hour(w, devs, state, lambda r: r, cut=False)
            if all(d.failed is None for d in devs):
                restore_h = (w.now_ms() - back) / 3_600_000
                break
    times = sorted((t - t0) / 3_600_000 for t in lapses.values())
    return {"file_channel": file_channel, "devices": len(devs), "sites": n_sites,
            "failed_closed": len(lapses),
            "first_lapse_h": times[0] if times else None,
            "last_lapse_h": times[-1] if times else None,
            "stale_renewal_warning_h": None if warn_at is None else (warn_at - t0) / 3_600_000,
            "warning_lead_h": (None if warn_at is None or not times
                               else round(times[0] - (warn_at - t0) / 3_600_000, 2)),
            "restored_within_h_after_path_returns": restore_h,
            "device_hours": round(len(devs) * (w.now_ms() - t0) / 3_600_000, 1)}


def false_halt_accounting(results: list[dict]) -> dict:
    """FALSE_HALT_EVENTS counted per event with its device count; rate per 10k device-years."""
    events = [{"event": "renewal path cut", "devices": r["failed_closed"]}
              for r in results if r["failed_closed"]]
    device_years = sum(r["device_hours"] for r in results) / (24 * 365)
    halts = sum(e["devices"] for e in events)
    return {"false_halt_events": len(events), "events": events,
            "device_years_simulated": round(device_years, 3),
            "false_halts_per_10k_device_years": (round(halts / device_years * 10_000)
                                                 if device_years else None)}
