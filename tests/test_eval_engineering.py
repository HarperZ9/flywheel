"""The evaluation-engineering register: the discipline's instruments as a
measured roster. Every instrument reports presence from a live receipt on
disk or in the store; a missing artifact reads absent, never fabricated.
The register is the facet's falsifier: if the instruments rot, it says so."""

import json

from harness.eval_engineering import instrument_register


def _write(p, doc):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="utf-8")


def test_empty_root_reads_absent_never_fabricated(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    reg = instrument_register(tmp_path)
    assert reg["schema"] == "flywheel.instrument-register/v1"
    by_name = {i["name"]: i for i in reg["instruments"]}
    for name in ("oracle_strength", "sealed_claims", "uplift_lanes",
                 "invention_sweeps"):
        assert by_name[name]["present"] is False, name
    # admission gates are code, not artifacts: present wherever the
    # harness itself is importable
    assert by_name["admission_gates"]["present"] is True
    assert reg["present_count"] == sum(
        1 for i in reg["instruments"] if i["present"])


def test_oracle_strength_reads_latest_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    _write(tmp_path / "artifacts" / "audit" / "oracle_strength_1.json",
           {"hard_flags": 9, "review_flags": 1, "clean": 90, "n_tasks": 100})
    _write(tmp_path / "artifacts" / "audit" / "oracle_strength_2.json",
           {"hard_flags": 0, "review_flags": 14, "clean": 96, "n_tasks": 110})
    reg = instrument_register(tmp_path)
    inst = next(i for i in reg["instruments"]
                if i["name"] == "oracle_strength")
    assert inst["present"] is True
    assert "0 hard" in inst["summary"] and "96/110" in inst["summary"]
    assert inst["receipt"].endswith("oracle_strength_2.json")


def test_sealed_claims_count_verdicts(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    claims = tmp_path / "docs" / "claims" / "2026-07-14-x"
    _write(claims / "thesis.json", {"claims": 2})
    _write(claims / "adjudication.json",
           {"thesis_seal": "a" * 64, "verdict_seal": "b" * 64,
            "measurement_seal": "c" * 64,
            "verdicts": [{"status": "MATCH"}, {"status": "DRIFT"}]})
    reg = instrument_register(tmp_path)
    inst = next(i for i in reg["instruments"] if i["name"] == "sealed_claims")
    assert inst["present"] is True
    assert inst["match"] == 1 and inst["drift"] == 1
    assert "no rescue" in inst["summary"] or "adjudicated" in inst["summary"]


def test_an_unsealed_adjudication_is_not_counted_as_a_verdict(tmp_path,
                                                              monkeypatch):
    """A hand-edited adjudication.json with no seals must NOT launder its
    verdicts past the register as authoritative (tenet 3)."""
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    claims = tmp_path / "docs" / "claims" / "forged"
    _write(claims / "thesis.json", {"claims": 1})
    # no seals: someone flipped a DRIFT to MATCH by hand
    _write(claims / "adjudication.json",
           {"verdicts": [{"status": "MATCH"}]})
    reg = instrument_register(tmp_path)
    inst = next(i for i in reg["instruments"] if i["name"] == "sealed_claims")
    assert inst["match"] == 0, "an unsealed adjudication must not be counted"
    assert inst["unsealed_adjudications"] == 1


def test_uplift_lanes_report_honest_nulls(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    _write(tmp_path / "artifacts" / "uplift" / "uplift_a.json",
           {"comparison_key": "uplift:x",
            "deltas": [{"includes_zero": True}]})
    _write(tmp_path / "artifacts" / "uplift" / "uplift_b.json",
           {"comparison_key": "uplift:x",
            "deltas": [{"includes_zero": False}]})
    reg = instrument_register(tmp_path)
    inst = next(i for i in reg["instruments"] if i["name"] == "uplift_lanes")
    assert inst["present"] is True
    assert inst["runs"] == 2
    assert inst["nulls_kept"] == 1


def test_tension_ledger_counts_from_the_store(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    from harness.tension_ledger import bank_tension
    a = {"label": "a", "value": 73.0, "sigma": 1.0, "unit": "u",
         "source_sha256": "a" * 64}
    b = {"label": "b", "value": 67.4, "sigma": 0.5, "unit": "u",
         "source_sha256": "b" * 64}
    bank_tension(a, b)
    reg = instrument_register(tmp_path)
    inst = next(i for i in reg["instruments"]
                if i["name"] == "tension_ledger")
    assert inst["present"] is True
    assert inst["entries"] == 1 and inst["tensions"] == 1
