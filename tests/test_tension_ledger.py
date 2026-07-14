"""Measurement tension as a first-class receipt: two measurements, their
intervals, and the honest verdict. A pair whose 95% intervals refuse to
overlap is a TENSION; a pair without frozen sources is UNVERIFIABLE and
earns no verdict at all (no receipt, no accept -- for physics too)."""

import pytest

from harness.tension_ledger import bank_tension, tension_entry, tension_ledger

H0_LOCAL = {"label": "SH0ES-like local ladder", "value": 73.0, "sigma": 1.0,
            "unit": "km/s/Mpc", "source_sha256": "a" * 64}
H0_CMB = {"label": "Planck-like CMB inference", "value": 67.4, "sigma": 0.5,
          "unit": "km/s/Mpc", "source_sha256": "b" * 64}


def test_hubble_shaped_pair_is_a_tension():
    e = tension_entry(H0_LOCAL, H0_CMB)
    assert e["verdict"] == "tension"
    assert e["sigma_distance"] == pytest.approx(5.0089, abs=1e-3)
    assert e["overlap_95"] is False
    # both 95% intervals are carried so a stranger can re-check
    lo_a, hi_a = e["a"]["interval_95"]
    assert lo_a == pytest.approx(73.0 - 1.96, abs=1e-9)
    assert hi_a == pytest.approx(73.0 + 1.96, abs=1e-9)


def test_overlapping_pair_is_consistent():
    a = dict(H0_LOCAL, value=70.0, sigma=2.0)
    b = dict(H0_CMB, value=68.0, sigma=1.5)
    e = tension_entry(a, b)
    assert e["verdict"] == "consistent"
    assert e["overlap_95"] is True


def test_missing_source_hash_is_unverifiable_no_verdict():
    a = dict(H0_LOCAL)
    del a["source_sha256"]
    e = tension_entry(a, H0_CMB)
    assert e["verdict"] == "unverifiable"
    assert "sigma_distance" not in e
    assert "source" in e["reason"]


def test_nonpositive_sigma_is_unverifiable():
    e = tension_entry(dict(H0_LOCAL, sigma=0.0), H0_CMB)
    assert e["verdict"] == "unverifiable"


def test_mismatched_units_are_unverifiable():
    e = tension_entry(H0_LOCAL, dict(H0_CMB, unit="mag"))
    assert e["verdict"] == "unverifiable"
    assert "unit" in e["reason"]


def test_published_pairs_recompute_their_sigmas():
    """The ledger must reproduce the field's own characterizations from
    the quoted central values and uncertainties alone: SH0ES vs Planck at
    5.8 sigma, CDF vs CMS W mass above 5 sigma, and the muon g-2 pair at
    ~0.6 sigma (the resolved anomaly, kept as a consistent entry)."""
    pairs = [
        (73.17, 0.86, 67.4, 0.5, "km/s/Mpc", 5.80, "tension"),
        (80433.5, 9.4, 80360.2, 9.9, "MeV", 5.37, "tension"),
        (116592070.5, 14.6, 116592033.0, 62.0, "1e-11", 0.59, "consistent"),
    ]
    for va, sa, vb, sb, unit, sig, verdict in pairs:
        e = tension_entry(
            {"label": "a", "value": va, "sigma": sa, "unit": unit,
             "source_sha256": "a" * 64},
            {"label": "b", "value": vb, "sigma": sb, "unit": unit,
             "source_sha256": "b" * 64})
        assert e["verdict"] == verdict, (unit, e)
        assert e["sigma_distance"] == pytest.approx(sig, abs=0.01)


def test_banked_tension_lands_in_the_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    r = bank_tension(H0_LOCAL, H0_CMB)
    assert r["stored"]
    led = tension_ledger()
    assert led["count"] == 1
    assert led["entries"][0]["verdict"] == "tension"


def test_unverifiable_pair_is_never_banked(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    a = dict(H0_LOCAL)
    del a["source_sha256"]
    r = bank_tension(a, H0_CMB)
    assert "error" in r
    assert tension_ledger()["count"] == 0
