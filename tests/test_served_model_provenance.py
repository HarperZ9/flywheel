"""Served-Model Provenance probe: fingerprint match/drift and the gov smp CLI."""
import json

import pytest

from harness import cli_entry
from harness import governance_cli
from harness import served_model_provenance as smp
from harness.transitive_witness import DRIFT, MATCH, UNVERIFIABLE

IDS = [f"p{i}" for i in range(10)]


def _battery(model, ids=IDS):
    return [{"probe_id": pid, "output": f"{model}|{pid}"} for pid in ids]


def _claim(model="kimi-k3", alternatives=None):
    claim = {"claimed_model": model, "reference": _battery(model)}
    if alternatives:
        claim["alternatives"] = {a: _battery(a) for a in alternatives}
    return claim


def test_match_when_observed_equals_claimed_reference():
    result = smp.analyze(_claim(), _battery("kimi-k3"))
    assert result["verdict"] == MATCH
    assert result["claimed_match_rate"] == 1.0
    assert result["mismatched_probes"] == []
    assert result["does_not_prove"] == smp.SMP_DOES_NOT_PROVE


def test_match_holds_when_an_alternative_is_present_but_claim_fits():
    result = smp.analyze(_claim(alternatives=["glm-5.3-flash"]), _battery("kimi-k3"))
    assert result["verdict"] == MATCH
    assert result["best_alternative"] == "glm-5.3-flash"
    assert result["best_alternative_match_rate"] == 0.0


def test_drift_when_observed_matches_an_alternative_better():
    result = smp.analyze(_claim(alternatives=["glm-5.3-flash"]), _battery("glm-5.3-flash"))
    assert result["verdict"] == DRIFT
    assert result["best_alternative"] == "glm-5.3-flash"
    assert result["best_alternative_match_rate"] == 1.0
    assert result["claimed_match_rate"] == 0.0


def test_drift_when_claim_match_is_very_low_and_no_alternative():
    result = smp.analyze(_claim(), _battery("something-else"))
    assert result["verdict"] == DRIFT
    assert result["claimed_match_rate"] == 0.0
    assert result["best_alternative"] is None


def test_unverifiable_when_too_few_shared_probes():
    result = smp.analyze(_claim(), _battery("kimi-k3", IDS[:5]))
    assert result["verdict"] == UNVERIFIABLE
    assert result["probes_compared"] == 5
    assert result["claimed_match_rate"] is None


def test_unverifiable_on_ambiguous_middle_match():
    # 6 of 10 match the claim, none an alternative: 0.6 is between floor and threshold
    observed = _battery("kimi-k3", IDS[:6]) + _battery("other", IDS[6:])
    result = smp.analyze(_claim(), observed)
    assert result["claimed_match_rate"] == 0.6
    assert result["verdict"] == UNVERIFIABLE


def test_reference_below_min_probes_is_rejected():
    claim = {"claimed_model": "m", "reference": _battery("m", IDS[:4])}
    with pytest.raises(smp.ProvenanceError):
        smp.analyze(claim, _battery("m"))


@pytest.mark.parametrize("claim,observed", [
    ({"reference": _battery("m")}, _battery("m")),                       # no claimed_model
    ({"claimed_model": "", "reference": _battery("m")}, _battery("m")),  # empty model
    ({"claimed_model": "m", "reference": []}, _battery("m")),            # empty reference
    ({"claimed_model": "m", "reference": _battery("m")}, []),            # empty observed
])
def test_malformed_inputs_are_rejected(claim, observed):
    with pytest.raises(smp.ProvenanceError):
        smp.analyze(claim, observed)


def test_duplicate_probe_id_is_rejected():
    claim = {"claimed_model": "m", "reference": _battery("m") + [{"probe_id": "p0", "output": "x"}]}
    with pytest.raises(smp.ProvenanceError):
        smp.analyze(claim, _battery("m"))


def test_threshold_out_of_range_is_rejected():
    with pytest.raises(smp.ProvenanceError):
        smp.analyze(_claim(), _battery("kimi-k3"), match_threshold=2.0)


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def test_cli_smp_match_exits_zero(tmp_path, capsys):
    claim = _write(tmp_path, "claim.json", _claim())
    obs = _write(tmp_path, "obs.json", _battery("kimi-k3"))
    assert governance_cli.main(["smp", claim, obs]) == 0
    assert "MATCH" in capsys.readouterr().out


def test_cli_smp_drift_exits_one_through_cli_entry(tmp_path):
    claim = _write(tmp_path, "claim.json", _claim(alternatives=["glm-5.3-flash"]))
    obs = _write(tmp_path, "obs.json", _battery("glm-5.3-flash"))
    assert cli_entry.main(["gov", "smp", claim, obs]) == 1


def test_cli_smp_unverifiable_exits_three(tmp_path):
    claim = _write(tmp_path, "claim.json", _claim())
    obs = _write(tmp_path, "obs.json", _battery("kimi-k3", IDS[:5]))
    assert governance_cli.main(["smp", claim, obs]) == 3
