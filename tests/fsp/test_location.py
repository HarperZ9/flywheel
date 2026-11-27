"""Red team against location by signal delay (SPEC.md section 10, threat row 14.8)."""

from __future__ import annotations

import pytest

from harness.fsp.crypto import Ed25519Signer
from harness.fsp.location import C, Landmark, Responder, bound_m, region_check
from harness.fsp.shim import tick

SITE = (47.60, -122.33)
FAR = (35.68, 139.69)


def _region():
    return [Landmark("lm-1", "party-1", (47.61, -122.20), 200_000),
            Landmark("lm-2", "party-2", (47.25, -122.44), 200_000),
            Landmark("lm-3", "party-1", (48.00, -122.00), 200_000)]


def test_bound_uses_vacuum_light_speed():
    assert C == 299_792_458
    assert bound_m(0.001) == pytest.approx(149_896.229, abs=0.001)


def test_device_at_its_site_passes():
    dev = Ed25519Signer()
    recs = [lm.measure(dev.public_hex(), Responder(dev, SITE), 1) for lm in _region()]
    assert region_check(_region(), recs, 3)["pass"] is False  # other landmarks, other keys
    region = _region()
    recs = [lm.measure(dev.public_hex(), Responder(dev, SITE), 1) for lm in region]
    assert region_check(region, recs, 3)["pass"] is True


def test_added_delay_fails_the_check_but_is_only_soft(sim):
    region = _region()
    recs = [lm.measure(sim.dev.key, Responder(sim.dev.signer, SITE), 1, added_delay_s=0.01)
            for lm in region]
    result = region_check(region, recs, 3)
    assert result["pass"] is False and "soft" in result["reason"]
    tick(sim.dev)
    assert sim.dev.failed is None


def test_relay_cannot_make_a_far_device_look_near():
    dev = Ed25519Signer()
    region = _region()
    recs = [lm.measure(dev.public_hex(), Responder(dev, FAR), 1, relay=SITE) for lm in region]
    assert region_check(region, recs, 3)["pass"] is False


def test_extracted_key_near_a_landmark_passes_documented_limit():
    """Stated limit: the bound holds only while the key stays in the device."""
    stolen = Ed25519Signer()
    region = _region()
    recs = [lm.measure(stolen.public_hex(), Responder(stolen, SITE), 1) for lm in region]
    assert region_check(region, recs, 3)["pass"] is True


def test_wrong_key_holder_gets_no_measurement():
    dev, other = Ed25519Signer(), Ed25519Signer()
    assert _region()[0].measure(dev.public_hex(), Responder(other, SITE), 1) is None


def test_region_with_too_few_landmarks_or_one_party_is_not_checkable():
    dev = Ed25519Signer()
    region = _region()[:2]
    recs = [lm.measure(dev.public_hex(), Responder(dev, SITE), 1) for lm in region]
    assert region_check(region, recs, 3)["pass"] is False
    one_party = [Landmark(f"lm-{i}", "party-1", SITE, 200_000) for i in range(3)]
    recs = [lm.measure(dev.public_hex(), Responder(dev, SITE), 1) for lm in one_party]
    assert region_check(one_party, recs, 3)["pass"] is False


def test_forged_measurement_record_is_ignored():
    dev = Ed25519Signer()
    region = _region()
    recs = [lm.measure(dev.public_hex(), Responder(dev, FAR), 1) for lm in region]
    for rec in recs:
        rec["body"]["bound_m"] = 1000
    assert region_check(region, recs, 3)["pass"] is False
