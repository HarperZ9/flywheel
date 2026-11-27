"""Shared fixtures: a simulated world with two devices in one cluster."""

from __future__ import annotations

import pytest

from harness.fsp import flows
from harness.fsp.backends.software import SoftwareSecureElement
from harness.fsp.orders import workload_tag
from harness.fsp.world import World


class Sim:
    def __init__(self, n_devices: int = 2) -> None:
        self.world = World()
        w = self.world
        self.backends = [SoftwareSecureElement(w.fw, w.clock) for _ in range(n_devices)]
        self.devs = [w.add_device(b, "c1") for b in self.backends]
        w.provision_cluster("c1", self.devs)
        self.renewal = flows.bootstrap(w, self.devs)
        self.tag = workload_tag(b"salt", "job-alpha")
        self.tag_b = workload_tag(b"salt", "job-beta")

    @property
    def dev(self):
        return self.devs[0]

    def advance(self, seconds: float) -> None:
        self.world.clock.advance(seconds)

    def halt_notice(self, tags=None, lead_s=None):
        w = self.world
        lead = (w.params.t_halt_notice if lead_s is None else lead_s) * 1000
        eff = w.now_ms() + w.params.t_halt_notice * 1000
        notice = flows.post_notice(w, "c1", tags or [self.tag], eff, eff + 3_600_000)
        return notice, notice[1] + lead

    def halt(self, tags=None, signers=None, **kw):
        notice, eff = self.halt_notice(tags)
        kw.setdefault("effective_ms", eff)
        kw.setdefault("expires_ms", eff + 3_600_000)
        order = flows.build_order(self.world, "halt", "c1", tags=tags or [self.tag],
                                  notice=notice, signers=signers, **kw)
        return order, notice

    def pkg(self, order, notice=None, dev=None):
        return flows.package(self.world, order, dev or self.dev, notice)


@pytest.fixture
def sim() -> Sim:
    return Sim()
