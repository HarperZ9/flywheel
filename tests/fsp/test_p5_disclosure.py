"""Red team against P5, minimal disclosure (SPEC.md sections 3.2 and 3.3)."""

from __future__ import annotations

import json
import re

from harness.fsp.backends import nvidia
from harness.fsp.canon import canon

CLAIMS = {"device_key", "counter", "fw_measurement", "tamper_state", "time_view",
          "checkpoints", "location", "enforcement", "renewal_epoch", "prev_fp"}


def test_conforming_heartbeat_carries_the_eight_claims_and_nothing_else(sim):
    hb = sim.dev.heartbeat()
    assert set(hb["body"]) == CLAIMS
    assert "usage" not in hb["body"]


def test_halted_workload_appears_only_as_an_opaque_tag(sim):
    from harness.fsp.shim import receive_order, tick
    order, notice = sim.halt()
    receive_order(sim.dev, sim.pkg(order, notice))
    sim.advance(sim.world.params.t_halt_notice + 1)
    tick(sim.dev)
    text = canon(sim.dev.heartbeat()).decode()
    assert "job-alpha" not in text
    assert re.fullmatch(r"[0-9a-f]{64}", sim.dev.enforcement()["tags"][0])


def test_every_logged_entry_is_free_of_job_names(sim):
    from harness.fsp.shim import receive_order
    order, notice = sim.halt()
    receive_order(sim.dev, sim.pkg(order, notice))
    sim.world.deliver(sim.dev)
    dump = json.dumps([lf for lg in sim.world.logs for lf in lg.leaves])
    assert "job-alpha" not in dump and "job-beta" not in dump


def test_telemetry_profile_is_marked_non_conforming_and_banded(sim):
    sim.backends[0].set_telemetry(nvidia.coarse({"power_w": 287.4, "util_pct": 63}))
    hb = sim.dev.heartbeat(profile="telemetry")
    assert hb["body"]["profile"] == "telemetry-nonconforming"
    assert hb["body"]["usage"] == {"power_band_w": 250, "power_band_width_w": 50,
                                   "util_band_pct": 50, "util_band_width_pct": 25}


def test_nvidia_query_names_only_power_and_utilization():
    assert nvidia.QUERY[0] == "--query-gpu=power.draw,utilization.gpu"
