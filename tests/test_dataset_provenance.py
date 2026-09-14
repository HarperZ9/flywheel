"""Dataset-Provenance Probe: shard provenance/quality verification and the gov dpp CLI."""
import json

import pytest

from harness import cli_entry
from harness import dataset_provenance as dp
from harness import governance_cli
from harness.transitive_witness import DRIFT, MATCH, UNVERIFIABLE


def _h(n):
    return f"{n:064x}"


def _shard(sid, n, source="corpus-a"):
    return {"shard_id": sid, "sha256": _h(n), "source": source}


def _manifest(shards=None):
    shards = shards or [_shard("s1", 1), _shard("s2", 2), _shard("s3", 3)]
    return {"dataset_id": "ds-1", "shards": shards}


def _observed(shards):
    return [{"shard_id": s["shard_id"], "sha256": s["sha256"]} for s in shards]


def test_match_when_observed_matches_declared_and_attributed():
    m = _manifest()
    result = dp.analyze(m, _observed(m["shards"]))
    assert result["verdict"] == MATCH
    assert result["coverage"] == 1.0
    assert result["hash_mismatch"] == [] and result["undeclared"] == []
    assert result["unknown_origin"] == []
    assert result["does_not_prove"] == dp.DPP_DOES_NOT_PROVE
    assert result["dataset_id"] == "ds-1"


def test_drift_on_hash_mismatch():
    m = _manifest()
    obs = _observed(m["shards"])
    obs[0]["sha256"] = _h(999)
    result = dp.analyze(m, obs)
    assert result["verdict"] == DRIFT
    assert result["hash_mismatch"] == ["s1"]


def test_drift_on_undeclared_shard():
    m = _manifest()
    obs = _observed(m["shards"]) + [{"shard_id": "sX", "sha256": _h(7)}]
    result = dp.analyze(m, obs)
    assert result["verdict"] == DRIFT
    assert result["undeclared"] == ["sX"]


def test_drift_on_unknown_origin():
    m = _manifest([_shard("s1", 1), _shard("s2", 2, source="unknown")])
    result = dp.analyze(m, _observed(m["shards"]))
    assert result["verdict"] == DRIFT
    assert result["unknown_origin"] == ["s2"]


def test_unverifiable_on_incomplete_coverage():
    m = _manifest()
    obs = _observed(m["shards"][:2])  # missing s3
    result = dp.analyze(m, obs)
    assert result["verdict"] == UNVERIFIABLE
    assert result["missing"] == ["s3"]
    assert result["coverage"] == round(2 / 3, 4)


def test_duplicate_hashes_reported_but_do_not_break_match():
    m = _manifest([_shard("s1", 5), _shard("s2", 5)])  # same content hash
    result = dp.analyze(m, _observed(m["shards"]))
    assert result["duplicate_hash_count"] == 1
    assert result["verdict"] == MATCH


@pytest.mark.parametrize("manifest,observed", [
    ({"shards": [_shard("s1", 1)]}, [{"shard_id": "s1", "sha256": _h(1)}]),   # no dataset_id
    ({"dataset_id": "d", "shards": []}, [{"shard_id": "s1", "sha256": _h(1)}]),  # empty shards
    ({"dataset_id": "d", "shards": [{"shard_id": "s1", "sha256": "xyz", "source": "a"}]},
     [{"shard_id": "s1", "sha256": _h(1)}]),                                    # bad hash
    ({"dataset_id": "d", "shards": [_shard("s1", 1), _shard("s1", 2)]},
     [{"shard_id": "s1", "sha256": _h(1)}]),                                    # dup shard_id
    (_manifest(), []),                                                          # empty observed
])
def test_malformed_inputs_are_rejected(manifest, observed):
    with pytest.raises(dp.DatasetProvenanceError):
        dp.analyze(manifest, observed)


def test_min_coverage_out_of_range_is_rejected():
    m = _manifest()
    with pytest.raises(dp.DatasetProvenanceError):
        dp.analyze(m, _observed(m["shards"]), min_coverage=1.5)


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def test_cli_dpp_match_exits_zero(tmp_path, capsys):
    m = _manifest()
    mp = _write(tmp_path, "m.json", m)
    op = _write(tmp_path, "o.json", _observed(m["shards"]))
    assert governance_cli.main(["dpp", mp, op]) == 0
    assert "MATCH" in capsys.readouterr().out


def test_cli_dpp_drift_exits_one_through_cli_entry(tmp_path):
    m = _manifest([_shard("s1", 1), _shard("s2", 2, source="")])
    mp = _write(tmp_path, "m.json", m)
    op = _write(tmp_path, "o.json", _observed(m["shards"]))
    assert cli_entry.main(["gov", "dpp", mp, op]) == 1


def test_cli_dpp_unverifiable_exits_three(tmp_path):
    m = _manifest()
    mp = _write(tmp_path, "m.json", m)
    op = _write(tmp_path, "o.json", _observed(m["shards"][:2]))
    assert governance_cli.main(["dpp", mp, op]) == 3
