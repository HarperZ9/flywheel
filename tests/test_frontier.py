"""The compute frontier, measured: a model earns its place in the roster
through a capability probe run on THIS machine (tokens/sec, latency,
output hash), and the frontier table composes probes with the uplift
bench's verified rates — capability-per-GB from receipts, never from
imported leaderboards."""

import json

from harness.frontier import SCHEMA, capability_probe, frontier_table


class _Out:
    def __init__(self, text):
        self.text = text


class _Stub:
    def __init__(self, text="def f():\n    return 1\n"):
        self.text = text

    def generate(self, prompt, *, seed, temperature, max_new_tokens,
                 system=""):
        return _Out(self.text)


def test_the_probe_measures_and_hashes():
    doc = capability_probe("stub-model", proposer=_Stub())
    assert doc["schema"] == SCHEMA
    assert doc["endpoint"] == "stub-model"
    assert doc["latency_s"] >= 0
    assert doc["tok_s"] >= 0
    assert len(doc["output_sha256"]) == 64
    assert "this machine" in doc["note"]


def test_a_dead_endpoint_is_a_named_error():
    class _Dead:
        def generate(self, *a, **k):
            raise ConnectionError("refused")

    doc = capability_probe("dead", proposer=_Dead())
    assert "error" in doc
    assert "refused" in doc["error"]


def test_the_frontier_table_composes_receipts(tmp_path):
    uplift = tmp_path / "artifacts" / "uplift"
    uplift.mkdir(parents=True)
    (uplift / "run.json").write_text(json.dumps({
        "schema": "flywheel.uplift-bench/v1",
        "comparison_key": "uplift:hard_v2",
        "rows": [
            {"provider": "ollama:m", "arm": "bare", "pass_rate": 0.08},
            {"provider": "ollama:m", "arm": "wrapped", "pass_rate": 0.19},
        ],
        "deltas": [{"provider": "ollama:m", "uplift": 0.11,
                    "includes_zero": False}],
    }), encoding="utf-8")
    probes = [{"endpoint": "ollama:m", "tok_s": 12.5, "disk_gb": 1.8}]
    table = frontier_table(tmp_path, probes=probes)
    row = table["rows"][0]
    assert row["endpoint"] == "ollama:m"
    assert row["bare_rate"] == 0.08
    assert row["verified_rate"] == 0.19
    assert row["capability_per_gb"] == round(0.19 / 1.8, 4)
    assert row["uplift_separated"] is True
    assert "measured" in table["note"]


def test_missing_disk_size_yields_an_honest_null(tmp_path):
    (tmp_path / "artifacts" / "uplift").mkdir(parents=True)
    table = frontier_table(tmp_path,
                           probes=[{"endpoint": "x", "tok_s": 5.0}])
    assert table["rows"][0]["capability_per_gb"] is None
