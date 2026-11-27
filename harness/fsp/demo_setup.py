"""Setup for the live demo: backend choice, world, device, workloads, transcript."""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import flows
from .backends.software import SoftwareSecureElement
from .crypto import verify
from .canon import canon, tag
from .params import Params
from .world import World
from .workloads import WorkloadManager

ROOT = Path(__file__).resolve().parents[2]
DEMO_PARAMS = dict(t_halt_notice=3, t_poll=1, renewal_validity=600)


class Transcript:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.data: dict = {"steps": []}

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        self.lines.append(text)

    def step(self, name: str, **facts) -> None:
        self.data["steps"].append({"step": name, **facts})


def make_backend(fw: str, out: Transcript):
    try:
        from .backends.windows import WindowsTpmBackend
        backend = WindowsTpmBackend("fsp-demo-device", fw)
    except (ImportError, OSError, RuntimeError) as exc:
        out.say(f"  TPM backend unavailable ({exc}); using the software element")
        return SoftwareSecureElement(fw)
    return backend


def build(out: Transcript):
    params = Params().with_demo(**DEMO_PARAMS)
    world = World(params, clock=time.time)
    backend = make_backend(world.fw, out)
    desc = backend.describe()
    out.say("Hardware backend, part by part:")
    for part in ("key", "timer", "counter", "time_floor", "tamper"):
        out.say(f"  {part:8s} {json.dumps(desc.get(part, {}))}")
    out.step("backend", describe=desc)
    run_dir = ROOT / "run"
    mgr = WorkloadManager(run_dir, salt=b"demo-operator-salt")
    dev = world.add_device(backend, "cluster-1", enforcer=mgr)
    peer = world.add_device(SoftwareSecureElement(world.fw, time.monotonic), "cluster-1")
    world.provision_cluster("cluster-1", [dev, peer])
    ren = flows.bootstrap(world, [dev, peer])
    out.say(f"Renewal epoch 1: {len(ren['members'])} leaves, signed by "
            f"{len(ren['msg']['sigs'])} of 7 seats, valid {params.renewal_validity} s (demo value)")
    return world, backend, dev, mgr


def show_heartbeats(world: World, dev, out: Transcript) -> None:
    hb = dev.heartbeat()
    sig = hb["sigs"][0]
    ok = verify(sig["alg"], sig["key"], tag("heartbeat") + canon(hb["body"]), sig["sig"])
    out.say(f"Conforming heartbeat: counter {hb['body']['counter']}, signed {sig['alg']}, "
            f"verifies {ok}, fields {sorted(hb['body'])}")
    out.say(f"  carries usage figures: {'usage' in hb['body']}")
    try:
        from .backends import nvidia
        raw = nvidia.read_raw()
        out.say(f"  nvidia-smi raw reading (local display only; no protocol message carries it): "
                f"{raw['power_w']} W, {raw['util_pct']} %")
    except (RuntimeError, OSError, ValueError, IndexError) as exc:
        out.say(f"  nvidia-smi unavailable: {exc}")
    tele = dev.heartbeat(profile="telemetry")
    out.say(f"Telemetry-profile heartbeat (non-conforming, Finding P2): usage "
            f"{json.dumps(tele['body']['usage'])}")
    dev.outbox += [hb, tele]
    world.deliver(dev)
    out.step("heartbeats", conforming_fields=sorted(hb["body"]), alg=sig["alg"],
             verifies=ok, telemetry_usage=tele["body"]["usage"])
